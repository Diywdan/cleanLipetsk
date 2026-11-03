"""Доменная логика реестра контейнерных площадок.

HTTP-маршруты находятся в :mod:`app.api.kp`; этот модуль отвечает за импорт источников,
историю карточек и автоматическую связь дел с площадками.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utc_now
from app.models import (
    Case, Executor, Kp, KpChangeLog, KpContainer, KpExternalId, KpResponsible,
    KpSourceRecord, Territory, ViolationType,
)

UTKO = "utko"
UTKO_LINK = "explicit"
UTKO_AREA = "Городской округ г. Липецк"
_SOURCE_RANK = {"utko": 1, "registry_owner": 2, "omsu": 3, "field": 4, "manual": 4}
_KP_TYPE_PREFIXES = ("ekoprom.", "housing_inspection.trash_inside_kp")


class SyncRefused(RuntimeError):
    """Импорт источника небезопасен для применения без явного подтверждения."""


def parse_address(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    text = " ".join(value.lower().replace("ё", "е").split())
    street = re.search(r"(.+?)\s+(?:ул(?:ица)?|пр(?:оспект)?|пер(?:еулок)?|пр-д)\b", text)
    house = re.search(r"(?:д\.?|дом)\s*([\w/-]+(?:\s*[а-я])?)", text)
    street_value = street.group(1).strip(" ,.") if street else None
    house_value = re.sub(r"\s+", "", house.group(1)) if house else None
    return street_value, house_value


def find(db: Session, key: str, include_deleted: bool = True) -> Kp | None:
    item = db.scalar(select(Kp).where((Kp.code == key) | (Kp.kp_id == key)))
    if item is None:
        item = db.scalar(select(Kp).join(KpExternalId).where(KpExternalId.external_id == key))
    if item is not None and not include_deleted and item.deleted_at is not None:
        return None
    return item


def next_code_number(db: Session) -> int:
    nums = [int(m.group(1)) for (code,) in db.execute(select(Kp.code))
            if (m := re.fullmatch(r"LP-(\d+)", code or ""))]
    return max(nums, default=0)


def _log(db: Session, item: Kp, field: str, old: Any, new: Any, source: str, actor: str,
         *, reason: str | None = None, applied: bool = True, source_record_id: int | None = None) -> None:
    db.add(KpChangeLog(kp_id=item.kp_id, version=item.version, field=field,
                       old_value=old, new_value=new, source=source, actor=actor,
                       reason=reason, applied=applied, source_record_id=source_record_id))


def apply_changes(db: Session, item: Kp, values: dict[str, Any], source: str, actor: str,
                  *, reason: str | None = None, same_version: bool = False,
                  source_record_id: int | None = None) -> list[str]:
    changed: list[str] = []
    sources = dict(item.field_sources or {})
    for field, new in values.items():
        old = getattr(item, field)
        if old == new:
            continue
        owner = sources.get(field)
        applied = not (source != "manual" and owner and _SOURCE_RANK.get(owner, 0) > _SOURCE_RANK.get(source, 0))
        _log(db, item, field, old, new, source, actor, reason=reason, applied=applied,
             source_record_id=source_record_id)
        changed.append(field)
        if applied:
            setattr(item, field, new)
            sources[field] = source
    if changed:
        item.field_sources = sources
        if not same_version:
            item.version += 1
        item.updated_at = utc_now()
    return changed


def new_kp(db: Session, number: int, data: dict[str, Any], source: str, actor: str,
           *, status: str = "unverified") -> Kp:
    lat, lon = data.pop("latitude", None), data.pop("longitude", None)
    loc = data.pop("location", None)
    if loc:
        lat, lon = loc
    item = Kp(kp_id=str(uuid.uuid4()), code=f"LP-{number:06d}", latitude=float(lat or 0),
              longitude=float(lon or 0), status=status, location_source="manual" if source == "manual" else "utko",
              field_sources={})
    item.field_sources = {key: source for key, value in data.items() if value is not None}
    for key, value in data.items():
        if hasattr(item, key):
            setattr(item, key, value)
    db.add(item)
    db.flush()
    _log(db, item, "created", None, {"code": item.code}, source, actor)
    return item


def _source_record(db: Session, source: str, external_id: str, payload: dict[str, Any],
                   item: Kp | None) -> KpSourceRecord | None:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    previous = db.scalar(select(KpSourceRecord).where(
        KpSourceRecord.source == source, KpSourceRecord.external_id == external_id
    ).order_by(KpSourceRecord.id.desc()).limit(1))
    if previous and previous.payload_hash == digest:
        previous.fetched_at = utc_now()
        previous.kp_id = item.kp_id if item else previous.kp_id
        return None
    record = KpSourceRecord(source=source, external_id=external_id, kp_id=item.kp_id if item else None,
                            payload=payload, payload_hash=digest, match_status="matched" if item else "new")
    db.add(record)
    db.flush()
    return record


def _external_id(db: Session, source: str, external_id: str, item: Kp) -> None:
    row = db.get(KpExternalId, (source, external_id))
    if row is None:
        db.add(KpExternalId(source=source, external_id=external_id, kp_id=item.kp_id))
    else:
        row.kp_id, row.last_seen_at = item.kp_id, utc_now()


def _utko_values(row: dict[str, Any]) -> dict[str, Any]:
    loc = row.get("location") or {}
    coords = loc.get("coordinates") or {}
    address = loc.get("address")
    street, house = parse_address(address)
    containers = row.get("containers") or []
    return {
        "registry_number": row.get("registryNumber"), "name": row.get("name"),
        "category": row.get("categoriesPlaceAccumulation"), "municipality": loc.get("areaName"),
        "settlement": loc.get("populationName"), "address_raw": address,
        "address_street": street, "address_house": house,
        "latitude": coords.get("latitude"), "longitude": coords.get("longitude"),
        "area_m2": row.get("areaSquare"), "containers_qty": row.get("containersQuantity"),
        "containers_volume_m3": row.get("containersVolume"),
        "separate_collection": row.get("isSeparateAccumulation"), "location_source": "utko",
    }, containers


def import_utko(db: Session, rows: list[dict[str, Any]], *, complete: bool = False,
                force: bool = False, area: str | None = UTKO_AREA) -> Counter:
    normalized = [(r, str(r.get("id") or "").strip()) for r in rows]
    normalized = [(r, key) for r, key in normalized if key and (not area or (r.get("location") or {}).get("areaName") == area)]
    if len({key for _, key in normalized}) != len(normalized):
        raise SyncRefused("В выгрузке повторяются GUID УТКО")
    current = list(db.scalars(select(Kp).where(Kp.deleted_at.is_(None))))
    scoped = [k for k in current if not area or k.municipality == area]
    if scoped and not force and abs(len(normalized) - len(scoped)) / len(scoped) > 0.05:
        raise SyncRefused(f"Количество площадок изменилось более чем на 5% ({len(scoped)} → {len(normalized)}); используйте --force")
    stats: Counter = Counter(total=len(normalized))
    seen: set[str] = set()
    registry_seen: dict[str, list[Kp]] = {}
    for row, external_id in normalized:
        seen.add(external_id)
        item = find(db, external_id)
        values, containers = _utko_values(row)
        created = item is None
        rebound = False
        if item is None:
            # Новый ID рядом со старой карточкой может быть переизданием GUID той же площадки.
            lat, lon = values.get("latitude"), values.get("longitude")
            candidate = None
            if lat is not None and lon is not None:
                for old in scoped:
                    old_ids = {e.external_id for e in old.external_ids if e.source == UTKO}
                    if old_ids and old_ids.isdisjoint(seen) and old.address_raw == values.get("address_raw"):
                        if distance_m(old.latitude, old.longitude, lat, lon) <= 30:
                            candidate = old
                            break
            item = candidate
            rebound = item is not None
        source_record = _source_record(db, UTKO, external_id, row, item)
        if item is None:
            number = next_code_number(db) + 1
            item = new_kp(db, number, values, UTKO, "sync:utko")
            stats["created"] += 1
        else:
            old_lat, old_lon = item.latitude, item.longitude
            if distance_m(old_lat, old_lon, values["latitude"], values["longitude"]) > 30:
                values.pop("latitude", None)
                values.pop("longitude", None)
                values["review_reason"] = f"источник сдвинул точку на {round(distance_m(old_lat, old_lon, _float((row.get('location') or {}).get('coordinates', {}).get('latitude')), _float((row.get('location') or {}).get('coordinates', {}).get('longitude'))))} м"
            elif item.review_reason and "сдвинул точку" in item.review_reason:
                values["review_reason"] = None
            changed = apply_changes(db, item, values, UTKO, "sync:utko", source_record_id=source_record.id if source_record else None)
            if changed:
                stats["updated"] += 1
            if item.status == "missing_in_source":
                apply_changes(db, item, {"status": "unverified"}, "utko", "sync:utko", reason="вернулась в выгрузку")
                stats["restored"] += 1
        _external_id(db, UTKO, external_id, item)
        if rebound:
            stats["bound"] += 1
        if source_record:
            source_record.kp_id, source_record.match_status = item.kp_id, "matched"
        if values.get("registry_number"):
            registry_seen.setdefault(values["registry_number"], []).append(item)
        containers_changed = _sync_containers(db, item, containers, source_record.id if source_record else None)
        ensure_rule_responsibles(item, regional_operator(db))
        if not created and not changed and not containers_changed:
            stats["unchanged"] += 1
    for matches in registry_seen.values():
        if len({m.kp_id for m in matches}) > 1:
            for item in matches:
                apply_changes(db, item, {"review_reason": "одинаковый номер реестра у нескольких площадок"}, "utko", "sync:utko")
    if complete:
        for item in scoped:
            if not any(e.external_id in seen for e in item.external_ids if e.source == UTKO) and item.status != "missing_in_source":
                apply_changes(db, item, {"status": "missing_in_source"}, "utko", "sync:utko", reason="нет в полной выгрузке")
                stats["missing"] += 1
    return stats


def _sync_containers(db: Session, item: Kp, rows: list[dict[str, Any]], source_record_id: int | None = None) -> bool:
    active = [c for c in item.containers if c.valid_to is None]
    values = [{"number": r.get("number"), "container_type": r.get("typeContainer"),
               "waste_group": r.get("wasteGroup"), "volume_m3": r.get("containerVolume"), "color": r.get("color")}
              for r in rows]
    keys = ("number", "container_type", "waste_group", "volume_m3", "color")
    old = [{k: getattr(c, k) for k in keys} for c in active]
    if old == values:
        return False
    today = date.today()
    for c in active:
        c.valid_to = today
    for value in values:
        item.containers.append(KpContainer(**value, source="utko", valid_from=today))
    _log(db, item, "containers", old or None, values, "utko", "sync:utko", source_record_id=source_record_id)
    item.version += 1
    return True


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest(db: Session, lat: float, lon: float, radius: float = 150, limit: int = 20) -> list[tuple[Kp, float]]:
    rows = db.scalars(select(Kp).where(Kp.deleted_at.is_(None)).order_by(Kp.code))
    found = [(k, distance_m(lat, lon, k.latitude, k.longitude)) for k in rows]
    return sorted((x for x in found if x[1] <= radius), key=lambda x: (x[1], x[0].code))[:limit]


def _is_kp_case(db: Session, case: Case) -> bool:
    code = getattr(case, "type_code", None)
    if not code and getattr(case, "type_violation_id", None):
        # Relationship-free lookup keeps this helper usable from the ingestion path.
        violation_type = db.get(ViolationType, case.type_violation_id)
        code = violation_type.code if violation_type else None
    return bool(code and (code.startswith("ekoprom.") or code == "housing_inspection.trash_inside_kp"))


def link_case(db: Session, case: Case) -> bool:
    if case.kp_method == "manual":
        return False
    if not _is_kp_case(db, case):
        if case.kp_id and case.kp_method != "manual":
            case.kp_id = case.kp_score = case.kp_method = None
            return True
        return False
    candidates = nearest(db, case.latitude, case.longitude, 50, 2)
    if not candidates:
        return False
    selected = candidates[0][0]
    method = "nearest_multi" if len(candidates) > 1 else "nearest_single"
    new = (selected.kp_id, 0.75, method)
    old = (case.kp_id, case.kp_score, case.kp_method)
    case.kp_id, case.kp_score, case.kp_method = new
    return new != old


def link_cases(db: Session) -> int:
    return sum(link_case(db, case) for case in db.scalars(select(Case).order_by(Case.id)))


def regional_operator(db: Session) -> Executor | None:
    return db.scalar(select(Executor).where(Executor.kind == "REG_OPERATOR", Executor.is_active.is_(True)).order_by(Executor.executor_id))


def ensure_rule_responsibles(item: Kp, operator: Executor | None) -> None:
    if operator and not any(r.valid_to is None and r.role == "waste_removal" for r in item.responsibles):
        item.responsibles.append(KpResponsible(role="waste_removal", executor_id=operator.executor_id,
                                               basis="rule", confirmed=False, priority=1, valid_from=date.today()))


def set_containers(db: Session, item: Kp, values: list[dict[str, Any]], source: str, actor: str,
                   *, reason: str | None = None) -> bool:
    active = [c for c in item.containers if c.valid_to is None]
    old = [{k: getattr(c, k) for k in ("number", "container_type", "waste_group", "volume_m3", "color")} for c in active]
    if old == values:
        return False
    today = date.today()
    for c in active:
        c.valid_to = today
    for value in values:
        item.containers.append(KpContainer(**value, source=source, valid_from=today))
    item.version += 1
    _log(db, item, "containers", old, values, source, actor, reason=reason)
    return True


def _active_containers(item: Kp) -> list[KpContainer]:
    return [c for c in item.containers if c.valid_to is None]


def row_view(item: Kp, distance: float | None = None) -> dict[str, Any]:
    result = {field: getattr(item, field) for field in (
        "kp_id", "code", "registry_number", "name", "status", "category", "municipality", "settlement",
        "address_raw", "address_street", "address_house", "latitude", "longitude", "location_source",
        "location_accuracy_m", "area_m2", "surface", "has_fence", "has_roof", "containers_qty",
        "containers_volume_m3", "separate_collection", "kgo_storage", "owner_executor_id", "in_yard",
        "in_yard_method", "land_parcel_cadnum", "verified_at", "verified_by", "review_reason", "version",
        "created_at", "updated_at", "deleted_at", "duplicate_of", "field_sources")}
    result["external_ids"] = [{"source": x.source, "external_id": x.external_id} for x in item.external_ids]
    if distance is not None:
        result["distance_m"] = round(distance, 1)
    return result


def detail_view(db: Session, item: Kp) -> dict[str, Any]:
    result = row_view(item)
    active = _active_containers(item)
    result["containers"] = [{"number": c.number, "container_type": c.container_type, "waste_group": c.waste_group,
                             "volume_m3": c.volume_m3, "color": c.color, "source": c.source,
                             "valid_from": c.valid_from, "valid_to": c.valid_to} for c in active]
    result["containers_closed"] = sum(c.valid_to is not None for c in item.containers)
    result["responsibles"] = [{"role": r.role, "executor_id": r.executor_id, "executor_name": r.executor.name,
                               "kind": r.executor.kind, "basis": r.basis, "confirmed": r.confirmed,
                               "priority": r.priority, "share_schedule": r.share_schedule,
                               "valid_from": r.valid_from, "valid_to": r.valid_to}
                              for r in item.responsibles if r.valid_to is None]
    cases = list(db.scalars(select(Case).where(Case.kp_id == item.kp_id).order_by(Case.id.desc())))
    result["cases"] = {"total": len(cases), "items": [{"id": c.id, "status": c.status, "address": c.address,
                                                       "created_at": c.created_at} for c in cases[:50]]}
    return result


def card_view(item: Kp, territories: list[Territory] | None = None) -> dict[str, Any]:
    active = _active_containers(item)
    separate = sum(1 for c in active if any(w in (c.waste_group or "").lower() for w in ("раздель", "пласт", "стекл", "бумаг")))
    tko = max(0, len(active) - separate)
    responsibles = [{"role": r.role, "confirmed": r.confirmed,
                     "organization": {"id": r.executor.executor_id, "name": r.executor.name, "kind": r.executor.kind}}
                    for r in item.responsibles if r.valid_to is None]
    source = {"utko": "FGIS_UTKO", "manual": "FIELD_CHECK", "field": "FIELD_CHECK"}.get(item.location_source, "FGIS_UTKO")
    return {"id": item.code, "code": item.code, "registryNumber": item.registry_number,
            "name": item.name, "status": item.status, "dataSource": source,
            "location": {"coordinates": [item.longitude, item.latitude], "address": item.address_raw},
            "containers": {"tko": tko, "separate": separate,
                           "kgmBay": bool(item.kgo_storage) or any("крупногабарит" in (c.container_type or "").lower()
                                                                       for c in active)},
            "fenced": item.has_fence, "responsibles": responsibles}


def change_view(entry: KpChangeLog, code: str | None = None) -> dict[str, Any]:
    return {"id": entry.id, "code": code, "version": entry.version, "field": entry.field,
            "old_value": entry.old_value, "new_value": entry.new_value, "source": entry.source,
            "actor": entry.actor, "reason": entry.reason, "applied": entry.applied, "changed_at": entry.changed_at}


def import_gzhi_codes(db: Session, rows: list[dict[str, Any]]) -> Counter:
    valid = []
    for row in rows:
        code, ext = (row.get("code") or "").strip(), (row.get("utko_id") or "").strip()
        if re.fullmatch(r"LP-\d{6}", code) and ext and _float(row.get("latitude")) is not None and _float(row.get("longitude")) is not None:
            valid.append((row, code, ext))
    if len({code for _, code, _ in valid}) != len(valid) or len({ext for _, _, ext in valid}) != len(valid):
        raise SyncRefused("В выгрузке ГЖИ повторяются код площадки или GUID УТКО")
    stats: Counter = Counter(rows=len(rows), skipped=len(rows) - len(valid))
    existing = {e.external_id: e.kp for e in db.scalars(select(KpExternalId).where(KpExternalId.source == UTKO))}
    all_items = list(db.scalars(select(Kp)))
    # Сначала освобождаем коды — корректно обрабатывает обмен кодами между двумя GUID.
    changes = [(row, code, ext, existing.get(ext)) for row, code, ext in valid]
    listed_ids = {item.kp_id for _, _, _, item in changes if item is not None}
    target_codes = {code for _, code, _, _ in changes}
    previous_codes: dict[str, str] = {}
    for item in all_items:
        if item.code in target_codes and item.kp_id not in listed_ids:
            previous_codes[item.kp_id] = item.code
            item.code = f"TMP-{uuid.uuid4().hex[:12]}"
    for _, code, _, item in changes:
        if item and item.code != code:
            previous_codes[item.kp_id] = item.code
            item.code = f"TMP-{uuid.uuid4().hex[:12]}"
    db.flush()
    for row, code, ext, item in changes:
        values = {"registry_number": row.get("registry_number") or None, "name": row.get("name") or None,
                  "municipality": row.get("municipality") or None, "settlement": row.get("settlement") or None,
                  "address_raw": row.get("address_raw") or None, "address_street": parse_address(row.get("address_raw"))[0],
                  "address_house": parse_address(row.get("address_raw"))[1], "latitude": _float(row.get("latitude")),
                  "longitude": _float(row.get("longitude")), "category": row.get("category") or None,
                  "location_source": "utko"}
        if item is None:
            number = next_code_number(db) + 1
            item = new_kp(db, number, values, "gzhi", "sync:gzhi", status=row.get("status") or "unverified")
            stats["created"] += 1
        else:
            if item.code != code:
                item.code = code
                _log(db, item, "code", previous_codes.get(item.kp_id, item.code), code, "gzhi", "sync:gzhi")
                stats["code_changed"] += 1
            stats["matched"] += 1
        if item.code != code:
            old = item.code
            item.code = code
            _log(db, item, "code", old, code, "gzhi", "sync:gzhi")
            stats["code_changed"] += 1
        _external_id(db, UTKO, ext, item)
        record = _source_record(db, "gzhi", ext, row, item)
        if record:
            record.match_status = "matched"
    # Unlisted local cards remain in the registry, renumbered after the highest GZHI code.
    max_num = max((int(code[3:]) for _, code, _, _ in changes), default=0)
    gzh_ids = {ext for _, _, ext, _ in changes}
    listed_ids = {i.kp_id for _, _, _, i in changes if i}
    not_listed = [k for k in all_items if k.kp_id not in listed_ids and k.code.startswith("TMP-")]
    for item in not_listed:
        if item.code.startswith("TMP-"):
            old_code = previous_codes.get(item.kp_id, item.code)
            item.code = f"LP-{max_num + 1:06d}"
            _log(db, item, "code", old_code, item.code, "gzhi", "sync:gzhi")
            max_num += 1
            stats["renumbered_not_in_gzhi"] += 1
            stats["code_changed"] += 1
    return stats


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
