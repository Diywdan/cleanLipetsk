"""Какие данные заполнены у рабочей заявки — образец для 000073.

Запуск: PYTHONPATH=/app python scripts/describe_case.py 122313
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase


SKIP = {"id", "created_at", "updated_at"}


def dump(label: str, obj) -> None:
    if obj is None:
        print(f"  {label}: —")
        return
    mapper = sa_inspect(type(obj))
    pieces = []
    for column in mapper.columns:
        key = column.key
        if key in SKIP:
            continue
        value = getattr(obj, key, None)
        if value is None or value == "":
            continue
        pieces.append(f"{key}={getattr(value, 'value', value)!r}")
    print(f"  {label}: " + (" ".join(pieces) if pieces else "—"))


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1
        print(f"=== заявка {number} (id={case.id}) ===")
        dump("сама заявка", case)
        dump("орган контроля", case.control_body)
        dump("вид контроля", case.control_kind)
        dump("форма мероприятия", case.control_form)
        dump("состояние", case.status)
        dump("контролируемое лицо", case.controlled_organization)
        dump("объект контроля", case.control_object)
        dump("ответственный", case.responsible_organization)
        dump("утверждающий", case.assignment_approved_by)

        print(f"  инспекторов: {len(case.inspectors)}")
        for row in case.inspectors:
            dump(f"    инспектор role={row.role}", row.inspector)
        print(f"  оснований: {len(case.bases)}")
        for row in case.bases:
            dump("    основание", row)
        print(f"  осмотров: {len(case.actions)}")
        for action in case.actions:
            dump(f"    осмотр {action.sequence_no}", action)
        print(f"  нарушений: {len(case.violations)}")
        for violation in case.violations:
            dump("    нарушение", violation)
            for provision in getattr(violation, "provisions", []) or []:
                dump("      статья", provision)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
