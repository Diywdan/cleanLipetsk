"""Notifications sent from document-service to the linked CRM case."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.models import ControlCase, DocumentPackage


log = logging.getLogger(__name__)


def package_generated(
    case: ControlCase,
    package: DocumentPackage,
    documents_count: int,
    actor_name: str | None = None,
    event_suffix: str = "generated",
) -> None:
    """Notify CRM after a package and its audit entry have been committed."""
    if not settings.crm_event_url or not settings.crm_integration_token:
        log.warning("CRM package event not sent: callback URL or integration token is not configured")
        return
    if not case.crm_case_id:
        log.warning("CRM package event not sent: document case %s is not linked to CRM", case.id)
        return

    occurred_at = datetime.now(timezone.utc)
    if event_suffix != "extended" and package.created_at is not None:
        occurred_at = (
            package.created_at.replace(tzinfo=timezone.utc)
            if package.created_at.tzinfo is None
            else package.created_at
        )

    payload = {
        "event_id": f"document-package:{package.id}:{event_suffix}",
        "crm_case_id": case.crm_case_id,
        "document_case_id": case.id,
        "package_id": package.id,
        "package_kind": package.package_kind.code,
        "package_name": package.package_kind.name,
        "documents_count": documents_count,
        "document_codes": [item.document_type.code for item in package.documents],
        "document_names": [item.document_type.name for item in package.documents],
        "documents": [
            {
                "id": item.id,
                "code": item.document_type.code,
                "name": item.document_type.name,
                "download_url": f"/api/documents/{item.id}/file",
            }
            for item in package.documents
        ],
        "actor_name": actor_name,
        "occurred_at": occurred_at.isoformat(),
    }
    request = Request(
        settings.crm_event_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.crm_integration_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            response.read()
        log.info("Sent generated package event %s to CRM", payload["event_id"])
    except (OSError, URLError, TimeoutError, ValueError):
        # Generation is already committed. Do not turn a temporary CRM outage
        # into a failed document build; the warning keeps the missed callback visible.
        log.exception("Could not send generated package event %s to CRM", payload["event_id"])
