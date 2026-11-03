"""Управы: за какими адресами закреплён инспектор.

Управа — принятое в департаменте название территории. Это набор адресов
(домов), а не свободный текст: именно по адресу объекта контроля заявка
попадает на управу. Поэтому адреса берутся из справочника адресов, а не
вводятся строкой: иначе один и тот же дом, записанный по-разному, оказался бы
в разных управах.

Закрепление инспектора за управой версионное: территории перераспределяются,
и по прошлым заявкам должно быть видно, кто отвечал за адрес на тот момент.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.control_body import ControlBody, Inspector
    from app.models.reference import Address


class Area(IntIdMixin, TimestampMixin, Base):
    """Управа — территория, закреплённая за органом контроля."""

    __tablename__ = "areas"
    __table_args__ = (
        Index("ix_areas_control_body_id", "control_body_id"),
    )

    control_body_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_bodies.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Адрес управы: он же место составления протокола об административном
    # правонарушении по её заявкам. Выбирается из общего справочника адресов,
    # а не вписывается руками.
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    # Номер кабинета управы: он печатается в уведомлении о явке вместе с
    # адресом («по адресу …, каб. № 207»).
    office: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    control_body: Mapped["ControlBody | None"] = relationship()
    address: Mapped["Address | None"] = relationship()
    addresses: Mapped[list["AreaAddress"]] = relationship(
        back_populates="area", cascade="all, delete-orphan"
    )
    inspectors: Mapped[list["AreaInspector"]] = relationship(
        back_populates="area", cascade="all, delete-orphan"
    )


class AreaAddress(IntIdMixin, TimestampMixin, Base):
    """Адрес (дом), входящий в управу."""

    __tablename__ = "area_addresses"
    __table_args__ = (
        UniqueConstraint("area_id", "address_id", name="uq_area_address"),
        Index("ix_area_addresses_address_id", "address_id"),
    )

    area_id: Mapped[int] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id", ondelete="CASCADE"), nullable=False
    )

    area: Mapped["Area"] = relationship(back_populates="addresses")
    address: Mapped["Address"] = relationship()


class AreaInspector(IntIdMixin, TimestampMixin, Base):
    """Кто отвечает за управу; период действия — история перераспределения."""

    __tablename__ = "area_inspectors"
    __table_args__ = (
        UniqueConstraint("area_id", "inspector_id", name="uq_area_inspector"),
        Index("ix_area_inspectors_inspector_id", "inspector_id"),
    )

    area_id: Mapped[int] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"), nullable=False
    )
    inspector_id: Mapped[int] = mapped_column(
        ForeignKey("inspectors.id", ondelete="CASCADE"), nullable=False
    )
    valid_from: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    valid_to: Mapped[date | None] = mapped_column(Date)

    area: Mapped["Area"] = relationship(back_populates="inspectors")
    inspector: Mapped["Inspector"] = relationship()
