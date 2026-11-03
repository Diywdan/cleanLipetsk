from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_session, utc_now
from app.domain import audit, user_view
from app.models import User
from app.schemas import LoginInput
from app.security import SESSION_COOKIE, hash_password, sign_session, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["Вход"])

# Хеш-пустышка: при неизвестном логине проверка длится столько же, сколько при известном.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.post("/login", status_code=204)
def login(body: LoginInput, response: Response, db: Session = Depends(get_session)) -> None:
    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    settings = get_settings()
    user.last_login_at = utc_now()
    audit(db, user.username, "auth.login", "user", str(user.id))
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user.id, user.session_version, settings.session_secret.get_secret_value(),
                     settings.session_ttl_seconds),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_view(user)
