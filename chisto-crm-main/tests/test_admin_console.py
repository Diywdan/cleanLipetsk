"""Консоль системного администратора: страница /admin/, сводка, фильтр дел по событию."""

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from conftest import ADMIN, canonical_event, login, pair, post_event


def test_console_served_next_to_api(client):
    redirect = client.get("/admin", follow_redirects=False)
    assert redirect.status_code in (307, 308) and redirect.headers["location"].endswith("/admin/")
    page = client.get("/admin/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "admin.js" in page.text and "Системный администратор" in page.text
    assert client.get("/admin/admin.js").status_code == 200
    assert client.get("/admin/admin.css").status_code == 200
    assert client.get("/admin/fonts/golos-text-cyrillic-wght-normal.woff2").status_code == 200


def test_summary_counts_for_admin(client):
    pair(client)
    assert post_event(client, canonical_event()).status_code == 202
    assert client.get("/api/v1/admin/summary").status_code == 401
    login(client)
    s = client.get("/api/v1/admin/summary").json()
    assert s["engineers"]["total"] == 4 and s["engineers"]["with_max"] <= s["engineers"]["total"]
    assert s["territories"] > 0 and s["executors"] > 0 and s["violation_types"] > 0
    assert s["events"] == {"PROCESSED": 1}
    assert s["cases"]["NEW"] == 1 and s["cases"]["overdue"] == 0
    assert s["registrations"] == {}
    assert s["users"]["total"] == s["users"]["active"] == 1
    assert s["integration"]["configured"] is True


def test_summary_hides_what_role_cannot_see(client):
    login(client)
    client.post("/api/v1/users", json={"username": "boss", "password": "manager-pass-1", "roles": ["manager"]})
    client.post("/api/v1/users", json={"username": "uk9", "password": "uk-master-pass-9", "roles": ["uk_master"],
                                       "executor_id": "EXEC-0002"})
    client.post("/api/v1/auth/logout")
    login(client, "boss", "manager-pass-1")
    s = client.get("/api/v1/admin/summary").json()
    assert s["events"] is not None and s["cases"] is not None
    assert s["registrations"] is None and s["users"] is None and s["integration"] is None
    client.post("/api/v1/auth/logout")
    login(client, "uk9", "uk-master-pass-9")  # у организации нет справочников — консоль ей закрыта
    assert client.get("/api/v1/admin/summary").status_code == 403


def test_cases_filtered_by_event(client):
    pair(client)
    first, second = canonical_event(), canonical_event()
    post_event(client, first)
    post_event(client, second)
    login(client)
    assert client.get("/api/v1/cases").json()["total"] == 2
    found = client.get("/api/v1/cases", params={"event_id": first["id"]}).json()
    assert found["total"] == 1 and found["items"][0]["event_id"] == first["id"]


def test_admin_is_system_administrator(client):
    login(client)
    assert client.get("/api/v1/auth/me").json()["full_name"] == "Системный администратор"
    roles = {r["code"]: r["name"] for r in client.get("/api/v1/roles").json()}
    assert roles["admin"] == "Системный администратор"


def test_migration_renames_only_factory_names(client):
    from app.db import get_engine
    from app.main import ROOT

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    engine = get_engine()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0002")
        connection.execute(sa.text("UPDATE roles SET name = 'Администратор' WHERE code = 'admin'"))
        connection.execute(sa.text("UPDATE users SET full_name = 'Администратор' WHERE username = :u"), {"u": ADMIN[0]})
        connection.execute(sa.text("UPDATE roles SET name = 'Наш диспетчер' WHERE code = 'dispatcher'"))
        command.upgrade(cfg, "head")
    with engine.connect() as connection:
        names = dict(connection.execute(sa.text("SELECT code, name FROM roles")).all())
        full_name = connection.execute(sa.text("SELECT full_name FROM users WHERE username = :u"), {"u": ADMIN[0]}).scalar()
    assert names["admin"] == "Системный администратор" and names["dispatcher"] == "Наш диспетчер"
    assert full_name == "Системный администратор"
