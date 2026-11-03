from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER = "generate-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="CRM_", extra="ignore"
    )

    database_url: str = "sqlite:///data/crm.db"
    log_level: str = "info"

    # Первый администратор: создаётся при старте, если пользователя с таким логином нет.
    # Пароль существующего пользователя при перезапуске не перезаписывается.
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    session_ttl_seconds: int = Field(default=28800, ge=300, le=604800)
    cookie_secure: bool = False

    # Интеграция с Data Gateway: READ — справочники, WRITE — сопряжение и регистрация.
    dg_read_token: SecretStr = SecretStr("")
    dg_write_token: SecretStr = SecretStr("")
    # Ключ подписи вебхука из secret manager; если пуст — берётся из сопряжения в БД.
    dg_webhook_signing_secret: SecretStr = SecretStr("")
    dg_webhook_max_skew_seconds: int = Field(default=300, ge=30, le=3600)
    # Адрес DG для свежих ссылок на фото (GET /api/v1/storage/object); пусто — из сопряжения в БД.
    dg_media_url: str = ""

    # Machine-to-machine connection to document-service.
    document_service_url: str = ""
    document_service_public_url: str = ""
    document_service_token: SecretStr = SecretStr("")

    # Фоновый разбор входящих: 0 — выключен (тесты).
    inbox_interval_seconds: float = Field(default=2.0, ge=0, le=60)
    # Как часто фоновый цикл переводит просроченные дела на КНМ.
    escalation_interval_seconds: float = Field(default=60.0, ge=1, le=3600)
    seed_demo: bool = False

    # Фото отчётов исполнителей: папка (в Docker — том) и предел размера одного файла.
    files_dir: str = "data/files"
    # Собранный фронт «Диспетчерской» (cleanLipetsk); нет index.html — CRM отдаёт только API
    web_dir: str = "web"
    # Подложка карты фронта (lipetsk.pmtiles); лежит отдельно от web/, чтобы выкладка фронта её не трогала
    maps_dir: str = "maps"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=100_000, le=50 * 1024 * 1024)

    def check_secrets(self) -> None:
        def strong(name: str, value: str) -> None:
            if len(value) < 32 or value == PLACEHOLDER:
                raise RuntimeError(f"CRM_{name} должен быть сгенерированным секретом не короче 32 символов")

        strong("SESSION_SECRET", self.session_secret.get_secret_value())
        strong("DG_READ_TOKEN", self.dg_read_token.get_secret_value())
        strong("DG_WRITE_TOKEN", self.dg_write_token.get_secret_value())
        if self.dg_read_token.get_secret_value() == self.dg_write_token.get_secret_value():
            raise RuntimeError("CRM_DG_READ_TOKEN и CRM_DG_WRITE_TOKEN должны различаться")
        if self.document_service_url:
            strong("DOCUMENT_SERVICE_TOKEN", self.document_service_token.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
