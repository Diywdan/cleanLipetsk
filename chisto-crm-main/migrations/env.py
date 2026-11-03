from __future__ import annotations

from alembic import context

from app import models  # noqa: F401 — регистрирует таблицы в metadata
from app.db import Base, get_engine

target_metadata = Base.metadata


def run() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:  # вызов из приложения: соединение уже открыто
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    with get_engine().connect() as connection:  # вызов из командной строки alembic
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run()
