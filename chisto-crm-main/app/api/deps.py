from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import User
from app.security import SESSION_COOKIE, bearer_matches, read_session


def require_dg_read(authorization: str | None = Header(default=None)) -> None:
    if not bearer_matches(authorization, get_settings().dg_read_token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid integration token")


def require_dg_write(authorization: str | None = Header(default=None)) -> None:
    if not bearer_matches(authorization, get_settings().dg_write_token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid integration token")


def current_user(request: Request, db: Session = Depends(get_session)) -> User:
    data = read_session(request.cookies.get(SESSION_COOKIE), get_settings().session_secret.get_secret_value())
    user = db.get(User, data["uid"]) if data else None
    if user is None or not user.is_active or user.session_version != data.get("ver"):
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


def require(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_user)) -> User:
        if permission not in user.permission_codes:
            raise HTTPException(status_code=403, detail=f"Нет права {permission}")
        return user

    return dependency
