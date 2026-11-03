"""Статусы всех заявок в терминах интерфейса диспетчера."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, ControlCase, DocumentPackage, Violation
from app.api.incidents import _status

TITLES = {
    "NEW": "Новое",
    "IN_PROGRESS": "В работе",
    "VERIFICATION": "На проверке",
    "CLOSED": "Устранено",
    "KNM_ESCALATION": "Передано на КНМ",
}


def main() -> None:
    db = SessionLocal()
    try:
        print(f"{'номер':10} {'статус':16} {'осмотр':16} {'наруш.':10} "
              f"{'устранено':10} {'пакетов':8} адрес")
        print("-" * 118)
        for case in db.scalars(select(ControlCase).order_by(ControlCase.id)):
            status = _status(db, case)
            actions = list(
                db.scalars(
                    select(ControlAction)
                    .where(ControlAction.control_case_id == case.id)
                    .order_by(ControlAction.sequence_no)
                )
            )
            kinds = [
                a.inspection_kind.value for a in actions
            ]
            violations = list(
                db.scalars(
                    select(Violation).where(Violation.control_case_id == case.id)
                )
            )
            eliminated = sum(1 for v in violations if v.is_eliminated)
            packages = len(
                list(
                    db.scalars(
                        select(DocumentPackage).where(
                            DocumentPackage.control_case_id == case.id
                        )
                    )
                )
            )
            addresses = case.control_object.address if case.control_object else None
            address_text = (
                addresses.full_address if addresses is not None else ""
            )
            print(f"{case.case_number or case.id!s:10} "
                  f"{TITLES.get(status, status):16} "
                  f"{','.join(kinds) or '—':16} "
                  f"{len(violations):<10} "
                  f"{eliminated}/{len(violations):<8} "
                  f"{packages:<8} "
                  f"{address_text[:40]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
