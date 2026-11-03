"""Обращения граждан и организаций — повод для контрольного мероприятия.

Обращение и мероприятие — разные сущности: жалоба фиксирует факт, а
юридически значимой единицей является контрольное мероприятие. Связь
многие-ко-многим реализована основаниями в control_case_bases.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import ApplicantKind, AppealStatus


if TYPE_CHECKING:
    from app.models.file import StoredFile
    from app.models.reference import Address, AppealSource, ControlObjectType
    from app.models.reference import ViolationType
    from app.models.user import User


class Appeal(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "appeals"
    __table_args__ = (
        Index("ix_appeals_reg_number", "reg_number"),
        Index("ix_appeals_status", "status"),
    )

    reg_number: Mapped[str | None] = mapped_column(String(100))
    reg_date: Mapped[date | None] = mapped_column(Date)

    source_id: Mapped[int | None] = mapped_column(ForeignKey("appeal_sources.id"))

    applicant_kind: Mapped[ApplicantKind] = mapped_column(
        code_enum(ApplicantKind, "applicant_kind"),
        nullable=False,
        server_default=ApplicantKind.CITIZEN.value,
    )
    applicant_name: Mapped[str | None] = mapped_column(String(500))
    applicant_address: Mapped[str | None] = mapped_column(Text)
    applicant_phone: Mapped[str | None] = mapped_column(String(50))
    applicant_email: Mapped[str | None] = mapped_column(String(255))

    subject: Mapped[str | None] = mapped_column(String(1000))
    text: Mapped[str | None] = mapped_column(Text)

    # Место нарушения может быть ещё не заведено объектом контроля,
    # поэтому адрес хранится и в обращении.
    control_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_objects.id", ondelete="SET NULL")
    )
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    violation_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("violation_types.id")
    )

    status: Mapped[AppealStatus] = mapped_column(
        code_enum(AppealStatus, "appeal_status"),
        nullable=False,
        server_default=AppealStatus.NEW.value,
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    result: Mapped[str | None] = mapped_column(Text)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    source: Mapped["AppealSource | None"] = relationship()
    control_object: Mapped["ControlObject | None"] = relationship()  # noqa: F821
    address: Mapped["Address | None"] = relationship()
    violation_type: Mapped["ViolationType | None"] = relationship()
    created_by: Mapped["User | None"] = relationship()

    files: Mapped[list["AppealFile"]] = relationship(
        back_populates="appeal",
        cascade="all, delete-orphan",
        order_by="AppealFile.sequence_no",
    )


class AppealFile(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "appeal_files"
    __table_args__ = (
        UniqueConstraint(
            "appeal_id",
            "file_id",
            name="uq_appeal_files_appeal_file",
        ),
    )

    appeal_id: Mapped[int] = mapped_column(
        ForeignKey("appeals.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(500))
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    appeal: Mapped["Appeal"] = relationship(back_populates="files")
    file: Mapped["StoredFile"] = relationship()
