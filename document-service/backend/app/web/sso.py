"""One-time browser handoff from CRM into the linked document-service case."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.dependencies import get_db
from app.models import ControlCase, Document, DocumentPackage, SsoLoginTicket, User
from app.services import auth


router = APIRouter(prefix="/ui/sso", tags=["ui-sso"])

FOCUS_FIELDS = {
    "control_kind_id", "control_form_id", "control_body_id",
    "controlled_organization_id", "control_object_id", "inspector_id",
    "assignment_approved_by_signatory_id", "assignment_date",
    "planned_start_at", "planned_end_at", "actual_start_at", "actual_end_at",
    "action_type", "action_started_at", "action_ended_at", "action_place_address",
    "basis_kind", "decision_number", "decision_date", "decision_item_description",
    "violation_article_ids", "prescription",
    "control_object_address",
    "controlled_org_inn", "controlled_org_legal_address",
    "controlled_org_unit_email",
}


def _decode_ticket(token: str) -> dict:
    try:
        header_part, payload_part, signature_part = token.split(".")
        message = f"{header_part}.{payload_part}".encode("ascii")
        expected = hmac.new(
            settings.crm_integration_token.encode(), message, hashlib.sha256
        ).digest()
        supplied = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("bad signature")
        header = json.loads(base64.urlsafe_b64decode(header_part + "=" * (-len(header_part) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4)))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("bad header")
        now = int(auth.now().timestamp())
        if (
            claims.get("iss") != "chisto-crm"
            or claims.get("aud") != "document-service"
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"].isdigit()
            or not isinstance(claims.get("document_case_id"), int)
            or not isinstance(claims.get("crm_case_id"), str)
            or not claims.get("jti")
            or not isinstance(claims.get("iat"), int)
            or not isinstance(claims.get("exp"), int)
            or claims["iat"] > now + 5
            or claims["exp"] <= now
            or claims["exp"] - claims["iat"] > 120
            or ("focus_field" in claims and claims["focus_field"] not in FOCUS_FIELDS)
            or ("document_id" in claims and (not isinstance(claims["document_id"], int) or claims["document_id"] < 1))
        ):
            raise ValueError("invalid claims")
        return claims
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=401, detail="Недействительная или просроченная ссылка входа") from error


@router.post("/consume")
async def consume_ticket(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    token = str(form.get("ticket") or "")
    if not token or len(token) > 4096:
        raise HTTPException(status_code=401, detail="Недействительная ссылка входа")
    claims = _decode_ticket(token)

    case = db.get(ControlCase, claims["document_case_id"])
    if case is None or case.crm_case_id != claims["crm_case_id"]:
        raise HTTPException(status_code=404, detail="Связанное мероприятие не найдено")

    document_id = claims.get("document_id")
    if document_id is not None:
        document = db.scalar(
            select(Document)
            .join(DocumentPackage, Document.package_id == DocumentPackage.id)
            .where(
                Document.id == document_id,
                DocumentPackage.control_case_id == case.id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Документ мероприятия не найден")

    now = auth.now()
    db.execute(delete(SsoLoginTicket).where(SsoLoginTicket.expires_at < now - timedelta(days=1)))
    db.add(
        SsoLoginTicket(
            jti=claims["jti"],
            expires_at=now + timedelta(seconds=120),
        )
    )
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=401, detail="Ссылка входа уже использована") from error

    user = db.scalar(select(User).where(User.crm_user_id == claims["sub"]))
    if user is None:
        user = User(
            crm_user_id=claims["sub"],
            email=f"crm-user-{claims['sub']}@identity.invalid",
            full_name=str(claims.get("name") or f"CRM user {claims['sub']}")[:255],
            password_hash=None,
        )
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись document-service отключена")
    else:
        user.full_name = str(claims.get("name") or user.full_name)[:255]

    if auth.grant_role(db, user, "inspector") is None:
        raise HTTPException(status_code=503, detail="В document-service не настроена роль инспектора")

    client_ip = request.client.host if request.client else None
    session = auth.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip,
        ttl=timedelta(hours=2),
    )
    destination = (
        f"/api/documents/{document_id}/file"
        if document_id is not None
        else f"/ui/cases/{case.id}"
    )
    focus_field = claims.get("focus_field")
    if focus_field == "control_object_address":
        if case.control_object_id is not None:
            destination = f"/ui/dictionaries#f-control-object-address-{case.control_object_id}"
        else:
            destination = f"/ui/cases/{case.id}/edit#f-control_object_id"
    elif focus_field in {"controlled_org_inn", "controlled_org_legal_address"}:
        if case.controlled_organization_id is not None:
            organization = case.controlled_organization
            inn_already_filled = bool(organization is not None and organization.inn)
            field_anchor = (
                "organization-legal-address"
                if focus_field == "controlled_org_legal_address"
                or (focus_field == "controlled_org_inn" and inn_already_filled)
                else "organization-inn"
            )
            destination = (
                f"/ui/dictionaries/organizations/{case.controlled_organization_id}"
                f"#f-{field_anchor}"
            )
        else:
            destination = f"/ui/cases/{case.id}/edit#f-controlled_organization_id"
    elif focus_field == "controlled_org_unit_email":
        if (
            case.controlled_organization_id is not None
            and case.controlled_unit is not None
            and case.controlled_unit.organization_id == case.controlled_organization_id
        ):
            destination = (
                f"/ui/dictionaries/organizations/{case.controlled_organization_id}"
                f"#f-unit-email-{case.controlled_unit_id}"
            )
        else:
            destination = f"/ui/cases/{case.id}/edit#f-controlled_unit_id"
    elif focus_field:
        destination = f"/ui/cases/{case.id}/edit#f-{focus_field}"
    response = RedirectResponse(destination, status_code=303)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        auth.SESSION_COOKIE,
        session.token,
        httponly=True,
        samesite="lax",
        max_age=2 * 60 * 60,
        path="/",
        secure=secure,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
