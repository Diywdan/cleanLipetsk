"""Осмотры заявки и всё, что на них ссылается."""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlAction,
    ControlCase,
    Document,
    DocumentPackage,
    PackageKind,
    Violation,
)


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1
        print(f"заявка {number} (id={case.id}), осмотров: {len(case.actions)}")

        for action in case.actions:
            kind = getattr(action.inspection_kind, "value", action.inspection_kind)
            place = (
                action.place_address.full_address if action.place_address else None
            )
            print(f"  действие id={action.id} №{action.sequence_no} вид={kind} "
                  f"тип={action.action_type}")
            print(f"      начало {action.started_at}, окончание {action.ended_at}")
            print(f"      место: {place}")
            print(f"      нарушение найдено: {action.is_violation_found}, "
                  f"результат: {action.result_text!r}")
            print(f"      инспекторов: {len(action.inspectors)}, "
                  f"файлов: {len(action.files)}")
            for item in action.files:
                name = item.file.original_name if item.file else "?"
                print(f"        файл {item.file_id} {name!r} подпись={item.caption!r}")
            # Что ссылается на это действие.
            violations = list(
                db.scalars(
                    select(Violation).where(Violation.control_action_id == action.id)
                )
            )
            print(f"      нарушений: {len(violations)}")
            for violation in violations:
                print(f"        нарушение id={violation.id} "
                      f"{violation.description[:70]!r} устранено={violation.is_eliminated}")
                # Предписания и решения ссылаются на нарушение.
                from app.models import Decision, Prescription

                prescriptions = list(
                    db.scalars(
                        select(Prescription).where(
                            Prescription.violation_id == violation.id
                        )
                    )
                )
                decisions = list(
                    db.scalars(
                        select(Decision).where(Decision.violation_id == violation.id)
                    )
                )
                print(f"        предписаний по нему: {len(prescriptions)} "
                      f"{[p.id for p in prescriptions]}")
                print(f"        решений по нему: {len(decisions)} "
                      f"{[d.id for d in decisions]}")
            result_doc = getattr(action, "result_document_id", None)
            print(f"      документ результата: {result_doc}")

        print()
        print("пакеты заявки:")
        for package in db.scalars(
            select(DocumentPackage)
            .where(DocumentPackage.control_case_id == case.id)
            .order_by(DocumentPackage.id)
        ):
            kind = db.get(PackageKind, package.package_kind_id)
            documents = list(
                db.scalars(select(Document).where(Document.package_id == package.id))
            )
            print(f"  пакет {package.id} {kind.code if kind else '?'} "
                  f"документов {len(documents)}, снимок {package.snapshot_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
