"""Кто вошёл и выход — для интерфейса диспетчера.

Вход у нас один на два интерфейса: сессия в куке, которую ставит страница
входа сервиса документов. Интерфейсу диспетчера нужно знать, кто именно
вошёл, — раньше у него в коде была зашита демонстрационная роль.

Роли сопоставляются по правам, а не по названию: в их модели три роли
(инспектор, мастер УК, руководство), и «руководство» у них только смотрит.
Поэтому правящая роль сервиса — инспектор в их терминах, а название нашей
роли отдаётся отдельным полем, чтобы интерфейс показывал его человеку.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import Role, User, UserRole
from app.services import auth


router = APIRouter(tags=["session"])


# Наша роль -> роль в терминах интерфейса диспетчера.
#   INSPECTOR — может действовать по делу;
#   ADMIN — только смотрит.
def dispatch_role(can_edit: bool) -> str:
    return "INSPECTOR" if can_edit else "ADMIN"


def _role_titles(db: Session, user: User) -> tuple[str, str]:
    """Код и название нашей роли: их показывает интерфейс диспетчера."""

    role = db.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
        .order_by(Role.id)
    ).first()
    if role is None:
        return "", ""
    return role.code, role.name


@router.get("/me")
def current_user_info(request: Request, db: Session = Depends(get_db)) -> dict:
    """Кто вошёл: имя, роль и права.

    Интерфейс диспетчера спрашивает это при открытии. Если ответа нет
    (401), он отправляет человека на нашу страницу входа и возвращает
    обратно — поэтому в ответе есть и адрес выхода.
    """

    user: User = request.state.user
    can_edit = auth.can_edit(user)
    code, title = _role_titles(db, user)
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": dispatch_role(can_edit),
        "serviceRole": code,
        "serviceRoleTitle": title,
        "isAdmin": auth.is_administrator(user),
        "canEdit": can_edit,
        "loginUrl": "/ui/login",
        "logoutUrl": "/api/logout",
    }


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Выход из сервиса документов.

    Интерфейс диспетчера — это тот же вход, поэтому выход общий: сессия
    отзывается, кука снимается, и оба интерфейса снова просят войти.
    """

    auth.revoke_session(db, request.cookies.get(auth.SESSION_COOKIE))
    response = JSONResponse({"message": "Вы вышли из сервиса документов"})
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response
