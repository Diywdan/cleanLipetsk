"""Текущее состояние заявки.

Состояние не хранится в базе, а выводится из данных заявки: осмотров и
собранных пакетов. Хранить его отдельным полем значило бы допустить
расхождение — заявка поменялась, а состояние осталось прежним.

Оператору состояние нужно, чтобы понимать, на каком шаге дело и что будет
дальше: осмотр, пакет документов или ожидание исполнения.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlCase, DocumentPackage
from app.models.enums import InspectionResult
from app.services import inspections


# Коды состояний: они попадают в разметку, названия — оператору.
IN_PROGRESS = "in_progress"
PRIMARY_INSPECTION = "primary_inspection"
PRIMARY_PRESCRIPTION = "primary_prescription"
REPEAT_INSPECTION = "repeat_inspection"
REPEAT_PRESCRIPTION = "repeat_prescription"
EXECUTED_PRESCRIPTION = "executed_prescription"

STATE_TITLES: dict[str, str] = {
    IN_PROGRESS: "На исполнении",
    PRIMARY_INSPECTION: "Первичный осмотр",
    PRIMARY_PRESCRIPTION: "Первичное предписание",
    REPEAT_INSPECTION: "Вторичный осмотр",
    REPEAT_PRESCRIPTION: "Вторичное предписание",
    EXECUTED_PRESCRIPTION: "Исполненное предписание",
}


def _built_kinds(db: Session, case_id: int) -> set[str]:
    """Виды пакетов, которые по заявке уже собраны."""

    return {
        package.package_kind.code
        for package in db.scalars(
            select(DocumentPackage).where(DocumentPackage.control_case_id == case_id)
        )
        if package.package_kind is not None
    }


def state(db: Session, case: ControlCase) -> str:
    """Код текущего состояния заявки."""

    primary = inspections.primary(db, case.id)
    repeat = inspections.repeat(db, case.id)
    kinds = _built_kinds(db, case.id)

    if primary is None:
        # Осмотра ещё не было: заявка в работе.
        return IN_PROGRESS

    if repeat is None:
        if "primary_prescription" in kinds:
            return PRIMARY_PRESCRIPTION
        return PRIMARY_INSPECTION

    # Пакет собирается по результату повторного осмотра, поэтому состояние
    # зависит и от результата, и от того, собран ли пакет.
    if repeat.inspection_result == InspectionResult.FIXED:
        if "executed_prescription" in kinds:
            return EXECUTED_PRESCRIPTION
        return REPEAT_INSPECTION
    if repeat.inspection_result == InspectionResult.NOT_FIXED:
        if "repeated_prescription" in kinds:
            return REPEAT_PRESCRIPTION
        return REPEAT_INSPECTION
    return REPEAT_INSPECTION


def state_title(db: Session, case: ControlCase) -> str:
    return STATE_TITLES.get(state(db, case), STATE_TITLES[IN_PROGRESS])


def control_due_on(db: Session, case: ControlCase) -> date | None:
    """Дата контроля: когда по заявке нужно действовать.

    Пока предписание не выдано, это срок исполнения заявки — его проставляет
    оператор. Как только предписание выдано, контрольная дата — срок его
    исполнения: проверять нужно именно его, а не срок заявки.
    """

    prescription = case.prescriptions[0] if case.prescriptions else None
    if prescription is not None and prescription.due_on is not None:
        return prescription.due_on
    return case.control_due_on


def control_source(db: Session, case: ControlCase) -> str:
    """Откуда взялась дата контроля — это пишется рядом с ней."""

    prescription = case.prescriptions[0] if case.prescriptions else None
    if prescription is not None and prescription.due_on is not None:
        return "срок исполнения предписания"
    if case.control_due_on is not None:
        return "срок исполнения заявки"
    return "не установлена"
