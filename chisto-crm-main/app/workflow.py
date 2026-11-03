"""Маршрут дела — зеркало src/entities/incident/lib/workflow.ts из фронта (Oxana48/cleanLipetsk).

Фронт держит копию правил только для кнопок, переходы проверяет CRM. Поменяли правило здесь —
поменяйте и во фронте (и наоборот), иначе кнопки начнут предлагать то, что сервер отклонит.

NEW ──confirm──▶ IN_PROGRESS ──report──▶ VERIFICATION ──approve──▶ CLOSED (FIXED)
 │                  ▲   │                     │
 │                  └───┼──────return─────────┘
 └──dismiss──▶ CLOSED (FALSE_POSITIVE)
                        └──escalate (срок вышел)──▶ KNM_ESCALATION ──act (статус тот же)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utc_now
from app.domain import audit
from app.models import Case, CaseHistory, Executor, User, ViolationType


@dataclass(frozen=True)
class Rule:
    title: str
    sources: tuple[str, ...]
    target: str | None  # None — статус не меняется
    permission: str  # у системы права есть всегда


RULES: dict[str, Rule] = {
    "CONFIRM": Rule("Подтвердить и направить исполнителю", ("NEW",), "IN_PROGRESS", "cases.inspect"),
    "DISMISS": Rule("Ложное срабатывание", ("NEW",), "CLOSED", "cases.inspect"),
    "SUBMIT_REPORT": Rule("Отправить фотоотчёт", ("IN_PROGRESS",), "VERIFICATION", "cases.report"),
    "APPROVE": Rule("Принять и закрыть", ("VERIFICATION",), "CLOSED", "cases.inspect"),
    "RETURN": Rule("Вернуть на доработку", ("VERIFICATION",), "IN_PROGRESS", "cases.inspect"),
    "ESCALATE": Rule("Передать на КНМ", ("IN_PROGRESS",), "KNM_ESCALATION", "cases.inspect"),
    "ISSUE_ACT": Rule("Сформировать акт и предписание", ("KNM_ESCALATION",), None, "cases.inspect"),
}

# Матрица сроков по регламенту ДРТ: для части источников срок задан жёстко,
# для остальных — срок, который выбрал инспектор (src/entities/incident/lib/sla.ts).
FIXED_HOURS_BY_SOURCE = {"DIRECT_ORDER": 24, "GOVERNOR_PORTAL": 72, "DELO_WEB": 720}
DEADLINE_HOURS = (24, 48, 72, 720)
# Дальше этого фото отчёта считается снятым не на месте — пометка инспектору.
REPORT_DISTANCE_WARN_M = 150


def deadline_hours(source: str, chosen: int) -> int:
    return FIXED_HOURS_BY_SOURCE.get(source, chosen)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _aware(value: datetime | None) -> datetime | None:
    # SQLite отдаёт время без пояса; всё в базе пишется в UTC
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def deny_reason(action: str, case: Case, user: User | None, now: datetime) -> tuple[int, str] | None:
    """Почему действие недоступно: (HTTP-статус, текст); None — можно."""
    rule = RULES[action]
    if user is not None and rule.permission not in user.permission_codes:
        return 403, "Действие недоступно для вашей роли"
    if action == "SUBMIT_REPORT" and user is not None and user.executor_id != case.executor_id:
        return 403, "Отчёт сдаёт организация-исполнитель этого дела"
    if case.status not in rule.sources:
        return 409, "Действие недоступно в текущем статусе дела"
    if action == "ESCALATE":
        deadline = _aware(case.deadline_at)
        if deadline is None or deadline > now:
            return 409, "Срок устранения ещё не истёк"
    return None


def _executor_name(db: Session, executor_id: str | None) -> str:
    executor = db.get(Executor, executor_id) if executor_id else None
    return executor.name if executor else executor_id or "исполнитель не назначен"


def _log(case: Case, action: str, title: str, description: str, user: User | None, at: datetime) -> None:
    if user is None:
        actor_type = "SYSTEM"
    else:
        actor_type = "UK" if action == "SUBMIT_REPORT" else "INSPECTOR"
    case.history.append(
        CaseHistory(
            action=action, title=title, description=description, at=at, actor_type=actor_type,
            actor_user_id=user.id if user else None,
            actor_name=(user.full_name or user.username) if user else None,
        )
    )


def _reassign(db: Session, case: Case, executor_id: str | None, type_id: str | None) -> str:
    """Инспектор поправляет исполнителя или тип при подтверждении. Возвращает строку для хроники."""
    executor_id = executor_id or case.executor_id
    type_id = type_id or case.type_violation_id
    executor = db.get(Executor, executor_id) if executor_id else None
    vtype = db.get(ViolationType, type_id) if type_id else None
    if executor is None or not executor.is_active:
        raise HTTPException(status_code=422, detail="Исполнитель не найден или отключён")
    if vtype is None or not vtype.is_active:
        raise HTTPException(status_code=422, detail="Тип нарушения не найден или отключён")
    if vtype not in executor.violation_types:
        raise HTTPException(status_code=422, detail="Исполнитель не отвечает за этот тип нарушения")
    notes = []
    if executor_id != case.executor_id:
        notes.append(f"исполнитель: {_executor_name(db, case.executor_id)} → {executor.name}" if case.executor_id
                     else f"назначен исполнитель {executor.name}")  # проблема из чатов пришла без исполнителя
    if type_id != case.type_violation_id:
        old = db.get(ViolationType, case.type_violation_id) if case.type_violation_id else None
        notes.append(f"тип: {old.name if old else case.type_violation_id} → {vtype.name}" if case.type_violation_id
                     else f"назначен тип {vtype.name}")
    case.executor_id, case.type_violation_id = executor_id, type_id
    case.review_reason = None  # инспектор свёл дело со справочниками
    return f" Исправлено при подтверждении — {'; '.join(notes)}." if notes else ""


def apply_action(db: Session, case: Case, action: str, payload: dict[str, Any], user: User | None,
                 now: datetime | None = None) -> Case:
    """Применить действие к делу: статус, сроки, хроника, аудит. Бросает HTTPException, если нельзя."""
    now = now or utc_now()
    denied = deny_reason(action, case, user, now)
    if denied:
        raise HTTPException(status_code=denied[0], detail=denied[1])
    rule = RULES[action]

    if action == "CONFIRM":
        note = ""
        if payload.get("executor_id") or payload.get("type_violation_id"):
            note = _reassign(db, case, payload.get("executor_id"), payload.get("type_violation_id"))
        if not case.executor_id or not case.type_violation_id:  # проблема из чатов пришла без них
            raise HTTPException(status_code=422, detail="Выберите исполнителя и тип нарушения")
        if case.review_reason:  # подтвердил как есть — расхождение снято под ответственность инспектора
            note += " Расхождение со справочниками принято инспектором."
            case.review_reason = None
        hours = deadline_hours(case.source, payload["deadline_hours"])
        case.validated_at, case.deadline_at = now, now + timedelta(hours=hours)
        _log(case, action, "Нарушение подтверждено",
             f"Инцидент подтвержден. Исполнитель: {_executor_name(db, case.executor_id)}; "
             f"срок устранения — {hours} ч.{note}", user, now)
    elif action == "DISMISS":
        reason = payload.get("reason")
        case.closed_at, case.resolution = now, "FALSE_POSITIVE"
        _log(case, action, "Ложное срабатывание",
             f"Сигнал не подтверждён: {reason}." if reason else "Сигнал не подтверждён, исполнителю не направлялся.",
             user, now)
    elif action == "SUBMIT_REPORT":
        report = payload["report"]
        coords = report.get("coords")
        distance = round(distance_m(case.latitude, case.longitude, coords[1], coords[0])) if coords else None
        case.report = {**report, "distance_m": distance}
        if distance is None:
            where = "место съёмки не определено"
        else:
            where = f"{distance} м от места нарушения"
            if distance > REPORT_DISTANCE_WARN_M:
                where += f" — дальше {REPORT_DISTANCE_WARN_M} м, проверьте, что снято на месте"
        _log(case, action, "Фотоотчёт исполнителя", f"Снимок после уборки, {where}.", user, now)
    elif action == "APPROVE":
        case.closed_at, case.resolution = now, "FIXED"
        _log(case, action, "Дело закрыто", "Инспектор принял работу.", user, now)
    elif action == "RETURN":
        comment = payload.get("comment")
        _log(case, action, "Возвращено на доработку", comment or "Работа не принята, срок не продлевается.", user, now)
    elif action == "ESCALATE":
        _log(case, action, "Срок истёк", "Материалы переданы на контрольно-надзорное мероприятие.", user, now)
    elif action == "ISSUE_ACT":
        _log(case, action, "Сформирован акт и предписание", "Инспектор оформил акт и предписание.", user, now)

    previous = case.status
    if rule.target:
        case.status = rule.target
    case.updated_at = now
    audit(db, user.username if user else "system", f"case.{action.lower()}", "case", str(case.id),
          status_from=previous, status_to=case.status)
    return case


def escalate_overdue(now: datetime | None = None) -> int:
    """Фоновая эскалация: просроченные дела уходят на КНМ, даже если их никто не открыл."""
    from app.db import session_scope

    now = now or utc_now()
    with session_scope() as db:
        overdue = db.scalars(
            select(Case).where(Case.status == "IN_PROGRESS", Case.deadline_at <= now).with_for_update()
        ).all()
        for case in overdue:
            apply_action(db, case, "ESCALATE", {}, None, now)
        return len(overdue)
