"""Объекты контроля и контрольные мероприятия с их основаниями и действиями."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin, code_enum
from app.models.enums import (
    CaseBaseKind,
    CasePartyKind,
    ControlActionType,
    InspectionKind,
    InspectionResult,
    InspectorRole,
    PhotoKind,
)


if TYPE_CHECKING:
    from app.models.appeal import Appeal
    from app.models.control_body import ControlBody, ControlBodySignatory, Inspector
    from app.models.enforcement import Decision, Prescription, Violation
    from app.models.file import StoredFile
    from app.models.organization import (
        Organization,
        OrganizationContact,
        OrganizationRequisite,
        OrganizationSignatory,
        OrganizationUnit,
    )
    from app.models.reference import (
        Address,
        ControlCaseStatus,
        ControlForm,
        ControlKind,
        ControlObjectType,
        Npa,
    )
    from app.models.user import User


class ControlObject(IntIdMixin, TimestampMixin, Base):
    """Объект контроля: земельный участок, контейнерная площадка, МКД и т. д."""

    __tablename__ = "control_objects"
    __table_args__ = (
        Index("ix_control_objects_object_type_id", "object_type_id"),
        Index("ix_control_objects_address_id", "address_id"),
    )

    object_type_id: Mapped[int] = mapped_column(
        ForeignKey("control_object_types.id"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(500))
    # Готовая формулировка объекта в родительном падеже для бланков:
    # «Земельного участка, расположенного по адресу: …». Согласование
    # причастий по роду морфологией не выводится — это текст оператора.
    name_genitive: Mapped[str | None] = mapped_column(String(1000))
    # Та же формулировка в предложном падеже: «на земельном участке,
    # расположенном по адресу: …». Нужна для описания нарушения.
    name_prepositional: Mapped[str | None] = mapped_column(String(1000))
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    cadastral_number: Mapped[str | None] = mapped_column(String(50))
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    owner_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    # Кто эксплуатирует объект. Это ещё не «ответственный за нарушение»:
    # ответственный зависит от вида нарушения и от того, кто вёл работы,
    # и определяется правилами (см. models/responsibility.py).
    operating_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )

    # Характеристики контейнерной площадки (число контейнеров, объём,
    # покрытие, периодичность вывоза) будут уточняться: jsonb избавляет
    # от миграции под каждую новую характеристику.
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    object_type: Mapped["ControlObjectType"] = relationship()
    address: Mapped["Address | None"] = relationship()
    owner: Mapped["Organization | None"] = relationship(
        foreign_keys=[owner_organization_id],
    )
    operating: Mapped["Organization | None"] = relationship(
        foreign_keys=[operating_organization_id],
    )


class ControlCase(IntIdMixin, TimestampMixin, Base):
    """Контрольное (надзорное) мероприятие — центральная сущность."""

    __tablename__ = "control_cases"
    __table_args__ = (
        Index("ix_control_cases_status_id", "status_id"),
        Index("ix_control_cases_controlled_organization_id", "controlled_organization_id"),
        Index("ix_control_cases_erp_number", "erp_number"),
        UniqueConstraint("crm_case_id", name="uq_control_cases_crm_case_id"),
    )

    case_number: Mapped[str | None] = mapped_column(String(100))
    # Внешний ключ дела из CRM. Нужен для повторной безопасной синхронизации:
    # один сигнал CRM всегда обновляет то же контрольное мероприятие.
    crm_case_id: Mapped[str | None] = mapped_column(String(128))

    control_kind_id: Mapped[int | None] = mapped_column(ForeignKey("control_kinds.id"))
    control_form_id: Mapped[int | None] = mapped_column(ForeignKey("control_forms.id"))
    control_body_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_bodies.id", ondelete="SET NULL")
    )

    controlled_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    controlled_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL")
    )
    control_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_objects.id", ondelete="SET NULL")
    )

    # Ответственный за устранение нарушения. На этом этапе выбирается
    # вручную из списка организаций: автоматическое определение по адресу
    # не делаем. Может совпадать с контролируемым лицом, а может и нет.
    responsible_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    responsible_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL")
    )

    purpose: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)

    status_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_case_statuses.id")
    )
    result: Mapped[str | None] = mapped_column(String(50))

    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Акт составляется отдельно от окончания обследования: в разобранном
    # акте обследование закончено в 13:00, а акт составлен в 17:00.
    act_composed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Номер и код присваивает портал прокуратуры; для нашего дела это
    # внешние идентификаторы, а не часть собственной нумерации.
    erp_number: Mapped[str | None] = mapped_column(String(50))
    erp_code: Mapped[str | None] = mapped_column(String(50))
    erp_url: Mapped[str | None] = mapped_column(String(1000))

    # QR-код из прокуратуры: выдаётся там же, где номер, и печатается в акте
    # и предписании. Система его не генерирует — она принимает готовую
    # картинку и подгоняет её под размер, зарезервированный в бланке.
    qr_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )

    # Номер акта, если он отличается от номера мероприятия: обычно портал
    # присваивает один номер на мероприятие, и он же идёт в акт. Поле оставлено
    # для уточнения — пустое значит «взять номер мероприятия».
    act_number: Mapped[str | None] = mapped_column(String(50))

    is_repeat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    previous_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_cases.id", ondelete="SET NULL")
    )

    assignment_number: Mapped[str | None] = mapped_column(String(50))
    assignment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Срок исполнения заявки: до выдачи предписания это и есть дата контроля,
    # по которой видно, что заявку пора проверять осмотром.
    control_due_on: Mapped[date | None] = mapped_column(Date)
    assignment_approved_by_signatory_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_body_signatories.id", ondelete="SET NULL")
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    control_kind: Mapped["ControlKind | None"] = relationship()
    control_form: Mapped["ControlForm | None"] = relationship()
    control_body: Mapped["ControlBody | None"] = relationship()
    controlled_organization: Mapped["Organization | None"] = relationship(
        foreign_keys=[controlled_organization_id],
    )
    controlled_unit: Mapped["OrganizationUnit | None"] = relationship(
        foreign_keys=[controlled_unit_id],
    )
    responsible_organization: Mapped["Organization | None"] = relationship(
        foreign_keys=[responsible_organization_id],
    )
    responsible_unit: Mapped["OrganizationUnit | None"] = relationship(
        foreign_keys=[responsible_unit_id],
    )
    control_object: Mapped["ControlObject | None"] = relationship()
    qr_file: Mapped["StoredFile | None"] = relationship()
    status: Mapped["ControlCaseStatus | None"] = relationship()
    assignment_approved_by: Mapped["ControlBodySignatory | None"] = relationship()
    created_by: Mapped["User | None"] = relationship()

    previous_case: Mapped["ControlCase | None"] = relationship(
        remote_side="ControlCase.id",
        back_populates="repeat_cases",
    )
    repeat_cases: Mapped[list["ControlCase"]] = relationship(
        back_populates="previous_case",
    )

    inspectors: Mapped[list["ControlCaseInspector"]] = relationship(
        back_populates="control_case",
        cascade="all, delete-orphan",
    )
    bases: Mapped[list["ControlCaseBase"]] = relationship(
        back_populates="control_case",
        cascade="all, delete-orphan",
    )
    parties: Mapped[list["ControlCaseParty"]] = relationship(
        back_populates="control_case",
        cascade="all, delete-orphan",
    )
    actions: Mapped[list["ControlAction"]] = relationship(
        back_populates="control_case",
        cascade="all, delete-orphan",
        order_by="ControlAction.sequence_no",
    )
    violations: Mapped[list["Violation"]] = relationship(  # noqa: F821
        back_populates="control_case",
        cascade="all, delete-orphan",
    )
    prescriptions: Mapped[list["Prescription"]] = relationship(  # noqa: F821
        back_populates="control_case",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[list["Decision"]] = relationship(  # noqa: F821
        back_populates="control_case",
        cascade="all, delete-orphan",
    )


class ControlCaseInspector(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "control_case_inspectors"
    __table_args__ = (
        UniqueConstraint(
            "control_case_id",
            "inspector_id",
            name="uq_control_case_inspectors_case_inspector",
        ),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    inspector_id: Mapped[int] = mapped_column(
        ForeignKey("inspectors.id"), nullable=False
    )
    role: Mapped[InspectorRole] = mapped_column(
        code_enum(InspectorRole, "inspector_role"),
        nullable=False,
        server_default=InspectorRole.PARTICIPANT.value,
    )

    control_case: Mapped["ControlCase"] = relationship(back_populates="inspectors")
    inspector: Mapped["Inspector"] = relationship()


class ControlCaseBase(IntIdMixin, TimestampMixin, Base):
    """Основание проведения мероприятия.

    Оснований бывает несколько и они разнородные (материал МУ, обращение
    жителя, ранее выданное предписание, требование прокуратуры), поэтому
    это отдельная таблица, а не поле в деле.
    """

    __tablename__ = "control_case_bases"
    __table_args__ = (
        Index("ix_control_case_bases_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[CaseBaseKind] = mapped_column(
        code_enum(CaseBaseKind, "case_base_kind"), nullable=False
    )
    document_number: Mapped[str | None] = mapped_column(String(100))
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    appeal_id: Mapped[int | None] = mapped_column(
        ForeignKey("appeals.id", ondelete="SET NULL")
    )
    prescription_id: Mapped[int | None] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="SET NULL")
    )
    npa_id: Mapped[int | None] = mapped_column(ForeignKey("npa.id"))
    description: Mapped[str | None] = mapped_column(Text)

    control_case: Mapped["ControlCase"] = relationship(back_populates="bases")
    appeal: Mapped["Appeal | None"] = relationship()
    prescription: Mapped["Prescription | None"] = relationship()  # noqa: F821
    npa: Mapped["Npa | None"] = relationship()


class ControlCaseParty(IntIdMixin, TimestampMixin, Base):
    """Снимок участников дела на момент его создания.

    Фиксирует конкретные версии реквизитов, подписантов и контактов:
    если у организации завтра новые реквизиты, уже начатое дело продолжает
    ссылаться на прежние, и печать документов не «поедет».
    """

    __tablename__ = "control_case_parties"
    __table_args__ = (
        UniqueConstraint(
            "control_case_id",
            "party_kind",
            "organization_id",
            "unit_id",
            name="uq_control_case_parties_case_kind_org_unit",
        ),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    party_kind: Mapped[CasePartyKind] = mapped_column(
        code_enum(CasePartyKind, "case_party_kind"), nullable=False
    )

    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL")
    )
    requisite_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_requisites.id", ondelete="SET NULL")
    )
    signatory_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_signatories.id", ondelete="SET NULL")
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_contacts.id", ondelete="SET NULL")
    )

    control_case: Mapped["ControlCase"] = relationship(back_populates="parties")
    organization: Mapped["Organization | None"] = relationship()
    unit: Mapped["OrganizationUnit | None"] = relationship()
    requisite: Mapped["OrganizationRequisite | None"] = relationship()
    signatory: Mapped["OrganizationSignatory | None"] = relationship()
    contact: Mapped["OrganizationContact | None"] = relationship()


class ControlAction(IntIdMixin, TimestampMixin, Base):
    """Контрольное (надзорное) действие со своими сроками и местом."""

    __tablename__ = "control_actions"
    __table_args__ = (
        Index("ix_control_actions_control_case_id", "control_case_id"),
    )

    control_case_id: Mapped[int] = mapped_column(
        ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    action_type: Mapped[ControlActionType] = mapped_column(
        code_enum(ControlActionType, "control_action_type"), nullable=False
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    place_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))

    result_text: Mapped[str | None] = mapped_column(Text)
    # Осмотр бывает первичный (выявляет нарушение) и повторный (проверяет,
    # устранено ли оно). У повторного заполняется результат осмотра.
    inspection_kind: Mapped[InspectionKind] = mapped_column(
        code_enum(InspectionKind, "inspection_kind"),
        nullable=False,
        server_default=text("'primary'"),
    )
    inspection_result: Mapped[InspectionResult | None] = mapped_column(
        code_enum(InspectionResult, "inspection_result")
    )
    is_violation_found: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # «По результатам которого составлен: протокол осмотра от 22.09.2026»
    result_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )

    control_case: Mapped["ControlCase"] = relationship(back_populates="actions")
    place_address: Mapped["Address | None"] = relationship()
    result_document: Mapped["Document | None"] = relationship()  # noqa: F821

    inspectors: Mapped[list["ControlActionInspector"]] = relationship(
        back_populates="control_action",
        cascade="all, delete-orphan",
    )
    files: Mapped[list["ControlActionFile"]] = relationship(
        back_populates="control_action",
        cascade="all, delete-orphan",
        order_by="ControlActionFile.sequence_no",
    )


class ControlActionInspector(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "control_action_inspectors"
    __table_args__ = (
        UniqueConstraint(
            "control_action_id",
            "inspector_id",
            name="uq_control_action_inspectors_action_inspector",
        ),
    )

    control_action_id: Mapped[int] = mapped_column(
        ForeignKey("control_actions.id", ondelete="CASCADE"), nullable=False
    )
    inspector_id: Mapped[int] = mapped_column(
        ForeignKey("inspectors.id"), nullable=False
    )

    control_action: Mapped["ControlAction"] = relationship(back_populates="inspectors")
    inspector: Mapped["Inspector"] = relationship()


class ControlActionFile(IntIdMixin, TimestampMixin, Base):
    """Фотоматериал или видеозапись, привязанные к контрольному действию."""

    __tablename__ = "control_action_files"
    __table_args__ = (
        UniqueConstraint(
            "control_action_id",
            "file_id",
            name="uq_control_action_files_action_file",
        ),
    )

    control_action_id: Mapped[int] = mapped_column(
        ForeignKey("control_actions.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    caption: Mapped[str | None] = mapped_column(String(500))
    # У осмотра одна фотография, но хранится она двумя файлами: размеченная
    # копия идёт в документы, оригинал остаётся для повторной разметки.
    photo_kind: Mapped[PhotoKind | None] = mapped_column(
        code_enum(PhotoKind, "photo_kind")
    )
    # Цвет надписи на фотографии: белый виден не на каждом снимке.
    annotation_color: Mapped[str | None] = mapped_column(String(20))
    sequence_no: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    control_action: Mapped["ControlAction"] = relationship(back_populates="files")
    file: Mapped["StoredFile"] = relationship()
