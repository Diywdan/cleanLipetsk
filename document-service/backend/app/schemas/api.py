"""Схемы ответов и запросов HTTP API."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class CaseShort(BaseModel):
    id: int
    erp_number: str | None = None
    control_kind: str | None = None
    control_form: str | None = None
    controlled_person: str | None = None
    responsible_person: str | None = None
    control_object: str | None = None
    status: str | None = None
    actual_start_at: datetime | None = None
    documents_count: int = 0


class CaseDetail(CaseShort):
    purpose: str | None = None
    subject: str | None = None
    assignment_number: str | None = None
    assignment_date: datetime | None = None
    act_composed_at: datetime | None = None
    inspectors: list[str] = Field(default_factory=list)
    bases: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    photos_count: int = 0


class DocumentInfo(BaseModel):
    id: int
    code: str
    name: str
    number: str | None = None
    document_date: date | None = None
    template: str | None = None
    pages: int | None = None
    file_id: int | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    snapshot_id: int | None = None
    download_url: str


class PackageGenerateRequest(BaseModel):
    package_kind: str = "primary_prescription"
    # Можно собрать только часть пакета: удобно для отладки шаблонов.
    only_codes: list[str] | None = None
    # Если для документа ещё не заведён шаблон: по умолчанию это ошибка,
    # но при allow_incomplete пакет собирается из того, что готово,
    # а недостающие коды возвращаются в ответе.
    allow_incomplete: bool = False
    # Собирать пакет, даже если часть полей дела не заполнена.
    skip_validation: bool = False


class CrmCaseSyncRequest(BaseModel):
    crm_case_id: str = Field(min_length=1, max_length=128)
    case_number: str = Field(min_length=1, max_length=100)
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    violation: str | None = None
    reported_at: datetime | None = None
    subject: str | None = None
    control_kind_id: int | None = None
    control_form_id: int | None = None
    control_body_id: int | None = None
    control_object_id: int | None = None
    controlled_organization_id: int | None = None
    assignment_approved_by_signatory_id: int | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    basis_kind: str | None = None
    basis_document_number: str | None = None
    basis_document_date: date | None = None
    basis_description: str | None = None
    decision_item_kind: str | None = None
    decision_item_description: str | None = None
    check_knm_readiness: bool = False


class PackageDetail(BaseModel):
    id: int
    case_id: int
    package_kind: str
    status: str
    snapshot_id: int | None = None
    created_at: datetime
    documents: list[DocumentInfo] = Field(default_factory=list)
    missing_templates: list[str] = Field(default_factory=list)


class CrmPackageContinuationResponse(BaseModel):
    crm_case_id: str
    control_case_id: int
    status: str
    readiness: dict
    package: PackageDetail


class DocumentTypeInfo(BaseModel):
    code: str
    name: str
    uses_external_number: bool
    template_versions: list[str] = Field(default_factory=list)

    @property
    def has_template(self) -> bool:
        return bool(self.template_versions)
