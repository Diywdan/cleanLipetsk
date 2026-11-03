"""Маршрут дела: те же переходы, что во фронте (workflow.ts), и ответ в форме IIncident."""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import EXEC_DDHIB, EXEC_EKOPROM, canonical_event, login, pair, post_event

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PHOTO = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
INCIDENT_KEYS = {"id", "status", "source", "priority", "location", "kp", "responsibles", "timeline", "media"}


def as_user(client: TestClient, username: str, password: str, roles: list[str], executor_id: str | None = None):
    login(client)
    body = {"username": username, "password": password, "roles": roles, "executor_id": executor_id}
    assert client.post("/api/v1/users", json=body).status_code == 201
    other = TestClient(client.app)
    login(other, username, password)
    return other


@pytest.fixture
def world(client):
    """Дело ДДХиБ из бота, инспектор и мастер ДДХиБ."""
    pair(client)
    assert post_event(client, canonical_event()).status_code == 202
    inspector = as_user(client, "insp", "inspector-pass-1", ["inspector"])
    master = as_user(client, "master", "uk-master-pass-1", ["uk_master"], EXEC_DDHIB)
    case_id = inspector.get("/api/v1/incidents").json()[0]["id"]
    return inspector, master, case_id


def act(user, case_id, action, body=None):
    return user.post(f"/api/v1/incidents/{case_id}/{action}", json=body if body is not None else {})


def report_body(**extra):
    return {"report": {"photoUrl": PHOTO, "takenAt": "2026-10-13T10:00:00Z", "coords": [39.5901, 52.6101], **extra}}


def test_incident_shape_matches_frontend(world):
    inspector, _, case_id = world
    incident = inspector.get(f"/api/v1/incidents/{case_id}").json()
    assert INCIDENT_KEYS <= set(incident)
    assert incident["status"] == "NEW" and incident["source"] == "INSPECTION" and incident["priority"] == "MEDIUM"
    assert incident["location"] == {"address": "Липецк, ул. Тестовая, 1", "coordinates": [39.59, 52.61], "upravaId": 1}
    assert incident["responsibles"][0]["organization"] == {"id": EXEC_DDHIB, "name": "ДДХиБ", "kind": "OMSU"}
    assert incident["kp"] is None and incident["media"]["boundingBoxes"] == []
    history = incident["timeline"]["history"]
    assert [h["title"] for h in history] == ["Нарушение зафиксировано"] and history[0]["type"] == "INSPECTOR"
    assert "deadlineAt" not in incident["timeline"]  # пустые поля не отдаются, как undefined во фронте


def test_full_route_to_closed(world):
    inspector, master, case_id = world
    confirmed = act(inspector, case_id, "confirm", {"deadlineHours": 48}).json()
    assert confirmed["status"] == "IN_PROGRESS"
    timeline = confirmed["timeline"]
    hours = (datetime.fromisoformat(timeline["deadlineAt"]) - datetime.fromisoformat(timeline["validatedAt"]))
    assert hours == timedelta(hours=48)
    assert timeline["history"][-1]["description"] == (
        "Инцидент подтвержден. Исполнитель: ДДХиБ; срок устранения — 48 ч."
    )

    reported = act(master, case_id, "report", report_body(comment="Убрано")).json()
    assert reported["status"] == "VERIFICATION"
    report = reported["media"]["report"]
    # пересчитано на сервере: 0,0001° по широте ≈ 11 м, по долготе на 52,6° ≈ 7 м
    assert report["distanceM"] == 13 and report["comment"] == "Убрано"
    assert reported["media"]["photoAfterUrl"] == report["photoUrl"]
    assert reported["timeline"]["history"][-1]["type"] == "UK"
    photo = master.get(report["photoUrl"])
    assert photo.status_code == 200 and photo.content == JPEG and photo.headers["content-type"] == "image/jpeg"

    closed = act(inspector, case_id, "approve").json()
    assert closed["status"] == "CLOSED" and closed["timeline"]["resolution"] == "FIXED"
    assert [h["title"] for h in closed["timeline"]["history"]] == [
        "Нарушение зафиксировано", "Нарушение подтверждено", "Фотоотчёт исполнителя", "Дело закрыто"]


def test_return_keeps_deadline(world):
    inspector, master, case_id = world
    deadline = act(inspector, case_id, "confirm", {"deadlineHours": 24}).json()["timeline"]["deadlineAt"]
    act(master, case_id, "report", report_body())
    returned = act(inspector, case_id, "return", {"comment": "Мусор у бака остался"}).json()
    assert returned["status"] == "IN_PROGRESS" and returned["timeline"]["deadlineAt"] == deadline
    assert returned["timeline"]["history"][-1]["description"] == "Мусор у бака остался"


def test_dismiss_closes_as_false_positive(world):
    inspector, _, case_id = world
    closed = act(inspector, case_id, "dismiss", {"reason": "На месте чисто"}).json()
    assert closed["status"] == "CLOSED" and closed["timeline"]["resolution"] == "FALSE_POSITIVE"
    assert closed["timeline"]["history"][-1]["description"] == "Сигнал не подтверждён: На месте чисто."


def test_roles_and_statuses(world):
    inspector, master, case_id = world
    denied = act(master, case_id, "confirm", {"deadlineHours": 24})
    assert denied.status_code == 403 and denied.json()["message"] == "Действие недоступно для вашей роли"
    wrong = act(inspector, case_id, "approve")
    assert wrong.status_code == 409 and wrong.json()["message"] == "Действие недоступно в текущем статусе дела"
    act(inspector, case_id, "confirm", {"deadlineHours": 24})
    assert act(inspector, case_id, "report", report_body()).status_code == 403  # отчёт — дело исполнителя
    bad = act(inspector, case_id, "confirm", {"deadlineHours": 5})
    assert bad.status_code == 422 and bad.json()["message"].startswith("Неверные данные")


def test_master_sees_only_own_organization(client, world):
    _, master, case_id = world
    other = as_user(client, "eco", "ekoprom-pass-1", ["uk_master"], EXEC_EKOPROM)
    assert other.get("/api/v1/incidents").json() == []
    assert other.get(f"/api/v1/incidents/{case_id}").status_code == 404
    assert len(master.get("/api/v1/incidents").json()) == 1


def test_escalation_by_deadline(world):
    from app import workflow

    inspector, _, case_id = world
    act(inspector, case_id, "confirm", {"deadlineHours": 24})
    early = act(inspector, case_id, "escalate")
    assert early.status_code == 409 and early.json()["message"] == "Срок устранения ещё не истёк"
    assert workflow.escalate_overdue(datetime.now(UTC) + timedelta(hours=23)) == 0
    assert workflow.escalate_overdue(datetime.now(UTC) + timedelta(hours=25)) == 1
    escalated = inspector.get(f"/api/v1/incidents/{case_id}").json()
    assert escalated["status"] == "KNM_ESCALATION" and escalated["timeline"]["history"][-1]["type"] == "SYSTEM"
    # The KNM package is generated through document-service only after the case
    # is linked to a document-service event; escalation itself does not create it.
    acted = act(inspector, case_id, "act")
    assert acted.status_code == 409
    assert acted.json()["detail"] == "Мероприятие сервиса документов ещё не связано с делом"
    still_escalated = inspector.get(f"/api/v1/incidents/{case_id}").json()
    assert still_escalated["status"] == "KNM_ESCALATION"
    assert still_escalated["timeline"]["history"][-1]["title"] == "Срок истёк"


def test_fixed_deadline_by_source(world):
    from app.db import session_scope
    from app.models import Case

    inspector, _, case_id = world
    with session_scope() as db:
        db.get(Case, int(case_id)).source = "GOVERNOR_PORTAL"
    timeline = act(inspector, case_id, "confirm", {"deadlineHours": 24}).json()["timeline"]
    delta = datetime.fromisoformat(timeline["deadlineAt"]) - datetime.fromisoformat(timeline["validatedAt"])
    assert delta == timedelta(hours=72)  # портал губернатора — 3 дня, выбор инспектора не действует


def test_confirm_fixes_mismatched_executor(client):
    pair(client)
    # бот прислал Экопром на «Ямы» — инспектор правит исполнителя при подтверждении
    post_event(client, canonical_event(violation__executor={"executor_id": EXEC_EKOPROM, "name": "Экопром"}))
    inspector = as_user(client, "insp", "inspector-pass-1", ["inspector"])
    incident = inspector.get("/api/v1/incidents").json()[0]
    assert incident["reviewReason"] and incident["responsibles"][0]["confirmed"] is False
    assert act(inspector, incident["id"], "confirm", {"deadlineHours": 24, "executorId": "EXEC-0003"}).status_code == 422
    fixed = act(inspector, incident["id"], "confirm", {"deadlineHours": 24, "executorId": EXEC_DDHIB}).json()
    assert fixed["reviewReason"] is None and fixed["responsibles"][0]["organization"]["id"] == EXEC_DDHIB
    assert "исполнитель: АО «ЭКОПРОМ-ЛИПЕЦК» → ДДХиБ" in fixed["timeline"]["history"][-1]["description"]


def test_confirm_as_is_accepts_mismatch(client):
    pair(client)
    post_event(client, canonical_event(violation__executor={"executor_id": EXEC_EKOPROM, "name": "Экопром"}))
    inspector = as_user(client, "insp", "inspector-pass-1", ["inspector"])
    case_id = inspector.get("/api/v1/incidents").json()[0]["id"]
    confirmed = act(inspector, case_id, "confirm", {"deadlineHours": 24}).json()
    assert confirmed["reviewReason"] is None and confirmed["responsibles"][0]["confirmed"] is True
    assert confirmed["responsibles"][0]["organization"]["id"] == EXEC_EKOPROM
    assert "Расхождение со справочниками принято инспектором." in confirmed["timeline"]["history"][-1]["description"]


def test_upload_then_report_by_url(world):
    inspector, master, case_id = world
    act(inspector, case_id, "confirm", {"deadlineHours": 24})
    uploaded = master.post("/api/v1/files", files={"file": ("after.jpg", JPEG, "image/jpeg")})
    assert uploaded.status_code == 201
    url = uploaded.json()["url"]
    body = {"report": {"photoUrl": url, "takenAt": "2026-10-13T10:00:00Z"}}
    reported = act(master, case_id, "report", body).json()
    assert reported["media"]["photoAfterUrl"] == url and "distanceM" not in reported["media"]["report"]
    assert "место съёмки не определено" in reported["timeline"]["history"][-1]["description"]
    fake = master.post("/api/v1/files", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert fake.status_code == 422
    assert inspector.post("/api/v1/files", files={"file": ("a.jpg", JPEG, "image/jpeg")}).status_code == 403


def test_far_photo_is_flagged(world):
    inspector, master, case_id = world
    act(inspector, case_id, "confirm", {"deadlineHours": 24})
    far = act(master, case_id, "report", report_body(coords=[39.60, 52.62])).json()
    assert far["media"]["report"]["distanceM"] > 150
    assert "проверьте, что снято на месте" in far["timeline"]["history"][-1]["description"]
