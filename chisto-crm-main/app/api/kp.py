"""API реестра контейнерных площадок (app/kp.py).

GET /kp — карточки в форме фронта (IKpCard[], docs/api-contract.md). Остальное — для консоли и шлюза, snake_case:
поиск, ближайшие к точке, журнал изменений, карточка целиком, правка, контейнеры, ответственные.
Карточки не удаляются: DELETE ставит deleted_at, дела продолжают на площадку ссылаться.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import kp as reg
from app.api.deps import require
from app.db import get_session, utc_now
from app.domain import audit, case_view
from app.models import Case, CaseHistory, Executor, Kp, KpChangeLog, KpResponsible, KpSourceRecord, Territory, User
from app.schemas import CaseKpIn, KpContainersIn, KpIn, KpPatch, KpResponsiblesIn, iso

router = APIRouter(prefix="/api/v1", tags=["Реестр КП"])
READ_REFS = require("references.read")
WRITE_REFS = require("references.write")


def _json(request: Request, data: Any) -> Response:
    """JSON со сжатием: 3 тыс. карточек — около мегабайта, сжатые — в 10 раз меньше."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Vary": "Accept-Encoding", "Cache-Control": "private, no-cache"}
    if len(body) > 1024 and "gzip" in request.headers.get("accept-encoding", ""):
        body, headers["Content-Encoding"] = gzip.compress(body, 6), "gzip"
    return Response(body, media_type="application/json", headers=headers)


def _get(db: Session, key: str) -> Kp:
    item = reg.find(db, key)
    if item is None:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    return item


def _executor(db: Session, executor_id: str) -> Executor:
    x = db.get(Executor, executor_id)
    if x is None:
        raise HTTPException(status_code=422, detail=f"Нет исполнителя {executor_id}")
    return x


def _territories(db: Session) -> list[Territory]:
    return list(db.scalars(select(Territory).where(Territory.is_active.is_(True)).order_by(Territory.territory_id)))


# --- Для фронта ---


@router.get("/kp")
def list_cards(request: Request, db: Session = Depends(get_session), _: User = Depends(require("cases.read"))):
    cards = db.scalars(
        select(Kp).where(Kp.deleted_at.is_(None)).order_by(Kp.code)
        .options(selectinload(Kp.containers), selectinload(Kp.responsibles).selectinload(KpResponsible.executor))
    )
    territories = _territories(db)
    return _json(request, [reg.card_view(k, territories) for k in cards])


# --- Поиск и выборки (фиксированные пути — до /kp/{key}) ---


@router.get("/kp/search")
def search(q: str = "", status: str | None = None, review: bool = False, deleted: bool = False,
           limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
           db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    """Код LP-…, номер реестра, адрес или наименование; слова запроса ищутся все сразу."""
    base = Kp.deleted_at.is_not(None) if deleted else Kp.deleted_at.is_(None)
    query = select(Kp).where(base)
    if status:
        query = query.where(Kp.status == status)
    if review:
        query = query.where(Kp.review_reason.is_not(None))
    for word in q.lower().split()[:6]:
        like = f"%{word}%"
        query = query.where(or_(func.lower(Kp.code).like(like), Kp.registry_number.like(like),
                                func.lower(Kp.address_raw).like(like), func.lower(Kp.name).like(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Kp.code).limit(limit).offset(offset))
    counts = dict(db.execute(select(Kp.status, func.count()).where(Kp.deleted_at.is_(None)).group_by(Kp.status)).all())
    return {
        "items": [reg.row_view(k) for k in rows],
        "total": total,
        "by_status": counts,
        "review": db.scalar(select(func.count()).select_from(Kp).where(
            and_(Kp.deleted_at.is_(None), Kp.review_reason.is_not(None)))),
        "deleted": db.scalar(select(func.count()).select_from(Kp).where(Kp.deleted_at.is_not(None))),
        "last_sync_at": iso(db.scalar(select(func.max(KpSourceRecord.fetched_at)).where(KpSourceRecord.source == "utko"))),
    }


@router.get("/kp/nearest")
def nearest(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
            r: float = Query(default=150, gt=0, le=2000), limit: int = Query(default=20, ge=1, le=100),
            db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    """Кандидаты по точке, ближние первыми (для бота ДРТ и сопоставления событий)."""
    return [reg.row_view(k, d) for k, d in reg.nearest(db, lat, lon, r, limit)]


@router.get("/kp/changes")
def changes(since: datetime | None = None, limit: int = Query(default=200, ge=1, le=1000),
            db: Session = Depends(get_session), _=Depends(READ_REFS)) -> list[dict]:
    """Журнал изменений карточек: с since — по возрастанию (для подписчиков), без — последние."""
    query = select(KpChangeLog, Kp.code).join(Kp, Kp.kp_id == KpChangeLog.kp_id)
    if since is not None:
        query = query.where(KpChangeLog.changed_at > since).order_by(KpChangeLog.id)
    else:
        query = query.order_by(KpChangeLog.id.desc())
    return [reg.change_view(entry, code) for entry, code in db.execute(query.limit(limit))]


# --- Карточка ---


@router.get("/kp/{key}")
def get_card(key: str, db: Session = Depends(get_session), _=Depends(READ_REFS)) -> dict:
    return reg.detail_view(db, _get(db, key))


@router.get("/kp/{key}/history")
def history(key: str, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_session),
            _=Depends(READ_REFS)) -> list[dict]:
    item = _get(db, key)
    rows = db.scalars(select(KpChangeLog).where(KpChangeLog.kp_id == item.kp_id)
                      .order_by(KpChangeLog.id.desc()).limit(limit))
    return [reg.change_view(entry) for entry in rows]


@router.get("/kp/{key}/sources")
def sources(key: str, limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_session),
            _=Depends(READ_REFS)) -> list[dict]:
    """Что говорили о площадке источники: снимки записей как есть."""
    item = _get(db, key)
    rows = db.scalars(select(KpSourceRecord).where(KpSourceRecord.kp_id == item.kp_id)
                      .order_by(KpSourceRecord.id.desc()).limit(limit))
    return [{"id": r.id, "source": r.source, "external_id": r.external_id, "fetched_at": iso(r.fetched_at),
             "match_status": r.match_status, "match_score": r.match_score, "payload": r.payload} for r in rows]


@router.post("/kp", status_code=201)
def create(body: KpIn, db: Session = Depends(get_session), user: User = Depends(WRITE_REFS)) -> dict:
    # Только заполненные поля: пустые не закрепляются за «manual» и потом заполнятся из источников
    data = {k: v for k, v in body.model_dump(exclude={"latitude", "longitude", "status"}).items() if v is not None}
    if data.get("owner_executor_id"):
        _executor(db, data["owner_executor_id"])
    data["address_street"], data["address_house"] = reg.parse_address(body.address_raw)
    data["location"] = [round(body.latitude, 6), round(body.longitude, 6)]
    item = reg.new_kp(db, reg.next_code_number(db) + 1, data, "manual", f"user:{user.username}", status=body.status)
    reg.ensure_rule_responsibles(item, reg.regional_operator(db))
    db.flush()
    audit(db, user.username, "kp.created", "kp", item.code)
    return reg.detail_view(db, item)


@router.patch("/kp/{key}")
def update(key: str, body: KpPatch, db: Session = Depends(get_session), user: User = Depends(WRITE_REFS)) -> dict:
    item = _get(db, key)
    data = body.model_dump(exclude_unset=True)
    reason, verified = data.pop("reason", None), data.pop("verified", None)
    if ("latitude" in data) != ("longitude" in data):
        raise HTTPException(status_code=422, detail="Точку меняют парой: latitude и longitude")
    values: dict[str, Any] = {}
    if "latitude" in data:
        lat, lon = data.pop("latitude"), data.pop("longitude")
        if lat is None or lon is None:
            raise HTTPException(status_code=422, detail="У площадки должна быть точка")
        values["location"] = [round(lat, 6), round(lon, 6)]
    if data.get("address_raw"):
        values["address_street"], values["address_house"] = reg.parse_address(data["address_raw"])
    if data.get("owner_executor_id"):
        _executor(db, data["owner_executor_id"])
    if data.get("duplicate_of"):
        target = reg.find(db, data["duplicate_of"], include_deleted=False)
        if target is None or target.kp_id == item.kp_id:
            raise HTTPException(status_code=422, detail="Дубль чего: площадка не найдена")
        data["duplicate_of"] = target.kp_id
        data.setdefault("status", "duplicate")
    values.update(data)
    actor = f"user:{user.username}"
    changed = reg.apply_changes(db, item, values, "manual", actor, reason=reason)
    if verified:
        item.verified_at, item.verified_by = utc_now(), user.username
        if item.status in ("unverified", "missing_in_source"):
            changed += reg.apply_changes(db, item, {"status": "active"}, "field", actor, reason="подтверждена на месте",
                                         same_version=bool(changed))
        changed.append("verified")
    db.flush()
    audit(db, user.username, "kp.updated", "kp", item.code, fields=sorted(set(changed)))
    return reg.detail_view(db, item)


@router.delete("/kp/{key}")
def delete(key: str, reason: str | None = None, db: Session = Depends(get_session),
           user: User = Depends(WRITE_REFS)) -> dict:
    """Мягкое удаление: карточка скрывается из реестра, история и привязки дел остаются."""
    item = _get(db, key)
    if item.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Площадка уже удалена")
    item.deleted_at = utc_now()
    item.version += 1
    reg._log(db, item, "deleted", None, iso(item.deleted_at), "manual", f"user:{user.username}", reason=reason)
    audit(db, user.username, "kp.deleted", "kp", item.code, reason=reason)
    return reg.detail_view(db, item)


@router.post("/kp/{key}/restore")
def restore(key: str, db: Session = Depends(get_session), user: User = Depends(WRITE_REFS)) -> dict:
    item = _get(db, key)
    if item.deleted_at is None:
        raise HTTPException(status_code=409, detail="Площадка не удалена")
    old, item.deleted_at = iso(item.deleted_at), None
    item.version += 1
    reg._log(db, item, "deleted", old, None, "manual", f"user:{user.username}", reason="восстановлена")
    audit(db, user.username, "kp.restored", "kp", item.code)
    return reg.detail_view(db, item)


@router.put("/kp/{key}/containers")
def put_containers(key: str, body: KpContainersIn, db: Session = Depends(get_session),
                   user: User = Depends(WRITE_REFS)) -> dict:
    item = _get(db, key)
    items = [c.model_dump() for c in body.containers]
    actor = f"user:{user.username}"
    bumped = reg.set_containers(db, item, items, "manual", actor, reason=body.reason)
    reg.apply_changes(db, item, {"containers_qty": len(items),
                                 "containers_volume_m3": round(sum(c["volume_m3"] or 0 for c in items), 3)},
                      "manual", actor, reason=body.reason, same_version=bumped)
    db.flush()
    audit(db, user.username, "kp.containers", "kp", item.code, count=len(items))
    return reg.detail_view(db, item)


@router.put("/kp/{key}/responsibles")
def put_responsibles(key: str, body: KpResponsiblesIn, db: Session = Depends(get_session),
                     user: User = Depends(WRITE_REFS)) -> dict:
    item = _get(db, key)
    for r in body.responsibles:
        _executor(db, r.executor_id)
    old = [{"role": r.role, "executor_id": r.executor_id, "confirmed": r.confirmed}
           for r in item.responsibles if r.valid_to is None]
    new = [{"role": r.role, "executor_id": r.executor_id, "confirmed": r.confirmed} for r in body.responsibles]
    if sorted(old, key=repr) == sorted(new, key=repr):
        return reg.detail_view(db, item)  # ничего не поменялось — новую версию не заводим
    today = date.today()
    for r in item.responsibles:
        if r.valid_to is None:
            r.valid_to = today
    for r in body.responsibles:
        item.responsibles.append(KpResponsible(valid_from=today, **r.model_dump()))
    item.version += 1
    reg._log(db, item, "responsibles", old, new, "manual", f"user:{user.username}", reason=body.reason)
    db.flush()
    db.expire(item, ["responsibles"])
    audit(db, user.username, "kp.responsibles", "kp", item.code, count=len(new))
    return reg.detail_view(db, item)


# --- Привязка дела к площадке руками ---


@router.put("/cases/{case_id}/kp")
def set_case_kp(case_id: int, body: CaseKpIn, db: Session = Depends(get_session),
                user: User = Depends(require("cases.inspect"))) -> dict:
    case = db.get(Case, case_id)
    if case is None or (user.executor_id and case.executor_id != user.executor_id):
        raise HTTPException(status_code=404, detail="Дело не найдено")
    target = reg.find(db, body.kp, include_deleted=False) if body.kp else None
    if body.kp and target is None:
        raise HTTPException(status_code=422, detail="Площадка не найдена")
    case.kp_id = target.kp_id if target else None
    case.kp_score = 1.0 if target else None
    case.kp_method = "manual"  # дальше автоматическая привязка это дело не трогает
    case.history.append(CaseHistory(
        action="KP", actor_type="INSPECTOR", actor_user_id=user.id, actor_name=user.full_name or user.username,
        title="Площадка уточнена" if target else "Площадка снята",
        description=f"{target.code} — {target.address_raw or 'без адреса'}" if target else "Дело не относится к площадке.",
    ))
    audit(db, user.username, "case.kp", "case", str(case_id), kp=target.code if target else None)
    db.flush()
    return case_view(case)
