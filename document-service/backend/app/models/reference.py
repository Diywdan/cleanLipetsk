"""Справочники, нормативные акты и адреса.

Смысловые перечни (статусы, типы документов, виды контроля) хранятся
таблицами, а не перечислениями: интеграция с CRM добавляет строку,
а не миграцию типа.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntIdMixin, TimestampMixin


class Address(IntIdMixin, TimestampMixin, Base):
    """Адрес в нормализованном виде плюс готовая строка для печати."""

    __tablename__ = "addresses"

    postal_code: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(255))
    district: Mapped[str | None] = mapped_column(String(255))
    locality: Mapped[str | None] = mapped_column(String(255))
    street: Mapped[str | None] = mapped_column(String(255))
    house: Mapped[str | None] = mapped_column(String(50))
    building: Mapped[str | None] = mapped_column(String(50))
    structure: Mapped[str | None] = mapped_column(String(50))
    apartment: Mapped[str | None] = mapped_column(String(50))
    fias_guid: Mapped[str | None] = mapped_column(String(36), index=True)
    # ГАР — государственный адресный реестр, пришедший на смену ФИАС.
    gar_guid: Mapped[str | None] = mapped_column(String(36), index=True)

    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))

    # «398600, Липецкая область, г Липецк, ул. Московская, д 8 а» — в документ
    # подставляется именно эта строка, а не результат склейки на лету.
    full_address: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Приведённый к единому виду адрес: по нему адрес находится при повторном
    # вводе (чтобы не плодить дубли) и выполняется поиск по части строки.
    search_key: Mapped[str | None] = mapped_column(String(500), index=True)

    # Устаревший адрес не удаляется, если на него ссылаются документы:
    # он уходит в архив и перестаёт предлагаться в списках.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    notes: Mapped[str | None] = mapped_column(Text)


class Npa(IntIdMixin, TimestampMixin, Base):
    """Нормативный правовой акт."""

    __tablename__ = "npa"

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    # «в нарушении … Правил благоустройства территорий города Липецка» —
    # название в родительном падеже печатается в протоколе осмотра.
    title_genitive: Mapped[str | None] = mapped_column(String(1000))
    number: Mapped[str | None] = mapped_column(String(100))
    adopted_on: Mapped[date | None] = mapped_column(Date)
    adopted_by: Mapped[str | None] = mapped_column(String(500))
    # «…, утверждённых решением Липецкого городского Совета депутатов»: в
    # требовании предписания название органа стоит в родительном падеже.
    # Заполняется только у актов, которые утверждены решением органа власти;
    # у федеральных законов этого оборота нет, поэтому поле пустое.
    adopted_by_genitive: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    articles: Mapped[list["NpaArticle"]] = relationship(
        back_populates="npa",
        cascade="all, delete-orphan",
    )


class NpaArticle(IntIdMixin, TimestampMixin, Base):
    """Структурная единица НПА: статья, часть, пункт, подпункт.

    Квалификация нарушения в документах составная
    («пункта 5.2 части 5 статьи 5, частей 7 и 12 статьи 14»), поэтому
    часть и пункт — отдельные поля, а reference_template хранит готовую
    строку для печати.
    """

    __tablename__ = "npa_articles"
    __table_args__ = (
        # Область ограничения — конкретная норма, а не НПА целиком:
        # у одного акта одновременно действует множество статей.
        ExcludeConstraint(
            ("npa_id", "="),
            (literal_column("COALESCE(article_number, '')"), "="),
            (literal_column("COALESCE(part_number, '')"), "="),
            (literal_column("COALESCE(point_number, '')"), "="),
            (literal_column("COALESCE(subpoint_number, '')"), "="),
            (literal_column("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_npa_articles_period",
            using="gist",
        ),
        Index("ix_npa_articles_ref", "npa_id", "article_number", "part_number"),
    )

    npa_id: Mapped[int] = mapped_column(
        ForeignKey("npa.id", ondelete="CASCADE"), nullable=False
    )
    article_number: Mapped[str | None] = mapped_column(String(50))
    part_number: Mapped[str | None] = mapped_column(String(50))
    point_number: Mapped[str | None] = mapped_column(String(50))
    subpoint_number: Mapped[str | None] = mapped_column(String(50))

    text: Mapped[str | None] = mapped_column(Text)
    reference_template: Mapped[str] = mapped_column(String(500), nullable=False)

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)

    npa: Mapped["Npa"] = relationship(back_populates="articles")


class ViolationType(IntIdMixin, TimestampMixin, Base):
    """Типовое нарушение по обращениям о благоустройстве."""

    __tablename__ = "violation_types"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Что именно не сделано: «нарушенное благоустройство в полном объёме после
    # производства земляных работ». В описание нарушения это идёт после «не
    # восстановлено», в требование — после действия, поэтому хранится
    # отдельно от названия вида нарушения.
    name_accusative: Mapped[str | None] = mapped_column(String(500))
    # Что предписано сделать с работами: «восстановление нарушенного
    # благоустройства». Если пусто — «работы по устранению нарушения».
    requirement_object: Mapped[str | None] = mapped_column(String(500))
    # Действие по умолчанию для предписания: код из services/violation_text.
    default_action: Mapped[str | None] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Признак ИЖ: снятая галочка означает многоквартирный дом — таких видов
    # нарушений большинство, и это состояние по умолчанию. В документах
    # название печатается с уточнением: «Дворовая территория (ИЖ)».
    is_individual_housing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Нормы, по которым вид нарушения квалифицируется. Список короткий —
    # именно его показывают делопроизводителю, чтобы не выбирать из всех
    # статей Правил. Статью, которой здесь нет, всё равно можно выбрать:
    # справочник норм доступен целиком.
    articles: Mapped[list["ViolationTypeArticle"]] = relationship(
        back_populates="violation_type",
        cascade="all, delete-orphan",
    )


class ViolationTypeArticle(IntIdMixin, TimestampMixin, Base):
    """Связь вида нарушения с нормой права.

    Связь множественная: одно нарушение может квалифицироваться несколькими
    нормами, одна норма — относиться к нескольким видам нарушений.
    """

    __tablename__ = "violation_type_articles"
    __table_args__ = (
        UniqueConstraint(
            "violation_type_id",
            "npa_article_id",
            name="uq_violation_type_articles_type_article",
        ),
    )

    violation_type_id: Mapped[int] = mapped_column(
        ForeignKey("violation_types.id", ondelete="CASCADE"), nullable=False
    )
    npa_article_id: Mapped[int] = mapped_column(
        ForeignKey("npa_articles.id", ondelete="CASCADE"), nullable=False
    )
    # Основная норма: её подставляют в документы по умолчанию.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    violation_type: Mapped["ViolationType"] = relationship(back_populates="articles")
    npa_article: Mapped["NpaArticle"] = relationship()


class Work(IntIdMixin, TimestampMixin, Base):
    """Вид работ, который указывают в нарушении и предписании.

    В документах одна и та же работа называется по-разному: в описании
    нарушения — «не восстановлено … асфальт – 4 кв.м.», в требовании —
    «восстановить асфальт – 4 кв.м.». Поэтому форма слова хранится отдельно,
    а объём печатается числом с единицей из справочника: так «кв.м» и «шт.»
    не расходятся по документам.
    """

    __tablename__ = "works"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    # «восстановить асфальт»: в требовании работа стоит в винительном падеже.
    name_accusative: Mapped[str | None] = mapped_column(String(500))
    # «шт.» — целое количество; «кв.м.» — допускает дробное.
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    is_measurable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ViolationTypeWork(IntIdMixin, TimestampMixin, Base):
    """Какие работы подсказывать для вида нарушения.

    Связь ограничивает только подсказку в форме: работу, которой здесь нет,
    всё равно можно выбрать — справочник работ доступен целиком.
    """

    __tablename__ = "violation_type_works"
    __table_args__ = (
        UniqueConstraint(
            "violation_type_id",
            "work_id",
            name="uq_violation_type_works_type_work",
        ),
    )

    violation_type_id: Mapped[int] = mapped_column(
        ForeignKey("violation_types.id", ondelete="CASCADE"), nullable=False
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )

    violation_type: Mapped["ViolationType"] = relationship()
    work: Mapped["Work"] = relationship()


class CaseTextOption(IntIdMixin, TimestampMixin, Base):
    """Готовые формулировки цели проведения и предмета заявки.

    Цель и предмет — длинные юридические фразы: набирать их руками в каждой
    заявке бессмысленно, а опечатка меняет текст документа. Поэтому они
    выбираются из списков.

    Формулировка хранится в заявке текстом, а не ссылкой: если запись в
    справочнике потом поправят, уже созданные заявки и документы по ним
    останутся прежними.
    """

    __tablename__ = "case_text_options"
    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_case_text_options_kind_value"),
        Index("ix_case_text_options_kind", "kind", "sort_order"),
    )

    # purpose — цель проведения, subject — предмет.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Поле называется value, а не text: имя text перекрыло бы функцию text()
    # из sqlalchemy, которой задаются значения по умолчанию ниже.
    value: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class AppealSource(IntIdMixin, TimestampMixin, Base):
    """Источник обращения: устное, письменное, материал МУ, прокуратура."""
    __tablename__ = "appeal_sources"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ControlObjectType(IntIdMixin, TimestampMixin, Base):
    """Вид объекта контроля (перечень из инструкции по пакету документов)."""

    __tablename__ = "control_object_types"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ControlKind(IntIdMixin, TimestampMixin, Base):
    """Вид контроля: «Муниципальный контроль в сфере благоустройства…»."""

    __tablename__ = "control_kinds"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    # В бланках вид контроля печатается в родительном падеже:
    # «проводится в рамках: Муниципального контроля в сфере благоустройства…».
    # Падежные формы хранятся данными, а не выводятся морфологией.
    name_genitive: Mapped[str | None] = mapped_column(String(1000))
    registry_code: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ControlForm(IntIdMixin, TimestampMixin, Base):
    """Форма мероприятия: выездное обследование, инспекционный визит и т. д."""

    __tablename__ = "control_forms"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    # «по результатам проведенного выездного обследования» — в решении форма
    # контроля стоит в родительном падеже.
    name_genitive: Mapped[str | None] = mapped_column(String(500))
    is_without_interaction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ControlCaseStatus(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "control_case_statuses"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class PrescriptionStatus(IntIdMixin, TimestampMixin, Base):
    """Виды предписания: первичное, повторное, исполненное, продлено и т. д."""

    __tablename__ = "prescription_statuses"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class DocumentType(IntIdMixin, TimestampMixin, Base):
    """Тип документа пакета: задание, акт, протокол осмотра, решение и т. д."""

    __tablename__ = "document_types"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    # Внешняя нумерация: номер и код присваивает портал прокуратуры (ЕРКНМ).
    uses_external_number: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class DocumentStatus(IntIdMixin, TimestampMixin, Base):
    __tablename__ = "document_statuses"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class PackageKind(IntIdMixin, TimestampMixin, Base):
    """Вид пакета: первичное, повторное, исполненное предписание."""

    __tablename__ = "package_kinds"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    documents: Mapped[list["PackageKindDocument"]] = relationship(
        back_populates="package_kind",
        cascade="all, delete-orphan",
        order_by="PackageKindDocument.sequence_no",
    )


class PackageKindDocument(IntIdMixin, Base):
    """Состав пакета: какие документы входят и в каком порядке.

    Правила «при вторичном предписании добавляется уведомление о явке»
    и «исполненное предписание — три документа» описываются данными,
    а не ветвлениями в коде генератора.
    """

    __tablename__ = "package_kind_documents"
    __table_args__ = (
        UniqueConstraint(
            "package_kind_id",
            "document_type_id",
            name="uq_package_kind_documents_kind_type",
        ),
    )

    package_kind_id: Mapped[int] = mapped_column(
        ForeignKey("package_kinds.id", ondelete="CASCADE"), nullable=False
    )
    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    package_kind: Mapped["PackageKind"] = relationship(back_populates="documents")
    document_type: Mapped["DocumentType"] = relationship()


class NumberSequence(IntIdMixin, TimestampMixin, Base):
    """Внутренняя нумерация документов (задание, уведомление, протокол).

    Номера акта, решения и предписания присваивает портал прокуратуры,
    поэтому для них счётчик не ведётся.
    """

    __tablename__ = "number_sequences"
    __table_args__ = (
        UniqueConstraint(
            "document_type_id",
            "year",
            "prefix",
            name="uq_number_sequences_type_year_prefix",
        ),
    )

    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    prefix: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("''")
    )
    last_value: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    document_type: Mapped["DocumentType"] = relationship()
