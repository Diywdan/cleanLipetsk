"""Почему заявка показывает тот или иной статус в интерфейсе диспетчера.

Печатает все входы, из которых складывается статус: осмотры, нарушение,
пакеты, отметки. И сам статус — тем же кодом, что отдаёт интерфейсу.
"""
from __future__ import annotations

import sys

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import ControlAction, ControlCase, DocumentPackage, PackageKind, Violation
from app.api.incidents import _status
from app.services import case_state


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1
        print(f"заявка {number} (id={case.id})")

        actions = list(
            db.scalars(
                select(ControlAction)
                .where(ControlAction.control_case_id == case.id)
                .order_by(ControlAction.sequence_no)
            )
        )
        print(f"  осмотров: {len(actions)}")
        for action in actions:
            print(f"    id={action.id} №{action.sequence_no} "
                  f"{action.inspection_kind.value} "
                  f"результат={action.inspection_result.value if action.inspection_result else None} "
                  f"нарушение={action.is_violation_found}")

        violations = list(
            db.scalars(select(Violation).where(Violation.control_case_id == case.id))
        )
        print(f"  нарушений: {len(violations)}")
        for violation in violations:
            print(f"    id={violation.id} устранено={violation.is_eliminated} "
                  f"когда={violation.eliminated_at} "
                  f"осмотр={violation.control_action_id}")
            print(f"      {violation.description[:80]!r}")

        packages = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"  пакетов: {len(packages)}")
        for package in packages:
            kind = db.get(PackageKind, package.package_kind_id)
            print(f"    id={package.id} {kind.code if kind else '?'}")

        marks = db.execute(
            text(
                "select comment from audit_log where entity_table = 'control_cases' "
                "and entity_id = :id and comment is not null order by id desc limit 6"
            ),
            {"id": case.id},
        ).all()
        print("  последние записи журнала по заявке:")
        for row in marks:
            print(f"    {row.comment}")

        print()
        status = _status(db, case)
        print(f"статус интерфейса диспетчера: {status}")
        titles = {
            "NEW": "Новое",
            "IN_PROGRESS": "В работе",
            "VERIFICATION": "На проверке",
            "CLOSED": "Устранено",
            "KNM_ESCALATION": "Передано на КНМ",
        }
        print(f"  подпись в интерфейсе: {titles.get(status, status)}")
        print(f"статус нашего интерфейса: {case_state.state(db, case)} "
              f"({case_state.state_title(db, case)})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
