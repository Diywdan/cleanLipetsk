from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import inbox, workflow
from app.api import admin, auth, incidents, integration, kp
from app.config import get_settings
from app.db import get_engine, session_scope
from app.seed import seed_all

log = logging.getLogger("crm")
ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.7.2"


def run_migrations() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    with get_engine().begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


async def _loop(name: str, job: Callable[[], int], interval: float) -> None:
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:
            log.exception("%s loop failed", name)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.check_secrets()
    run_migrations()
    with session_scope() as db:
        seed_all(db)
    tasks = []
    if settings.inbox_interval_seconds:  # 0 — фоновые циклы выключены (тесты)
        # Добирает входящие, которые не разобрались сразу (перезапуск, сбой)
        tasks.append(asyncio.create_task(_loop("inbox", inbox.process_pending, settings.inbox_interval_seconds)))
        # Просроченные дела уходят на КНМ, даже если их никто не открыл
        tasks.append(asyncio.create_task(
            _loop("escalation", workflow.escalate_overdue, settings.escalation_interval_seconds)))
    yield
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="CRM «Чистый Липецк»", version=VERSION, lifespan=lifespan)
app.include_router(integration.read)
app.include_router(integration.delivery)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(incidents.router)
app.include_router(kp.router)


# Фронт показывает текст ошибки из поля message (docs/api-contract.md); detail остаётся для остальных.
@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    body = {"detail": exc.detail}
    if isinstance(exc.detail, str):
        body["message"] = exc.detail
    return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = jsonable_encoder(exc.errors(), exclude={"input"})
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", [])[1:])
    message = f"Неверные данные: {field} — {first.get('msg')}" if first else "Неверные данные"
    return JSONResponse({"detail": errors, "message": message}, status_code=422)


@app.middleware("http")
async def cache_policy(request: Request, call_next: Callable) -> Response:
    """Страницы и консоль — каждый раз сверять с сервером (ETag → 304), иначе после выкладки браузер
    держит старый index.html или admin.js. Сборка фронта в /assets/ с хешем в имени — кешировать насовсем."""
    response = await call_next(request)
    path = request.url.path
    if request.method == "GET" and "cache-control" not in response.headers and not path.startswith(("/api/", "/maps/")):
        response.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if path.startswith("/assets/")
                                             else "no-cache")
    return response


@app.get("/health", tags=["Служебное"])
def health() -> dict:
    with session_scope() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "version": VERSION}


def _local_dir(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else ROOT / path


# Подложка карты: файл тайлов OpenStreetMap, фронт читает его кусками (HTTP Range).
# Открытые данные, поэтому без входа.
_maps = _local_dir(get_settings().maps_dir)
if _maps.is_dir():
    app.mount("/maps", StaticFiles(directory=_maps), name="maps")

# Консоль системного администратора: справочники, инженеры и их MAX, регистрации из бота, события DG,
# пользователи и журнал. Сама страница — статика в пакете, права проверяет API.
ADMIN_UI = Path(__file__).resolve().parent / "admin_ui"


@app.get("/admin", include_in_schema=False)
def admin_console() -> RedirectResponse:
    return RedirectResponse("/admin/")


app.mount("/admin", StaticFiles(directory=ADMIN_UI, html=True), name="admin")

# Фронт с того же адреса, что и API: кука сессии (SameSite=strict) работает без CORS.
# Монтируется последним — маршруты API и /health выше имеют приоритет.
_web = _local_dir(get_settings().web_dir)
if (_web / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
