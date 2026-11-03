"""Управление пользователями и сессиями: раздел администратора.

Заводить операторов и менять им пароли можно из интерфейса — раньше для
этого требовался доступ к командной строке сервера.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import Inspector, Role, User, UserRole, UserSession
from app.services import audit, auth
from app.web import forms
from app.web.auth import current_user
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui-users"])

BACK = "/ui/users"


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    ok: str | None = None,
    err: str | None = None,
    user: User = Depends(current_user),
) -> HTMLResponse:
    users = list(db.scalars(select(User).order_by(User.id)))
    sessions = list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > auth.now(),
            )
            .order_by(UserSession.last_seen_at.desc().nullslast())
        )
    )
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "users": users,
            "roles": list(db.scalars(select(Role).order_by(Role.id))),
            "inspectors": list(
                db.scalars(
                    select(Inspector)
                    .where(Inspector.is_active.is_(True))
                    .order_by(Inspector.full_name)
                )
            ),
            # Текущая связь учётной записи с сотрудником.
            "inspector_by_user": {
                linked.user_id: linked.id
                for linked in db.scalars(
                    select(Inspector).where(Inspector.user_id.is_not(None))
                )
            },
            "sessions": sessions,
            "ok": ok,
            "err": err,
        },
    )


@router.post("/users")
async def create_user(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = (forms.clean(form.get("email")) or "").lower()
    full_name = forms.clean(form.get("full_name"))
    password = str(form.get("password") or "")
    role_code = forms.clean(form.get("role_code")) or "inspector"

    if not email or not full_name:
        return RedirectResponse(f"{BACK}?err=Укажите ФИО и почту", status_code=303)
    if len(password) < 8:
        return RedirectResponse(
            f"{BACK}?err=Пароль должен быть не короче 8 символов", status_code=303
        )
    if db.scalar(select(User).where(User.email == email)) is not None:
        return RedirectResponse(
            f"{BACK}?err=Пользователь с такой почтой уже есть", status_code=303
        )

    user = User(
        full_name=full_name,
        email=email,
        position=forms.clean(form.get("position")),
        phone=forms.clean(form.get("phone")),
        password_hash=auth.hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = auth.grant_role(db, user, role_code)
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="users",
        entity_id=user.id,
        action="create",
        comment=f"создан пользователь {full_name} ({email}), роль {role_code}",
    )
    db.commit()
    return RedirectResponse(
        f"{BACK}?ok=Пользователь {full_name} создан"
        + ("" if role is not None else " (роль не найдена)"),
        status_code=303,
    )


@router.post("/users/{user_id}/password")
async def set_password(
    user_id: int, request: Request, db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        return RedirectResponse(f"{BACK}?err=Пользователь не найден", status_code=303)
    form = await request.form()
    password = str(form.get("password") or "")
    if len(password) < 8:
        return RedirectResponse(
            f"{BACK}?err=Пароль должен быть не короче 8 символов", status_code=303
        )
    user.password_hash = auth.hash_password(password)
    # Старые сессии отзываем: смена пароля должна закрывать доступ.
    for session in db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
        )
    ):
        session.revoked_at = auth.now()
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="users",
        entity_id=user_id,
        action="password",
        comment=f"сменён пароль пользователя {user.full_name}",
    )
    db.commit()
    return RedirectResponse(
        f"{BACK}?ok=Пароль изменён, сессии пользователя закрыты", status_code=303
    )


@router.post("/users/{user_id}/active")
async def toggle_active(
    user_id: int, request: Request, db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        return RedirectResponse(f"{BACK}?err=Пользователь не найден", status_code=303)
    form = await request.form()
    user.is_active = (forms.clean(form.get("is_active")) or "") == "1"
    if not user.is_active:
        for session in db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        ):
            session.revoked_at = auth.now()
    state = "включён" if user.is_active else "заблокирован"
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="users",
        entity_id=user_id,
        action="unblock" if user.is_active else "block",
        comment=f"пользователь {user.full_name} {state}",
    )
    db.commit()
    return RedirectResponse(f"{BACK}?ok=Пользователь {state}", status_code=303)


@router.post("/users/{user_id}/inspector")
async def set_user_inspector(
    user_id: int, request: Request, db: Session = Depends(get_db)
):
    """Связывает учётную запись с сотрудником из справочника инспекторов.

    Связь хранится в карточке инспектора (`inspectors.user_id`): через неё
    определяется участок и, значит, какие заявки сотруднику видны.
    """

    user = db.get(User, user_id)
    if user is None:
        return RedirectResponse(f"{BACK}?err=Пользователь не найден", status_code=303)

    form = await request.form()
    inspector_id = forms.parse_int(form.get("inspector_id"))

    # Снимаем прежнюю связь и ставим новую: у сотрудника одна учётная запись.
    for linked in db.scalars(
        select(Inspector).where(Inspector.user_id == user_id)
    ):
        if inspector_id is None or linked.id != inspector_id:
            linked.user_id = None

    inspector = db.get(Inspector, inspector_id) if inspector_id else None
    if inspector is not None:
        inspector.user_id = user_id

    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="users",
        entity_id=user_id,
        action="update",
        comment=(
            f"пользователь {user.full_name} связан с сотрудником "
            f"{inspector.full_name}"
            if inspector
            else f"связь пользователя {user.full_name} с сотрудником снята"
        ),
    )
    db.commit()
    return RedirectResponse(f"{BACK}?ok=Связь с сотрудником сохранена", status_code=303)


@router.post("/users/{user_id}/roles")
async def add_role(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        return RedirectResponse(f"{BACK}?err=Пользователь не найден", status_code=303)
    form = await request.form()
    code = forms.clean(form.get("role_code")) or ""
    role = auth.grant_role(db, user, code)
    if role is not None:
        audit.record(
            db,
            actor=getattr(request.state, "user", None),
            entity_table="users",
            entity_id=user_id,
            action="role_grant",
            comment=f"пользователю {user.full_name} выдана роль {role.name}",
        )
    db.commit()
    if role is None:
        return RedirectResponse(f"{BACK}?err=Роль не найдена", status_code=303)
    return RedirectResponse(f"{BACK}?ok=Роль {role.name} выдана", status_code=303)


@router.post("/users/{user_id}/roles/{link_id}/delete")
async def remove_role(
    user_id: int,
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    link = db.get(UserRole, link_id)
    if link is not None and link.user_id == user_id:
        role_name = link.role.name if link.role else str(link.role_id)
        db.delete(link)
        audit.record(
            db,
            actor=getattr(request.state, "user", None),
            entity_table="users",
            entity_id=user_id,
            action="role_revoke",
            comment=f"снята роль {role_name}",
        )
        db.commit()
        return RedirectResponse(f"{BACK}?ok=Роль снята", status_code=303)
    return RedirectResponse(f"{BACK}?err=Роль не найдена", status_code=303)


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: int, request: Request, db: Session = Depends(get_db)
):
    session = db.get(UserSession, session_id)
    if session is None:
        return RedirectResponse(f"{BACK}?err=Сессия не найдена", status_code=303)
    session.revoked_at = auth.now()
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="user_sessions",
        entity_id=session_id,
        action="session_revoke",
        comment=(
            "закрыта сессия пользователя "
            f"{session.user.full_name if session.user else session.user_id}"
        ),
    )
    db.commit()
    return RedirectResponse(f"{BACK}?ok=Сессия закрыта", status_code=303)
