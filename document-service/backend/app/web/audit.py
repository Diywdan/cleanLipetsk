"""Журнал действий: раздел администратора.

Показывает, кто создавал и менял заявки, собирал пакеты документов и правил
справочники — в системе с персональными данными это обязательная часть.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import AuditLog, User
from app.services import audit
from app.web.auth import current_user
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui-audit"])

PAGE_SIZE = 100


@router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    db: Session = Depends(get_db),
    action: str | None = None,
    entity_table: str | None = None,
    actor_id: int | None = None,
    user: User = Depends(current_user),
) -> HTMLResponse:
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(PAGE_SIZE)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_table:
        query = query.where(AuditLog.entity_table == entity_table)
    if actor_id:
        query = query.where(AuditLog.actor_user_id == actor_id)

    entries = list(db.scalars(query))
    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "entries": entries,
            "actions": sorted(set(db.scalars(select(AuditLog.action)))),
            "entities": sorted(set(db.scalars(select(AuditLog.entity_table)))),
            "users": list(db.scalars(select(User).order_by(User.full_name))),
            "action_titles": audit.ACTION_TITLES,
            "entity_titles": audit.ENTITY_TITLES,
            "filter_action": action,
            "filter_entity": entity_table,
            "filter_actor": actor_id,
            "page_size": PAGE_SIZE,
        },
    )
