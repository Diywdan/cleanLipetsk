"""Пакеты документов, сформированные документы, отправка и снимки данных."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import (
    DeliveryMethod,
    DeliveryRecipientKind,
    DeliveryStatus,
    PackageStatus,
    SnapshotEntityKind,
)


if TYPE_CHECKING:
    from app.models.control_case import ControlCase
    from app.models.file import StoredFile
    from app.models.organization import Organization, OrganizationUnit
    from app.models.reference import (
        Address,
        DocumentStatus,
        DocumentType,
        PackageKind,
    )
    from app.models.user import User


class DataSnapshot(IntIdMixin, TimestampMixin, Base):
    """Снимок данных, из которого собран документ.

    Хранит полный набор значений подстановки и хэш вместе с версией
    шаблона: перегенерация идёт из снимка, поэтому повторная печать даёт
    тот же документ, даже если справочники с тех пор изменились.
    """

    __tablename__ = "data_snapshots"
    __table_args__ = (
        Index("ix_data_snapshots_entity", "entity_kind", "entity_id"),
    )

    entity_kind: Mapped[SnapshotEntityKind] = mapped_column(
        code_enum(SnapshotEntityKind, "snapshot_entity_kind"), nullable=False
    )
    entity_id: Mapped[int | None] = mapped_column()

    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    created_by: Mapped["User | None"] = relationship()


class DocumentTemplate(IntIdMixin, TimestampMixin, Base):
    """Версия DOCX-шаблона документа.

    Версия обязательна: без неё нельзя воспроизвести документ через год
    после того, как форму бланка поменяли приказом.
    """

    __tablename__ = "document_templates"
    __table_args__ = (
        UniqueConstraint(
            "document_type_id",
            "version",
            name="uq_document_templates_type_version",
        ),
    )

    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)

    # «Приложение к приказу департамента … от 30.12.2022 № 104»
    approval_ref: Mapped[str | None] = mapped_column(String(1000))

    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    document_type: Mapped["DocumentType"] = relationship()
    file: Mapped["StoredFile | None"] = relationship()


class DocumentPackage(IntIdMixin, TimestampMixin, Base):
    """Пакет документов по мероприятию: первичный, повторный, исполненный."""

    __tablename__ = "document_packages"
    __table_args__ = (
        Index("ix_document_packages_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    package_kind_id: Mapped[int] = mapped_column(
        ForeignKey("package_kinds.id"), nullable=False
    )
    status: Mapped[PackageStatus] = mapped_column(
        code_enum(PackageStatus, "package_status"),
        nullable=False,
        server_default=PackageStatus.DRAFT.value,
    )

    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    control_case: Mapped["ControlCase"] = relationship()
    package_kind: Mapped["PackageKind"] = relationship()
    snapshot: Mapped["DataSnapshot | None"] = relationship()
    created_by: Mapped["User | None"] = relationship()

    documents: Mapped[list["Document"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
    )


class Document(IntIdMixin, TimestampMixin, Base):
    """Сформированный документ пакета."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_package_id", "package_id"),
        Index("ix_documents_erp_number", "erp_number"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey("document_packages.id", ondelete="CASCADE"), nullable=False
    )
    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id"), nullable=False
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_templates.id", ondelete="SET NULL")
    )

    number: Mapped[str | None] = mapped_column(String(50))
    document_date: Mapped[date | None] = mapped_column(Date)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("document_statuses.id"))

    erp_number: Mapped[str | None] = mapped_column(String(50))
    erp_code: Mapped[str | None] = mapped_column(String(50))

    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_snapshots.id", ondelete="SET NULL")
    )
    generated_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    signed_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )

    # Направление ссылается на акт и предписание, из которых оно собрано.
    parent_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Число листов: печатается в приложении к направлению («на 5 л. в 1 экз.»).
    pages: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    package: Mapped["DocumentPackage"] = relationship(back_populates="documents")
    document_type: Mapped["DocumentType"] = relationship()
    template: Mapped["DocumentTemplate | None"] = relationship()
    status: Mapped["DocumentStatus | None"] = relationship()
    snapshot: Mapped["DataSnapshot | None"] = relationship()
    generated_file: Mapped["StoredFile | None"] = relationship(
        foreign_keys=[generated_file_id],
    )
    signed_file: Mapped["StoredFile | None"] = relationship(
        foreign_keys=[signed_file_id],
    )
    parent_document: Mapped["Document | None"] = relationship(
        remote_side="Document.id",
        back_populates="child_documents",
    )
    child_documents: Mapped[list["Document"]] = relationship(
        back_populates="parent_document",
    )
    created_by: Mapped["User | None"] = relationship()

    attachments: Mapped[list["DocumentAttachment"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentAttachment.sequence_no",
    )
    deliveries: Mapped[list["DocumentDelivery"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentAttachment(IntIdMixin, TimestampMixin, Base):
    """Приложение к документу: «Акт … на 5 л. в 1 экз.»."""

    __tablename__ = "document_attachments"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "file_id",
            name="uq_document_attachments_document_file",
        ),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(500))
    pages: Mapped[int | None] = mapped_column(Integer)
    copies: Mapped[int | None] = mapped_column(Integer)
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    document: Mapped["Document"] = relationship(back_populates="attachments")
    file: Mapped["StoredFile"] = relationship()


class DocumentDelivery(IntIdMixin, TimestampMixin, Base):
    """Факт направления документа получателю.

    Направление предписания уходит двум адресатам (филиалу и головной
    организации), и по каждому нужна своя отметка о вручении.
    """

    __tablename__ = "document_deliveries"
    __table_args__ = (
        Index("ix_document_deliveries_document_id", "document_id"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    recipient_kind: Mapped[DeliveryRecipientKind] = mapped_column(
        code_enum(DeliveryRecipientKind, "delivery_recipient_kind"), nullable=False
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL")
    )
    email: Mapped[str | None] = mapped_column(String(255))
    postal_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL")
    )

    method: Mapped[DeliveryMethod] = mapped_column(
        code_enum(DeliveryMethod, "delivery_method"),
        nullable=False,
        server_default=DeliveryMethod.EMAIL.value,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        code_enum(DeliveryStatus, "delivery_status"),
        nullable=False,
        server_default=DeliveryStatus.PENDING.value,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_number: Mapped[str | None] = mapped_column(String(100))
    receipt_date: Mapped[date | None] = mapped_column(Date)
    error_text: Mapped[str | None] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="deliveries")
    organization: Mapped["Organization | None"] = relationship()
    unit: Mapped["OrganizationUnit | None"] = relationship()
    postal_address: Mapped["Address | None"] = relationship()
