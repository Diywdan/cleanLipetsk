"""CRUD справочников как в тестовой CRM: чтение по ID и удаление того, на что ничего не ссылается."""

from conftest import ASG, ENG, EXEC_DDHIB, TERR, TYPE_POTHOLES, canonical_event, login, pair, post_event


def test_get_by_id(client):
    login(client)
    assert client.get(f"/api/v1/territories/{TERR}").json()["territory_id"] == TERR
    assert client.get(f"/api/v1/executors/{EXEC_DDHIB}").json()["kind"] == "OMSU"
    assert client.get(f"/api/v1/violation-types/{TYPE_POTHOLES}").json()["name"] == "Ямы"
    assert client.get(f"/api/v1/assignments/{ASG}").json()["engineer_id"] == ENG
    assert client.get("/api/v1/executors/EXEC-9999").status_code == 404


def test_delete_mistaken_records(client):
    login(client)
    t = client.post("/api/v1/territories", json={"name": "Ошибочный участок"}).json()["territory_id"]
    v = client.post("/api/v1/violation-types", json={"name": "Лишний тип", "code": "test.extra"}).json()["type_violation_id"]
    x = client.post("/api/v1/executors", json={"name": "Лишняя организация", "violation_type_ids": [v]}).json()["executor_id"]
    e = client.post("/api/v1/engineers", json={"full_name": "Тестов Тест", "phone": "+79990001111"}).json()["engineer_id"]
    a = client.post("/api/v1/assignments", json={"engineer_id": e, "territory_id": t}).json()["assignment_id"]

    # тип привязан к исполнителю, участок — к назначению: сначала они
    assert client.delete(f"/api/v1/violation-types/{v}").status_code == 409
    assert "назначения: 1" in client.delete(f"/api/v1/territories/{t}").json()["message"]
    assert client.delete(f"/api/v1/executors/{x}").json() == {"deleted": x}
    assert client.delete(f"/api/v1/violation-types/{v}").status_code == 200
    assert client.delete(f"/api/v1/engineers/{e}").status_code == 200  # назначение уходит вместе с инженером
    assert client.get(f"/api/v1/assignments/{a}").status_code == 404
    assert client.delete(f"/api/v1/territories/{t}").status_code == 200
    actions = {r["action"] for r in client.get("/api/v1/audit").json()}
    assert {"executor.deleted", "violation_type.deleted", "engineer.deleted", "territory.deleted"} <= actions


def test_records_with_cases_are_not_deleted(client):
    pair(client)
    assert post_event(client, canonical_event()).status_code == 202
    login(client)
    for path in (f"engineers/{ENG}", f"executors/{EXEC_DDHIB}", f"violation-types/{TYPE_POTHOLES}",
                 f"assignments/{ASG}", f"territories/{TERR}"):
        response = client.delete(f"/api/v1/{path}")
        assert response.status_code == 409, path
        assert "снимите «Активен»" in response.json()["message"]


def test_delete_needs_write_rights(client):
    from test_workflow import as_user

    inspector = as_user(client, "insp", "inspector-pass-1", ["inspector"])
    assert inspector.delete(f"/api/v1/territories/{TERR}").status_code == 403
    assert inspector.delete("/api/v1/kp/LP-000001").status_code == 403
