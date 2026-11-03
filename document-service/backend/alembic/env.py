import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.db.session import Base

# Импорт пакета моделей наполняет Base.metadata; отдельные имена не нужны.
import app.models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


database_url = (
    f"postgresql+psycopg://"
    f"{os.environ['DATABASE_USER']}:"
    f"{os.environ['DATABASE_PASSWORD']}@"
    f"{os.environ['DATABASE_HOST']}:"
    f"{os.environ['DATABASE_PORT']}/"
    f"{os.environ['DATABASE_NAME']}"
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=None,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
