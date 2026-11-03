"""Аккаунты ДРТ и ведомств: профиль для фронта, область видимости, кто сдаёт отчёт."""

from fastapi.testclient import TestClient

from conftest import EXEC_DDHIB, EXEC_EKOPROM, canonical_event, login, pair, post_event
from test_workflow import act, report_body


def test_me_in_frontend_shape(client):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    # администратор CRM во фронте ведёт дела как инспектор; ADMIN фронта — руководство, только смотрит
    assert (me["role"], me["department"], me["organization"]) == ("INSPECTOR", "DRT", None)
    boss = {"username": "boss", "password": "rukovodstvo-pass-1", "roles": ["manager"]}
    assert client.post("/api/v1/users", json=boss).json()["role"] == "ADMIN"


def test_executor_needs_organization(client):
    login(client)
    body = {"username": "minpr", "password": "minprirody-pass-1", "roles": ["executor"]}
    missing = client.post("/api/v1/users", json=body)
    assert missing.status_code == 422 and "организация" in missing.json()["message"]
    created = client.post("/api/v1/users", json={**body, "executor_id": EXEC_DDHIB}).json()
    assert created["role"] == "UK" and created["department"] == "DDHIB"
    assert created["organization"] == {"id": EXEC_DDHIB, "name": "ДДХиБ", "kind": "OMSU"}
    moved = client.patch(f"/api/v1/users/{created['id']}", json={"executor_id": EXEC_EKOPROM}).json()
    assert moved["organization"]["kind"] == "REG_OPERATOR" and moved["department"] == "EKOPROM"
    cleared = client.patch(f"/api/v1/users/{created['id']}", json={"executor_id": None})
    assert cleared.status_code == 422


def test_report_only_by_case_organization(client):
    pair(client)
    post_event(client, canonical_event())
    login(client)
    # инспектор с правом отчёта, но без организации — проверка области не пускает
    body = {"username": "both", "password": "inspector-pass-1", "roles": ["inspector", "uk_master"]}
    assert client.post("/api/v1/users", json=body).status_code == 201
    both = TestClient(client.app)
    login(both, "both", "inspector-pass-1")
    case_id = both.get("/api/v1/incidents").json()[0]["id"]
    act(both, case_id, "confirm", {"deadlineHours": 24})
    denied = act(both, case_id, "report", report_body())
    assert denied.status_code == 403 and denied.json()["message"] == "Отчёт сдаёт организация-исполнитель этого дела"


def test_agency_accounts_command(client):
    from app import cli

    pair(client)
    post_event(client, canonical_event())  # дело ДДХиБ
    rows = cli.agency_accounts("executor")
    accounts = {username: (org, password) for username, org, password in rows}
    # инспектор и руководство ДРТ + 9 ведомств из бота
    assert len(rows) == 11 and all(password for _, password in accounts.values())
    assert accounts["drt"][0] == "ДРТ" and "nature_ministry" in accounts and "rukovodstvo" in accounts
    assert all(password is None for _, _, password in cli.agency_accounts("executor"))  # повтор ничего не меняет

    drt = TestClient(client.app)
    login(drt, "drt", accounts["drt"][1])
    assert drt.get("/api/v1/auth/me").json()["role"] == "INSPECTOR"
    assert len(drt.get("/api/v1/incidents").json()) == 1

    nature = TestClient(client.app)
    login(nature, "nature_ministry", accounts["nature_ministry"][1])
    me = nature.get("/api/v1/auth/me").json()
    assert (me["role"], me["department"], me["organization"]["kind"]) == ("UK", "MPLO", "MPR")
    assert nature.get("/api/v1/incidents").json() == []  # чужое дело не видно

    ddhib = TestClient(client.app)
    login(ddhib, "ddhib", accounts["ddhib"][1])
    case_id = ddhib.get("/api/v1/incidents").json()[0]["id"]
    act(drt, case_id, "confirm", {"deadlineHours": 24})
    assert act(ddhib, case_id, "report", report_body()).json()["status"] == "VERIFICATION"
