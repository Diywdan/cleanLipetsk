"""Контролируемые лица: организации, их филиалы и версии реквизитов.

Филиал не является отдельным юридическим лицом, поэтому «АО "РИР Энерго"
в лице филиала АО «РИР Энерго»-«Липецкая генерация»» собирается из двух
записей: organizations + organization_units.
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
from app.models.enums import (
    ContactKind,
    ContactPurpose,
    OrganizationKind,
    OrganizationRoleCode,
    OrganizationUnitKind,
    SignatoryBasisKind,
)


if TYPE_CHECKING:
    from app.models.reference import Address


def _period_exclude(name: str, *scope: str) -> ExcludeConstraint:
    """Запрет пересекающихся периодов действия для версионных строк.

    Проверка живёт в СУБД, а не в коде: две версии с пересекающимися
    сроками физически не запишутся. COALESCE(unit_id, 0) нужен, потому что
    строки уровня организации (unit_id IS NULL) иначе не сравнивались бы
    между собой, а *scope сужает область: у организации одновременно могут
    действовать несколько ролей и несколько подписантов, поэтому период
    ограничивается не парой «организация + филиал», а конкретной ролью или
    конкретным лицом.
    """

    elements: list[tuple[object, str]] = [
        ("organization_id", "="),
        (literal_column("COALESCE(unit_id, 0)"), "="),
    ]
    elements.extend(
        (literal_column(expression), "=") for expression in scope
    )
    elements.append(
        (literal_column("daterange(valid_from, valid_to, '[]')"), "&&"),
    )
    return ExcludeConstraint(*elements, name=name, using="gist")


class Organization(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    kind: Mapped[OrganizationKind] = mapped_column(
        code_enum(OrganizationKind, "organization_kind"),
        nullable=False,
        server_default=OrganizationKind.LEGAL_ENTITY.value,
    )
    short_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(1000))
    ogrn: Mapped[str | None] = mapped_column(String(20))
    inn: Mapped[str | None] = mapped_column(String(20), index=True)
    kpp: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    units: Mapped[list["OrganizationUnit"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    requisites: Mapped[list["OrganizationRequisite"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    roles: Mapped[list["OrganizationRole"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[list["OrganizationContact"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    signatories: Mapped[list["OrganizationSignatory"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class OrganizationUnit(IntIdMixin, TimestampMixin, Base):
    """Филиал, представительство, обособленное структурное подразделение."""

    __tablename__ = "organization_units"
    __table_args__ = (
        Index("ix_organization_units_organization_id", "organization_id"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    parent_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL")
    )
    kind: Mapped[OrganizationUnitKind] = mapped_column(
        code_enum(OrganizationUnitKind, "organization_unit_kind"),
        nullable=False,
        server_default=OrganizationUnitKind.BRANCH.value,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="units")
    parent: Mapped["OrganizationUnit | None"] = relationship(
        remote_side="OrganizationUnit.id",
        back_populates="children",
    )
    children: Mapped[list["OrganizationUnit"]] = relationship(
        back_populates="parent",
    )
    address: Mapped["Address | None"] = relationship()


class OrganizationRequisite(IntIdMixin, TimestampMixin, Base):
    """Реквизиты организации (или филиала) с историей изменений."""

    __tablename__ = "organization_requisites"
    __table_args__ = (
        _period_exclude("ex_organization_requisites_period"),
        Index("ix_organization_requisites_organization_id", "organization_id"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE")
    )

    inn: Mapped[str | None] = mapped_column(String(20))
    kpp: Mapped[str | None] = mapped_column(String(20))
    ogrn: Mapped[str | None] = mapped_column(String(20))
    legal_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    postal_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="requisites")
    unit: Mapped["OrganizationUnit | None"] = relationship()
    legal_address: Mapped["Address | None"] = relationship(
        foreign_keys=[legal_address_id],
    )
    postal_address: Mapped["Address | None"] = relationship(
        foreign_keys=[postal_address_id],
    )


class OrganizationRole(IntIdMixin, TimestampMixin, Base):
    """Роль организации в деле: регоператор ТКО, УК, подрядчик, собственник."""

    __tablename__ = "organization_roles"
    __table_args__ = (
        _period_exclude("ex_organization_roles_period", "role"),
        Index("ix_organization_roles_organization_id", "organization_id"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE")
    )
    role: Mapped[OrganizationRoleCode] = mapped_column(
        code_enum(OrganizationRoleCode, "organization_role_code"),
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="roles")
    unit: Mapped["OrganizationUnit | None"] = relationship()


class OrganizationContact(IntIdMixin, TimestampMixin, Base):
    """Контакт для отправки документов.

    Направление предписания уходит двум получателям (филиалу и головной
    организации), поэтому адрес электронной почты — не одно поле в карточке,
    а набор контактов с назначением.
    """

    __tablename__ = "organization_contacts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "unit_id",
            "kind",
            "value",
            name="uq_organization_contacts_owner_kind_value",
        ),
        Index("ix_organization_contacts_organization_id", "organization_id"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE")
    )
    kind: Mapped[ContactKind] = mapped_column(
        code_enum(ContactKind, "contact_kind"), nullable=False
    )
    purpose: Mapped[ContactPurpose] = mapped_column(
        code_enum(ContactPurpose, "contact_purpose"),
        nullable=False,
        server_default=ContactPurpose.DOCUMENT_DELIVERY.value,
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    organization: Mapped["Organization"] = relationship(back_populates="contacts")
    unit: Mapped["OrganizationUnit | None"] = relationship()


class OrganizationSignatory(IntIdMixin, TimestampMixin, Base):
    """Законный представитель контролируемого лица (кому адресуем документы)."""

    __tablename__ = "organization_signatories"
    __table_args__ = (
        _period_exclude("ex_organization_signatories_period", "full_name"),
        Index("ix_organization_signatories_organization_id", "organization_id"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE")
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(500), nullable=False)

    basis_kind: Mapped[SignatoryBasisKind | None] = mapped_column(
        code_enum(SignatoryBasisKind, "signatory_basis_kind")
    )
    basis_number: Mapped[str | None] = mapped_column(String(100))
    basis_date: Mapped[date | None] = mapped_column(Date)

    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="signatories")
    unit: Mapped["OrganizationUnit | None"] = relationship()
