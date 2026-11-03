"""Все модели проекта.

Импорт этого пакета наполняет Base.metadata — на него опираются Alembic
и проверка схемы. Порядок импортов не важен: связи разрешаются по строкам.
"""

from app.models.appeal import Appeal, AppealFile
from app.models.audit import AuditLog
from app.models.control_body import (
    ControlBody,
    ControlBodySignatory,
    ControlBodyUnit,
    ControlCaseExpert,
    Expert,
    Inspector,
)
from app.models.control_case import (
    ControlAction,
    ControlActionFile,
    ControlActionInspector,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    ControlCaseParty,
    ControlObject,
)
from app.models.document import (
    DataSnapshot,
    Document,
    DocumentAttachment,
    DocumentDelivery,
    DocumentPackage,
    DocumentTemplate,
)
from app.models.enforcement import (
    Decision,
    DecisionItem,
    Prescription,
    PrescriptionItem,
    Violation,
    ViolationProvision,
    ViolationWork,
)
from app.models.file import StoredFile
from app.models.organization import (
    Organization,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationRole,
    OrganizationSignatory,
    OrganizationUnit,
)
from app.models.reference import (
    Address,
    AppealSource,
    ControlCaseStatus,
    ControlForm,
    ControlKind,
    ControlObjectType,
    DocumentStatus,
    DocumentType,
    Npa,
    NpaArticle,
    NumberSequence,
    PackageKind,
    PackageKindDocument,
    CaseTextOption,
    PrescriptionStatus,
    ViolationType,
    ViolationTypeArticle,
    ViolationTypeWork,
    Work,
)
from app.models.administrative import AdministrativeCase
from app.models.area import (
    Area,
    AreaAddress,
    AreaInspector,
)
from app.models.session import UserSession
from app.models.sso_login_ticket import SsoLoginTicket
from app.models.user import Role, User, UserRole


__all__ = [
    "Address",
    "AdministrativeCase",
    "Appeal",
    "AppealFile",
    "AppealSource",
    "AuditLog",
    "ControlAction",
    "Area",
    "AreaAddress",
    "AreaInspector",
    "ControlActionFile",
    "ControlActionInspector",
    "ControlBody",
    "ControlBodySignatory",
    "ControlBodyUnit",
    "ControlCase",
    "ControlCaseBase",
    "ControlCaseExpert",
    "ControlCaseInspector",
    "ControlCaseParty",
    "ControlCaseStatus",
    "ControlForm",
    "ControlKind",
    "ControlObject",
    "ControlObjectType",
    "DataSnapshot",
    "Decision",
    "DecisionItem",
    "Document",
    "DocumentAttachment",
    "DocumentDelivery",
    "DocumentPackage",
    "DocumentStatus",
    "DocumentTemplate",
    "DocumentType",
    "Expert",
    "CaseTextOption",
    "Inspector",
    "Npa",
    "NpaArticle",
    "NumberSequence",
    "Organization",
    "OrganizationContact",
    "OrganizationRequisite",
    "OrganizationRole",
    "OrganizationSignatory",
    "OrganizationUnit",
    "PackageKind",
    "PackageKindDocument",
    "Prescription",
    "PrescriptionItem",
    "PrescriptionStatus",
    "Role",
    "StoredFile",
    "User",
    "UserRole",
    "UserSession",
    "SsoLoginTicket",
    "Violation",
    "ViolationProvision",
    "ViolationType",
    "ViolationTypeArticle",
    "ViolationTypeWork",
    "ViolationWork",
    "Work",
]
