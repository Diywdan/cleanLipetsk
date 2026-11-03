"""Регистрация инженера при первом запуске бота (§23): все пять статусов и идемпотентность."""

from datetime import datetime
from uuid import uuid4

from conftest import ASG, ENG, login, read_headers, write_headers

URL = "/api/v1/integration/bot-users/registrations"
# Поля ответа строго как CRMRegistrationResponse в DG (лишнее поле DG отвергнет).
RESPONSE_KEYS = {"registration_id", "status", "max_user_id", "engineer", "assignment", "reason", "processed_at"}


def request(max_user_id: str, phone: str, key: str | None = None) -> dict:
    return {
        "schema": "datagateway.bot_user_registration",
        "schema_version": "1.0",
        "registration_event_id": str(uuid4()),
        "idempotency_key": key or f"registration:{max_user_id}:{uuid4().hex[:6]}",
        "max_user_id": max_user_id,
        "phone": phone,
        "requested_at": "2026-10-13T08:00:00Z",
    }


def register(client, body, path=URL):
    return client.post(path, headers={**write_headers(), "Idempotency-Key": body["idempotency_key"]}, json=body)


def test_registered_by_phone_in_local_format(client):
    response = register(client, request("max-ivanov", "8 (999) 000-04-82"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == RESPONSE_KEYS
    assert data["status"] == "registered"
    assert data["engineer"] == {"engineer_id": ENG, "name": "Иванов Иван Иванович", "is_active": True}
    assert data["assignment"]["assignment_id"] == ASG
    assert datetime.fromisoformat(data["processed_at"]).tzinfo is not None  # DG требует время с поясом
    identity = client.get("/api/v1/integration/assignments/bot-users/max-ivanov", headers=read_headers()).json()
    assert identity == {"max_user_id": "max-ivanov", "engineer_id": ENG, "is_active": True}


def test_idempotency(client):
    body = request("max-ivanov", "+79990000482", key="registration:max-ivanov:1")
    first = register(client, body).json()
    again = register(client, {**body, "registration_event_id": str(uuid4())}).json()
    assert again == first
    changed = register(client, {**body, "phone": "+79990000517"})
    assert changed.status_code == 409
    mismatch = client.post(URL, headers={**write_headers(), "Idempotency-Key": "other"}, json=body)
    assert mismatch.status_code == 422


def test_already_registered_with_new_key(client):
    register(client, request("max-ivanov", "+79990000482"))
    data = register(client, request("max-ivanov", "+79990000482")).json()
    assert data["status"] == "already_registered" and data["engineer"]["engineer_id"] == ENG


def test_conflicts(client):
    register(client, request("max-ivanov", "+79990000482"))
    # тот же MAX-пользователь с телефоном другого инженера
    assert register(client, request("max-ivanov", "+79990000517")).json()["status"] == "conflict"
    # другой MAX-пользователь с телефоном уже связанного инженера
    data = register(client, request("max-stranger", "+79990000482")).json()
    assert data["status"] == "conflict" and data["engineer"] is None


def test_inactive_engineer_rejected(client):
    login(client)
    client.patch(f"/api/v1/engineers/{ENG}", json={"is_active": False})
    data = register(client, request("max-ivanov", "+79990000482")).json()
    assert data["status"] == "rejected" and data["assignment"] is None


def test_unknown_phone_goes_to_review_and_dispatcher_resolves(client):
    body = request("max-newbie", "+79991234567", key="registration:max-newbie:1")
    data = register(client, body).json()
    assert data["status"] == "pending_review" and data["engineer"] is None

    login(client)
    pending = client.get("/api/v1/registrations?status=pending_review").json()
    assert [r["max_user_id"] for r in pending] == ["max-newbie"]
    reg_id = pending[0]["registration_id"]
    resolved = client.post(f"/api/v1/registrations/{reg_id}/resolve", json={"engineer_id": "ENG-00003"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "registered"
    assert client.post(f"/api/v1/registrations/{reg_id}/resolve", json={"engineer_id": "ENG-00003"}).status_code == 409

    identity = client.get("/api/v1/integration/assignments/bot-users/max-newbie", headers=read_headers()).json()
    assert identity["engineer_id"] == "ENG-00003"
    # повтор исходного запроса из DG теперь отдаёт актуальный результат
    assert register(client, body).json()["status"] == "registered"


def test_dispatcher_rejects_request(client):
    register(client, request("max-spam", "+79995550000"))
    login(client)
    reg_id = client.get("/api/v1/registrations?status=pending_review").json()[0]["registration_id"]
    rejected = client.post(f"/api/v1/registrations/{reg_id}/reject", json={"reason": "Не сотрудник ДРТ"})
    assert rejected.json()["status"] == "rejected"


def test_dg_default_mock_path_is_supported(client):
    response = register(client, request("max-ivanov", "+79990000482"), path="/mock/crm/bot-users/registrations")
    assert response.status_code == 200 and response.json()["status"] == "registered"


def test_bad_phone_is_422(client):
    assert register(client, request("max-x", "1234567890ab")).status_code == 422
