"""Орган контроля: департамент, его управления, подписанты и инспекторы.

В документах орган контроля — не «наша организация», а отдельная сущность
со своим бланком, адресом, подписантами и структурными подразделениями.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import ExpertKind


if TYPE_CHECKING:
    from app.models.reference import Address


class ControlBody(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "control_bodies"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(1000))
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    units: Mapped[list["ControlBodyUnit"]] = relationship(
        back_populates="control_body",
        cascade="all, delete-orphan",
    )
    signatories: Mapped[list["ControlBodySignatory"]] = relationship(
        back_populates="control_body",
        cascade="all, delete-orphan",
    )
    address: Mapped["Address | None"] = relationship()


class ControlBodyUnit(IntIdMixin, TimestampMixin, Base):
    """Управление внутри департамента, например управление муниципального контроля."""

    __tablename__ = "control_body_units"
    __table_args__ = (
        UniqueConstraint(
            "control_body_id",
            "name",
            name="uq_control_body_units_body_name",
        ),
    )

    control_body_id: Mapped[int] = mapped_column(
        ForeignKey("control_bodies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    control_body: Mapped["ControlBody"] = relationship(back_populates="units")
    inspectors: Mapped[list["Inspector"]] = relationship(back_populates="unit")


class ControlBodySignatory(IntIdMixin, TimestampMixin, Base):
    """Лицо, уполномоченное утверждать задание и решение.

    Версионируется: председатели и заместители меняются, а подписанный
    документ задним числом переписывать нельзя.
    """

    __tablename__ = "control_body_signatories"
    __table_args__ = (
        ExcludeConstraint(
            ("control_body_id", "="),
            (literal_column("COALESCE(unit_id, 0)"), "="),
            # Утверждающих лиц одновременно может быть несколько
            # (председатель и заместитель), поэтому период ограничивается
            # конкретным человеком.
            (literal_column("full_name"), "="),
            (literal_column("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_control_body_signatories_period",
            using="gist",
        ),
        Index("ix_control_body_signatories_body_id", "control_body_id"),
    )

    control_body_id: Mapped[int] = mapped_column(
        ForeignKey("control_bodies.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_body_units.id", ondelete="SET NULL")
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(500), nullable=False)
    # «в соответствии с заданием заместителя председателя департамента …» —
    # в акте должность утверждающего стоит в родительном падеже.
    position_genitive: Mapped[str | None] = mapped_column(String(500))
    # Фамилия с инициалами в родительном падеже: «Инютиной Т.Н.».
    short_name_genitive: Mapped[str | None] = mapped_column(String(255))
    basis_kind: Mapped[str | None] = mapped_column(String(64))
    basis_number: Mapped[str | None] = mapped_column(String(100))
    basis_date: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    control_body: Mapped["ControlBody"] = relationship(back_populates="signatories")
    unit: Mapped["ControlBodyUnit | None"] = relationship()


class Inspector(IntIdMixin, TimestampMixin, Base):
    """Муниципальный инспектор: должность, контакты, удостоверение."""

    __tablename__ = "inspectors"
    __table_args__ = (
        Index("ix_inspectors_control_body_unit_id", "control_body_unit_id"),
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    control_body_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_body_units.id", ondelete="SET NULL")
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(500), nullable=False)
    # Творительный падеж нужен протоколу осмотра: «Осмотр проведён
    # Главным консультантом … Комолых Евгенией Юрьевной». Падежные формы
    # хранятся данными: склонение ФИО морфологией даёт ошибки в документах.
    full_name_instrumental: Mapped[str | None] = mapped_column(String(255))
    position_instrumental: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))

    certificate_number: Mapped[str | None] = mapped_column(String(100))
    certificate_issued_on: Mapped[date | None] = mapped_column(Date)
    certificate_expires_on: Mapped[date | None] = mapped_column(Date)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    user: Mapped["User | None"] = relationship()  # noqa: F821
    unit: Mapped["ControlBodyUnit | None"] = relationship(back_populates="inspectors")


class Expert(IntIdMixin, TimestampMixin, Base):
    """Эксперт или экспертная организация, привлекаемые к мероприятию."""

    __tablename__ = "experts"

    kind: Mapped[ExpertKind] = mapped_column(
        code_enum(ExpertKind, "expert_kind"),
        nullable=False,
        server_default=ExpertKind.PERSON.value,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[str | None] = mapped_column(String(500))
    accreditation_number: Mapped[str | None] = mapped_column(String(100))
    accreditation_authority: Mapped[str | None] = mapped_column(String(500))
    accreditation_valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ControlCaseExpert(IntIdMixin, TimestampMixin, Base):
    """Привлечение эксперта к конкретному мероприятию.

    В акте есть раздел «к проведению были привлечены», и в разобранном
    документе он заполнен значением «не привлекались» — это отсутствие
    строк в этой таблице, а не текст в поле.
    """

    __tablename__ = "control_case_experts"
    __table_args__ = (
        UniqueConstraint(
            "control_case_id",
            "expert_id",
            name="uq_control_case_experts_case_expert",
        ),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    expert_id: Mapped[int] = mapped_column(
        ForeignKey("experts.id"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(String(255))
