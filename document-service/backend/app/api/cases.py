"""Обращения и контрольные мероприятия."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import (
    ControlAction,
    ControlActionFile,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    Document,
    DocumentPackage,
    Violation,
)
from app.schemas.api import CaseDetail, CaseShort
from app.services import ru, snapshots


router = APIRouter(prefix="/cases", tags=["cases"])


def case_documents(db: Session, case_id: int) -> list[Document]:
    """Все сформированные документы по делу, в порядке создания."""

    return list(
        db.scalars(
            select(Document)
            .join(DocumentPackage, Document.package_id == DocumentPackage.id)
            .where(DocumentPackage.control_case_id == case_id)
            .order_by(Document.id)
        )
    )


def _short(case: ControlCase, documents_count: int) -> CaseShort:
    return CaseShort(
        id=case.id,
        erp_number=case.erp_number,
        control_kind=case.control_kind.name if case.control_kind else None,
        control_form=case.control_form.name if case.control_form else None,
        controlled_person=(
            case.controlled_organization.short_name
            if case.controlled_organization
            else None
        ),
        responsible_person=(
            case.responsible_organization.short_name
            if case.responsible_organization
            else None
        ),
        control_object=case.control_object.name if case.control_object else None,
        status=case.status.code if case.status else None,
        actual_start_at=case.actual_start_at,
        documents_count=documents_count,
    )


@router.get("", response_model=list[CaseShort])
def list_cases(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CaseShort]:
    stmt = (
        select(ControlCase)
        .order_by(ControlCase.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        _short(case, len(case_documents(db, case.id)))
        for case in db.scalars(stmt)
    ]


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, db: Session = Depends(get_db)) -> CaseDetail:
    case = db.get(ControlCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"дело {case_id} не найдено")

    inspectors = [
        link.inspector.full_name
        for link in db.scalars(
            select(ControlCaseInspector).where(
                ControlCaseInspector.control_case_id == case_id
            )
        )
        if link.inspector is not None
    ]
    bases = [
        base.description or base.kind.value
        for base in db.scalars(
            select(ControlCaseBase).where(ControlCaseBase.control_case_id == case_id)
        )
    ]
    violations = [
        violation.description
        for violation in db.scalars(
            select(Violation).where(Violation.control_case_id == case_id)
        )
    ]
    photos = (
        db.scalar(
            select(func.count(ControlActionFile.id))
            .join(
                ControlAction,
                ControlAction.id == ControlActionFile.control_action_id,
            )
            .where(ControlAction.control_case_id == case_id)
        )
        or 0
    )

    base = _short(case, len(case_documents(db, case_id)))
    return CaseDetail(
        **base.model_dump(),
        purpose=case.purpose,
        subject=case.subject,
        assignment_number=case.assignment_number,
        assignment_date=case.assignment_date,
        act_composed_at=case.act_composed_at,
        inspectors=inspectors,
        bases=bases,
        violations=violations,
        photos_count=photos,
    )


@router.get("/{case_id}/context")
def get_case_context(case_id: int, db: Session = Depends(get_db)) -> dict:
    """Значения подстановки по делу — ровно то, что уходит в документы."""

    if db.get(ControlCase, case_id) is None:
        raise HTTPException(status_code=404, detail=f"дело {case_id} не найдено")
    payload = snapshots.build_case_context(db, case_id)
    return {
        "schema_version": payload["schema_version"],
        "sha256": snapshots.payload_digest(payload),
        "payload": payload,
    }


@router.get("/{case_id}/dates")
def get_case_dates(case_id: int, db: Session = Depends(get_db)) -> dict:
    """Даты дела в том виде, в каком они печатаются в документах."""

    case = db.get(ControlCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"дело {case_id} не найдено")
    return {
        "planned": {
            "start": ru.date_words(case.planned_start_at),
            "end": ru.date_words(case.planned_end_at),
            "start_time": ru.time_official(case.planned_start_at),
            "end_time": ru.time_official(case.planned_end_at),
        },
        "actual": {
            "start": ru.date_words(case.actual_start_at),
            "end": ru.date_words(case.actual_end_at),
        },
        "act_composed": ru.date_words(case.act_composed_at),
        "assignment": ru.date_words(case.assignment_date),
    }
