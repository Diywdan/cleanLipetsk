"""Пользователи системы и роли."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.control_body import ControlBody


class User(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    engineer_id: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Заполняется, когда включим авторизацию: таблицы готовим заранее,
    # чтобы вход не потребовал отдельной миграции.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # CRM users are linked by their stable CRM user id; SSO accounts have no local password.
    crm_user_id: Mapped[str | None] = mapped_column(String(128), unique=True)

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Role(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))


class UserRole(IntIdMixin, TimestampMixin, Base):
    """Роль пользователя; может быть ограничена органом контроля.

    Инспектор одного департамента не должен видеть дела другого, поэтому
    область действия роли хранится здесь, а не в карточке пользователя.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role_id",
            "control_body_id",
            name="uq_user_roles_user_role_body",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    control_body_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_bodies.id", ondelete="CASCADE")
    )

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship()
    control_body: Mapped["ControlBody | None"] = relationship()
