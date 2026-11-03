from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Единые имена ограничений: без них Alembic генерирует безымянные
# constraint'ы, которые потом невозможно изменить в миграции.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IntIdMixin:
    """Суррогатный первичный ключ: bigint, а не serial — запас на годы вперёд."""

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def code_enum(enum_cls: type[Enum], name: str, length: int = 64) -> SAEnum:
    """Перечисление как varchar + check вместо нативного типа PostgreSQL.

    Нативные enum-типы требуют ALTER TYPE при каждом новом значении; для
    справочных полей это лишняя связанность миграций с данными.
    Хранится значение (value), а не имя члена перечисления.
    """

    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
