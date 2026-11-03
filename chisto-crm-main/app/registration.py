"""Регистрация инженера при первом запуске бота (контракт §23): MAX Bot → DG → CRM.

CRM — единственный владелец полного телефона и связи max_user_id → engineer_id.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utc_now
from app.domain import assignment_contract, audit, current_assignment
from app.models import BotRegistration, Engineer
from app.schemas import BotRegistrationRequest, iso
from app.security import fingerprint, mask_phone, normalize_phone


def _response(reg: BotRegistration, engineer: Engineer | None, db: Session) -> dict[str, Any]:
    assignment = None
    if engineer is not None and engineer.is_active and reg.status in {"registered", "already_registered"}:
        current = current_assignment(db, engineer.engineer_id)
        assignment = assignment_contract(current) if current else None
    return {
        "registration_id": reg.registration_id,
        "status": reg.status,
        "max_user_id": reg.max_user_id,
        "engineer": (
            {"engineer_id": engineer.engineer_id, "name": engineer.full_name, "is_active": engineer.is_active}
            if engineer is not None
            else None
        ),
        "assignment": assignment,
        "reason": reg.reason,
        "processed_at": iso(utc_now()),
    }


def _decide(db: Session, max_user_id: str, phone: str) -> tuple[str, str | None, Engineer | None]:
    by_user = db.scalar(select(Engineer).where(Engineer.max_user_id == max_user_id))
    by_phone = db.scalar(select(Engineer).where(Engineer.phone == phone))
    if by_user is not None:
        if by_phone is not None and by_phone.engineer_id == by_user.engineer_id:
            if not by_user.is_active:
                return "rejected", "Профиль инженера неактивен", by_user
            return "already_registered", None, by_user
        return "conflict", "MAX-пользователь уже связан с другим инженером", None
    if by_phone is None:
        return "pending_review", "Телефон не найден в CRM — запрос передан на проверку", None
    if not by_phone.is_active:
        return "rejected", "Профиль инженера неактивен", by_phone
    if by_phone.max_user_id and by_phone.max_user_id != max_user_id:
        return "conflict", "Инженер уже связан с другим MAX-пользователем", None
    by_phone.max_user_id = max_user_id
    return "registered", None, by_phone


def register(db: Session, body: BotRegistrationRequest) -> dict[str, Any]:
    try:
        phone = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    print_ = fingerprint(body.max_user_id, phone)

    existing = db.scalar(select(BotRegistration).where(BotRegistration.idempotency_key == body.idempotency_key))
    if existing is not None:
        if existing.fingerprint != print_:
            raise HTTPException(status_code=409, detail="Idempotency key reused with different registration data")
        return existing.response

    status, reason, engineer = _decide(db, body.max_user_id, phone)
    reg = BotRegistration(
        registration_id=f"CRM-REG-{uuid4().hex[:16]}",
        idempotency_key=body.idempotency_key,
        registration_event_id=str(body.registration_event_id),
        fingerprint=print_,
        max_user_id=body.max_user_id,
        phone=phone,
        status=status,
        reason=reason,
        engineer_id=engineer.engineer_id if engineer else None,
        requested_at=body.requested_at,
        response={},
    )
    if status == "registered":
        reg.resolved_at = utc_now()
        reg.resolved_by = "auto:phone"
    reg.response = _response(reg, engineer, db)
    db.add(reg)
    audit(db, "datagateway", f"registration.{status}", "bot_registration", reg.registration_id,
          max_user_id=body.max_user_id, phone=mask_phone(phone))
    return reg.response


def resolve(db: Session, reg: BotRegistration, engineer: Engineer, actor: str) -> None:
    """Диспетчер вручную связывает запрос «на проверке» с инженером."""
    if reg.status != "pending_review":
        raise HTTPException(status_code=409, detail="Запрос уже разобран")
    if not engineer.is_active:
        raise HTTPException(status_code=409, detail="Инженер неактивен")
    if engineer.max_user_id and engineer.max_user_id != reg.max_user_id:
        raise HTTPException(status_code=409, detail="Инженер уже связан с другим MAX-пользователем")
    other = db.scalar(select(Engineer).where(Engineer.max_user_id == reg.max_user_id))
    if other is not None and other.engineer_id != engineer.engineer_id:
        raise HTTPException(status_code=409, detail="MAX-пользователь уже связан с другим инженером")
    engineer.max_user_id = reg.max_user_id
    reg.status, reg.reason, reg.engineer_id = "registered", None, engineer.engineer_id
    reg.resolved_at, reg.resolved_by = utc_now(), actor
    # Повтор того же запроса из DG теперь вернёт уже актуальный результат.
    reg.response = _response(reg, engineer, db)
    audit(db, actor, "registration.resolved", "bot_registration", reg.registration_id,
          engineer_id=engineer.engineer_id)


def reject(db: Session, reg: BotRegistration, reason: str, actor: str) -> None:
    if reg.status != "pending_review":
        raise HTTPException(status_code=409, detail="Запрос уже разобран")
    reg.status, reg.reason = "rejected", reason
    reg.resolved_at, reg.resolved_by = utc_now(), actor
    reg.response = _response(reg, None, db)
    audit(db, actor, "registration.rejected", "bot_registration", reg.registration_id, reason=reason)
