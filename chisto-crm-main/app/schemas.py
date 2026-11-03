from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.security import PERMISSIONS, normalize_phone


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# =====================================================================
# Контракт DG → CRM: datagateway.violation/1.0 (docs/max_dg_crm_contract_v1.md §18)
# Поля и ограничения совпадают с моделью DG — менять только вместе с ней.
# =====================================================================


class CanonicalTimestamps(Strict):
    reported_at: AwareDatetime | None = None
    received_at: AwareDatetime
    processed_at: AwareDatetime


class CanonicalSource(Strict):
    type: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)


class CanonicalReporter(Strict):
    engineer_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)


class TerritoryValidation(Strict):
    status: Literal["completed", "unavailable", "not_checked"] = "not_checked"
    is_inside: bool | None = None
    distance_to_boundary_meters: float | None = Field(default=None, ge=0)


class CanonicalAssignment(Strict):
    id: str = Field(min_length=1, max_length=128)
    territory_id: str = Field(min_length=1, max_length=128)
    territory_validation: TerritoryValidation


class CanonicalExecutor(Strict):
    executor_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)


class CanonicalViolationType(Strict):
    type_violation_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    selected_by: Literal["inspector"] = "inspector"


class CanonicalViolationBody(Strict):
    executor: CanonicalExecutor
    type: CanonicalViolationType
    comment: str | None = Field(default=None, max_length=4000)


class CanonicalCoordinates(Strict):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CanonicalLocation(Strict):
    coordinates: CanonicalCoordinates
    accuracy_meters: float | None = Field(default=None, ge=0)
    address: dict[str, Any] | None = None
    territory: dict[str, Any] | None = None
    district: dict[str, Any] | None = None


class CanonicalMediaStorage(Strict):
    provider: Literal["s3"] = "s3"
    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=1024)


class CanonicalMediaItem(Strict):
    id: str = Field(min_length=1, max_length=1024)
    type: Literal["image", "video"]
    storage: CanonicalMediaStorage
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalValidation(Strict):
    engineer_valid: bool
    executor_valid: bool
    violation_type_valid: bool
    executor_violation_relation_valid: bool
    assignment_valid: bool


class CanonicalEnrichment(Strict):
    geo: dict[str, Any]
    references: dict[str, Any]
    ai: dict[str, Any]


class CanonicalDeduplication(Strict):
    status: Literal["checked", "not_checked"]
    is_possible_duplicate: bool
    matches: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalQuality(Strict):
    score: float = Field(ge=0, le=1)
    checks: dict[str, bool]
    warnings: list[str] = Field(default_factory=list)


class CanonicalProcessing(Strict):
    trace_id: str = Field(min_length=1, max_length=128)
    status: Literal["completed"] = "completed"


class CanonicalViolationEventV1(Strict):
    schema_name: Literal["datagateway.violation"] = Field(default="datagateway.violation", alias="schema")
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    event_type: Literal["violation"] = "violation"
    timestamps: CanonicalTimestamps
    source: CanonicalSource
    reporter: CanonicalReporter
    assignment: CanonicalAssignment
    violation: CanonicalViolationBody
    location: CanonicalLocation
    media: list[CanonicalMediaItem]
    validation: CanonicalValidation
    enrichment: CanonicalEnrichment
    deduplication: CanonicalDeduplication
    quality: CanonicalQuality
    processing: CanonicalProcessing


# =====================================================================
# Контракт DG → CRM: datagateway.waste_site_problem/1.0 — проблема на КП от жителей
# (Домовой ГЖИ, data_gateway_48: domain/waste_site_problem/schemas.py). Менять вместе с DG.
# =====================================================================


class WspCoordinates(Strict):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class WspSource(Strict):
    type: str = Field(min_length=1, max_length=64)
    system: str | None = Field(default=None, max_length=64)
    channel: str | None = Field(default=None, max_length=64)
    problem_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    external_id: str = Field(min_length=1, max_length=255)
    event_type: str | None = Field(default=None, max_length=128)


class WspTimestamps(Strict):
    first_reported_at: AwareDatetime | None = None
    last_reported_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    received_at: AwareDatetime


class WspWasteSite(Strict):
    utko_id: str | None = Field(default=None, max_length=128)
    registry_number: str | None = Field(default=None, max_length=128)
    code: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=1000)
    municipality: str | None = Field(default=None, max_length=500)
    coordinates: WspCoordinates | None = None
    containers_qty: int | None = Field(default=None, ge=0)
    containers_volume_m3: float | None = Field(default=None, ge=0)
    match_score: float | None = Field(default=None, ge=0, le=1)
    match_presumed: bool | None = None


class WspLocation(Strict):
    coordinates: WspCoordinates
    address: str | None = Field(default=None, max_length=1000)
    municipality: str | None = Field(default=None, max_length=500)


class WspTheme(Strict):
    eds_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=500)
    short_name: str | None = Field(default=None, max_length=200)
    group: str | None = Field(default=None, max_length=200)


class WspOrganization(Strict):
    name: str = Field(min_length=1, max_length=500)
    inn: str | None = Field(default=None, max_length=12)
    kind: str | None = Field(default=None, max_length=200)


class WspResponsibleHint(Strict):
    preliminary: bool = True
    basis: str | None = Field(default=None, max_length=2000)
    organizations: list[WspOrganization] = Field(default_factory=list)


class WspProblem(Strict):
    theme: WspTheme
    status: str = Field(min_length=1, max_length=32)
    summary: str | None = Field(default=None, max_length=4000)
    houses_count: int | None = Field(default=None, ge=0)
    messages_count: int | None = Field(default=None, ge=0)
    residents_count: int | None = Field(default=None, ge=0)
    media_count: int | None = Field(default=None, ge=0)
    responsible_hint: WspResponsibleHint | None = None


class WspMessage(Strict):
    message_id: str = Field(min_length=1, max_length=255)
    sent_at: AwareDatetime | None = None
    author: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=8000)
    media_ids: list[str] = Field(default_factory=list)


class WspHouse(Strict):
    fias: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=1000)
    coordinates: WspCoordinates | None = None
    distance_to_site_m: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=4000)
    resolved: bool | None = None
    resolved_at: AwareDatetime | None = None
    messages: list[WspMessage] = Field(default_factory=list)


class WspProcessing(Strict):
    trace_id: str | None = Field(default=None, max_length=128)


class CanonicalWasteSiteProblemV1(Strict):
    schema_name: Literal["datagateway.waste_site_problem"] = Field(
        default="datagateway.waste_site_problem", alias="schema"
    )
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    event_type: Literal["waste_site_problem"] = "waste_site_problem"
    source: WspSource
    timestamps: WspTimestamps
    waste_site: WspWasteSite | None = None
    location: WspLocation
    problem: WspProblem
    houses: list[WspHouse] = Field(default_factory=list)
    media: list[CanonicalMediaItem] = Field(default_factory=list)
    processing: WspProcessing


CanonicalEvent = Annotated[
    CanonicalViolationEventV1 | CanonicalWasteSiteProblemV1, Field(discriminator="event_type")
]


class DataGatewayEventEnvelope(Strict):
    event_id: UUID
    event_type: Literal["violation", "waste_site_problem"]
    source: str = Field(min_length=1, max_length=128)
    source_event_id: str = Field(min_length=1, max_length=255)
    canonical: CanonicalEvent
    emitted_at: AwareDatetime

    @model_validator(mode="after")
    def same_event_type(self) -> DataGatewayEventEnvelope:
        if self.canonical.event_type != self.event_type:
            raise ValueError("event_type конверта не совпадает с каноническим событием")
        return self


class DataGatewayConfigureInput(Strict):
    consumer_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_-]+$")
    webhook_signing_secret: SecretStr = Field(min_length=32, max_length=512)
    datagateway_url: str | None = Field(default=None, max_length=2000)


# --- Регистрация инженера (§23): DG → CRM ---


class BotRegistrationRequest(Strict):
    schema_name: Literal["datagateway.bot_user_registration"] = Field(
        default="datagateway.bot_user_registration", alias="schema"
    )
    schema_version: Literal["1.0"] = "1.0"
    registration_event_id: UUID
    idempotency_key: str = Field(min_length=4, max_length=512)
    max_user_id: str = Field(min_length=2, max_length=128)
    phone: str = Field(min_length=10, max_length=20)
    requested_at: AwareDatetime


RegistrationStatus = Literal["registered", "already_registered", "pending_review", "rejected", "conflict"]


# =====================================================================
# Админка CRM
# =====================================================================


class LoginInput(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class Bounds(Strict):
    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)


class TerritoryIn(Strict):
    name: str = Field(min_length=2, max_length=200)
    bounds: Bounds | None = None
    is_active: bool = True


class TerritoryPatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    bounds: Bounds | None = None
    is_active: bool | None = None


def _phone(value: str | None) -> str | None:
    return normalize_phone(value) if value is not None else None


def _email(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Некорректный email")
    return value.lower()


def _max_id(value: str | None) -> str | None:
    """MAX user ID, заданный администратором; пусто — не привязан. Ограничения как у регистрации из бота."""
    if value is None or value == "":
        return None
    if not re.fullmatch(r"\S{2,128}", value):
        raise ValueError("MAX user ID: от 2 до 128 символов, без пробелов")
    return value


class EngineerIn(Strict):
    full_name: str = Field(min_length=3, max_length=200)
    phone: str = Field(min_length=10, max_length=20)
    email: str | None = None
    # Задан сразу — бот узнаёт инженера без регистрации по телефону.
    max_user_id: str | None = None
    is_active: bool = True

    _norm_phone = field_validator("phone")(_phone)
    _norm_email = field_validator("email")(_email)
    _norm_max = field_validator("max_user_id")(_max_id)


class EngineerPatch(Strict):
    full_name: str | None = Field(default=None, min_length=3, max_length=200)
    phone: str | None = Field(default=None, min_length=10, max_length=20)
    email: str | None = None
    max_user_id: str | None = None
    is_active: bool | None = None

    _norm_phone = field_validator("phone")(_phone)
    _norm_email = field_validator("email")(_email)
    _norm_max = field_validator("max_user_id")(_max_id)


class ViolationTypeIn(Strict):
    name: str = Field(min_length=2, max_length=300)
    code: str | None = Field(default=None, max_length=120)
    description: str = Field(default="", max_length=2000)
    requires_description: bool = False
    is_active: bool = True


class ViolationTypePatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    requires_description: bool | None = None
    is_active: bool | None = None


OrganizationKind = Literal["UK", "REG_OPERATOR", "OMSU", "DRT", "UPRAVA", "MPR", "GZHI"]


class ExecutorIn(Strict):
    name: str = Field(min_length=2, max_length=300)
    code: str | None = Field(default=None, max_length=64)
    full_name: str = Field(default="", max_length=500)
    kind: OrganizationKind = "OMSU"
    violation_type_ids: list[str] = Field(default_factory=list)
    is_active: bool = True


class ExecutorPatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=300)
    full_name: str | None = Field(default=None, max_length=500)
    kind: OrganizationKind | None = None
    violation_type_ids: list[str] | None = None
    is_active: bool | None = None


class AssignmentIn(Strict):
    engineer_id: str
    territory_id: str
    route_id: str | None = Field(default=None, max_length=64)
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool = True


class AssignmentPatch(Strict):
    territory_id: str | None = None
    route_id: str | None = Field(default=None, max_length=64)
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool | None = None


class ResolveRegistrationIn(Strict):
    engineer_id: str


class RejectRegistrationIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


def _known_permissions(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    unknown = sorted(set(value) - PERMISSIONS.keys())
    if unknown:
        raise ValueError(f"Неизвестные права: {', '.join(unknown)}")
    return sorted(set(value))


class RoleIn(Strict):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=1000)
    permissions: list[str] = Field(default_factory=list)

    _perms = field_validator("permissions")(_known_permissions)


class RolePatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] | None = None

    _perms = field_validator("permissions")(_known_permissions)


class UserIn(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(default="", max_length=200)
    password: str = Field(min_length=10, max_length=1024)
    roles: list[str] = Field(default_factory=list)
    executor_id: str | None = None
    is_active: bool = True


class UserPatch(Strict):
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=10, max_length=1024)
    roles: list[str] | None = None
    executor_id: str | None = None
    is_active: bool | None = None


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int


# --- Реестр КП (app/kp.py) ---

KpStatus = Literal["active", "unverified", "planned", "relocated", "liquidated", "duplicate", "missing_in_source"]
KpRole = Literal["site_maintenance", "waste_removal", "new_site_decision", "territory", "supervision"]
KpSurface = Literal["ASPHALT", "CONCRETE", "SOIL"]


class KpFields(Strict):
    registry_number: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=120)
    municipality: str | None = Field(default=None, max_length=200)
    settlement: str | None = Field(default=None, max_length=200)
    location_accuracy_m: int | None = Field(default=None, ge=0, le=100_000)
    area_m2: float | None = Field(default=None, ge=0, le=100_000)
    surface: KpSurface | None = None
    has_fence: bool | None = None
    has_roof: bool | None = None
    separate_collection: bool | None = None
    kgo_storage: str | None = Field(default=None, max_length=200)
    owner_executor_id: str | None = Field(default=None, max_length=64)
    in_yard: bool | None = None
    in_yard_method: Literal["cadastre", "omsu", "field", "rule", "manual"] | None = None
    land_parcel_cadnum: str | None = Field(default=None, max_length=40)


class KpIn(KpFields):
    address_raw: str = Field(min_length=3, max_length=1000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    status: KpStatus = "unverified"


class KpPatch(KpFields):
    address_raw: str | None = Field(default=None, min_length=3, max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    status: KpStatus | None = None
    duplicate_of: str | None = Field(default=None, max_length=128)  # ID, код LP-… или GUID УТКО
    review_reason: str | None = Field(default=None, max_length=2000)
    # true — площадка подтверждена на месте: verified_at/by, статус unverified → active
    verified: bool | None = None
    reason: str | None = Field(default=None, max_length=1000)  # почему правка — в журнал


class KpContainerIn(Strict):
    number: str | None = Field(default=None, max_length=16)
    container_type: str | None = Field(default=None, max_length=120)
    waste_group: str | None = Field(default=None, max_length=200)
    volume_m3: float | None = Field(default=None, ge=0, le=100)
    color: str | None = Field(default=None, max_length=64)


class KpContainersIn(Strict):
    containers: list[KpContainerIn] = Field(max_length=200)
    reason: str | None = Field(default=None, max_length=1000)


class KpResponsibleIn(Strict):
    role: KpRole
    executor_id: str = Field(min_length=1, max_length=64)
    basis: str | None = Field(default="manual", max_length=32)
    priority: int = Field(default=1, ge=1, le=100)
    confirmed: bool = False
    share_schedule: dict[str, Any] | None = None


class KpResponsiblesIn(Strict):
    responsibles: list[KpResponsibleIn] = Field(max_length=50)
    reason: str | None = Field(default=None, max_length=1000)


class CaseKpIn(Strict):
    kp: str | None = Field(default=None, max_length=128)  # ID, код LP-… или GUID; null — отвязать


# =====================================================================
# Маршрут дела — тела запросов ровно как в docs/api-contract.md фронта (camelCase)
# =====================================================================


class Camel(Strict):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


class ConfirmIn(Camel):
    deadline_hours: Literal[24, 48, 72, 720] = Field(alias="deadlineHours")
    # Сверх контракта: инспектор может поправить исполнителя или тип, если событие не сошлось со справочниками
    executor_id: str | None = Field(default=None, alias="executorId", max_length=64)
    type_violation_id: str | None = Field(default=None, alias="typeViolationId", max_length=64)


class DocumentServiceDataIn(Camel):
    subject: str | None = Field(default=None, min_length=1, max_length=2000)
    control_kind_id: int | None = Field(default=None, ge=1)
    control_form_id: int | None = Field(default=None, ge=1)
    control_body_id: int | None = Field(default=None, ge=1)
    control_object_id: int | None = Field(default=None, ge=1)
    controlled_organization_id: int | None = Field(default=None, ge=1)
    assignment_approved_by_signatory_id: int | None = Field(default=None, ge=1)
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    basis_kind: Literal[
        "mu_material", "appeal", "prescription", "prosecutor_request", "plan", "other"
    ] | None = None
    basis_document_number: str | None = Field(default=None, max_length=100)
    basis_document_date: date | None = None
    basis_description: str | None = Field(default=None, max_length=2000)
    decision_item_kind: Literal["issue_prescription", "initiate_admin_case", "other"] | None = None
    decision_item_description: str | None = Field(default=None, min_length=1, max_length=4000)


class DocumentServiceFileLink(Strict):
    id: int = Field(ge=1)
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    download_url: str = Field(min_length=1, max_length=500)


class DocumentServiceGeneratedEvent(Strict):
    event_id: str = Field(min_length=1, max_length=160)
    crm_case_id: str = Field(min_length=1, max_length=128)
    document_case_id: int = Field(ge=1)
    package_id: int = Field(ge=1)
    package_kind: str = Field(min_length=1, max_length=64)
    package_name: str = Field(min_length=1, max_length=200)
    documents_count: int = Field(ge=0, le=100)
    document_codes: list[str] = Field(default_factory=list, max_length=100)
    document_names: list[str] = Field(default_factory=list, max_length=100)
    documents: list[DocumentServiceFileLink] = Field(default_factory=list, max_length=100)
    actor_name: str | None = Field(default=None, max_length=200)
    occurred_at: AwareDatetime


class DismissIn(Camel):
    reason: str | None = Field(default=None, max_length=1000)


class PhotoReportIn(Camel):
    photo_url: str = Field(alias="photoUrl", min_length=1, max_length=20_000_000)
    taken_at: AwareDatetime | None = Field(default=None, alias="takenAt")
    coords: tuple[float, float] | None = None  # [долгота, широта] телефона
    distance_m: float | None = Field(default=None, alias="distanceM")  # сервер пересчитывает сам
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("coords")
    @classmethod
    def coords_in_range(cls, value: tuple[float, float] | None) -> tuple[float, float] | None:
        if value is not None and not (-180 <= value[0] <= 180 and -90 <= value[1] <= 90):
            raise ValueError("координаты вне диапазона: нужен [долгота, широта]")
        return value


class ReportIn(Camel):
    report: PhotoReportIn


class ReturnIn(Camel):
    comment: str | None = Field(default=None, max_length=1000)


class EmptyIn(Camel):
    pass


def iso(value: datetime | None) -> str | None:
    """ISO с часовым поясом. SQLite отдаёт время без пояса — там всегда хранится UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
