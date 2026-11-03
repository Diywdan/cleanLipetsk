from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditLog,
    BotRegistration,
    Case,
    Engineer,
    Executor,
    IncomingEvent,
    Role,
    Territory,
    User,
    ViolationType,
)
from app.schemas import iso

# --- Идентификаторы: PREFIX-00042, следующий за максимальным ---


def next_id(db: Session, column, prefix: str, width: int) -> str:
    values = db.scalars(select(column).where(column.like(f"{prefix}-%"))).all()
    numbers = [int(v.rsplit("-", 1)[1]) for v in values if v.rsplit("-", 1)[1].isdigit()]
    return f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"


def audit(db: Session, actor: str, action: str, entity: str, entity_id: str, **detail: Any) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id, detail=detail))


# --- Назначения ---


def current_assignment(db: Session, engineer_id: str, today: date | None = None) -> Assignment | None:
    """Активное назначение, действующее сегодня; из нескольких — с самой поздней датой начала."""
    today = today or date.today()
    rows = db.scalars(
        select(Assignment).where(Assignment.engineer_id == engineer_id, Assignment.is_active.is_(True))
    ).all()
    valid = [
        a
        for a in rows
        if (a.starts_on is None or a.starts_on <= today) and (a.ends_on is None or a.ends_on >= today)
    ]
    valid.sort(key=lambda a: (a.starts_on or date.min, a.created_at), reverse=True)
    return valid[0] if valid else None


def inside_bounds(bounds: dict[str, Any] | None, lat: float, lon: float) -> bool | None:
    if not bounds:
        return None
    return bounds["south"] <= lat <= bounds["north"] and bounds["west"] <= lon <= bounds["east"]


def assignment_contract(a: Assignment) -> dict[str, Any]:
    """Форма назначения из контракта DG (как в снимке local_references.json)."""
    return {
        "assignment_id": a.assignment_id,
        "engineer_id": a.engineer_id,
        "territory_id": a.territory_id,
        "territory_name": a.territory.name,
        "route_id": a.route_id,
        "is_active": a.is_active,
        "bounds": a.territory.bounds,
    }


# --- Представления для админки ---


def territory_view(t: Territory) -> dict[str, Any]:
    return {"territory_id": t.territory_id, "name": t.name, "bounds": t.bounds, "is_active": t.is_active}


def engineer_view(db: Session, e: Engineer) -> dict[str, Any]:
    a = current_assignment(db, e.engineer_id)
    return {
        "engineer_id": e.engineer_id,
        "full_name": e.full_name,
        "phone": e.phone,
        "email": e.email,
        "max_user_id": e.max_user_id,
        "is_active": e.is_active,
        "current_assignment": assignment_view(a) if a else None,
        "created_at": iso(e.created_at),
        "updated_at": iso(e.updated_at),
    }


def violation_type_view(v: ViolationType) -> dict[str, Any]:
    return {
        "type_violation_id": v.type_violation_id,
        "code": v.code,
        "name": v.name,
        "description": v.description,
        "requires_description": v.requires_description,
        "is_active": v.is_active,
    }


def executor_view(x: Executor) -> dict[str, Any]:
    return {
        "executor_id": x.executor_id,
        "code": x.code,
        "name": x.name,
        "full_name": x.full_name,
        "kind": x.kind,
        "is_active": x.is_active,
        "violation_types": [violation_type_view(v) for v in x.violation_types],
    }


def assignment_view(a: Assignment) -> dict[str, Any]:
    return {
        "assignment_id": a.assignment_id,
        "engineer_id": a.engineer_id,
        "territory_id": a.territory_id,
        "territory_name": a.territory.name,
        "route_id": a.route_id,
        "starts_on": a.starts_on.isoformat() if a.starts_on else None,
        "ends_on": a.ends_on.isoformat() if a.ends_on else None,
        "is_active": a.is_active,
    }


def registration_view(r: BotRegistration) -> dict[str, Any]:
    return {
        "registration_id": r.registration_id,
        "max_user_id": r.max_user_id,
        "phone": r.phone,
        "status": r.status,
        "reason": r.reason,
        "engineer_id": r.engineer_id,
        "requested_at": iso(r.requested_at),
        "created_at": iso(r.created_at),
        "resolved_at": iso(r.resolved_at),
        "resolved_by": r.resolved_by,
    }


def event_view(e: IncomingEvent, full: bool = False) -> dict[str, Any]:
    data = {
        "event_id": e.event_id,
        "source": e.source,
        "source_event_id": e.source_event_id,
        "schema": f"{e.schema_name}/{e.schema_version}",
        "status": e.status,
        "error": e.error,
        "duplicate_count": e.duplicate_count,
        "received_at": iso(e.received_at),
        "processed_at": iso(e.processed_at),
    }
    if full:
        data["canonical"] = e.canonical
        data["envelope"] = e.envelope
        data["payload_sha256"] = e.payload_sha256
    return data


def case_view(c: Case) -> dict[str, Any]:
    return {
        "id": c.id,
        "event_id": c.event_id,
        "status": c.status,
        "review_reason": c.review_reason,
        "engineer_id": c.engineer_id,
        "executor_id": c.executor_id,
        "type_violation_id": c.type_violation_id,
        "assignment_id": c.assignment_id,
        "territory_id": c.territory_id,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "address": c.address,
        "comment": c.comment,
        "media": c.media,
        "kp_id": c.kp_id,
        "kp_score": c.kp_score,
        "kp_method": c.kp_method,
        "source": c.source,
        "priority": c.priority,
        "validated_at": iso(c.validated_at),
        "deadline_at": iso(c.deadline_at),
        "closed_at": iso(c.closed_at),
        "resolution": c.resolution,
        "reported_at": iso(c.reported_at),
        "created_at": iso(c.created_at),
        "updated_at": iso(c.updated_at),
    }


def uprava_id(territory_id: str | None) -> int:
    """Номер управы для фильтра фронта — из номера участка (TERR-002 → 2); пока участки = округа."""
    digits = "".join(ch for ch in territory_id or "" if ch.isdigit())
    return int(digits) if digits else 0


def _before_photo(c: Case, media_url: Callable[[int, int], str]) -> str:
    # Постоянная ссылка CRM: снимок отдаётся из её копии, а не по ссылке DG, которая живёт час (app/media.py)
    for index, item in enumerate(c.media or []):
        if item.get("type") == "image":
            return media_url(c.id, index)
    return ""


def incident_view(c: Case, executor: Executor | None, vtype: ViolationType | None, repeats: int,
                  file_url: Callable[[str], str], media_url: Callable[[int, int], str],
                  kp: dict[str, Any] | None = None) -> dict[str, Any]:
    """Дело в форме IIncident фронта (src/entities/incident/types). Пустые поля не отдаются вовсе."""
    timeline: dict[str, Any] = {"createdAt": iso(c.reported_at or c.created_at)}
    for key, value in (("validatedAt", c.validated_at), ("deadlineAt", c.deadline_at), ("closedAt", c.closed_at)):
        if value is not None:
            timeline[key] = iso(value)
    if c.resolution:
        timeline["resolution"] = c.resolution
    history = []
    for event in sorted(c.history, key=lambda item: (iso(item.at), item.id)):
        title = event.title
        description = event.description
        event_id_parts = (event.external_event_id or "").split(":")
        event_package_id = (
            event_id_parts[1]
            if len(event_id_parts) == 3
            and event_id_parts[0] == "document-package"
            and event_id_parts[2] == "extended"
            and event_id_parts[1].isdigit()
            else None
        )
        if event.action == "KNM_PACKAGE_GENERATED" and event_package_id:
            title = f"Пакет №{event_package_id} сформирован"
            description = f"Сформирован пакет КНМ №{event_package_id}."
        elif event.action == "KNM_PACKAGE_GENERATED" and not description:
            description = "Пакет КНМ сформирован в сервисе документов."
        history.append({
            "id": str(event.id),
            "timestamp": iso(event.at),
            "title": title,
            "description": description,
            "type": event.actor_type,
            **({"actor": event.actor_name} if event.actor_name else {}),
        })
    timeline["history"] = history

    media: dict[str, Any] = {"photoBeforeUrl": _before_photo(c, media_url), "boundingBoxes": []}
    if c.report:
        report = {"photoUrl": file_url(c.report["file"]), "takenAt": c.report["taken_at"]}
        for key, value in (("coords", c.report.get("coords")), ("distanceM", c.report.get("distance_m")),
                           ("comment", c.report.get("comment"))):
            if value is not None:
                report[key] = value
        media["photoAfterUrl"], media["report"] = report["photoUrl"], report

    # Исполнитель дела; роль по его виду: регоператор отвечает за вывоз, остальные — за содержание.
    # Проблема из домовых чатов может прийти без исполнителя — его выбирает инспектор.
    responsibles = []
    if c.executor_id:
        organization = {"id": c.executor_id, "name": executor.name if executor else c.executor_id,
                        "kind": executor.kind if executor else "OMSU"}
        responsibles.append({"role": "waste_removal" if organization["kind"] == "REG_OPERATOR" else "site_maintenance",
                             "organization": organization,
                             "confirmed": c.review_reason is None, "recidivismCount": repeats})
    view = {
        "id": str(c.id),
        "status": c.status,
        "source": c.source,
        "priority": c.priority,
        "location": {"address": c.address or "", "coordinates": [c.longitude, c.latitude],
                     "upravaId": uprava_id(c.territory_id)},
        "kp": kp,  # привязка к площадке из реестра КП (app/kp.py), null — не определена
        "responsibles": responsibles,
        "timeline": timeline,
        "media": media,
        "knmPackageGenerated": any(
            event.action == "KNM_PACKAGE_GENERATED" for event in c.history
        ),
        # Сверх контракта фронта — ему не мешает
        "comment": c.comment,
        "reviewReason": c.review_reason,
        "eventId": c.event_id,
    }
    if c.type_violation_id:
        view["violationType"] = {"id": c.type_violation_id, "name": vtype.name if vtype else None}
    if c.engineer_id:
        view["engineerId"] = c.engineer_id
    return view


def role_view(r: Role) -> dict[str, Any]:
    return {
        "code": r.code,
        "name": r.name,
        "description": r.description,
        "is_system": r.is_system,
        "permissions": [p.code for p in r.permissions],
    }


# Ведомства фронта (LipetskDepartment) по ключу из бота; у остальных — ключ заглавными.
FRONT_DEPARTMENTS = {"ddhib": "DDHIB", "housing_inspection": "GZHI", "nature_ministry": "MPLO"}


def front_role(u: User) -> str | None:
    """Роль фронта (src/entities/user/types): INSPECTOR ведёт дела, UK сдаёт отчёты,
    ADMIN — руководство, только смотрит. Администратор CRM ведёт дела как инспектор."""
    perms = u.permission_codes
    if "cases.inspect" in perms:
        return "INSPECTOR"
    if "cases.report" in perms:
        return "UK"
    if "cases.read" in perms:
        return "ADMIN"
    return None


def user_view(u: User) -> dict[str, Any]:
    x = u.executor
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "executor_id": u.executor_id,
        "is_active": u.is_active,
        "roles": [r.code for r in u.roles],
        "permissions": sorted(u.permission_codes),
        "created_at": iso(u.created_at),
        "last_login_at": iso(u.last_login_at),
        # то же в форме IUser фронта; без организации — сотрудник ДРТ
        "name": u.full_name or u.username,
        "role": front_role(u),
        "department": FRONT_DEPARTMENTS.get(x.code or "", (x.code or x.executor_id).upper()) if x else "DRT",
        "organizationName": x.name if x else None,
        "organization": {"id": x.executor_id, "name": x.name, "kind": x.kind} if x else None,
    }
