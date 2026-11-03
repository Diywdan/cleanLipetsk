"""API админки CRM: справочники, инженеры, назначения, регистрации, входящие, дела, пользователи.

Справочники обычно выключаются (is_active=false): на их ID ссылаются кеш DG и уже заведённые дела.
Удалить (DELETE) можно только запись, на которую ничего не ссылается, — заведённую по ошибке;
иначе 409 с подсказкой выключить.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import media, problems, registration
from app.api.deps import require
from app.api.integration import integration_status
from app.db import get_session, utc_now
from app.domain import (
    assignment_view,
    audit,
    case_view,
    engineer_view,
    event_view,
    executor_view,
    next_id,
    registration_view,
    role_view,
    territory_view,
    user_view,
    violation_type_view,
)
from app.models import (
    Assignment,
    AuditLog,
    BotRegistration,
    Case,
    Engineer,
    Executor,
    IncomingEvent,
    Kp,
    KpResponsible,
    Permission,
    Role,
    Territory,
    User,
    ViolationType,
    executor_violation_types,
)
from app.schemas import (
    AssignmentIn,
    AssignmentPatch,
    EngineerIn,
    EngineerPatch,
    ExecutorIn,
    ExecutorPatch,
    RejectRegistrationIn,
    ResolveRegistrationIn,
    RoleIn,
    RolePatch,
    TerritoryIn,
    TerritoryPatch,
    UserIn,
    UserPatch,
    ViolationTypeIn,
    ViolationTypePatch,
    iso,
)
from app.security import PERMISSIONS, hash_password

router = APIRouter(prefix="/api/v1", tags=["Админка CRM"])

READ_REFS = require("references.read")
WRITE_REFS = require("references.write")
WRITE_ENGINEERS = require("engineers.write")


def _get(db: Session, model, key: Any, what: str):
    item = db.get(model, key)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{what} не найден")
    return item


def _apply(obj: Any, patch: Any, skip: set[str] = frozenset()) -> dict[str, Any]:
    changes = patch.model_dump(exclude_unset=True, exclude=set(skip))
    for key, value in changes.items():
        setattr(obj, key, value)
    return changes


def _commit(db: Session, what: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{what}: значение уже занято") from exc


def _refs(db: Session, *checks: tuple[str, Any]) -> list[str]:
    """Что ссылается на запись: [(«дела», запрос), …] → [«дела: 3», …]."""
    found = []
    for label, query in checks:
        n = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        if n:
            found.append(f"{label}: {n}")
    return found


def _delete(db: Session, item: Any, what: str, refs: list[str]) -> None:
    if refs:
        raise HTTPException(status_code=409, detail=f"{what} нельзя удалить — на него ссылаются ({'; '.join(refs)}). "
                                                     "Выключите запись: снимите «Активен» в карточке (is_active=false).")
    db.delete(item)
    db.flush()


def _types(db: Session, ids: list[str]) -> list[ViolationType]:
    items = [db.get(ViolationType, i) for i in dict.fromkeys(ids)]
    missing = [i for i, item in zip(dict.fromkeys(ids), items) if item is None]
    if missing:
        raise HTTPException(status_code=422, detail=f"Нет типов нарушений: {', '.join(missing)}")
    return items


# --- Сводка для консоли администратора ---


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _by_status(db: Session, column) -> dict[str, int]:
    return dict(db.execute(select(column, func.count()).group_by(column)).all())


@router.get("/admin/summary")
def admin_summary(db: Session = Depends(get_session), user=Depends(READ_REFS)) -> dict:
    """Цифры для экрана «Обзор»: справочники, бот, входящие события, дела. Статус DG — при праве на интеграцию."""
    perms = user.permission_codes
    return {
        "engineers": {
            "total": _count(db, Engineer),
            "active": _count(db, Engineer, Engineer.is_active.is_(True)),
            "with_max": _count(db, Engineer, Engineer.max_user_id.is_not(None)),
        },
        "territories": _count(db, Territory, Territory.is_active.is_(True)),
        "assignments": _count(db, Assignment, Assignment.is_active.is_(True)),
        "executors": _count(db, Executor, Executor.is_active.is_(True)),
        "violation_types": _count(db, ViolationType, ViolationType.is_active.is_(True)),
        "kp": {"total": _count(db, Kp, Kp.deleted_at.is_(None)),
               "review": _count(db, Kp, Kp.deleted_at.is_(None), Kp.review_reason.is_not(None))},
        "registrations": _by_status(db, BotRegistration.status) if "registrations.review" in perms else None,
        "events": _by_status(db, IncomingEvent.status) if "events.read" in perms else None,
        "cases": {
            **_by_status(db, Case.status),
            "overdue": _count(db, Case, Case.status == "IN_PROGRESS", Case.deadline_at < utc_now()),
        } if "cases.read" in perms and not user.executor_id else None,
        "users": {"total": _count(db, User), "active": _count(db, User, User.is_active.is_(True))}
        if "users.manage" in perms else None,
        "integration": integration_status(db) if "integration.manage" in perms else None,
    }


# --- Участки ---


@router.get("/territories")
def list_territories(db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    return [territory_view(t) for t in db.scalars(select(Territory).order_by(Territory.territory_id))]


@router.post("/territories", status_code=201)
def create_territory(body: TerritoryIn, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    t = Territory(territory_id=next_id(db, Territory.territory_id, "TERR", 3), **body.model_dump(mode="json"))
    db.add(t)
    _commit(db, "Участок")
    audit(db, user.username, "territory.created", "territory", t.territory_id)
    return territory_view(t)


@router.get("/territories/{territory_id}")
def get_territory(territory_id: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return territory_view(_get(db, Territory, territory_id, "Участок"))


@router.delete("/territories/{territory_id}")
def delete_territory(territory_id: str, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    t = _get(db, Territory, territory_id, "Участок")
    _delete(db, t, "Участок", _refs(
        db,
        ("назначения", select(Assignment.assignment_id).where(Assignment.territory_id == territory_id)),
        ("дела", select(Case.id).where(Case.territory_id == territory_id)),
    ))
    audit(db, user.username, "territory.deleted", "territory", territory_id, name=t.name)
    return {"deleted": territory_id}


@router.patch("/territories/{territory_id}")
def update_territory(territory_id: str, body: TerritoryPatch, db: Session = Depends(get_session),
                     user=Depends(WRITE_REFS)) -> dict:
    t = _get(db, Territory, territory_id, "Участок")
    changes = body.model_dump(mode="json", exclude_unset=True)
    for key, value in changes.items():
        setattr(t, key, value)
    _commit(db, "Участок")
    audit(db, user.username, "territory.updated", "territory", territory_id, **changes)
    return territory_view(t)


# --- Инженеры ---


@router.get("/engineers")
def list_engineers(active_only: bool = False, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    query = select(Engineer).order_by(Engineer.engineer_id)
    if active_only:
        query = query.where(Engineer.is_active.is_(True))
    return [engineer_view(db, e) for e in db.scalars(query)]


@router.get("/engineers/{engineer_id}")
def get_engineer(engineer_id: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return engineer_view(db, _get(db, Engineer, engineer_id, "Инженер"))


def _check_max(db: Session, max_user_id: str | None, engineer_id: str | None = None) -> None:
    """MAX user ID принадлежит одному инженеру: занят другим — 409 с именем, а не «значение занято»."""
    if not max_user_id:
        return
    other = db.scalar(select(Engineer).where(Engineer.max_user_id == max_user_id))
    if other is not None and other.engineer_id != engineer_id:
        raise HTTPException(status_code=409,
                            detail=f"MAX user ID уже привязан к инженеру {other.full_name} ({other.engineer_id})")


def _close_pending(db: Session, e: Engineer, actor: str) -> None:
    """Запросы бота «на разборе» с этим MAX user ID закрываются привязкой к инженеру — не висят в очереди."""
    if not e.max_user_id or not e.is_active:
        return
    pending = db.scalars(select(BotRegistration).where(BotRegistration.max_user_id == e.max_user_id,
                                                       BotRegistration.status == "pending_review"))
    for reg in list(pending):
        registration.resolve(db, reg, e, actor)


@router.post("/engineers", status_code=201)
def create_engineer(body: EngineerIn, db: Session = Depends(get_session), user=Depends(WRITE_ENGINEERS)) -> dict:
    _check_max(db, body.max_user_id)
    e = Engineer(engineer_id=next_id(db, Engineer.engineer_id, "ENG", 5), **body.model_dump())
    db.add(e)
    _commit(db, "Телефон")
    audit(db, user.username, "engineer.created", "engineer", e.engineer_id, max_user_id=e.max_user_id)
    _close_pending(db, e, user.username)
    return engineer_view(db, e)


@router.patch("/engineers/{engineer_id}")
def update_engineer(engineer_id: str, body: EngineerPatch, db: Session = Depends(get_session),
                    user=Depends(WRITE_ENGINEERS)) -> dict:
    e = _get(db, Engineer, engineer_id, "Инженер")
    if "max_user_id" in body.model_fields_set:
        _check_max(db, body.max_user_id, engineer_id)
    old_max = e.max_user_id
    changes = _apply(e, body)
    _commit(db, "Телефон")
    extra = {"max_user_id": e.max_user_id, "old_max_user_id": old_max} if e.max_user_id != old_max else {}
    audit(db, user.username, "engineer.updated", "engineer", engineer_id, fields=sorted(changes), **extra)
    _close_pending(db, e, user.username)
    return engineer_view(db, e)


@router.delete("/engineers/{engineer_id}")
def delete_engineer(engineer_id: str, db: Session = Depends(get_session), user=Depends(WRITE_ENGINEERS)) -> dict:
    """Назначения инженера удаляются вместе с ним; если есть дела или регистрации из бота — 409."""
    e = _get(db, Engineer, engineer_id, "Инженер")
    refs = _refs(
        db,
        ("дела", select(Case.id).where(Case.engineer_id == engineer_id)),
        ("регистрации из бота",
         select(BotRegistration.registration_id).where(BotRegistration.engineer_id == engineer_id)),
    )
    if not refs:
        for a in list(e.assignments):
            db.delete(a)
    _delete(db, e, "Инженера", refs)
    audit(db, user.username, "engineer.deleted", "engineer", engineer_id, full_name=e.full_name)
    return {"deleted": engineer_id}


@router.post("/engineers/{engineer_id}/unlink-max")
def unlink_max(engineer_id: str, db: Session = Depends(get_session), user=Depends(WRITE_ENGINEERS)) -> dict:
    """Отвязать MAX (сменил телефон или аккаунт) — бот попросит зарегистрироваться заново."""
    e = _get(db, Engineer, engineer_id, "Инженер")
    old, e.max_user_id = e.max_user_id, None
    audit(db, user.username, "engineer.max_unlinked", "engineer", engineer_id, max_user_id=old)
    return engineer_view(db, e)


# --- Типы нарушений и исполнители ---


@router.get("/violation-types")
def list_types(db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    return [violation_type_view(v) for v in db.scalars(select(ViolationType).order_by(ViolationType.type_violation_id))]


@router.post("/violation-types", status_code=201)
def create_type(body: ViolationTypeIn, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    v = ViolationType(type_violation_id=next_id(db, ViolationType.type_violation_id, "VIOLATION", 4),
                      **body.model_dump())
    db.add(v)
    _commit(db, "Код типа")
    audit(db, user.username, "violation_type.created", "violation_type", v.type_violation_id)
    return violation_type_view(v)


@router.get("/violation-types/{type_id}")
def get_type(type_id: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return violation_type_view(_get(db, ViolationType, type_id, "Тип нарушения"))


@router.delete("/violation-types/{type_id}")
def delete_type(type_id: str, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    v = _get(db, ViolationType, type_id, "Тип нарушения")
    _delete(db, v, "Тип нарушения", _refs(
        db,
        ("дела", select(Case.id).where(Case.type_violation_id == type_id)),
        ("исполнители", select(executor_violation_types.c.executor_id)
         .where(executor_violation_types.c.type_violation_id == type_id)),
    ))
    audit(db, user.username, "violation_type.deleted", "violation_type", type_id, name=v.name)
    return {"deleted": type_id}


@router.patch("/violation-types/{type_id}")
def update_type(type_id: str, body: ViolationTypePatch, db: Session = Depends(get_session),
                user=Depends(WRITE_REFS)) -> dict:
    v = _get(db, ViolationType, type_id, "Тип нарушения")
    changes = _apply(v, body)
    audit(db, user.username, "violation_type.updated", "violation_type", type_id, fields=sorted(changes))
    return violation_type_view(v)


@router.get("/executors")
def list_executors(db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    return [executor_view(x) for x in db.scalars(select(Executor).order_by(Executor.executor_id))]


@router.post("/executors", status_code=201)
def create_executor(body: ExecutorIn, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    x = Executor(executor_id=next_id(db, Executor.executor_id, "EXEC", 4),
                 **body.model_dump(exclude={"violation_type_ids"}))
    x.violation_types = _types(db, body.violation_type_ids)
    db.add(x)
    _commit(db, "Название или код исполнителя")
    audit(db, user.username, "executor.created", "executor", x.executor_id)
    return executor_view(x)


@router.get("/executors/{executor_id}")
def get_executor(executor_id: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return executor_view(_get(db, Executor, executor_id, "Исполнитель"))


@router.delete("/executors/{executor_id}")
def delete_executor(executor_id: str, db: Session = Depends(get_session), user=Depends(WRITE_REFS)) -> dict:
    x = _get(db, Executor, executor_id, "Исполнитель")
    _delete(db, x, "Исполнителя", _refs(
        db,
        ("дела", select(Case.id).where(Case.executor_id == executor_id)),
        ("пользователи", select(User.id).where(User.executor_id == executor_id)),
        ("ответственный на площадках КП", select(KpResponsible.id).where(KpResponsible.executor_id == executor_id)),
        ("собственник площадок КП", select(Kp.kp_id).where(Kp.owner_executor_id == executor_id)),
    ))
    audit(db, user.username, "executor.deleted", "executor", executor_id, name=x.name)
    return {"deleted": executor_id}


@router.patch("/executors/{executor_id}")
def update_executor(executor_id: str, body: ExecutorPatch, db: Session = Depends(get_session),
                    user=Depends(WRITE_REFS)) -> dict:
    x = _get(db, Executor, executor_id, "Исполнитель")
    changes = _apply(x, body, skip={"violation_type_ids"})
    if body.violation_type_ids is not None:
        x.violation_types = _types(db, body.violation_type_ids)
        changes["violation_type_ids"] = body.violation_type_ids
    _commit(db, "Название исполнителя")
    audit(db, user.username, "executor.updated", "executor", executor_id, fields=sorted(changes))
    return executor_view(x)


# --- Назначения ---


@router.get("/assignments")
def list_assignments(engineer_id: str | None = None, db: Session = Depends(get_session),
                     _=Depends(READ_REFS)) -> list[dict]:
    query = select(Assignment).order_by(Assignment.assignment_id)
    if engineer_id:
        query = query.where(Assignment.engineer_id == engineer_id)
    return [assignment_view(a) for a in db.scalars(query)]


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignmentIn, db: Session = Depends(get_session), user=Depends(WRITE_ENGINEERS)) -> dict:
    _get(db, Engineer, body.engineer_id, "Инженер")
    _get(db, Territory, body.territory_id, "Участок")
    a = Assignment(assignment_id=next_id(db, Assignment.assignment_id, "ASG", 6), **body.model_dump())
    db.add(a)
    db.flush()
    db.refresh(a)
    audit(db, user.username, "assignment.created", "assignment", a.assignment_id,
          engineer_id=a.engineer_id, territory_id=a.territory_id)
    return assignment_view(a)


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return assignment_view(_get(db, Assignment, assignment_id, "Назначение"))


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: str, db: Session = Depends(get_session), user=Depends(WRITE_ENGINEERS)) -> dict:
    a = _get(db, Assignment, assignment_id, "Назначение")
    _delete(db, a, "Назначение", _refs(db, ("дела", select(Case.id).where(Case.assignment_id == assignment_id))))
    audit(db, user.username, "assignment.deleted", "assignment", assignment_id, engineer_id=a.engineer_id)
    return {"deleted": assignment_id}


@router.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, body: AssignmentPatch, db: Session = Depends(get_session),
                      user=Depends(WRITE_ENGINEERS)) -> dict:
    a = _get(db, Assignment, assignment_id, "Назначение")
    if body.territory_id is not None:
        _get(db, Territory, body.territory_id, "Участок")
    changes = _apply(a, body)
    db.flush()
    db.refresh(a)
    audit(db, user.username, "assignment.updated", "assignment", assignment_id, fields=sorted(changes))
    return assignment_view(a)


# --- Регистрации из бота ---


@router.get("/registrations")
def list_registrations(status: str | None = None, db: Session = Depends(get_session),
                       _=Depends(require("registrations.review"))) -> list[dict]:
    query = select(BotRegistration).order_by(BotRegistration.created_at.desc())
    if status:
        query = query.where(BotRegistration.status == status)
    return [registration_view(r) for r in db.scalars(query)]


@router.post("/registrations/{registration_id}/resolve")
def resolve_registration(registration_id: str, body: ResolveRegistrationIn, db: Session = Depends(get_session),
                         user=Depends(require("registrations.review"))) -> dict:
    reg = _get(db, BotRegistration, registration_id, "Запрос")
    engineer = _get(db, Engineer, body.engineer_id, "Инженер")
    registration.resolve(db, reg, engineer, user.username)
    return registration_view(reg)


@router.post("/registrations/{registration_id}/reject")
def reject_registration(registration_id: str, body: RejectRegistrationIn, db: Session = Depends(get_session),
                        user=Depends(require("registrations.review"))) -> dict:
    reg = _get(db, BotRegistration, registration_id, "Запрос")
    registration.reject(db, reg, body.reason, user.username)
    return registration_view(reg)


# --- Входящие события и дела ---


@router.get("/events")
def list_events(status: str | None = None, limit: int = Query(default=100, ge=1, le=500), offset: int = 0,
                db: Session = Depends(get_session), _=Depends(require("events.read"))) -> dict:
    query = select(IncomingEvent)
    if status:
        query = query.where(IncomingEvent.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(IncomingEvent.received_at.desc()).limit(limit).offset(offset))
    return {"items": [event_view(e) for e in rows], "total": total}


@router.get("/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_session), _=Depends(require("events.read"))) -> dict:
    return event_view(_get(db, IncomingEvent, event_id, "Событие"), full=True)


@router.get("/events/{event_id}/media/{index}")
def get_event_media(event_id: str, index: int, db: Session = Depends(get_session),
                    _=Depends(require("events.read"))):
    """Файл события по постоянной ссылке CRM (app/media.py): снимок из копии CRM, видео — потоком из DG."""
    event = _get(db, IncomingEvent, event_id, "Событие")
    case = db.scalars(select(Case).where(Case.event_id == event_id)).first()
    return media.response(db, case, (case.media if case else None) or event.canonical.get("media") or [], index)


@router.get("/cases")
def list_cases(status: str | None = None, event_id: str | None = None,
               limit: int = Query(default=100, ge=1, le=500), offset: int = 0,
               db: Session = Depends(get_session), user=Depends(require("cases.read"))) -> dict:
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    if event_id:
        event = db.get(IncomingEvent, event_id)
        canonical = event.canonical if event is not None else {}
        if canonical.get("event_type") == "waste_site_problem":  # ревизии проблемы ведут в одно дело
            query = query.where(or_(Case.event_id == event_id,
                                    Case.external_key == problems.case_key(canonical["source"])))
        else:
            query = query.where(Case.event_id == event_id)
    if user.executor_id:  # мастер УК видит дела только своей организации
        query = query.where(Case.executor_id == user.executor_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Case.created_at.desc(), Case.id.desc()).limit(limit).offset(offset))
    return {"items": [case_view(c) for c in rows], "total": total}


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_session), user=Depends(require("cases.read"))) -> dict:
    c = _get(db, Case, case_id, "Дело")
    if user.executor_id and c.executor_id != user.executor_id:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    return case_view(c)


# --- Пользователи и роли ---

MANAGE_USERS = require("users.manage")


@router.get("/permissions")
def list_permissions(_=Depends(MANAGE_USERS)) -> list[dict]:
    return [{"code": code, "name": name} for code, name in PERMISSIONS.items()]


@router.get("/roles")
def list_roles(db: Session = Depends(get_session), _=Depends(MANAGE_USERS)) -> list[dict]:
    return [role_view(r) for r in db.scalars(select(Role).order_by(Role.code))]


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, db: Session = Depends(get_session), user=Depends(MANAGE_USERS)) -> dict:
    if db.get(Role, body.code) is not None:
        raise HTTPException(status_code=409, detail="Роль с таким кодом уже есть")
    role = Role(code=body.code, name=body.name, description=body.description)
    role.permissions = [db.get(Permission, p) for p in body.permissions]
    db.add(role)
    audit(db, user.username, "role.created", "role", body.code, permissions=body.permissions)
    return role_view(role)


@router.patch("/roles/{code}")
def update_role(code: str, body: RolePatch, db: Session = Depends(get_session), user=Depends(MANAGE_USERS)) -> dict:
    role = _get(db, Role, code, "Роль")
    if role.code == "admin" and body.permissions is not None:
        raise HTTPException(status_code=409, detail="Права администратора меняются только в коде")
    changes = _apply(role, body, skip={"permissions"})
    if body.permissions is not None:
        role.permissions = [db.get(Permission, p) for p in body.permissions]
        changes["permissions"] = body.permissions
    audit(db, user.username, "role.updated", "role", code, **changes)
    return role_view(role)


def _roles(db: Session, codes: list[str]) -> list[Role]:
    roles = [db.get(Role, c) for c in dict.fromkeys(codes)]
    if any(r is None for r in roles):
        raise HTTPException(status_code=422, detail="Неизвестная роль")
    return roles


def _check_scope(user: User) -> None:
    # Без организации исполнитель видел бы и мог закрывать отчётом чужие дела
    perms = user.permission_codes
    if "cases.report" in perms and "cases.inspect" not in perms and not user.executor_id:
        raise HTTPException(status_code=422, detail="Исполнителю нужна организация (executor_id)")


@router.get("/users")
def list_users(db: Session = Depends(get_session), _=Depends(MANAGE_USERS)) -> list[dict]:
    return [user_view(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_session), actor=Depends(MANAGE_USERS)) -> dict:
    if body.executor_id:
        _get(db, Executor, body.executor_id, "Исполнитель")
    user = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password),
                executor_id=body.executor_id, is_active=body.is_active)
    user.roles = _roles(db, body.roles)
    _check_scope(user)
    db.add(user)
    _commit(db, "Логин")
    audit(db, actor.username, "user.created", "user", str(user.id), roles=body.roles)
    return user_view(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_session), actor=Depends(MANAGE_USERS)) -> dict:
    user = _get(db, User, user_id, "Пользователь")
    if user.id == actor.id and (body.is_active is False or (body.roles is not None and "admin" not in body.roles)):
        raise HTTPException(status_code=409, detail="Нельзя отключить себя или снять с себя роль администратора")
    if body.executor_id:
        _get(db, Executor, body.executor_id, "Исполнитель")
    changes = _apply(user, body, skip={"password", "roles"})
    if "executor_id" in changes:
        db.flush()
        db.expire(user, ["executor"])
    if body.roles is not None:
        user.roles = _roles(db, body.roles)
        changes["roles"] = body.roles
    _check_scope(user)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes["password"] = "changed"
    if body.password is not None or body.is_active is False:
        user.session_version += 1  # выход со всех устройств
    audit(db, actor.username, "user.updated", "user", str(user_id), fields=sorted(changes))
    return user_view(user)


# --- Интеграция и журнал ---


@router.get("/integration/datagateway")
def dg_status(db: Session = Depends(get_session), _=Depends(require("integration.manage"))) -> dict:
    return integration_status(db)


@router.get("/audit")
def list_audit(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_session),
               _=Depends(require("audit.read"))) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [{"at": iso(r.at), "actor": r.actor, "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "detail": r.detail} for r in rows]
