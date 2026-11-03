"""Приём событий от DG: подпись, сопряжение, идемпотентность, разбор в дело."""

import json
from datetime import UTC, datetime, timedelta

from conftest import (
    ENG,
    EXEC_EKOPROM,
    SIGNING_SECRET,
    TYPE_POTHOLES,
    canonical_event,
    envelope,
    login,
    pair,
    post_event,
    read_headers,
    signed,
    write_headers,
)

URL = "/api/v1/integrations/datagateway/events"


def test_not_configured_is_503(client):
    assert post_event(client, canonical_event()).status_code == 503


def test_configure_needs_write_token(client):
    body = {"consumer_key": "drt-crm", "webhook_signing_secret": SIGNING_SECRET}
    assert client.post("/api/v1/integrations/datagateway/configure", headers=read_headers(), json=body).status_code == 401
    pair(client)
    login(client)
    status = client.get("/api/v1/integration/datagateway").json()
    assert status["configured"] is True and status["consumer_key"] == "drt-crm"


def test_accepted_event_becomes_new_case(client):
    pair(client)
    event = canonical_event()
    response = post_event(client, event)
    assert response.status_code == 202, response.text
    assert response.json() == {"event_id": event["id"], "receipt_id": event["id"], "status": "accepted",
                               "duplicate": False}
    login(client)
    cases = client.get("/api/v1/cases").json()
    assert cases["total"] == 1
    case = cases["items"][0]
    assert case["status"] == "NEW" and case["engineer_id"] == ENG and case["type_violation_id"] == TYPE_POTHOLES
    assert case["address"] == "Липецк, ул. Тестовая, 1" and case["reported_at"].startswith("2026-10-13T08:00:00")
    event_row = client.get(f"/api/v1/events/{event['id']}").json()
    assert event_row["status"] == "PROCESSED" and event_row["canonical"]["id"] == event["id"]
    assert client.get("/api/v1/integration/datagateway").json()["last_delivery_at"] is not None


def test_duplicate_and_conflicting_payload(client):
    pair(client)
    event = canonical_event()
    assert post_event(client, event).status_code == 202
    again = post_event(client, event)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    changed = canonical_event(event["id"], violation__comment="Другой текст")
    assert post_event(client, changed).status_code == 409
    login(client)
    assert client.get(f"/api/v1/events/{event['id']}").json()["duplicate_count"] == 1
    assert client.get("/api/v1/cases").json()["total"] == 1


def test_mismatch_with_references_goes_to_review(client):
    pair(client)
    # Экопром не отвечает за ямы — дело заводится NEW с пометкой, решает инспектор
    event = canonical_event(violation__executor={"executor_id": EXEC_EKOPROM, "name": "Экопром"})
    assert post_event(client, event).status_code == 202
    login(client)
    case = client.get("/api/v1/cases").json()["items"][0]
    assert case["status"] == "NEW"
    assert "исполнитель не отвечает за этот тип нарушения" in case["review_reason"]
    assert client.get(f"/api/v1/events/{event['id']}").json()["status"] == "NEEDS_REVIEW"


def test_signature_failures(client):
    pair(client)
    event = canonical_event()
    assert post_event(client, event, secret="x" * 40).status_code == 401
    assert post_event(client, event, consumer="someone-else").status_code == 401
    old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    assert post_event(client, event, timestamp=old).status_code == 401
    assert post_event(client, event, timestamp="not-a-date").status_code == 401
    raw = json.dumps(envelope(event)).encode()
    headers = signed(raw, event["id"])
    del headers["X-DG-Signature"]
    assert client.post(URL, content=raw, headers=headers).status_code == 401


def test_identifier_mismatch_is_422(client):
    pair(client)
    event = canonical_event()
    raw = json.dumps(envelope(event)).encode()
    headers = {**signed(raw, event["id"]), "Idempotency-Key": "something-else"}
    assert client.post(URL, content=raw, headers=headers).status_code == 422
    broken = envelope(event)
    broken["canonical"]["schema_version"] = "2.0"
    raw = json.dumps(broken).encode()
    assert client.post(URL, content=raw, headers=signed(raw, event["id"])).status_code == 422


def test_env_secret_works_without_pairing(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("CRM_DG_WEBHOOK_SIGNING_SECRET", SIGNING_SECRET)
    get_settings.cache_clear()
    assert post_event(client, canonical_event()).status_code == 202


def test_pending_events_are_picked_up(client):
    """Событие записано, а разбор не случился (сбой) — фоновый проход его доберёт."""
    from app import inbox
    from app.db import session_scope
    from app.models import IncomingEvent
    from app.schemas import DataGatewayEventEnvelope

    env = DataGatewayEventEnvelope.model_validate(envelope(canonical_event()))
    with session_scope() as db:
        inbox.save_envelope(db, env)
    assert inbox.process_pending() == 1
    with session_scope() as db:
        assert db.get(IncomingEvent, str(env.event_id)).status == "PROCESSED"
    assert inbox.process_pending() == 0
    _ = write_headers
