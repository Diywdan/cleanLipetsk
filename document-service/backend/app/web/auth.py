"""Вход оператора в систему: страница входа, сессия в куке, выход.

Все страницы интерфейса защищены зависимостью `current_user`: без живой
сессии браузер переадресуется на форму входа.
"""

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.dependencies import get_db
from app.models import User
from app.services import auth
from app.web import forms
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui-auth"])


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Пускает дальше только вошедшего пользователя (для страниц).

    Здесь же отсекаются изменения от роли «наблюдатель»: смотреть можно,
    менять — нет.
    """

    token = request.cookies.get(auth.SESSION_COOKIE)
    user = auth.resolve_session(db, token)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/ui/login"})
    if request.method not in SAFE_METHODS and not auth.can_edit(user):
        raise HTTPException(
            status_code=303,
            headers={
                "Location": "/ui?err="
                + quote("У вашей роли доступ только для просмотра")
            },
        )
    request.state.user = user
    request.state.is_admin = auth.is_administrator(user)
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """Раздел только для администратора: остальных возвращаем с пояснением.

    Сообщение в заголовке Location кодируем: заголовки HTTP передаются
    в latin-1, и кириллица в них приводит к ошибке сервера.
    """

    if not auth.is_administrator(user):
        raise HTTPException(
            status_code=303,
            headers={
                "Location": "/ui?err="
                + quote("Раздел доступен только администратору")
            },
        )
    return user


def require_session(request: Request, db: Session = Depends(get_db)) -> User:
    """То же для программного интерфейса: отвечает 401, а не переадресацией.

    Переадресация на форму входа имеет смысл в браузере, но не для клиента,
    который ждёт JSON. Текст отдаём в формате интерфейса диспетчера — с полем
    message (см. app/api/errors.py).
    """

    token = request.cookies.get(auth.SESSION_COOKIE)
    user = auth.resolve_session(db, token)
    if user is None:
        raise ApiError(status_code=401, message="Нужно войти в сервис документов")
    if request.method not in SAFE_METHODS and not auth.can_edit(user):
        raise ApiError(
            status_code=403, message="У вашей роли доступ только для просмотра"
        )
    request.state.user = user
    return user


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str | None = None,
    db: Session = Depends(get_db),
    err: str | None = None,
) -> HTMLResponse:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if auth.resolve_session(db, token) is not None:
        return RedirectResponse(safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"err": err, "next": safe_next(next)},
        status_code=200 if not err else 401,
    )


def safe_next(value: str | None) -> str:
    """Куда вернуться после входа.

    Принимаем только путь на своём сервере: открытая переадресация — готовое
    приглашение для фишинга («войдите и вернитесь на чужой сайт»). Адрес
    интерфейса диспетчера (/dispatch/) так тоже проходит.
    """

    if not value or not value.startswith("/") or value.startswith("//"):
        return "/ui"
    return value


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    login_value = forms.clean(form.get("login")) or ""
    password = str(form.get("password") or "")
    back = safe_next(forms.clean(form.get("next")))

    user = auth.authenticate(db, login_value, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"err": "Неверная почта или пароль", "next": back},
            status_code=401,
        )

    client = request.client.host if request.client else None
    session = auth.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client,
    )
    auth.purge_expired(db)

    response = RedirectResponse(back, status_code=303)
    # Флаг Secure выставляется, только когда соединение действительно
    # защищено: по HTTP браузер такую куку не отправит, и вход отвалится.
    # За прокси настоящая схема приходит в X-Forwarded-Proto.
    secure = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    response.set_cookie(
        auth.SESSION_COOKIE,
        session.token,
        httponly=True,
        samesite="lax",
        max_age=int(auth.SESSION_TTL.total_seconds()),
        path="/",
        secure=secure,
    )
    return response


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(auth.SESSION_COOKIE)
    auth.revoke_session(db, token)
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response
