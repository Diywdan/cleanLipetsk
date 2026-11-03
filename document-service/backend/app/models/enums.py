"""Перечисления-дискриминаторы.

Смысловые перечни, которые может расширять бизнес (статусы дел, типы
документов, виды контроля), вынесены в таблицы-справочники. Здесь —
только технические дискриминаторы, которые меняются вместе с кодом.
"""

from enum import Enum


class OrganizationKind(str, Enum):
    LEGAL_ENTITY = "legal_entity"
    ENTREPRENEUR = "entrepreneur"
    INDIVIDUAL = "individual"


class OrganizationUnitKind(str, Enum):
    BRANCH = "branch"
    REPRESENTATION = "representation"
    SEPARATE_UNIT = "separate_unit"


class OrganizationRoleCode(str, Enum):
    REGIONAL_OPERATOR = "regional_operator"
    MANAGING_ORGANIZATION = "managing_organization"
    CONTRACTOR = "contractor"
    OWNER = "owner"
    OTHER = "other"


class SignatoryBasisKind(str, Enum):
    CHARTER = "charter"
    TRUST = "trust"
    ORDER = "order"
    OTHER = "other"


class ContactKind(str, Enum):
    EMAIL = "email"
    PHONE = "phone"


class ContactPurpose(str, Enum):
    DOCUMENT_DELIVERY = "document_delivery"
    NOTIFICATIONS = "notifications"
    GENERAL = "general"


class ApplicantKind(str, Enum):
    CITIZEN = "citizen"
    ORGANIZATION = "organization"
    ANONYMOUS = "anonymous"


class AppealStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    REJECTED = "rejected"
    CLOSED = "closed"


class CaseBaseKind(str, Enum):
    MU_MATERIAL = "mu_material"
    APPEAL = "appeal"
    PRESCRIPTION = "prescription"
    PROSECUTOR_REQUEST = "prosecutor_request"
    PLAN = "plan"
    OTHER = "other"


class CasePartyKind(str, Enum):
    CONTROLLED = "controlled"
    RESPONSIBLE = "responsible"
    APPROVER = "approver"
    RECIPIENT = "recipient"


class InspectorRole(str, Enum):
    LEADER = "leader"
    PARTICIPANT = "participant"


class ExpertKind(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"


class ControlActionType(str, Enum):
    INSPECTION = "inspection"
    INSTRUMENTAL_SURVEY = "instrumental_survey"
    SAMPLING = "sampling"
    TESTING = "testing"
    EXPERTISE = "expertise"
    PHOTO_FIXATION = "photo_fixation"
    VIDEO_RECORDING = "video_recording"


class InspectionKind(str, Enum):
    """Осмотр объекта: первичный выявляет нарушение, повторный — устранено ли оно."""

    PRIMARY = "primary"
    REPEAT = "repeat"


class InspectionResult(str, Enum):
    """Чем закончился осмотр. У первичного осмотра результата нет.

    Промежуточного «устранено частично» нет намеренно: от него зависит,
    какой пакет собирать дальше, а частичный результат не даёт однозначного
    ответа. Нарушение либо снято, либо нет — снимает его инспектор вручную.
    """

    FIXED = "fixed"
    NOT_FIXED = "not_fixed"


class PhotoKind(str, Enum):
    """Фотография осмотра: размеченная копия и исходный снимок.

    Оригинал хранится отдельно: если документы придётся переделывать
    (например, изменится дата осмотра), разметку наносят заново на исходный
    снимок, а не поверх прежней надписи.
    """

    ANNOTATED = "annotated"
    ORIGINAL = "original"


class DecisionItemKind(str, Enum):
    ISSUE_PRESCRIPTION = "issue_prescription"
    INITIATE_ADMIN_CASE = "initiate_admin_case"
    OTHER = "other"


class FileKind(str, Enum):
    TEMPLATE = "template"
    GENERATED = "generated"
    SIGNED_SCAN = "signed_scan"
    PHOTO = "photo"
    VIDEO = "video"
    ATTACHMENT = "attachment"
    OTHER = "other"


class DeliveryRecipientKind(str, Enum):
    ORGANIZATION = "organization"
    UNIT = "unit"
    PROSECUTOR = "prosecutor"
    APPLICANT = "applicant"
    OTHER = "other"


class DeliveryMethod(str, Enum):
    EMAIL = "email"
    POST = "post"
    PORTAL = "portal"
    IN_PERSON = "in_person"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class PackageStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    GENERATED = "generated"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SnapshotEntityKind(str, Enum):
    DOCUMENT = "document"
    PACKAGE = "package"
    CASE = "case"


class ControlledPartyKind(str, Enum):
    """Кого именно привлекаем/уведомляем: юрлицо или его филиал."""

    ORGANIZATION = "organization"
    UNIT = "unit"
    BOTH = "both"
