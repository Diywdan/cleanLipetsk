from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite не проверяет внешние ключи без PRAGMA
            dbapi_conn.execute("PRAGMA foreign_keys = ON")
            # Встроенный lower() SQLite понимает только латиницу — поиск по русскому адресу его не переживёт
            dbapi_conn.create_function("lower", 1, lambda v: v.lower() if isinstance(v, str) else v,
                                       deterministic=True)

    return engine


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Зависимость FastAPI: одна транзакция на запрос."""
    with session_scope() as session:
        yield session


def reset_caches() -> None:
    get_engine.cache_clear()
    _session_factory.cache_clear()
