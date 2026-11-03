"""Нарушения, предписания и решения — юридический результат мероприятия."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import DecisionItemKind


if TYPE_CHECKING:
    from app.models.control_body import ControlBodySignatory, Inspector
    from app.models.control_case import ControlAction, ControlCase
    from app.models.organization import Organization
    from app.models.reference import Address, NpaArticle, PrescriptionStatus, ViolationType


class Violation(IntIdMixin, TimestampMixin, Base):
    """Выявленное нарушение обязательных требований."""

    __tablename__ = "violations"
    __table_args__ = (
        Index("ix_violations_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    control_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_actions.id", ondelete="SET NULL")
    )
    violation_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("violation_types.id")
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))

    is_eliminated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    eliminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    control_case: Mapped["ControlCase"] = relationship(back_populates="violations")
    control_action: Mapped["ControlAction | None"] = relationship()
    violation_type: Mapped["ViolationType | None"] = relationship()
    address: Mapped["Address | None"] = relationship()

    provisions: Mapped[list["ViolationProvision"]] = relationship(
        back_populates="violation",
        cascade="all, delete-orphan",
    )
    # Работы с объёмами: из них собирается и описание нарушения, и требование
    # предписания. Хранятся у нарушения, потому что это характеристика самого
    # нарушения, а не документа: при вторичном предписании их не вводят заново.
    works: Mapped[list["ViolationWork"]] = relationship(
        back_populates="violation",
        cascade="all, delete-orphan",
        order_by="ViolationWork.sequence_no",
    )


class ViolationProvision(IntIdMixin, TimestampMixin, Base):
    """Квалификация нарушения по конкретной норме.

    Связь именно множественная: в разобранном предписании одно нарушение
    квалифицируется одновременно по пункту 5.2 части 5 статьи 5 и по
    частям 7 и 12 статьи 14 Правил благоустройства.
    """

    __tablename__ = "violation_provisions"
    __table_args__ = (
        UniqueConstraint(
            "violation_id",
            "npa_article_id",
            name="uq_violation_provisions_violation_article",
        ),
    )

    violation_id: Mapped[int] = mapped_column(
        ForeignKey("violations.id", ondelete="CASCADE"), nullable=False
    )
    npa_article_id: Mapped[int] = mapped_column(
        ForeignKey("npa_articles.id"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)

    violation: Mapped["Violation"] = relationship(back_populates="provisions")
    npa_article: Mapped["NpaArticle"] = relationship()


class ViolationWork(IntIdMixin, TimestampMixin, Base):
    """Работа, которую нужно выполнить по нарушению, и её объём.

    «асфальт – 4 кв.м.» — работа из справочника, объём числом, единица
    измерения из справочника. Один и тот же список печатается и в описании
    нарушения, и в требовании предписания: требование лишь меняет форму
    слова («восстановить асфальт»).
    """

    __tablename__ = "violation_works"
    __table_args__ = (
        UniqueConstraint(
            "violation_id",
            "work_id",
            name="uq_violation_works_violation_work",
        ),
    )

    violation_id: Mapped[int] = mapped_column(
        ForeignKey("violations.id", ondelete="CASCADE"), nullable=False
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("works.id"), nullable=False
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    violation: Mapped["Violation"] = relationship(back_populates="works")
    work: Mapped["Work"] = relationship()


class Prescription(IntIdMixin, TimestampMixin, Base):
    """Предписание об устранении нарушения."""

    __tablename__ = "prescriptions"
    __table_args__ = (
        Index("ix_prescriptions_control_case_id", "control_case_id"),
        Index("ix_prescriptions_number", "number"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[str | None] = mapped_column(String(50))
    issued_on: Mapped[date | None] = mapped_column(Date)
    due_on: Mapped[date | None] = mapped_column(Date)

    status_id: Mapped[int | None] = mapped_column(
        ForeignKey("prescription_statuses.id")
    )

    # Повторное предписание ссылается на первоначальное: без этой связи
    # нельзя показать историю «не исполнено → выдано повторно».
    parent_prescription_id: Mapped[int | None] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="SET NULL")
    )

    notified_on: Mapped[date | None] = mapped_column(Date)
    executed_on: Mapped[date | None] = mapped_column(Date)
    executed_confirmed_on: Mapped[date | None] = mapped_column(Date)
    execution_act_number: Mapped[str | None] = mapped_column(String(50))
    execution_act_date: Mapped[date | None] = mapped_column(Date)
    execution_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    control_case: Mapped["ControlCase"] = relationship(back_populates="prescriptions")
    status: Mapped["PrescriptionStatus | None"] = relationship()
    parent: Mapped["Prescription | None"] = relationship(
        remote_side="Prescription.id",
        back_populates="children",
    )
    children: Mapped[list["Prescription"]] = relationship(back_populates="parent")

    items: Mapped[list["PrescriptionItem"]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        order_by="PrescriptionItem.sequence_no",
    )


class PrescriptionItem(IntIdMixin, TimestampMixin, Base):
    """Что предписано сделать по нарушению.

    Работы и объёмы берутся из нарушения (violation_works): в требовании они
    не вводятся заново, а только получают действие — «восстановить»,
    «устранить», «убрать». Готовая формулировка собирается в документе.
    """

    __tablename__ = "prescription_items"
    __table_args__ = (
        Index("ix_prescription_items_prescription_id", "prescription_id"),
    )

    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    npa_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("npa_articles.id", ondelete="SET NULL")
    )

    # Действие, которое предписано выполнить с работами нарушения.
    action_code: Mapped[str | None] = mapped_column(String(50))
    due_on: Mapped[date | None] = mapped_column(Date)

    # Прежние поля: остаются ради уже напечатанных документов, в бланках не
    # используются. Новые документы собираются из работ нарушения.
    requirement_text: Mapped[str | None] = mapped_column(Text)
    work_name: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(50))

    prescription: Mapped["Prescription"] = relationship(back_populates="items")
    npa_article: Mapped["NpaArticle | None"] = relationship()


class Decision(IntIdMixin, TimestampMixin, Base):
    """Решение по результатам контрольного мероприятия."""

    __tablename__ = "decisions"
    __table_args__ = (
        Index("ix_decisions_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str | None] = mapped_column(String(50))
    decision_date: Mapped[date | None] = mapped_column(Date)
    decision_kind: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str | None] = mapped_column(Text)

    approved_by_signatory_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_body_signatories.id", ondelete="SET NULL")
    )
    prepared_by_inspector_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspectors.id", ondelete="SET NULL")
    )

    control_case: Mapped["ControlCase"] = relationship(back_populates="decisions")
    approved_by: Mapped["ControlBodySignatory | None"] = relationship()
    prepared_by: Mapped["Inspector | None"] = relationship()

    items: Mapped[list["DecisionItem"]] = relationship(
        back_populates="decision",
        cascade="all, delete-orphan",
        order_by="DecisionItem.sequence_no",
    )


class DecisionItem(IntIdMixin, TimestampMixin, Base):
    """Пункт решения: выдать предписание, возбудить дело об АП и т. д."""

    __tablename__ = "decision_items"
    __table_args__ = (
        UniqueConstraint(
            "decision_id",
            "sequence_no",
            name="uq_decision_items_decision_sequence",
        ),
    )

    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[DecisionItemKind] = mapped_column(
        code_enum(DecisionItemKind, "decision_item_kind"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    npa_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("npa_articles.id", ondelete="SET NULL")
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )

    decision: Mapped["Decision"] = relationship(back_populates="items")
    npa_article: Mapped["NpaArticle | None"] = relationship()
    organization: Mapped["Organization | None"] = relationship()
