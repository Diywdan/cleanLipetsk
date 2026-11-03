"""Справочный API для DG: пути, токены и формы ответов как в контракте и test_crm_drt."""

from conftest import ASG, ENG, EXEC_DDHIB, TERR, TYPE_POTHOLES, login, read_headers, write_headers


def test_tokens_are_scoped(client):
    assert client.get("/api/v1/integration/engineers").status_code == 401
    assert client.get("/api/v1/integration/engineers", headers=write_headers()).status_code == 401
    assert client.get("/api/v1/integration/engineers", headers=read_headers()).status_code == 200
    body = {"schema": "datagateway.bot_user_registration", "schema_version": "1.0",
            "registration_event_id": "c27c2c9f-eef7-462c-aa07-cbe437d35acc", "idempotency_key": "reg-1",
            "max_user_id": "max-1", "phone": "+79990000482", "requested_at": "2026-10-13T08:00:00Z"}
    assert client.post("/api/v1/integration/bot-users/registrations", headers=read_headers(),
                       json=body).status_code == 401


def test_reference_shapes(client):
    engineers = client.get("/api/v1/integration/engineers", headers=read_headers()).json()["items"]
    assert engineers[0] == {"engineer_id": ENG, "name": "Иванов Иван Иванович", "is_active": True}
    assert client.get(f"/api/v1/integration/engineers/{ENG}", headers=read_headers()).json()["engineer_id"] == ENG

    executors = client.get("/api/v1/integration/executors", headers=read_headers()).json()["items"]
    assert len(executors) == 9 and set(executors[0]) == {"executor_id", "name", "is_active"}

    types = client.get(f"/api/v1/integration/executors/{EXEC_DDHIB}/violation-types", headers=read_headers()).json()
    assert types["executor_id"] == EXEC_DDHIB and len(types["items"]) == 16
    assert types["items"][0] == {"type_violation_id": TYPE_POTHOLES, "name": "Ямы", "is_active": True}

    one = client.get(f"/api/v1/integration/violation-types/{TYPE_POTHOLES}", headers=read_headers()).json()
    assert one == {"type_violation_id": TYPE_POTHOLES, "name": "Ямы", "is_active": True}
    assert client.get("/api/v1/integration/executors/EXEC-9999", headers=read_headers()).status_code == 404


def test_deactivated_engineer_leaves_active_list(client):
    login(client)
    assert client.patch(f"/api/v1/engineers/{ENG}", json={"is_active": False}).status_code == 200
    active = client.get("/api/v1/integration/engineers", headers=read_headers()).json()["items"]
    assert ENG not in {e["engineer_id"] for e in active}
    everyone = client.get("/api/v1/integration/engineers?active_only=false", headers=read_headers()).json()["items"]
    assert {"engineer_id": ENG, "name": "Иванов Иван Иванович", "is_active": False} in everyone
    assert client.get(f"/api/v1/integration/assignments/engineers/{ENG}/current",
                      headers=read_headers()).status_code == 404


def test_current_assignment_and_validation(client):
    current = client.get(f"/api/v1/integration/assignments/engineers/{ENG}/current", headers=read_headers()).json()
    assert current == {
        "assignment_id": ASG, "engineer_id": ENG, "territory_id": TERR, "territory_name": "Центральный округ",
        "route_id": None, "is_active": True,
        "bounds": {"south": 52.5, "west": 39.4, "north": 52.75, "east": 39.8},
    }
    url = f"/api/v1/integration/assignments/engineers/{ENG}/assignments/{ASG}/validate"
    inside = client.get(url, params={"territory_id": TERR, "lat": 52.61, "lon": 39.59}, headers=read_headers()).json()
    assert inside["assignment_valid"] is True
    assert inside["territory_validation"] == {"status": "completed", "is_inside": True, "distance_to_boundary_meters": 0.0}
    outside = client.get(url, params={"territory_id": TERR, "lat": 55.75, "lon": 37.6}, headers=read_headers()).json()
    assert outside["assignment_valid"] is True and outside["territory_validation"]["is_inside"] is False
    wrong = client.get(url, params={"territory_id": "TERR-002", "lat": 52.61, "lon": 39.59}, headers=read_headers())
    assert wrong.json()["assignment_valid"] is False


def test_bot_identity_unknown_user(client):
    assert client.get("/api/v1/integration/assignments/bot-users/max-nobody", headers=read_headers()).status_code == 404
