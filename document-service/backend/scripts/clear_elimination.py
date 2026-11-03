"""Снятие отметки «нарушение устранено» у заявки.

Отметка ставится интерфейсом диспетчера при приёме работы. Если повторного
осмотра не было, она остаётся без подтверждения и статус заявки показывает
«Устранено» раньше времени. Скрипт снимает отметку и показывает, каким
станет статус.

По умолчанию — только показать. Снять: --apply

Запуск: PYTHONPATH=/app python scripts/clear_elimination.py 122313 [--apply]
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, ControlCase, Violation
from app.api.incidents import _status

TITLES = {
    "NEW": "Новое",
    "IN_PROGRESS": "В работе",
    "VERIFICATION": "На проверке",
    "CLOSED": "Устранено",
    "KNM_ESCALATION": "Передано на КНМ",
}


def show(case: ControlCase, db) -> None:
    status = _status(db, case)
    print(f"  статус интерфейса диспетчера: {status} "
          f"({TITLES.get(status, status)})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("number", nargs="?", default="122313")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == args.number)
        )
        if case is None:
            print(f"заявка {args.number!r} не найдена")
            return 1

        violations = list(
            db.scalars(
                select(Violation)
                .where(Violation.control_case_id == case.id)
                .order_by(Violation.id)
            )
        )
        actions = list(
            db.scalars(
                select(ControlAction)
                .where(ControlAction.control_case_id == case.id)
                .order_by(ControlAction.sequence_no)
            )
        )
        repeats = [a for a in actions if a.inspection_kind.value == "repeat"]

        print(f"заявка {args.number} (id={case.id})")
        for violation in violations:
            print(f"  нарушение id={violation.id} устранено={violation.is_eliminated} "
                  f"когда={violation.eliminated_at}")
        print(f"  повторных осмотров: {len(repeats)}")
        if repeats:
            for action in repeats:
                result = (
                    action.inspection_result.value
                    if action.inspection_result
                    else None
                )
                print(f"    осмотр id={action.id} результат={result}")
        show(case, db)

        marked = [v for v in violations if v.is_eliminated]
        if not marked:
            print("\nотметки нет — снимать нечего")
            return 0
        if repeats:
            print("\nПРЕДУПРЕЖДЕНИЕ: есть повторный осмотр — "
                  "устранение может быть подтверждено им")
            return 1

        if not args.apply:
            print("\nЭто проверка. Для снятия добавьте --apply")
            return 0

        for violation in marked:
            violation.is_eliminated = False
            violation.eliminated_at = None
        db.commit()
        print(f"\nотметка снята у нарушений: {[v.id for v in marked]}")
        print("после снятия:")
        show(case, db)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
