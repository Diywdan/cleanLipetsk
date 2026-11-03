from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_host: str
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str
    crm_integration_token: str = ""
    crm_event_url: str = ""

    # Часовой пояс, в котором печатаются документы. В базе моменты времени
    # хранятся в UTC.
    display_timezone: str = "Europe/Moscow"

    # Каталог файлового хранилища (том docker).
    data_root: str = "/data"

    # Город, который печатается в бланках («г. Липецк»).
    document_place: str = "Липецк"

    # Показывать инспектору только заявки по адресам его управы.
    # По умолчанию выключено: пока управы не заполнены, ограничение
    # скрыло бы от инспекторов все заявки. Руководитель и администратор
    # видят все заявки независимо от этой настройки.
    restrict_cases_by_uprava: bool = False

    model_config = SettingsConfigDict(
        extra="ignore",
    )


settings = Settings()
