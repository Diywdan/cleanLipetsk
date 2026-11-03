from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import document_service
from app.api.incidents import document_service_event
from app.config import get_settings
from app.db import session_scope
from app.models import Case, CaseHistory
from app.schemas import DocumentServiceGeneratedEvent
from conftest import EXEC_EKOPROM, canonical_event, login, pair, post_event

TOKEN = "document-service-token-for-tests-only"


def _inspector(client: TestClient, username: str = "knm-insp", executor_id: str | None = None):
    login(client)
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "password": "inspector-pass-1",
            "roles": ["inspector"],
            "executor_id": executor_id,
        },
    )
    assert response.status_code == 201, response.text
    inspector = TestClient(client.app)
    login(inspector, username, "inspector-pass-1")
    return inspector


@pytest.fixture
def knm_case(client, monkeypatch):
    from app import kp

    monkeypatch.setattr(kp, "link_case", lambda *_args: None, raising=False)
    pair(client)
    assert post_event(client, canonical_event()).status_code == 202
    inspector = _inspector(client)
    case_id = inspector.get("/api/v1/incidents").json()[0]["id"]
    with session_scope() as db:
        case = db.get(Case, int(case_id))
        case.status = "KNM_ESCALATION"
        case.document_service_case_id = 77
        case.document_service_status = "generated"
    return inspector, int(case_id)


def _generated(case_id: int, *, status: str = "generated") -> dict:
    return {
        "crm_case_id": str(case_id),
        "control_case_id": 77,
        "status": status,
        "readiness": {
            "is_ready": status == "generated",
            "issues": [],
            "warnings": [],
            "missing_templates": [],
        },
        "package": {
            "id": 45,
            "missing_templates": [],
            "documents": [
                {
                    "code": "act",
                    "name": "Акт",
                    "download_url": "/api/documents/901/file",
                },
                {
                    "code": "direction",
                    "name": "Направление предписания",
                    "download_url": "/api/documents/902/file",
                },
            ],
        },
    }


def _callback_payload(case_id: int) -> DocumentServiceGeneratedEvent:
    return DocumentServiceGeneratedEvent(
        event_id="document-package:45:extended",
        crm_case_id=str(case_id),
        document_case_id=77,
        package_id=45,
        package_kind="primary_prescription",
        package_name="Первичное предписание",
        documents_count=6,
        document_codes=["assignment", "decision", "act", "inspection_protocol", "prescription", "direction"],
        document_names=["Задание", "Решение", "Акт", "Протокол осмотра", "Предписание", "Направление предписания"],
        occurred_at=datetime.now(UTC),
    )


def _set_token(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "document_service_token", SecretStr(TOKEN))


def test_continue_uses_crm_case_id_in_route(monkeypatch):
    request = Mock(return_value={
        "crm_case_id": "12",
        "control_case_id": 77,
        "status": "generated",
    })
    monkeypatch.setattr(document_service, "_request", request)

    document_service.continue_knm_package(
        SimpleNamespace(id=12, document_service_case_id=77)
    )

    request.assert_called_once_with(
        "POST",
        "/internal/crm/cases/12/packages/continue",
    )


def test_issue_act_calls_document_service_and_records_one_idempotent_event(knm_case, monkeypatch):
    inspector, case_id = knm_case
    monkeypatch.setattr(
        get_settings(),
        "document_service_public_url",
        "https://documents.example/base",
    )
    continue_package = Mock(return_value=_generated(case_id))
    monkeypatch.setattr(document_service, "continue_knm_package", continue_package)

    first = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})
    second = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "KNM_ESCALATION"
    assert first.json()["knmPackageGenerated"] is True
    expected_package = {
        "status": "generated",
        "packageId": 45,
        "documents": [
            {
                "code": "act",
                "name": "Акт",
                "downloadUrl": "https://documents.example/base/api/documents/901/file",
            },
            {
                "code": "direction",
                "name": "Направление предписания",
                "downloadUrl": "https://documents.example/base/api/documents/902/file",
            },
        ],
    }
    assert first.json()["knmPackage"] == expected_package
    entries = [
        item for item in second.json()["timeline"]["history"]
        if item["title"] == "Пакет №45 сформирован"
    ]
    assert len(entries) == 1
    assert entries[0]["description"] == "Сформирован пакет КНМ №45."
    assert continue_package.call_count == 2
    assert inspector.get(f"/api/v1/incidents/{case_id}").json()["knmPackage"] == expected_package
    listed = inspector.get("/api/v1/incidents").json()
    assert next(item for item in listed if int(item["id"]) == case_id)["knmPackage"] == expected_package
    with session_scope() as db:
        events = db.query(CaseHistory).filter_by(
            case_id=case_id,
            external_event_id="document-package:45:extended",
        ).all()
        assert len(events) == 1
        assert db.get(Case, case_id).document_service_readiness["knm_package"]["package_id"] == 45


def test_knm_package_is_null_before_generation(knm_case):
    inspector, case_id = knm_case

    assert inspector.get(f"/api/v1/incidents/{case_id}").json()["knmPackage"] is None
    listed = inspector.get("/api/v1/incidents").json()
    assert next(item for item in listed if int(item["id"]) == case_id)["knmPackage"] is None


def test_extended_callback_saves_package_without_inventing_download_urls(knm_case, monkeypatch):
    inspector, case_id = knm_case
    _set_token(monkeypatch)

    with session_scope() as db:
        result = document_service_event(
            _callback_payload(case_id),
            authorization=f"Bearer {TOKEN}",
            db=db,
        )
        assert result["accepted"] is True

    expected_codes = ["act", "inspection_protocol", "prescription", "direction"]
    expected_names = ["Акт", "Протокол осмотра", "Предписание", "Направление предписания"]
    detail = inspector.get(f"/api/v1/incidents/{case_id}").json()
    assert detail["knmPackage"] == {
        "status": "generated",
        "packageId": 45,
        "documents": [
            {"code": code, "name": name, "downloadUrl": None}
            for code, name in zip(expected_codes, expected_names)
        ],
    }
    listed = inspector.get("/api/v1/incidents").json()
    assert next(item for item in listed if int(item["id"]) == case_id)["knmPackage"] == detail["knmPackage"]
    with session_scope() as db:
        package = db.get(Case, case_id).document_service_readiness["knm_package"]
        assert package["package_id"] == 45
        assert all("download_path" not in document for document in package["documents"])
        assert "is_ready" not in db.get(Case, case_id).document_service_readiness


def test_extended_callback_same_package_preserves_download_paths(knm_case, monkeypatch):
    inspector, case_id = knm_case
    _set_token(monkeypatch)
    monkeypatch.setattr(document_service, "continue_knm_package", Mock(return_value=_generated(case_id)))
    assert inspector.post(f"/api/v1/incidents/{case_id}/act", json={}).status_code == 200

    with session_scope() as db:
        result = document_service_event(
            _callback_payload(case_id),
            authorization=f"Bearer {TOKEN}",
            db=db,
        )
        assert result["accepted"] is True
        package = db.get(Case, case_id).document_service_readiness["knm_package"]
        assert next(document for document in package["documents"] if document["code"] == "act")[
            "download_path"
        ] == "/api/documents/901/file"
        assert next(document for document in package["documents"] if document["code"] == "direction")[
            "download_path"
        ] == "/api/documents/902/file"


def test_document_service_readiness_sync_is_persisted_and_visible(knm_case, monkeypatch):
    inspector, case_id = knm_case
    readiness = {
        "is_ready": False,
        "issues": [{"field": "act_composed_at", "message": "Не указана дата составления акта"}],
        "warnings": [],
        "missing_templates": [],
    }
    synced_cases = []

    def sync_case(case, document_data=None, check_knm_readiness=False):
        synced_cases.append((case.id, document_data, check_knm_readiness))
        return {
            "crm_case_id": str(case.id),
            "control_case_id": 77,
            "status": "needs_input",
            "readiness": readiness,
        }

    monkeypatch.setattr(document_service, "sync_confirmed_case", sync_case)
    request_body = {"subject": "Проверка по обращению"}
    first = inspector.post(
        f"/api/v1/incidents/{case_id}/document-service/data",
        json=request_body,
    )
    second = inspector.post(
        f"/api/v1/incidents/{case_id}/document-service/data",
        json=request_body,
    )

    assert first.status_code == second.status_code == 200
    assert synced_cases == [
        (case_id, request_body, True),
        (case_id, request_body, True),
    ]
    with session_scope() as db:
        case = db.get(Case, case_id)
        assert case.document_service_readiness == readiness
        assert db.query(CaseHistory).filter_by(
            case_id=case_id,
            action="KNM_PACKAGE_GENERATED",
        ).count() == 0
    detail = inspector.get(f"/api/v1/incidents/{case_id}").json()
    listed = inspector.get("/api/v1/incidents").json()
    assert detail["document_service"]["readiness"] == readiness
    assert next(item for item in listed if int(item["id"]) == case_id)["document_service"]["readiness"] == readiness


def test_document_service_readiness_is_visible_without_status(knm_case):
    inspector, case_id = knm_case
    readiness = {"is_ready": False, "issues": [{"field": "prescription"}]}
    with session_scope() as db:
        case = db.get(Case, case_id)
        case.document_service_status = None
        case.document_service_readiness = readiness

    detail = inspector.get(f"/api/v1/incidents/{case_id}").json()
    listed = inspector.get("/api/v1/incidents").json()
    assert detail["document_service"]["status"] is None
    assert detail["document_service"]["readiness"] == readiness
    assert next(item for item in listed if int(item["id"]) == case_id)["document_service"]["readiness"] == readiness


def test_sso_ticket_contains_only_approved_focus_fields(monkeypatch):
    monkeypatch.setattr(get_settings(), "document_service_public_url", "https://documents.example")
    monkeypatch.setattr(get_settings(), "document_service_token", SecretStr(TOKEN))
    case = SimpleNamespace(id=12, document_service_case_id=77)
    user = SimpleNamespace(id=5, full_name="Инспектор", username="inspector")

    for issue_field, expected_focus in (
        ("act_composed_at", "act_composed_at"),
        ("violations", "violations"),
        ("prescription", "prescription"),
        ("action.3.place", "action_place_address"),
    ):
        ticket = document_service.create_sso_ticket(case, user, issue_field=issue_field)
        header, payload, signature = ticket.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        message = f"{header}.{payload}".encode("ascii")
        expected_signature = hmac.new(TOKEN.encode(), message, hashlib.sha256).digest()
        assert hmac.compare_digest(
            signature,
            base64.urlsafe_b64encode(expected_signature).rstrip(b"=").decode("ascii"),
        )
        assert claims["focus_field"] == expected_focus

    malformed = document_service.create_sso_ticket(
        case,
        user,
        issue_field="action.3.place?selector=body",
    )
    claims = json.loads(base64.urlsafe_b64decode(malformed.split(".")[1] + "=="))
    assert "focus_field" not in claims


def test_download_url_uses_only_configured_public_origin(knm_case, monkeypatch):
    inspector, case_id = knm_case
    monkeypatch.setattr(
        get_settings(),
        "document_service_public_url",
        "https://private:secret@documents.example/base",
    )
    monkeypatch.setattr(
        document_service,
        "continue_knm_package",
        Mock(return_value=_generated(case_id)),
    )

    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 200
    assert all(
        item["downloadUrl"] is None
        for item in response.json()["knmPackage"]["documents"]
    )
    assert "secret" not in response.text


def test_invalid_document_service_download_url_is_rejected(knm_case, monkeypatch):
    inspector, case_id = knm_case
    result = _generated(case_id)
    result["package"]["documents"][0]["download_url"] = "https://attacker.example/file"
    monkeypatch.setattr(document_service, "continue_knm_package", Mock(return_value=result))

    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 502
    assert "ссылку на документ" in response.json()["message"]
    with session_scope() as db:
        assert db.get(Case, case_id).document_service_readiness is None


def test_issue_act_rejects_wrong_status_before_service_call(knm_case, monkeypatch):
    inspector, case_id = knm_case
    with session_scope() as db:
        db.get(Case, case_id).status = "IN_PROGRESS"
    continue_package = Mock()
    monkeypatch.setattr(document_service, "continue_knm_package", continue_package)

    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 409
    continue_package.assert_not_called()


def test_issue_act_returns_readiness_remarks_without_success_event(knm_case, monkeypatch):
    inspector, case_id = knm_case
    result = _generated(case_id, status="needs_input")
    result["readiness"] = {
        "is_ready": False,
        "issues": [{"message": "Не указана дата проведения"}],
        "warnings": [],
        "missing_templates": [],
    }
    result["package"]["missing_templates"] = ["direction"]
    monkeypatch.setattr(
        document_service,
        "continue_knm_package",
        Mock(return_value=result),
    )

    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})
    message = response.json()["message"]

    assert response.status_code == 422
    assert message == "Пакет КНМ не сформирован. Обратите внимание на замечания"
    with session_scope() as db:
        case = db.get(Case, case_id)
        assert case.document_service_status == "needs_input"
        assert case.document_service_readiness["is_ready"] is False
        assert db.query(CaseHistory).filter_by(
            case_id=case_id,
            action="KNM_PACKAGE_GENERATED",
        ).count() == 0


def test_issue_act_reports_service_failure_without_success_event(knm_case, monkeypatch):
    inspector, case_id = knm_case
    monkeypatch.setattr(
        document_service,
        "continue_knm_package",
        Mock(side_effect=RuntimeError("document-service недоступен")),
    )

    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 502
    assert response.json()["message"] == "document-service недоступен"
    with session_scope() as db:
        assert db.query(CaseHistory).filter_by(
            case_id=case_id,
            action="KNM_PACKAGE_GENERATED",
        ).count() == 0


def test_callback_during_continue_converges_on_same_history_event(knm_case, monkeypatch):
    inspector, case_id = knm_case
    _set_token(monkeypatch)

    def continue_with_synchronous_callback(case):
        with session_scope() as db:
            result = document_service_event(
                _callback_payload(case_id),
                authorization=f"Bearer {TOKEN}",
                db=db,
            )
            assert result["accepted"] is True
        return _generated(case_id)

    monkeypatch.setattr(
        document_service,
        "continue_knm_package",
        continue_with_synchronous_callback,
    )
    response = inspector.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 200, response.text
    assert response.json()["knmPackageGenerated"] is True
    assert response.json()["knmPackage"]["packageId"] == 45
    for _ in range(2):
        with session_scope() as db:
            result = document_service_event(
                _callback_payload(case_id),
                authorization=f"Bearer {TOKEN}",
                db=db,
            )
            assert result["duplicate"] is True
    with session_scope() as db:
        assert db.query(CaseHistory).filter_by(
            case_id=case_id,
            external_event_id="document-package:45:extended",
        ).count() == 1
    assert inspector.get(f"/api/v1/incidents/{case_id}").json()["knmPackage"]["packageId"] == 45


def test_issue_act_enforces_case_owner(knm_case, client, monkeypatch):
    _, case_id = knm_case
    outsider = _inspector(client, "other-inspector", EXEC_EKOPROM)
    continue_package = Mock()
    monkeypatch.setattr(document_service, "continue_knm_package", continue_package)

    response = outsider.post(f"/api/v1/incidents/{case_id}/act", json={})

    assert response.status_code == 404
    continue_package.assert_not_called()
