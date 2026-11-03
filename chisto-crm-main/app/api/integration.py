"""Интеграционный API для Data Gateway (контракт MAX ↔ DG ↔ CRM v1, §20 и §23).

Пути и формы ответов совпадают с тестовой CRM zvnic/test_crm_drt: DG переключается
на эту CRM сменой адреса и токенов, без правки своего кода.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import inbox, registration
from app.api.deps import require_dg_read, require_dg_write
from app.db import get_session, session_scope, utc_now
from app.domain import assignment_contract, audit, current_assignment, inside_bounds
from app.models import Assignment, DgIntegration, Engineer, Executor, ViolationType
from app.schemas import BotRegistrationRequest, DataGatewayConfigureInput, DataGatewayEventEnvelope, iso

read = APIRouter(dependencies=[Depends(require_dg_read)], tags=["DataGateway: справочники (read-only)"])
delivery = APIRouter(tags=["DataGateway: доставка и регистрация"])


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} не найден")


def _get(db: Session, model, key: str, what: str):
    item = db.get(model, key)
    if item is None:
        raise _not_found(what)
    return item


def _ref(item_id: str, name: str, active: bool, key: str) -> dict[str, Any]:
    return {key: item_id, "name": name, "is_active": active}


@read.get("/api/v1/integration/engineers")
def engineers(active_only: bool = Query(default=True), db: Session = Depends(get_session)) -> dict:
    rows = db.scalars(select(Engineer).order_by(Engineer.engineer_id)).all()
    return {"items": [_ref(e.engineer_id, e.full_name, e.is_active, "engineer_id")
                      for e in rows if e.is_active or not active_only]}


@read.get("/api/v1/integration/engineers/{engineer_id}")
def engineer(engineer_id: str, db: Session = Depends(get_session)) -> dict:
    e = _get(db, Engineer, engineer_id, "Инженер")
    return _ref(e.engineer_id, e.full_name, e.is_active, "engineer_id")


@read.get("/api/v1/integration/executors")
def executors(active_only: bool = Query(default=True), db: Session = Depends(get_session)) -> dict:
    rows = db.scalars(select(Executor).order_by(Executor.executor_id)).all()
    return {"items": [_ref(x.executor_id, x.name, x.is_active, "executor_id")
                      for x in rows if x.is_active or not active_only]}


@read.get("/api/v1/integration/executors/{executor_id}")
def executor(executor_id: str, db: Session = Depends(get_session)) -> dict:
    x = _get(db, Executor, executor_id, "Исполнитель")
    return _ref(x.executor_id, x.name, x.is_active, "executor_id")


@read.get("/api/v1/integration/executors/{executor_id}/violation-types")
def executor_types(executor_id: str, db: Session = Depends(get_session)) -> dict:
    x = _get(db, Executor, executor_id, "Исполнитель")
    return {
        "executor_id": x.executor_id,
        "items": [_ref(v.type_violation_id, v.name, v.is_active, "type_violation_id")
                  for v in x.violation_types if v.is_active],
    }


@read.get("/api/v1/integration/violation-types/{type_id}")
def violation_type(type_id: str, db: Session = Depends(get_session)) -> dict:
    v = _get(db, ViolationType, type_id, "Тип нарушения")
    return _ref(v.type_violation_id, v.name, v.is_active, "type_violation_id")


@read.get("/api/v1/integration/assignments/bot-users/{max_user_id}")
def bot_identity(max_user_id: str, db: Session = Depends(get_session)) -> dict:
    e = db.scalar(select(Engineer).where(Engineer.max_user_id == max_user_id))
    if e is None:
        raise _not_found("Привязка MAX")
    return {"max_user_id": e.max_user_id, "engineer_id": e.engineer_id, "is_active": e.is_active}


@read.get("/api/v1/integration/assignments/engineers/{engineer_id}/current")
def current(engineer_id: str, db: Session = Depends(get_session)) -> dict:
    e = db.get(Engineer, engineer_id)
    a = current_assignment(db, engineer_id) if e is not None and e.is_active else None
    if a is None:
        raise _not_found("Активное назначение")
    return assignment_contract(a)


@read.get("/api/v1/integration/assignments/engineers/{engineer_id}/assignments/{assignment_id}/validate")
def validate_assignment(
    engineer_id: str, assignment_id: str, territory_id: str, lat: float, lon: float,
    db: Session = Depends(get_session),
) -> dict:
    e = db.get(Engineer, engineer_id)
    a = db.get(Assignment, assignment_id)
    valid = bool(
        e and e.is_active and a and a.is_active and a.engineer_id == engineer_id and a.territory_id == territory_id
    )
    inside = inside_bounds(a.territory.bounds, lat, lon) if a else None
    return {
        "assignment_valid": valid,
        "engineer_id": engineer_id,
        "assignment_id": assignment_id,
        "territory_id": territory_id,
        "territory_validation": {
            "status": "completed" if inside is not None else "unavailable",
            "is_inside": inside,
            "distance_to_boundary_meters": 0.0 if inside else None,
        },
    }


# --- Регистрация инженера: DG → CRM (WRITE-токен) ---


@delivery.post("/api/v1/integration/bot-users/registrations", dependencies=[Depends(require_dg_write)])
@delivery.post("/mock/crm/bot-users/registrations", dependencies=[Depends(require_dg_write)],
               include_in_schema=False)  # путь DG по умолчанию (CRM_REGISTRATION_PATH)
def register_bot_user(
    body: BotRegistrationRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
) -> dict:
    if idempotency_key and idempotency_key != body.idempotency_key:
        raise HTTPException(status_code=422, detail="Idempotency-Key does not match request")
    try:
        with session_scope() as db:
            return registration.register(db, body)
    except IntegrityError:
        # Параллельный запрос с тем же ключом успел первым — отдаём его результат.
        with session_scope() as db:
            return registration.register(db, body)


# --- Сопряжение и приём событий ---


@delivery.post("/api/v1/integrations/datagateway/configure", dependencies=[Depends(require_dg_write)])
def configure(body: DataGatewayConfigureInput, db: Session = Depends(get_session)) -> dict:
    row = db.get(DgIntegration, 1)
    if row is None:
        row = DgIntegration(singleton=1)
        db.add(row)
    row.consumer_key = body.consumer_key
    row.webhook_signing_secret = body.webhook_signing_secret.get_secret_value()
    row.datagateway_url = body.datagateway_url
    row.configured_at = utc_now()
    audit(db, "datagateway", "integration.configured", "dg_integration", "1",
          consumer_key=body.consumer_key, datagateway_url=body.datagateway_url)
    return {"status": "configured", "consumer_key": body.consumer_key,
            "webhook_path": "/api/v1/integrations/datagateway/events"}


@delivery.post("/api/v1/integrations/datagateway/events")
async def accept_event(
    request: Request,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    event_header: str | None = Header(default=None, alias="X-DG-Event-Id"),
    consumer_key: str | None = Header(default=None, alias="X-DG-Consumer-Key"),
    timestamp: str | None = Header(default=None, alias="X-DG-Timestamp"),
    signature: str | None = Header(default=None, alias="X-DG-Signature"),
) -> JSONResponse:
    raw = await request.body()
    with session_scope() as db:
        inbox.verify_signature(db, body=raw, timestamp=timestamp, signature=signature, consumer_key=consumer_key)
    try:
        envelope = DataGatewayEventEnvelope.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    event_id = str(envelope.event_id)
    if idempotency_key != event_id or event_header != event_id:
        raise HTTPException(status_code=422, detail="DataGateway event identifiers do not match")
    if envelope.canonical.id != envelope.event_id:
        raise HTTPException(status_code=422, detail="Canonical event id does not match envelope")
    try:
        with session_scope() as db:
            created = inbox.save_envelope(db, envelope)
    except IntegrityError:
        with session_scope() as db:  # гонка двух одинаковых доставок
            created = inbox.save_envelope(db, envelope)
    if created:
        background.add_task(inbox.process_event, event_id)
    return JSONResponse(
        status_code=202 if created else 200,
        content={"event_id": event_id, "receipt_id": event_id,
                 "status": "accepted" if created else "duplicate", "duplicate": not created},
    )


def integration_status(db: Session) -> dict:
    row = db.get(DgIntegration, 1)
    return {
        "configured": row is not None,
        "consumer_key": row.consumer_key if row else None,
        "datagateway_url": row.datagateway_url if row else None,
        "configured_at": iso(row.configured_at) if row else None,
        "last_delivery_at": iso(row.last_delivery_at) if row else None,
        "webhook_path": "/api/v1/integrations/datagateway/events",
    }
