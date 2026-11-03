from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

READ_TOKEN = "read-token-for-tests-that-is-longer-than-32-characters"
WRITE_TOKEN = "write-token-for-tests-that-is-longer-than-32-characters"
SIGNING_SECRET = "signing-secret-for-tests-that-is-longer-than-32-characters"
SESSION_SECRET = "session-secret-for-tests-that-is-longer-than-32-characters"
ADMIN = ("crm-admin", "admin-password-123")

# Демо-данные seed_demo: первый инженер, его назначение, ДДХиБ и «Ямы».
ENG, ASG, TERR = "ENG-00001", "ASG-000001", "TERR-001"
EXEC_DDHIB, TYPE_POTHOLES = "EXEC-0001", "VIOLATION-0001"
EXEC_EKOPROM = "EXEC-0002"


def _reset() -> None:
    from app.config import get_settings
    from app.db import reset_caches

    get_settings.cache_clear()
    reset_caches()


def _database_url(tmp_path) -> str:
    """По умолчанию SQLite во временной папке; CRM_TEST_DATABASE_URL — прогон на PostgreSQL."""
    url = os.environ.get("CRM_TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{(tmp_path / 'crm.db').as_posix()}"
    engine = sa.create_engine(url)
    with engine.begin() as connection:  # каждый тест начинается с пустой схемы
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()
    return url


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    env = {
        "CRM_DATABASE_URL": _database_url(tmp_path),
        "CRM_DG_READ_TOKEN": READ_TOKEN,
        "CRM_DG_WRITE_TOKEN": WRITE_TOKEN,
        "CRM_SESSION_SECRET": SESSION_SECRET,
        "CRM_ADMIN_USERNAME": ADMIN[0],
        "CRM_ADMIN_PASSWORD": ADMIN[1],
        "CRM_INBOX_INTERVAL_SECONDS": "0",
        "CRM_FILES_DIR": str(tmp_path / "files"),
        "CRM_SEED_DEMO": "true",
        "CRM_DG_WEBHOOK_SIGNING_SECRET": "",
        # The developer .env may point at a running document-service. Unit tests
        # keep the integration disabled unless a test explicitly configures it.
        "CRM_DOCUMENT_SERVICE_URL": "",
        "CRM_DOCUMENT_SERVICE_PUBLIC_URL": "",
        "CRM_DOCUMENT_SERVICE_TOKEN": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _reset()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    _reset()


def read_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {READ_TOKEN}"}


def write_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {WRITE_TOKEN}"}


def login(client: TestClient, username: str = ADMIN[0], password: str = ADMIN[1]) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 204, response.text


def canonical_event(event_id: str | None = None, **override) -> dict:
    current = event_id or str(uuid4())
    event = {
        "schema": "datagateway.violation",
        "schema_version": "1.0",
        "id": current,
        "event_type": "violation",
        "timestamps": {
            "reported_at": "2026-10-13T08:00:00Z",
            "received_at": "2026-10-13T08:01:00Z",
            "processed_at": "2026-10-13T08:02:00Z",
        },
        "source": {"type": "max_bot", "external_id": f"max-{current}"},
        "reporter": {"engineer_id": ENG, "name": "Иванов Иван Иванович"},
        "assignment": {
            "id": ASG,
            "territory_id": TERR,
            "territory_validation": {"status": "completed", "is_inside": True, "distance_to_boundary_meters": 0},
        },
        "violation": {
            "executor": {"executor_id": EXEC_DDHIB, "name": "ДДХиБ"},
            "type": {"type_violation_id": TYPE_POTHOLES, "name": "Ямы", "selected_by": "inspector"},
            "comment": "Яма у подъезда",
        },
        "location": {
            "coordinates": {"latitude": 52.61, "longitude": 39.59},
            "accuracy_meters": 5,
            "address": {"formatted": "Липецк, ул. Тестовая, 1"},
        },
        "media": [],
        "validation": {
            "engineer_valid": True,
            "executor_valid": True,
            "violation_type_valid": True,
            "executor_violation_relation_valid": True,
            "assignment_valid": True,
        },
        "enrichment": {"geo": {"status": "completed"}, "references": {"status": "completed"}, "ai": {"status": "not_checked"}},
        "deduplication": {"status": "checked", "is_possible_duplicate": False, "matches": []},
        "quality": {"score": 0.9, "checks": {"has_location": True}, "warnings": []},
        "processing": {"trace_id": f"trace-{current}", "status": "completed"},
    }
    for path, value in override.items():
        node = event
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return event


def envelope(event: dict) -> dict:
    return {
        "event_id": event["id"],
        "event_type": "violation",
        "source": "max_bot",
        "source_event_id": event["source"]["external_id"],
        "canonical": event,
        "emitted_at": "2026-10-13T08:03:00Z",
    }


def signed(raw: bytes, event_id: str, *, secret: str = SIGNING_SECRET, timestamp: str | None = None,
           consumer: str = "drt-crm") -> dict[str, str]:
    ts = timestamp or datetime.now(UTC).isoformat()
    sig = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Idempotency-Key": event_id,
        "X-DG-Event-Id": event_id,
        "X-DG-Consumer-Key": consumer,
        "X-DG-Timestamp": ts,
        "X-DG-Signature": f"sha256={sig}",
    }


def pair(client: TestClient) -> None:
    response = client.post(
        "/api/v1/integrations/datagateway/configure",
        headers=write_headers(),
        json={"consumer_key": "drt-crm", "webhook_signing_secret": SIGNING_SECRET,
              "datagateway_url": "http://datagateway:8000"},
    )
    assert response.status_code == 200, response.text


def post_event(client: TestClient, event: dict, **sign_kwargs):
    raw = json.dumps(envelope(event), ensure_ascii=False).encode()
    return client.post("/api/v1/integrations/datagateway/events", content=raw,
                       headers=signed(raw, event["id"], **sign_kwargs))
