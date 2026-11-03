"""Коды КП по нумерации ГЖИ: перенумерация по GUID УТКО, площадки всей области, совместимость с выгрузкой УТКО."""

import pytest

from conftest import login
from test_kp import LAT, LON, load, utko_row

A, B, D = ("aaaaaaaa-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002",
           "dddddddd-0000-4000-8000-000000000004")
ELETS = "eeeeeeee-0000-4000-8000-000000000005"
UTKO = [utko_row(A, 1), utko_row(B, 2, lat=LAT + 0.01), utko_row(D, 3, lat=LAT + 0.02)]


def gzhi_row(code: str, guid: str, municipality: str = "Городской округ г. Липецк", **extra) -> dict:
    row = {"code": code, "utko_id": guid, "registry_number": "0099999-48", "name": "05-0001",
           "municipality": municipality, "settlement": municipality, "address_raw": "Мира ул, в районе д. 31",
           "latitude": "52.6195", "longitude": "38.5005", "category": "Контейнерная площадка", "status": "unverified"}
    row.update(extra)
    return row


# A и B меняются кодами, D у ГЖИ нет, его код LP-000003 отдан Ельцу
GZHI = [gzhi_row("LP-000002", A), gzhi_row("LP-000001", B), gzhi_row("LP-000003", ELETS, "Городской округ г. Елец"),
        gzhi_row("LP-000004", "ffffffff-0000-4000-8000-000000000006", "Задонский муниципальный округ",
                 status="missing_in_source"),
        gzhi_row("плохой", "1234", latitude="")]


def codes(db) -> dict[str, str]:
    from sqlalchemy import select

    from app.models import Kp, KpExternalId

    return {e.external_id: e.kp.code for e in db.scalars(select(KpExternalId).where(KpExternalId.source == "utko"))
            } | {"_all": sorted(db.scalars(select(Kp.code)))}


def run(rows):
    from app import kp
    from app.db import session_scope

    with session_scope() as db:
        return kp.import_gzhi_codes(db, rows)


@pytest.fixture
def renumbered(client):
    login(client)
    load(UTKO, complete=True)
    stats = run(GZHI)
    assert stats["rows"] == 5 and stats["skipped"] == 1 and stats["matched"] == 2 and stats["created"] == 2
    assert stats["code_changed"] == 3 and stats["renumbered_not_in_gzhi"] == 1
    return client


def test_codes_follow_gzhi(renumbered):
    from sqlalchemy import select

    from app import kp
    from app.db import session_scope
    from app.models import KpChangeLog

    with session_scope() as db:
        got = codes(db)
        assert got[A] == "LP-000002" and got[B] == "LP-000001" and got[ELETS] == "LP-000003"
        assert got[D] == "LP-000005"  # своя, у ГЖИ нет: номер после последнего
        assert got["_all"] == [f"LP-00000{n}" for n in range(1, 6)]
        elets = kp.find(db, "LP-000003")
        assert elets.municipality == "Городской округ г. Елец" and elets.address_street == "мира"
        assert elets.address_house == "31" and elets.status == "unverified" and elets.responsibles == []
        assert kp.find(db, "LP-000004").status == "missing_in_source"
        a = kp.find(db, "LP-000002")
        log = db.scalars(select(KpChangeLog).where(KpChangeLog.kp_id == a.kp_id, KpChangeLog.field == "code"))
        assert [(c.old_value, c.new_value, c.source) for c in log] == [("LP-000001", "LP-000002", "gzhi")]
    card = next(c for c in renumbered.get("/api/v1/kp").json() if c["code"] == "LP-000003")
    assert card["dataSource"] == "FGIS_UTKO" and card["location"]["address"] == "Мира ул, в районе д. 31"


def test_rerun_changes_nothing(renumbered):
    again = run(GZHI)
    assert again["code_changed"] == 0 and again["created"] == 0 and again["renumbered_not_in_gzhi"] == 0


def test_utko_sync_of_one_area_ignores_rest_of_region(renumbered):
    from app import kp
    from app.db import session_scope

    stats = load(UTKO, complete=True)  # Липецк: 3 площадки против 5 в реестре — не «скачок», чужое не пропало
    assert stats["unchanged"] == 3 and stats.get("missing", 0) == 0 and stats.get("created", 0) == 0
    with session_scope() as db:
        assert kp.find(db, "LP-000003").status == "unverified"
    new = load(UTKO + [utko_row("99999999-0000-4000-8000-000000000009", 9, lat=LAT + 0.03)], force=True)
    assert new["created"] == 1
    with session_scope() as db:
        assert codes(db)["99999999-0000-4000-8000-000000000009"] == "LP-000006"


def test_repeated_code_refused(client):
    from app import kp

    login(client)
    load(UTKO, complete=True)
    with pytest.raises(kp.SyncRefused):
        run([gzhi_row("LP-000002", A), gzhi_row("LP-000002", B)])
    from app.db import session_scope

    with session_scope() as db:
        assert codes(db)[A] == "LP-000001"  # ничего не тронуто
