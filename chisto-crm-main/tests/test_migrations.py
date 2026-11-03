"""Миграции совпадают с моделями: новая колонка без миграции уронит этот тест."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base, get_engine


def test_models_match_migrations(client):  # фикстура уже прогнала alembic upgrade head
    with get_engine().connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
