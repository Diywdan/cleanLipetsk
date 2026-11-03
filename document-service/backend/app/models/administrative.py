"""Административное производство по заявке.

Уведомление о явке и протокол об административном правонарушении — документы
одного производства по части 1 статьи 19.5 КоАП РФ (неисполнение предписания
в срок). Их данные не выводятся из заявки: номер и дата протокола, дата и
время явки, статья, описание события правонарушения — сведения, которые
должностное лицо вносит само.

Хранится в отдельной таблице, а не в заявке: у заявки этих данных нет вовсе,
а у административного производства своя нумерация и свои сроки.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.control_case import ControlCase


class AdministrativeCase(IntIdMixin, TimestampMixin, Base):
    """Производство по делу об административном правонарушении."""

    __tablename__ = "administrative_cases"
    __table_args__ = (
        Index("ix_administrative_cases_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # --- Протокол --------------------------------------------------------
    protocol_number: Mapped[str | None] = mapped_column(String(100))
    protocol_date: Mapped[date | None] = mapped_column(Date)
    # «г. Липецк, ул. Механизаторов, 15» — место составления протокола.
    protocol_place: Mapped[str | None] = mapped_column(String(500))

    # --- Явка для составления протокола ----------------------------------
    appearance_date: Mapped[date | None] = mapped_column(Date)
    # Время хранится строкой: в бланке оно печатается как «11» час. «30» мин.
    appearance_time: Mapped[str | None] = mapped_column(String(20))
    appearance_place: Mapped[str | None] = mapped_column(String(500))
    appearance_office: Mapped[str | None] = mapped_column(String(50))

    # --- Уведомление о явке ----------------------------------------------
    notice_number: Mapped[str | None] = mapped_column(String(100))
    notice_date: Mapped[date | None] = mapped_column(Date)

    # --- Ранее выданное предписание ---------------------------------------
    # Протокол по части 1 статьи 19.5 описывает неисполнение предыдущего
    # предписания: «предписания Департамента от 06.07.2026 № … со сроком
    # исполнения до 06.08.2026». Это предписание прошлого дела, поэтому его
    # данные вводятся здесь, а не берутся из текущего предписания заявки.
    prior_prescription_number: Mapped[str | None] = mapped_column(String(50))
    prior_prescription_date: Mapped[date | None] = mapped_column(Date)
    prior_prescription_due: Mapped[date | None] = mapped_column(Date)
    # «части 1,2 статьи 4» — по какой норме было выдано предписание.
    prior_prescription_basis: Mapped[str | None] = mapped_column(String(255))

    # --- Правонарушение ---------------------------------------------------
    # «частью 1 статьи 19.5» — подставляется в текст уведомления и протокола.
    offense_article: Mapped[str | None] = mapped_column(String(255))
    offense_date: Mapped[date | None] = mapped_column(Date)
    offense_time: Mapped[str | None] = mapped_column(String(20))
    offense_place: Mapped[str | None] = mapped_column(String(500))
    # Длинный текст «Административное правонарушение выразилось в следующем».
    offense_description: Mapped[str | None] = mapped_column(Text)
    # Кто присутствовал: «законного представителя … ФИО, должность, телефон».
    representative_info: Mapped[str | None] = mapped_column(Text)
    # Отметка о неявке; если не заполнена, собирается из даты и места явки.
    appearance_note: Mapped[str | None] = mapped_column(Text)
    # «акт выездного обследования и протокол осмотра от 12.08.2026».
    appendix_note: Mapped[str | None] = mapped_column(Text)

    control_case: Mapped["ControlCase"] = relationship()
