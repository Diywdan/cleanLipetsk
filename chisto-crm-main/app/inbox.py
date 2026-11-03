"""Приём канонических событий DG (push consumer, контракт §20).

Транспорт и бизнес разделены: событие сначала надёжно пишется во входящие
(DG получает 202), а дело заводится отдельным шагом. Повтор с тем же
event_id и тем же содержимым — 200 duplicate, с другим содержимым — 409.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import kp, media, problems
from app.config import get_settings
from app.db import session_scope, utc_now
from app.models import (
    Assignment,
    Case,
    CaseHistory,
    DgIntegration,
    Engineer,
    Executor,
    IncomingEvent,
    ViolationType,
)
from app.schemas import CanonicalViolationEventV1, CanonicalWasteSiteProblemV1, DataGatewayEventEnvelope

log = logging.getLogger("crm.inbox")

# Источник события DG → источник дела во фронте (IncidentSource). Бот ДРТ — обход инженера.
SOURCES = {"max_bot": "INSPECTION"}


def canonical_hash(event: CanonicalViolationEventV1 | CanonicalWasteSiteProblemV1) -> str:
    body = json.dumps(
        event.model_dump(mode="json", by_alias=True), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(body).hexdigest()


def _secret(db: Session) -> tuple[str, str | None]:
    row = db.get(DgIntegration, 1)
    configured = get_settings().dg_webhook_signing_secret.get_secret_value()
    if configured:
        return configured, row.consumer_key if row else None
    if row is None:
        raise HTTPException(status_code=503, detail="DataGateway webhook is not configured")
    return row.webhook_signing_secret, row.consumer_key


def verify_signature(
    db: Session, *, body: bytes, timestamp: str | None, signature: str | None, consumer_key: str | None
) -> None:
    if not timestamp or not signature or not consumer_key:
        raise HTTPException(status_code=401, detail="Missing DataGateway signature headers")
    secret, expected_consumer = _secret(db)
    if expected_consumer and not hmac.compare_digest(expected_consumer, consumer_key):
        raise HTTPException(status_code=401, detail="Unknown DataGateway consumer")
    try:
        signed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if signed_at.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid DataGateway timestamp") from exc
    if abs((datetime.now(UTC) - signed_at).total_seconds()) > get_settings().dg_webhook_max_skew_seconds:
        raise HTTPException(status_code=401, detail="Expired DataGateway signature")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise HTTPException(status_code=401, detail="Invalid DataGateway signature")


def save_envelope(db: Session, envelope: DataGatewayEventEnvelope) -> bool:
    """True — событие новое, False — повтор того же события."""
    event = envelope.canonical
    event_id = str(envelope.event_id)
    digest = canonical_hash(event)
    existing = db.get(IncomingEvent, event_id)
    if existing is not None:
        if existing.payload_sha256 != digest:
            raise HTTPException(status_code=409, detail="Idempotency key was already used with another canonical payload")
        existing.duplicate_count += 1
        return False
    db.add(
        IncomingEvent(
            event_id=event_id,
            envelope=envelope.model_dump(mode="json", by_alias=True),
            canonical=event.model_dump(mode="json", by_alias=True),
            payload_sha256=digest,
            schema_name=event.schema_name,
            schema_version=event.schema_version,
            source=envelope.source,
            source_event_id=envelope.source_event_id,
            status="RECEIVED",
        )
    )
    integration = db.get(DgIntegration, 1)
    if integration is not None:
        integration.last_delivery_at = utc_now()
    return True


def _business_checks(db: Session, event: dict) -> list[str]:
    engineer_id = event["reporter"]["engineer_id"]
    executor_id = event["violation"]["executor"]["executor_id"]
    type_id = event["violation"]["type"]["type_violation_id"]
    assignment_id = event["assignment"]["id"]
    territory_id = event["assignment"]["territory_id"]
    errors: list[str] = []
    engineer = db.get(Engineer, engineer_id)
    if engineer is None or not engineer.is_active:
        errors.append("инженер не найден или неактивен")
    executor = db.get(Executor, executor_id)
    if executor is None or not executor.is_active:
        errors.append("исполнитель не найден или неактивен")
    vtype = db.get(ViolationType, type_id)
    if vtype is None or not vtype.is_active:
        errors.append("тип нарушения не найден или неактивен")
    if executor is not None and vtype is not None and vtype not in executor.violation_types:
        errors.append("исполнитель не отвечает за этот тип нарушения")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.engineer_id != engineer_id or assignment.territory_id != territory_id:
        errors.append("назначение не совпадает с CRM")
    return errors


def process_event(event_id: str) -> None:
    case_id = _create_case(event_id)
    if case_id is not None:
        # Снимки — к себе, пока ссылка DG из события жива (час); сбой не мешает делу — заберём при просмотре
        try:
            media.cache_case_media(case_id)
        except Exception:
            log.exception("inbox: media of case %s not cached", case_id)


def _create_case(event_id: str) -> int | None:
    with session_scope() as db:
        row = db.get(IncomingEvent, event_id, with_for_update=True)
        if row is None or row.status != "RECEIVED":
            return None
        try:
            event = row.canonical
            if event.get("event_type") == "waste_site_problem":  # проблема от жителей (app/problems.py)
                case, row.status, row.error = problems.accept(db, row)
                row.processed_at = utc_now()
                db.flush()
                return case.id if case is not None else None
            errors = _business_checks(db, event)
            violation = event["violation"]
            coords = event["location"]["coordinates"]
            reported = event["timestamps"].get("reported_at")
            reported_at = datetime.fromisoformat(reported.replace("Z", "+00:00")) if reported else None
            # Дело всегда NEW: расхождение со справочниками решает инспектор при подтверждении
            case = Case(
                event_id=event_id,
                engineer_id=event["reporter"]["engineer_id"],
                executor_id=violation["executor"]["executor_id"],
                type_violation_id=violation["type"]["type_violation_id"],
                assignment_id=event["assignment"]["id"],
                territory_id=event["assignment"]["territory_id"],
                latitude=coords["latitude"],
                longitude=coords["longitude"],
                address=(event["location"].get("address") or {}).get("formatted"),
                comment=violation.get("comment"),
                media=event.get("media") or [],
                reported_at=reported_at,
                status="NEW",
                review_reason="; ".join(errors) or None,
                source=SOURCES.get(event["source"]["type"], "INSPECTION"),
            )
            now = utc_now()
            case.history.append(CaseHistory(
                action="CREATED", at=reported_at or now, actor_type="INSPECTOR",
                actor_name=event["reporter"].get("name"), title="Нарушение зафиксировано",
                description=f"Инженер через бот ДРТ: {violation['type'].get('name') or 'тип не указан'}"
                            f" — {violation['executor'].get('name') or 'исполнитель не указан'}.",
            ))
            if errors:
                case.history.append(CaseHistory(
                    action="REVIEW", at=now, actor_type="SYSTEM", title="Не сходится со справочниками",
                    description="; ".join(errors) + ". Проверьте при подтверждении.",
                ))
            kp.link_case(db, case)  # дело о площадке — к ближайшей КП из реестра
            db.add(case)
            row.status = "NEEDS_REVIEW" if errors else "PROCESSED"
            row.error = "; ".join(errors) or None
            row.processed_at = utc_now()
            db.flush()  # ошибки записи ловим здесь, а не при коммите
            return case.id
        except Exception as exc:  # дело не завелось — событие остаётся во входящих с ошибкой
            log.exception("inbox: event %s failed", event_id)
            db.rollback()
            row = db.get(IncomingEvent, event_id)
            row.status, row.error, row.processed_at = "FAILED", str(exc)[:1000], utc_now()
            return None


def process_pending(limit: int = 100) -> int:
    with session_scope() as db:
        ids = db.scalars(
            select(IncomingEvent.event_id)
            .where(IncomingEvent.status == "RECEIVED")
            .order_by(IncomingEvent.received_at)
            .limit(limit)
        ).all()
    for event_id in ids:
        process_event(event_id)
    return len(ids)
