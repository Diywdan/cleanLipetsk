"""Журнал изменений: кто и когда менял дело, предписание или реквизиты."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_table", "entity_id"),
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_table: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(String(1000))

    actor: Mapped["User | None"] = relationship()
