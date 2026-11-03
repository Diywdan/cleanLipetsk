"""Machine-to-machine API used by CRM; never exposed through user sessions."""

from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.dependencies import get_db
from app.forms import parse_datetime
from app.models import (
    ControlAction,
    ControlBody,
    ControlBodySignatory,
    ControlCase,
    ControlCaseBase,
    ControlObject,
    CaseTextOption,
    ControlForm,
    ControlKind,
    Decision,
    DecisionItem,
    Document,
    DocumentPackage,
    Organization,
    PackageKind,
)
from app.models.enums import (
    CaseBaseKind,
    ControlActionType,
    DecisionItemKind,
    InspectionKind,
)
from app.schemas.api import CrmCaseSyncRequest, CrmPackageContinuationResponse
from app.services import (
    auto_dates,
    audit,
    crm_events,
    dictionaries,
    generation,
    labels,
    package_details,
    validation,
)


router = APIRouter(prefix="/internal/crm", tags=["crm-integration"])
PRIMARY_DOCUMENTS = ["assignment", "decision"]
PRIMARY_EXTENSION_DOCUMENTS = [
    "act",
    "inspection_protocol",
    "prescription",
    "direction",
]
PRIMARY_PACKAGE_DOCUMENTS = PRIMARY_DOCUMENTS + PRIMARY_EXTENSION_DOCUMENTS
PRIMARY_PACKAGE = "primary_prescription"


def _authorize(authorization: str | None) -> None:
    configured = settings.crm_integration_token
    if not configured:
        raise HTTPException(status_code=503, detail="интеграция CRM не настроена")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="недействительный токен интеграции")


@router.get("/cases/{crm_case_id}/options")
def case_options(
    crm_case_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Read reference options and current selections for the CRM form."""

    _authorize(authorization)
    case = db.scalar(select(ControlCase).where(ControlCase.crm_case_id == crm_case_id))
    basis = (
        db.scalar(
            select(ControlCaseBase)
            .where(ControlCaseBase.control_case_id == case.id)
            .order_by(ControlCaseBase.id)
        )
        if case
        else None
    )
    decision = (
        db.scalar(select(Decision).where(Decision.control_case_id == case.id).order_by(Decision.id))
        if case
        else None
    )
    item = decision.items[0] if decision and decision.items else None
    subjects = list(
        db.scalars(
            select(CaseTextOption)
            .where(CaseTextOption.kind == "subject", CaseTextOption.is_active.is_(True))
            .order_by(CaseTextOption.sort_order, CaseTextOption.id)
        )
    )
    return {
        "control_kinds": [
            {"id": row.id, "name": row.name}
            for row in db.scalars(select(ControlKind).where(ControlKind.is_active.is_(True)).order_by(ControlKind.name))
        ],
        "control_forms": [
            {"id": row.id, "name": row.name}
            for row in db.scalars(select(ControlForm).where(ControlForm.is_active.is_(True)).order_by(ControlForm.sort_order, ControlForm.name))
        ],
        "control_bodies": [
            {"id": row.id, "name": row.name}
            for row in db.scalars(select(ControlBody).where(ControlBody.is_active.is_(True)).order_by(ControlBody.name))
        ],
        "control_objects": [
            {
                "id": row.id,
                "name": row.name or row.object_type.name,
                "object_type": row.object_type.name,
                "address": row.address.full_address if row.address else None,
            }
            for row in db.scalars(
                select(ControlObject)
                .where(ControlObject.is_active.is_(True))
                .order_by(ControlObject.name, ControlObject.id)
            )
        ],
        "organizations": [
            {"id": row.id, "name": row.short_name, "inn": row.inn}
            for row in db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.short_name))
        ],
        "signatories": [
            {
                "id": row.id,
                "control_body_id": row.control_body_id,
                "name": row.full_name,
                "position": row.position,
            }
            for row in db.scalars(
                select(ControlBodySignatory)
                .where(
                    ControlBodySignatory.valid_from <= date.today(),
                    (ControlBodySignatory.valid_to.is_(None))
                    | (ControlBodySignatory.valid_to >= date.today()),
                )
                .order_by(ControlBodySignatory.full_name)
            )
        ],
        "basis_kinds": [
            {"code": code, "name": name}
            for code, name in labels.options(
                [value.value for value in CaseBaseKind], labels.BASIS_KIND_TITLES
            )
        ],
        "decision_item_kinds": [
            {"code": DecisionItemKind.ISSUE_PRESCRIPTION.value, "name": "Выдать предписание"},
            {"code": DecisionItemKind.INITIATE_ADMIN_CASE.value, "name": "Возбудить дело об административном правонарушении"},
            {"code": DecisionItemKind.OTHER.value, "name": "Иное"},
        ],
        "subjects": [{"value": row.value} for row in subjects],
        "values": {
            "subject": case.subject if case else (subjects[0].value if subjects else None),
            "control_kind_id": case.control_kind_id if case else None,
            "control_form_id": case.control_form_id if case else None,
            "control_body_id": case.control_body_id if case else None,
            "control_object_id": case.control_object_id if case else None,
            "controlled_organization_id": case.controlled_organization_id if case else None,
            "assignment_approved_by_signatory_id": case.assignment_approved_by_signatory_id if case else None,
            "planned_start_at": case.planned_start_at.isoformat() if case and case.planned_start_at else None,
            "planned_end_at": case.planned_end_at.isoformat() if case and case.planned_end_at else None,
            "basis_kind": basis.kind.value if basis else None,
            "basis_document_number": basis.document_number if basis else None,
            "basis_document_date": basis.document_date.date().isoformat() if basis and basis.document_date else None,
            "basis_description": basis.description if basis else None,
            "decision_item_kind": item.kind.value if item else DecisionItemKind.ISSUE_PRESCRIPTION.value,
            "decision_item_description": item.description if item else "выдать предписание об устранении нарушений",
        },
    }


@router.post("/cases/sync")
def sync_case(
    body: CrmCaseSyncRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Create/update the linked draft and generate assignment + decision if ready."""

    _authorize(authorization)
    default_subject = db.scalar(
        select(CaseTextOption.value)
        .where(CaseTextOption.kind == "subject", CaseTextOption.is_active.is_(True))
        .order_by(CaseTextOption.sort_order, CaseTextOption.id)
    )
    case = db.scalar(
        select(ControlCase)
        .where(ControlCase.crm_case_id == body.crm_case_id)
        .with_for_update()
    )
    if case is None:
        case = ControlCase(
            crm_case_id=body.crm_case_id,
            case_number=body.case_number,
            purpose="Рассмотрение поступившей из CRM фиксации нарушения",
            subject=body.subject or default_subject,
        )
        db.add(case)
        db.flush()
    else:
        case.case_number = body.case_number
        if "subject" in body.model_fields_set:
            case.subject = body.subject

    reference_models = {
        "control_kind_id": ControlKind,
        "control_form_id": ControlForm,
        "control_body_id": ControlBody,
        "control_object_id": ControlObject,
        "controlled_organization_id": Organization,
    }
    for field_name, model in reference_models.items():
        selected = getattr(body, field_name)
        if selected is not None:
            reference = db.get(model, selected)
            if reference is None or (
                hasattr(reference, "is_active") and not reference.is_active
            ):
                raise HTTPException(status_code=422, detail=f"некорректное значение {field_name}")

    for field_name in (
        "control_kind_id",
        "control_form_id",
        "control_body_id",
        "control_object_id",
        "controlled_organization_id",
        "assignment_approved_by_signatory_id",
    ):
        selected = getattr(body, field_name)
        if field_name in body.model_fields_set:
            setattr(case, field_name, selected)
    db.flush()
    if case.controlled_organization is not None:
        dictionaries.save_requisites(db, case.controlled_organization, {})
    for field_name in ("planned_start_at", "planned_end_at"):
        if field_name in body.model_fields_set:
            selected = getattr(body, field_name)
            setattr(case, field_name, parse_datetime(selected.isoformat()) if selected else None)

    primary = db.scalar(
        select(ControlAction)
        .where(
            ControlAction.control_case_id == case.id,
            ControlAction.inspection_kind == InspectionKind.PRIMARY,
        )
        .order_by(ControlAction.sequence_no)
    )
    if primary is None:
        primary = ControlAction(
            control_case_id=case.id,
            sequence_no=1,
            action_type=ControlActionType.INSPECTION,
            inspection_kind=InspectionKind.PRIMARY,
        )
        db.add(primary)
    primary.result_text = body.violation or body.address or "Фиксация нарушения поступила из CRM"
    if body.reported_at is not None:
        primary.started_at = body.reported_at
        primary.ended_at = body.reported_at
        case.actual_start_at = body.reported_at
        case.actual_end_at = body.reported_at
        auto_dates.apply_after_inspection(db, case, primary)

    if body.assignment_approved_by_signatory_id is not None:
        signatory = db.get(ControlBodySignatory, body.assignment_approved_by_signatory_id)
        if signatory is None or (
            case.control_body_id is not None
            and signatory.control_body_id != case.control_body_id
        ):
            raise HTTPException(status_code=422, detail="подписант не относится к выбранному органу контроля")
    if "basis_kind" in body.model_fields_set and not body.basis_kind:
        old_basis = db.scalar(
            select(ControlCaseBase)
            .where(ControlCaseBase.control_case_id == case.id)
            .order_by(ControlCaseBase.id)
        )
        if old_basis is not None:
            db.delete(old_basis)
    elif body.basis_kind:
        try:
            kind = CaseBaseKind(body.basis_kind)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="неизвестный тип основания") from error
        basis = db.scalar(
            select(ControlCaseBase)
            .where(ControlCaseBase.control_case_id == case.id)
            .order_by(ControlCaseBase.id)
        )
        if basis is None:
            basis = ControlCaseBase(control_case_id=case.id, kind=kind)
            db.add(basis)
        basis.kind = kind
        basis.document_number = body.basis_document_number
        basis.document_date = (
            parse_datetime(f"{body.basis_document_date.isoformat()}T00:00")
            if body.basis_document_date
            else None
        )
        basis.description = body.basis_description

    if body.decision_item_description is not None:
        try:
            item_kind = DecisionItemKind(
                body.decision_item_kind or DecisionItemKind.ISSUE_PRESCRIPTION.value
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail="неизвестный тип пункта решения") from error
        decision = db.scalar(
            select(Decision).where(Decision.control_case_id == case.id).order_by(Decision.id)
        )
        if decision is None:
            decision = Decision(control_case_id=case.id)
            db.add(decision)
        decision.approved_by_signatory_id = case.assignment_approved_by_signatory_id
        item = decision.items[0] if decision.items else None
        if item is None:
            item = DecisionItem(decision=decision, sequence_no=1, kind=item_kind)
            db.add(item)
        item.kind = item_kind
        item.description = body.decision_item_description
    elif "decision_item_description" in body.model_fields_set:
        decision = db.scalar(
            select(Decision).where(Decision.control_case_id == case.id).order_by(Decision.id)
        )
        if decision and decision.items:
            db.delete(decision.items[0])

    # Date automation creates the decision shell. Keep it idempotent when no
    # inspection timestamp has arrived yet.
    db.flush()
    package_kind = db.scalar(
        select(PackageKind).where(PackageKind.code == PRIMARY_PACKAGE)
    )
    if package_kind is None:
        raise HTTPException(status_code=503, detail="не настроен вид первичного пакета")
    existing = db.scalar(
        select(DocumentPackage)
        .where(
            DocumentPackage.control_case_id == case.id,
            DocumentPackage.package_kind_id == package_kind.id,
        )
        .order_by(desc(DocumentPackage.id))
        .with_for_update()
    )
    existing_codes = (
        {
            document.document_type.code
            for document in db.scalars(
                select(Document).where(Document.package_id == existing.id)
            )
        }
        if existing is not None
        else set()
    )
    if body.check_knm_readiness:
        missing_knm_codes = [
            code for code in PRIMARY_PACKAGE_DOCUMENTS if code not in existing_codes
        ]
        readiness = (
            validation.check_readiness(
                db,
                case.id,
                PRIMARY_PACKAGE,
                only_codes=missing_knm_codes,
            )
            if missing_knm_codes
            else validation.Readiness(
                case_id=case.id,
                package_kind=PRIMARY_PACKAGE,
                documents=[],
            )
        )
        response = {
            "crm_case_id": body.crm_case_id,
            "control_case_id": case.id,
            "status": (
                "generated"
                if set(PRIMARY_DOCUMENTS).issubset(existing_codes)
                else "needs_input"
            ),
            "documents": None,
            "primary_package": (
                package_details.package_detail(db, existing).model_dump(mode="json")
                if existing is not None
                else None
            ),
            "readiness": readiness.as_dict(),
        }
        db.commit()
        return response

    missing_codes = [
        code for code in PRIMARY_DOCUMENTS if code not in existing_codes
    ]
    readiness = validation.check_readiness(
        db,
        case.id,
        PRIMARY_PACKAGE,
        only_codes=missing_codes or PRIMARY_DOCUMENTS,
    )
    generated: dict | None = None
    if readiness.is_ready:
        if not missing_codes:
            generated = {
                "package_id": existing.id,
                "documents": PRIMARY_DOCUMENTS,
                "missing_templates": [],
            }
        else:
            result = generation.generate_package(
                db,
                case.id,
                package_kind_code=PRIMARY_PACKAGE,
                only_codes=missing_codes,
                existing_package_id=existing.id if existing is not None else None,
            )
            generated = {
                "package_id": result.package_id,
                "documents": (
                    PRIMARY_DOCUMENTS
                    if not result.missing_templates
                    else [item.code for item in result.created]
                ),
                "missing_templates": result.missing_templates,
            }
    response = {
        "crm_case_id": body.crm_case_id,
        "control_case_id": case.id,
        "status": "generated" if generated else "needs_input",
        "documents": generated,
        "primary_package": None,
        "readiness": readiness.as_dict(),
    }
    if generated:
        generated_package = db.get(DocumentPackage, generated["package_id"])
        if generated_package is not None:
            response["primary_package"] = package_details.package_detail(
                db, generated_package
            ).model_dump(mode="json")
    db.commit()
    return response


@router.post(
    "/cases/{crm_case_id}/packages/continue",
    response_model=CrmPackageContinuationResponse,
)
def continue_primary_package(
    crm_case_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CrmPackageContinuationResponse:
    """Append remaining documents to the linked primary package."""

    _authorize(authorization)
    case = db.scalar(
        select(ControlCase)
        .where(ControlCase.crm_case_id == crm_case_id)
        .with_for_update()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="дело CRM не найдено")

    package_kind = db.scalar(
        select(PackageKind).where(PackageKind.code == PRIMARY_PACKAGE)
    )
    if package_kind is None:
        raise HTTPException(status_code=503, detail="не настроен вид первичного пакета")
    package = db.scalar(
        select(DocumentPackage)
        .where(
            DocumentPackage.control_case_id == case.id,
            DocumentPackage.package_kind_id == package_kind.id,
        )
        .order_by(desc(DocumentPackage.id))
        .with_for_update()
    )
    if package is None:
        raise HTTPException(
            status_code=409,
            detail="первичный пакет ещё не сформирован",
        )

    existing_codes = {
        document.document_type.code
        for document in db.scalars(
            select(Document).where(Document.package_id == package.id)
        )
    }
    missing_codes = [
        code for code in PRIMARY_PACKAGE_DOCUMENTS if code not in existing_codes
    ]
    if missing_codes:
        readiness = validation.check_readiness(
            db, case.id, PRIMARY_PACKAGE, only_codes=missing_codes
        )
    else:
        readiness = validation.Readiness(
            case_id=case.id,
            package_kind=PRIMARY_PACKAGE,
            documents=PRIMARY_PACKAGE_DOCUMENTS.copy(),
        )

    result = None
    if readiness.is_ready and missing_codes:
        result = generation.generate_package(
            db,
            case.id,
            package_kind_code=PRIMARY_PACKAGE,
            only_codes=missing_codes,
            existing_package_id=package.id,
            commit=False,
        )
        readiness.missing_templates.extend(result.missing_templates)

    complete = not missing_codes or (
        result is not None
        and not result.missing_templates
        and set(PRIMARY_PACKAGE_DOCUMENTS)
        <= (
            existing_codes
            | {document.code for document in result.created}
        )
    )
    if result is not None and result.created:
        audit.record(
            db,
            actor=None,
            entity_table="document_packages",
            entity_id=package.id,
            action="generate",
            comment=(
                f"продолжение первичного пакета по запросу CRM: "
                f"документов {len(result.created)}"
            ),
        )
        db.commit()
        if complete:
            crm_events.package_generated(
                case,
                package,
                len(PRIMARY_PACKAGE_DOCUMENTS),
                event_suffix="extended",
            )

    return CrmPackageContinuationResponse(
        crm_case_id=crm_case_id,
        control_case_id=case.id,
        status="generated" if complete else "needs_input",
        readiness=readiness.as_dict(),
        package=package_details.package_detail(
            db, package, readiness.missing_templates
        ),
    )
