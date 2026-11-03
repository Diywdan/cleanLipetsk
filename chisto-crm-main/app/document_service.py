"""CRM client for the document-service internal API."""

from __future__ import annotations

import logging
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

import httpx

from app.config import get_settings
from app.models import Case, User


log = logging.getLogger("crm.document_service")

# Readiness codes returned by document-service -> input names in its case form.
# Keep this allowlist narrow: CRM may request a field jump, but cannot choose
# an arbitrary URL or DOM selector in the document-service.
READINESS_FIELD_TARGETS = {
    "control_kind": "control_kind_id",
    "control_form": "control_form_id",
    "control_body": "control_body_id",
    "controlled_organization": "controlled_organization_id",
    "control_object": "control_object_id",
    # This detail belongs to the selected object in the DS dictionary, not to
    # a field on the case form. The DS SSO consumer resolves it through the case.
    "control_object.address": "control_object_address",
    "inspectors": "inspector_id",
    "requisites": "controlled_org_inn",
    "requisites.inn": "controlled_org_inn",
    "requisites.legal_address": "controlled_org_legal_address",
    "unit.email": "controlled_org_unit_email",
    "approver": "assignment_approved_by_signatory_id",
    "assignment_date": "assignment_date",
    "planned_start_at": "planned_start_at",
    "planned_end_at": "planned_end_at",
    "actual_start_at": "actual_start_at",
    "actual_end_at": "actual_end_at",
    "actions": "action_type",
    "bases": "basis_kind",
    "decision": "decision_number",
    "decision.decision_date": "decision_date",
    "decision.items": "decision_item_description",
    "act_composed_at": "act_composed_at",
    "violations": "violations",
    "prescription": "prescription",
}


def _readiness_field_target(issue_field: str | None) -> str | None:
    if not issue_field:
        return None
    target = READINESS_FIELD_TARGETS.get(issue_field)
    if target:
        return target
    action_fields = {
        "started_at": "action_started_at",
        "ended_at": "action_ended_at",
        "place": "action_place_address",
    }
    match = re.fullmatch(r"action\.\d+\.(started_at|ended_at|place)", issue_field)
    if match:
        return action_fields[match.group(1)]
    if re.fullmatch(r"violation\.\d+\.provisions", issue_field):
        return "violation_article_ids"
    return None


def create_sso_ticket(
    case: Case,
    user: User,
    issue_field: str | None = None,
    document_id: int | None = None,
) -> str:
    """Sign a short-lived browser handoff ticket for the linked DS case."""
    settings = get_settings()
    secret = settings.document_service_token.get_secret_value()
    if not settings.document_service_public_url or len(secret) < 32:
        raise RuntimeError("Вход в сервис документов не настроен")

    def encode(value: dict) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = encode({"alg": "HS256", "typ": "JWT"})
    issued_at = int(time.time())
    claims = {
        "iss": "chisto-crm",
        "aud": "document-service",
        "sub": str(user.id),
        "name": user.full_name or user.username,
        "crm_case_id": str(case.id),
        "document_case_id": case.document_service_case_id,
        "jti": secrets.token_urlsafe(24),
        "iat": issued_at,
        "exp": issued_at + 90,
    }
    focus_field = _readiness_field_target(issue_field)
    if focus_field:
        claims["focus_field"] = focus_field
    if document_id is not None:
        claims["document_id"] = document_id
    payload = encode(claims)
    message = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _request(method: str, path: str, *, json: dict | None = None) -> dict:
    settings = get_settings()
    if not settings.document_service_url:
        raise RuntimeError("Интеграция с сервисом документов не настроена")
    try:
        response = httpx.request(
            method,
            f"{settings.document_service_url.rstrip('/')}{path}",
            json=json,
            headers={
                "Authorization": f"Bearer {settings.document_service_token.get_secret_value()}"
            },
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        log.exception("document-service request failed: %s %s", method, path)
        raise RuntimeError(f"Ошибка запроса к сервису документов: {error}") from error


def get_case_options(case: Case) -> dict:
    return _request("GET", f"/internal/crm/cases/{case.id}/options")


def sync_confirmed_case(
    case: Case,
    document_data: dict | None = None,
    check_knm_readiness: bool = False,
) -> dict | None:
    """Sync form data, then prepare stage-2 documents or check KNM readiness."""

    settings = get_settings()
    if not settings.document_service_url:
        return None

    payload = {
        "crm_case_id": str(case.id),
        "case_number": f"CRM-{case.id}",
        "address": case.address,
        "latitude": case.latitude,
        "longitude": case.longitude,
        "violation": case.comment,
        "reported_at": case.reported_at.isoformat() if case.reported_at else None,
        "check_knm_readiness": check_knm_readiness,
    }
    if document_data:
        payload.update(document_data)
    return _request("POST", "/internal/crm/cases/sync", json=payload)


def continue_knm_package(case: Case) -> dict:
    """Continue the linked primary package after checking its CRM and DS identities."""
    if not case.document_service_case_id:
        raise RuntimeError("Мероприятие сервиса документов ещё не связано с делом")

    # The route parameter is the CRM case ID stored as ControlCase.crm_case_id,
    # not document_service_case_id (the DS control_case_id).
    result = _request(
        "POST",
        f"/internal/crm/cases/{case.id}/packages/continue",
    )
    if (
        result.get("crm_case_id") != str(case.id)
        or result.get("control_case_id") != case.document_service_case_id
    ):
        raise RuntimeError("Ответ сервиса документов относится к другому мероприятию")
    return result
