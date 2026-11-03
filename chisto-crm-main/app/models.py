from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utc_now

Json = JSON().with_variant(JSONB(), "postgresql")
TS = DateTime(timezone=True)

# --- Справочники (мастер-данные, которые DG читает через /api/v1/integration) ---

executor_violation_types = Table(
    "executor_violation_types",
    Base.metadata,
    Column("executor_id", ForeignKey("executors.executor_id", ondelete="CASCADE"), primary_key=True),
    Column(
        "type_violation_id",
        ForeignKey("violation_types.type_violation_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


class Territory(Base):
    """Участок закрепления инженера (округ, район обхода)."""

    __tablename__ = "territories"
    territory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # Прямоугольник {south, west, north, east} — как в снимке DG; полигон добавим, когда появится.
    bounds: Mapped[dict[str, Any] | None] = mapped_column(Json, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Engineer(Base):
    __tablename__ = "engineers"
    engineer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # Телефон в E.164 — по нему бот находит инженера при первой регистрации.
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    max_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utc_now, onupdate=utc_now)

    assignments: Mapped[list[Assignment]] = relationship(back_populates="engineer")


class ViolationType(Base):
    __tablename__ = "violation_types"
    type_violation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Ключ из справочника бота («ddhib.potholes»), чтобы сверяться без привязки к названию.
    code: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    requires_description: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Executor(Base):
    """Организация-исполнитель: ведомство, УК, регоператор."""

    __tablename__ = "executors"
    executor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    full_name: Mapped[str] = mapped_column(String(500), default="")
    # Вид организации для фронта: UK, REG_OPERATOR, OMSU, DRT, UPRAVA, MPR, GZHI.
    kind: Mapped[str] = mapped_column(String(16), default="OMSU", server_default="OMSU")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    violation_types: Mapped[list[ViolationType]] = relationship(
        secondary=executor_violation_types, order_by=ViolationType.type_violation_id
    )


class Assignment(Base):
    """Назначение инженера на участок. Текущее — активное с самой поздней датой начала."""

    __tablename__ = "assignments"
    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    engineer_id: Mapped[str] = mapped_column(ForeignKey("engineers.engineer_id", ondelete="CASCADE"))
    territory_id: Mapped[str] = mapped_column(ForeignKey("territories.territory_id", ondelete="RESTRICT"))
    route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now)

    engineer: Mapped[Engineer] = relationship(back_populates="assignments")
    territory: Mapped[Territory] = relationship()


# --- Регистрация инженеров из бота (через DG) ---


class BotRegistration(Base):
    __tablename__ = "bot_registrations"
    registration_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(512), unique=True)
    registration_event_id: Mapped[str] = mapped_column(String(64))
    # Отпечаток (max_user_id + телефон): повтор ключа с другими данными — 409.
    fingerprint: Mapped[str] = mapped_column(String(64))
    max_user_id: Mapped[str] = mapped_column(String(128), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    engineer_id: Mapped[str | None] = mapped_column(
        ForeignKey("engineers.engineer_id", ondelete="SET NULL"), nullable=True
    )
    # Ответ DG сохраняем целиком: повтор того же запроса возвращает его без изменений.
    response: Mapped[dict[str, Any]] = mapped_column(Json)
    requested_at: Mapped[datetime] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --- Приём событий из DG ---


class IncomingEvent(Base):
    """Входящие (inbox): событие записано — DG получает 202, разбор идёт отдельно."""

    __tablename__ = "incoming_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    envelope: Mapped[dict[str, Any]] = mapped_column(Json)
    canonical: Mapped[dict[str, Any]] = mapped_column(Json)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(128))
    source_event_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(TS, default=utc_now, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class Case(Base):
    """Дело о нарушении, заведённое по событию DG: с обхода инженера или из внешнего источника."""

    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("incoming_events.event_id", ondelete="RESTRICT"), unique=True
    )
    # У проблемы из домовых чатов нет инженера и назначения; исполнитель и тип могут не найтись
    engineer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    executor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    type_violation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    territory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    media: Mapped[list[dict[str, Any]]] = mapped_column(Json, default=list)
    reported_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    # Маршрут дела (app/workflow.py): NEW → IN_PROGRESS → VERIFICATION → CLOSED, просрочка → KNM_ESCALATION.
    status: Mapped[str] = mapped_column(String(32), index=True)
    # Расхождение события со справочниками CRM; дело всё равно NEW, решает инспектор.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="INSPECTION", server_default="INSPECTION")
    priority: Mapped[str] = mapped_column(String(8), default="MEDIUM", server_default="MEDIUM")
    validated_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(TS, nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # FIXED | FALSE_POSITIVE
    # Фотоотчёт исполнителя: путь к файлу в хранилище CRM, время и место съёмки.
    report: Mapped[dict[str, Any] | None] = mapped_column(Json, nullable=True)
    # Контейнерная площадка из реестра КП (app/kp.py): привязка по точке события, способ и уверенность.
    kp_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kp_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    kp_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Проблема во внешнем источнике («domovoy:<problem_id>»): её ревизии обновляют это же дело (app/inbox.py)
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    external_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external: Mapped[dict[str, Any] | None] = mapped_column(Json, nullable=True)
    document_service_case_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_service_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_service_readiness: Mapped[dict[str, Any] | None] = mapped_column(Json, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utc_now, onupdate=utc_now)

    history: Mapped[list[CaseHistory]] = relationship(
        order_by="CaseHistory.id", cascade="all, delete-orphan", back_populates="case"
    )


class CaseHistory(Base):
    """Хроника дела: кто, когда и что сделал. Записи не меняются и не удаляются."""

    __tablename__ = "case_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    action: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    actor_type: Mapped[str] = mapped_column(String(16))  # AI | INSPECTOR | UK | SYSTEM — как во фронте
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)

    case: Mapped[Case] = relationship(back_populates="history")


class DgIntegration(Base):
    __tablename__ = "dg_integration"
    singleton: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    consumer_key: Mapped[str] = mapped_column(String(64))
    webhook_signing_secret: Mapped[str] = mapped_column(String(512))
    datagateway_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    configured_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    last_delivery_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


# --- Реестр контейнерных площадок (КП) ---
# «Справочник КП и ведение карточек» (раздел 4): карточка собирается из источников, сырые снимки лежат
# рядом, каждое изменение — в журнале. Без PostGIS: точка — две колонки, поиск по окну координат и
# расстояние в коде (площадок в городе ~3 тыс.).


class Kp(Base):
    """Карточка контейнерной площадки. Не удаляется никогда — только deleted_at: на неё ссылаются дела."""

    __tablename__ = "kp"
    kp_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # LP-000123 — для бота и общения
    registry_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # наименование в источнике («01-С264»)
    # active, unverified, planned, relocated, liquidated, duplicate, missing_in_source
    status: Mapped[str] = mapped_column(String(24), default="unverified", index=True)
    duplicate_of: Mapped[str | None] = mapped_column(ForeignKey("kp.kp_id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(200), nullable=True)
    settlement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_house: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float)
    location_source: Mapped[str] = mapped_column(String(16), default="utko")  # utko, omsu, field, manual
    location_accuracy_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ASPHALT, CONCRETE, SOIL
    has_fence: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_roof: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    containers_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    containers_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    separate_collection: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kgo_storage: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_executor_id: Mapped[str | None] = mapped_column(
        ForeignKey("executors.executor_id", ondelete="SET NULL"), nullable=True
    )
    in_yard: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    in_yard_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    land_parcel_cadnum: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Кто последним заполнил поле: {"area_m2": "utko", "location": "manual"} — матрица владения (раздел 5.3)
    field_sources: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    # Почему карточку надо проверить: источник сдвинул точку, пропала из выгрузки и т. п.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)

    containers: Mapped[list[KpContainer]] = relationship(
        order_by="KpContainer.id", cascade="all, delete-orphan", back_populates="kp"
    )
    responsibles: Mapped[list[KpResponsible]] = relationship(
        order_by="(KpResponsible.priority, KpResponsible.id)", cascade="all, delete-orphan", back_populates="kp"
    )
    external_ids: Mapped[list[KpExternalId]] = relationship(cascade="all, delete-orphan", back_populates="kp")
    owner: Mapped[Executor | None] = relationship()


class KpContainer(Base):
    """Контейнер на площадке. При смене состава старые закрываются valid_to, а не удаляются."""

    __tablename__ = "kp_container"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kp_id: Mapped[str] = mapped_column(ForeignKey("kp.kp_id", ondelete="CASCADE"), index=True)
    number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    container_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    waste_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="utko")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    kp: Mapped[Kp] = relationship(back_populates="containers")


class KpExternalId(Base):
    """ID площадки во внешней системе (для ФГИС УТКО — GUID). По нему идёт синхронизация."""

    __tablename__ = "kp_external_id"
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kp_id: Mapped[str] = mapped_column(ForeignKey("kp.kp_id", ondelete="CASCADE"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(TS, default=utc_now)

    kp: Mapped[Kp] = relationship(back_populates="external_ids")


class KpSourceRecord(Base):
    """Сырой снимок записи источника. Пишется, когда запись новая или изменилась (по хешу)."""

    __tablename__ = "kp_source_record"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    kp_id: Mapped[str | None] = mapped_column(ForeignKey("kp.kp_id", ondelete="SET NULL"), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(Json)
    payload_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    match_status: Mapped[str] = mapped_column(String(16), default="new")  # new, matched, conflict, ignored
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class KpResponsible(Base):
    """Кто за что отвечает на площадке: роль, организация, основание, подтверждено ли."""

    __tablename__ = "kp_responsible"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kp_id: Mapped[str] = mapped_column(ForeignKey("kp.kp_id", ondelete="CASCADE"), index=True)
    # site_maintenance, waste_removal, new_site_decision, territory, supervision
    role: Mapped[str] = mapped_column(String(32))
    executor_id: Mapped[str] = mapped_column(ForeignKey("executors.executor_id", ondelete="RESTRICT"), index=True)
    basis: Mapped[str | None] = mapped_column(String(32), nullable=True)  # rule, registry_owner, contract, manual…
    share_schedule: Mapped[dict[str, Any] | None] = mapped_column(Json, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    kp: Mapped[Kp] = relationship(back_populates="responsibles")
    executor: Mapped[Executor] = relationship()


class KpChangeLog(Base):
    """История карточки: поле, было, стало, кто и почему. Записи не меняются."""

    __tablename__ = "kp_change_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kp_id: Mapped[str] = mapped_column(ForeignKey("kp.kp_id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Any] = mapped_column(Json, nullable=True)
    new_value: Mapped[Any] = mapped_column(Json, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    source_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("kp_source_record.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(TS, default=utc_now, index=True)
    actor: Mapped[str] = mapped_column(String(128))  # sync:utko, user:<логин>, rule
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Применено ли: источник ниже по приоритету не перезаписывает поле — его значение только в журнале
    applied: Mapped[bool] = mapped_column(Boolean, default=True)


# --- Пользователи CRM и расширяемые роли ---

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_code", ForeignKey("roles.code", ondelete="CASCADE"), primary_key=True),
    Column("permission_code", ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_code", ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class Role(Base):
    """Роль — набор прав. Новые роли заводятся данными, без правки кода."""

    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, order_by=Permission.code
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    # Аккаунт организации (ведомство, УК, регоператор): видит только её дела.
    executor_id: Mapped[str | None] = mapped_column(
        ForeignKey("executors.executor_id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Растёт при смене пароля и отключении — старые сессии перестают действовать.
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(TS, default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, order_by=Role.code)
    executor: Mapped[Executor | None] = relationship()

    @property
    def permission_codes(self) -> set[str]:
        return {p.code for role in self.roles for p in role.permissions}


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(TS, default=utc_now, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
