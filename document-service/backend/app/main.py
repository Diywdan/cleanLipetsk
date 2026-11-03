from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import ApiError, api_error_handler
from app.api.router import api_router
from app.api.crm_internal import router as crm_internal_router
from app.db.dependencies import get_db
from app.web.areas import router as areas_router
from app.web.audit import router as audit_router
from app.web.auth import current_user, require_admin
from app.web.auth import router as auth_router
from app.web.inspections import router as inspections_router
from app.web.router import router as web_router
from app.web.users import router as users_router
from app.web.sso import router as sso_router


app = FastAPI(
    title="Document Service",
    version="0.2.0",
    description=(
        "Формирование пакетов документов по контрольным мероприятиям "
        "(муниципальный контроль в сфере благоустройства)."
    ),
)

app.include_router(api_router)
app.include_router(crm_internal_router)

# Ошибки программного интерфейса отдаём так, как ждёт интерфейс диспетчера:
# с полем message. Обработчик только для ApiError — перехват всех HTTPException
# сломал бы переадресацию страниц на форму входа (см. app/api/errors.py).
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(auth_router)
app.include_router(sso_router)
# Все страницы интерфейса требуют входа: без живой сессии — переадресация
# на форму входа (см. app/web/auth.py).
app.include_router(web_router, dependencies=[Depends(current_user)])
# Управление пользователями — только для администратора.
app.include_router(users_router, dependencies=[Depends(require_admin)])
app.include_router(audit_router, dependencies=[Depends(require_admin)])
# Управы: за какими адресами закреплены инспекторы.
app.include_router(areas_router, dependencies=[Depends(current_user)])
# Осмотры объекта: отдельный шаг до формирования пакета документов.
app.include_router(inspections_router, dependencies=[Depends(current_user)])


@app.get("/")
def root():
    return {
        "service": "document-service",
        "version": app.version,
        "ui": "/ui",
        "docs": "/docs",
        "api": {
            "cases": "/api/cases",
            "document_types": "/api/document-types",
            "package_kinds": "/api/package-kinds",
        },
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "document-service",
    }


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": result.scalar(),
    }
