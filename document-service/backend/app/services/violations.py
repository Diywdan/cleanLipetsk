"""Нарушение и требование: сохранение работ и сборка текстов.

Работы с объёмами вводятся в двух местах — в карточке заявки и на странице
осмотра. Чтобы оба места давали одинаковый результат, сохранение и сборка
текста живут здесь, а страницы только вызывают их.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlCase, Violation, ViolationType, ViolationWork, Work
from app.services import violation_text


def save_works(
    db: Session,
    violation: Violation,
    rows: list[tuple[int, Decimal | None]],
) -> None:
    """Заменяет работы нарушения набором из формы."""

    for item in list(violation.works):
        db.delete(item)
    db.flush()
    for order, (work_id, quantity) in enumerate(rows, start=1):
        db.add(
            ViolationWork(
                violation_id=violation.id,
                work_id=work_id,
                quantity=quantity,
                sequence_no=order,
            )
        )
    db.flush()


def works_text(db: Session, rows: list[tuple[int, Decimal | None]]) -> str | None:
    """«асфальт – 4 кв.м., грунт – 20 кв.м.» по строкам формы."""

    if not rows:
        return None
    works = {
        work.id: work
        for work in db.scalars(select(Work).where(Work.id.in_([row[0] for row in rows])))
    }
    parts = []
    for work_id, quantity in rows:
        work = works.get(work_id)
        if work is not None:
            parts.append(violation_text.work_line(work, quantity, accusative=True))
    return ", ".join(parts) or None


def description_for(
    db: Session,
    case: ControlCase,
    rows: list[tuple[int, Decimal | None]],
    violation_type_id: int | None,
) -> str | None:
    """Описание нарушения из справочников: вид, объект, работы."""

    control_object = case.control_object
    if control_object is None:
        return None
    place = (
        control_object.name_prepositional
        or control_object.name_genitive
        or control_object.name
    )
    if not place:
        return None
    text = works_text(db, rows)
    if not text:
        return None
    violation_type = db.get(ViolationType, violation_type_id) if violation_type_id else None
    return violation_text.violation_description(
        place,
        text,
        violation_type_name=(
            violation_type.name_accusative if violation_type is not None else None
        ),
        action=(
            violation_type.default_action if violation_type is not None else None
        ),
    )


def requirement_for(violation: Violation, prescription) -> str | None:
    """Требование предписания из данных нарушения.

    В карточке нужен собранный текст: введённого вручную требования больше
    нет, а работы и нормы уже есть у нарушения.
    """

    if prescription is None or not prescription.items or violation is None:
        return None
    item = prescription.items[0]
    if not violation.works:
        return item.requirement_text
    text = ", ".join(
        violation_text.work_line(
            work_item.work, work_item.quantity, accusative=True
        )
        for work_item in violation.works
        if work_item.work is not None
    )
    if not text:
        return item.requirement_text
    references = []
    npa = None
    for provision in violation.provisions:
        article = provision.npa_article
        if article is None:
            continue
        references.append(article.reference_template)
        if npa is None and article.npa is not None:
            npa = {
                "title_genitive": article.npa.title_genitive or article.npa.title,
                "adopted_on": (
                    article.npa.adopted_on.isoformat()
                    if article.npa.adopted_on
                    else None
                ),
                "number": article.npa.number,
                "adopted_by_genitive": article.npa.adopted_by_genitive,
            }
    case = violation.control_case
    control_object = case.control_object if case is not None else None
    address_text = (
        control_object.address.full_address
        if control_object is not None and control_object.address is not None
        else None
    )
    violation_type = violation.violation_type
    return violation_text.requirement_from_data(
        references,
        npa,
        item.action_code or (violation_type.default_action if violation_type else None),
        address_text,
        text,
        requirement_object=(
            violation_type.requirement_object if violation_type is not None else None
        ),
    )
