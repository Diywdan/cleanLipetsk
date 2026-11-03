from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base


DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=settings.database_user,
    password=settings.database_password,
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


__all__ = ["Base", "engine", "SessionLocal"]
