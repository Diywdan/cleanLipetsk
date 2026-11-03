"""Единый роутер API.

Программный интерфейс закрыт той же сессией, что и страницы: иначе документы
и персональные данные оказались бы доступны без входа, как только сервис
станет виден снаружи.
"""

from fastapi import APIRouter, Depends

from app.api import cases, dictionaries, documents, incidents, packages, session
from app.web.auth import require_session


api_router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_session)],
)
api_router.include_router(session.router)
api_router.include_router(cases.router)
api_router.include_router(packages.router)
api_router.include_router(documents.router)
api_router.include_router(dictionaries.router)
# Обращения — фасад для интерфейса диспетчера (SPA «Чистый Липецк»).
api_router.include_router(incidents.router)


@api_router.get("/kp", tags=["incidents"])
def kp_registry() -> list[dict]:
    """Справочник контейнерных площадок для интерфейса диспетчера.

    Реестр площадок ведёт CRM и отдаёт его через Data Gateway (решение
    совещания 07.10), поэтому у нас его нет: интерфейс получает пустой
    список и считает статистику по обращениям, как и раньше. Когда Gateway
    станет доступен, сюда встанет вызов его API — правок в интерфейсе не
    потребуется.
    """

    return []


__all__ = ["api_router"]
