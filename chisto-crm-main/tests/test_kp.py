"""Реестр КП: загрузка из ФГИС УТКО, матрица владения, карточки для фронта и консоли, привязка дел."""

import copy

import pytest

from conftest import EXEC_EKOPROM, canonical_event, login, pair, post_event

LAT, LON = 52.6101, 39.5901


def utko_row(guid: str, n: int, lat: float = LAT, lon: float = LON, **extra) -> dict:
    row = {
        "id": guid,
        "registryNumber": f"00{n:05d}-48",
        "areaSquare": 16.0,
        "containersVolume": 2.2,
        "name": f"01-П{n:03d}",
        "categoriesPlaceAccumulation": "Контейнерная площадка",
        "isSeparateAccumulation": False,
        "containersQuantity": 2,
        "storageMethod": "Иное",
        "location": {
            "populationName": "Городской округ г. Липецк",
            "coordinates": {"latitude": lat, "longitude": lon},
            "areaName": "Городской округ г. Липецк",
            "address": f"Перова ул, в районе д. {n} В",
        },
        "containers": [
            {"number": "1", "color": "Зеленый", "typeContainer": "Для совместного накопления ТКО",
             "containerVolume": 1.1, "wasteGroup": "Несортированные ТКО"},
            {"number": "2", "color": "Синий", "typeContainer": "Для раздельного накопления ТКО",
             "containerVolume": 1.1, "wasteGroup": "Пластмассовые изделия"},
        ],
    }
    row.update(extra)
    return row


ROWS = [
    utko_row("guid-1", 1),
    utko_row("guid-2", 2, lat=LAT + 0.01),  # ~1,1 км севернее
    utko_row("guid-other", 3, location={"areaName": "Грязинский муниципальный район",
                                        "coordinates": {"latitude": 52.5, "longitude": 39.9}, "address": "с. Казинка"}),
]


def load(rows, **kwargs):
    from app import kp
    from app.db import session_scope

    with session_scope() as db:
        return kp.import_utko(db, copy.deepcopy(rows), **kwargs)


@pytest.fixture
def registry(client):
    login(client)
    stats = load(ROWS, complete=True)
    assert stats["created"] == 2 and stats["total"] == 2  # чужой район отфильтрован
    return client


def ekoprom_type(client) -> str:
    return next(t["type_violation_id"] for t in client.get("/api/v1/violation-types").json()
                if t["code"] == "ekoprom.waste_removal")


def test_front_cards(registry):
    cards = registry.get("/api/v1/kp", headers={"Accept-Encoding": "gzip"}).json()
    assert [c["code"] for c in cards] == ["LP-000001", "LP-000002"]
    card = cards[0]
    assert card["registryNumber"] == "0000001-48" and card["dataSource"] == "FGIS_UTKO"
    assert card["location"]["coordinates"] == [LON, LAT] and card["location"]["address"] == "Перова ул, в районе д. 1 В"
    assert card["containers"] == {"tko": 1, "separate": 1, "kgmBay": False}
    # вывоз — региональный оператор по правилу, не подтверждён
    assert card["responsibles"] == [{"role": "waste_removal", "confirmed": False, "organization": {
        "id": EXEC_EKOPROM, "name": "АО «ЭКОПРОМ-ЛИПЕЦК»", "kind": "REG_OPERATOR"}}]


def test_search_nearest_and_detail(registry):
    found = registry.get("/api/v1/kp/search", params={"q": "перова 2"}).json()
    assert found["total"] == 1 and found["items"][0]["code"] == "LP-000002"
    assert found["by_status"] == {"unverified": 2}
    near = registry.get("/api/v1/kp/nearest", params={"lat": LAT + 0.0002, "lon": LON, "r": 150}).json()
    assert [k["code"] for k in near] == ["LP-000001"] and 20 < near[0]["distance_m"] < 25
    detail = registry.get("/api/v1/kp/LP-000001").json()
    assert detail["address_street"] == "перова" and detail["address_house"] == "1в"
    assert len(detail["containers"]) == 2 and detail["external_ids"][0]["external_id"] == "guid-1"
    assert registry.get("/api/v1/kp/guid-1").json()["code"] == "LP-000001"  # и по GUID УТКО
    assert registry.get("/api/v1/kp/LP-999999").status_code == 404


def test_resync_is_idempotent_and_logs_changes(registry):
    assert load(ROWS)["unchanged"] == 2
    changed = copy.deepcopy(ROWS)
    changed[0]["areaSquare"] = 20.0
    changed[0]["containers"] = changed[0]["containers"][:1]
    stats = load(changed)
    assert stats["updated"] == 1 and stats["unchanged"] == 1
    detail = registry.get("/api/v1/kp/LP-000001").json()
    assert detail["area_m2"] == 20.0 and len(detail["containers"]) == 1 and detail["containers_closed"] == 2
    fields = {h["field"] for h in registry.get("/api/v1/kp/LP-000001/history").json()}
    assert {"area_m2", "containers", "created"} <= fields
    feed = registry.get("/api/v1/kp/changes", params={"since": "2000-01-01T00:00:00Z"}).json()
    assert feed[0]["field"] == "created" and {e["code"] for e in feed} == {"LP-000001", "LP-000002"}


def test_manual_edit_wins_over_source(registry):
    assert registry.patch("/api/v1/kp/LP-000001", json={"area_m2": 30, "reason": "замер на месте"}).status_code == 200
    changed = copy.deepcopy(ROWS)
    changed[0]["areaSquare"] = 99.0
    load(changed)
    detail = registry.get("/api/v1/kp/LP-000001").json()
    assert detail["area_m2"] == 30 and detail["field_sources"]["area_m2"] == "manual"
    skipped = [h for h in registry.get("/api/v1/kp/LP-000001/history").json() if h["field"] == "area_m2"]
    assert skipped[0]["applied"] is False and skipped[0]["new_value"] == 99.0


def test_source_shift_goes_to_review(registry):
    moved = copy.deepcopy(ROWS)
    moved[0]["location"]["coordinates"]["latitude"] = LAT + 0.001  # 111 м
    load(moved)
    detail = registry.get("/api/v1/kp/LP-000001").json()
    assert detail["latitude"] == LAT and "сдвинул точку на 111 м" in detail["review_reason"]
    assert registry.get("/api/v1/kp/search", params={"review": True}).json()["total"] == 1


def test_missing_only_on_complete_export(registry):
    assert load(ROWS[1:], force=True)["missing"] == 0  # неполная выгрузка ничего не помечает
    assert load(ROWS[1:], complete=True, force=True)["missing"] == 1
    assert registry.get("/api/v1/kp/LP-000001").json()["status"] == "missing_in_source"
    assert load(ROWS, complete=True)["restored"] == 1
    assert registry.get("/api/v1/kp/LP-000001").json()["status"] == "unverified"


def test_sync_refuses_big_jump(registry):
    from app.kp import SyncRefused

    with pytest.raises(SyncRefused):
        load(ROWS[:1])


def test_guid_swap_binds_to_old_card(registry):
    swapped = copy.deepcopy(ROWS)
    swapped[0]["id"] = "guid-1-new"
    assert load(swapped)["bound"] == 1
    detail = registry.get("/api/v1/kp/LP-000001").json()
    assert {e["external_id"] for e in detail["external_ids"]} == {"guid-1", "guid-1-new"}


def test_manual_create_edit_delete_restore(registry):
    body = {"address_raw": "Ленина ул, в районе д. 15 А", "latitude": 52.61, "longitude": 39.6, "area_m2": 12}
    created = registry.post("/api/v1/kp", json=body).json()
    assert created["code"] == "LP-000003" and created["location_source"] == "manual"
    assert created["address_street"] == "ленина" and created["address_house"] == "15а"
    key = created["code"]
    verified = registry.patch(f"/api/v1/kp/{key}", json={"verified": True, "surface": "ASPHALT", "has_fence": True}).json()
    assert verified["status"] == "active" and verified["verified_at"] and verified["surface"] == "ASPHALT"
    assert verified["version"] == 2  # правка полей и подтверждение — одна версия
    assert registry.patch(f"/api/v1/kp/{key}", json={"latitude": 52.0}).status_code == 422
    put = registry.put(f"/api/v1/kp/{key}/containers", json={"containers": [
        {"number": "1", "container_type": "Для крупногабаритных отходов", "volume_m3": 8}]}).json()
    assert put["containers_qty"] == 1 and put["containers_volume_m3"] == 8 and put["version"] == 3
    team = {"responsibles": [{"role": "site_maintenance", "executor_id": "EXEC-0001", "confirmed": True},
                             {"role": "waste_removal", "executor_id": EXEC_EKOPROM}], "reason": "договор на содержание"}
    resp = registry.put(f"/api/v1/kp/{key}/responsibles", json=team).json()
    assert [(r["role"], r["confirmed"]) for r in resp["responsibles"]] == [("site_maintenance", True), ("waste_removal", False)]
    assert resp["version"] == 4
    assert registry.put(f"/api/v1/kp/{key}/responsibles", json=team).json()["version"] == 4  # без изменений — без версии
    assert registry.get(f"/api/v1/kp/{key}/history").json()[0]["reason"] == "договор на содержание"
    card = next(c for c in registry.get("/api/v1/kp").json() if c["code"] == key)
    assert card["containers"]["kgmBay"] is True and card["fenced"] is True and card["dataSource"] == "FIELD_CHECK"

    assert registry.delete(f"/api/v1/kp/{key}").json()["deleted_at"]
    assert key not in {c["code"] for c in registry.get("/api/v1/kp").json()}
    assert registry.get("/api/v1/kp/search", params={"deleted": True}).json()["total"] == 1
    assert registry.delete(f"/api/v1/kp/{key}").status_code == 409
    assert registry.post(f"/api/v1/kp/{key}/restore").json()["deleted_at"] is None


def test_case_links_to_nearest_kp(registry):
    pair(registry)
    eko = ekoprom_type(registry)
    event = canonical_event(**{"violation__executor": {"executor_id": EXEC_EKOPROM, "name": "АО «ЭКОПРОМ-ЛИПЕЦК»"},
                               "violation__type": {"type_violation_id": eko, "name": "Вывоз КГО, ТКО",
                                                   "selected_by": "inspector"},
                               "location__coordinates": {"latitude": LAT + 0.0002, "longitude": LON}})
    assert post_event(registry, event).status_code == 202
    assert post_event(registry, canonical_event()).status_code == 202  # яма рядом — не про площадку
    incidents = {i["violationType"]["id"]: i for i in registry.get("/api/v1/incidents").json()}
    link = incidents[eko]["kp"]
    assert link["code"] == "LP-000001" and link["method"] == "nearest_single" and link["score"] == 0.75
    assert link["registryNumber"] == "0000001-48"
    pothole = next(i for t, i in incidents.items() if t != eko)
    assert pothole["kp"] is None
    # регоператор в деле — роль «вывоз», а не «содержание площадки»
    assert [r["role"] for r in incidents[eko]["responsibles"]] == ["waste_removal"]
    assert [r["role"] for r in pothole["responsibles"]] == ["site_maintenance"]

    # инспектор привязывает яму к площадке руками — автоматика её больше не трогает
    put = registry.put(f"/api/v1/cases/{pothole['id']}/kp", json={"kp": "LP-000002"})
    assert put.status_code == 200 and put.json()["kp_method"] == "manual"
    from app import kp
    from app.db import session_scope

    with session_scope() as db:
        kp.link_cases(db)
    again = registry.get(f"/api/v1/incidents/{pothole['id']}").json()
    assert again["kp"]["code"] == "LP-000002" and again["timeline"]["history"][-1]["title"] == "Площадка уточнена"
    assert registry.get("/api/v1/kp/LP-000001").json()["cases"]["total"] == 1


def test_front_kp_requires_login(client):
    assert client.get("/api/v1/kp").status_code == 401
