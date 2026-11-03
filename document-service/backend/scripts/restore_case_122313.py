"""Восстановление полей заявки 122313 после неудачной проверки формы.

Проверка отправляла частичную форму, а обработчик сохраняет все поля целиком:
не переданные поля очищаются. Значения взяты из журнала изменений (audit_log)
и из исходного предписания.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Violation, ViolationWork
from app.services import snapshots

CASE_NUMBER = "122313"

PURPOSE = (
    "Оценка соблюдения контролируемым лицом обязательных требований "
    "действующего законодательства, проверка фактов, изложенных в материале "
    "МУ «Управление главного смотрителя г. Липецка» № 7975-39-01-10 от …"
)

FIELDS = {
    "purpose": PURPOSE,
    "status_id": 4,
    "assignment_date": datetime(2026, 9, 20, 21, 0, tzinfo=timezone.utc),
    "act_composed_at": datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc),
    "assignment_number": "б/н",
    "responsible_organization_id": 8,
    "controlled_unit_id": 7,
    "control_object_id": 7,
    "erp_number": "48001704800001509034",
    "actual_start_at": datetime(2026, 9, 22, 5, 30, tzinfo=timezone.utc),
    "controlled_organization_id": 8,
    "actual_end_at": datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
}

# Работы по нарушению — как было до проверки: асфальт 4, грунт 20, бордюр 4.
WORKS = [("asphalt", Decimal("4")), ("soil", Decimal("20")), ("road_border", Decimal("4"))]


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        if case is None:
            raise SystemExit("заявка не найдена")
        for field, value in FIELDS.items():
            current = getattr(case, field)
            if current != value:
                print(f"  {field}: {current!r} -> {value!r}")
                setattr(case, field, value)
        db.flush()

        violation = db.scalar(
            select(Violation).where(Violation.control_case_id == case.id)
        )
        if violation is not None:
            from app.models import Work

            works = {
                work.code: work
                for work in db.scalars(select(Work))
            }
            for item in list(violation.works):
                db.delete(item)
            db.flush()
            for order, (code, quantity) in enumerate(WORKS, start=1):
                work = works.get(code)
                if work is None:
                    continue
                db.add(
                    ViolationWork(
                        violation_id=violation.id,
                        work_id=work.id,
                        quantity=quantity,
                        sequence_no=order,
                    )
                )
            db.flush()

        db.commit()

        # Описание в заявке собирается из работ, поэтому обновляем его тем же
        # расчётом, что и документы.
        payload = snapshots.build_case_context(db, case.id)
        description = (payload.get("violations") or [{}])[0].get("description")
        if violation is not None and description:
            violation.description = description
            db.commit()

        print()
        print("проверка после восстановления:")
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        for field in FIELDS:
            print(f"  {field} = {getattr(case, field)!r}")
        violation = db.scalar(
            select(Violation).where(Violation.control_case_id == case.id)
        )
        for item in violation.works:
            print(f"  {item.work.name}: {item.quantity}")
        print(f"  описание: {violation.description}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
