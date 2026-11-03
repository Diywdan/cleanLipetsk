"""Задача 4: чего не хватает заявке, чтобы собрать пакет документов.

Запуск: PYTHONPATH=/app python scripts/check_case_readiness.py 000073
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, ControlCase, Document, DocumentPackage, Violation


def find_case(db, number: str) -> ControlCase | None:
    case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
    if case is not None:
        return case
    if number.isdigit():
        return db.get(ControlCase, int(number))
    return None


def describe(obj, limit: int = 6) -> str:
    if obj is None:
        return "—"
    mapper = sa_inspect(type(obj))
    pieces = []
    for column in mapper.columns:
        key = column.key
        if key in ("id", "created_at", "updated_at"):
            continue
        value = getattr(obj, key, None)
        if value is None or value == "":
            continue
        enum_value = getattr(value, "value", value)
        pieces.append(f"{key}={enum_value!r}")
        if len(pieces) >= limit:
            break
    return " ".join(pieces) or "—"


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "000073"
    db = SessionLocal()
    try:
        case = find_case(db, number)
        if case is None:
            print(f"заявка {number!r} не найдена")
            print("\nпоследние заявки:")
            for row in db.scalars(
                select(ControlCase).order_by(ControlCase.id.desc()).limit(10)
            ):
                print(f"  id={row.id} номер={row.case_number!r}")
            return 1

        print(f"заявка id={case.id} номер={case.case_number!r}")
        print(f"  объект контроля: {describe(case.control_object)}")
        print(f"  контролируемое лицо: {describe(case.controlled_organization)}")
        print(f"  ответственный: {describe(case.responsible_organization)}")
        print(f"  контрольный орган: {describe(case.control_body)}")
        print(f"  вид контроля: {describe(case.control_kind)}")
        print(f"  состояние: {describe(case.status)}")
        print(f"  {describe(case, limit=14)}")

        actions = list(
            db.scalars(
                select(ControlAction)
                .where(ControlAction.control_case_id == case.id)
                .order_by(ControlAction.id)
            )
        )
        print(f"\n  осмотров: {len(actions)}")
        for action in actions:
            print(f"    id={action.id} {describe(action, limit=8)}")

        violations = list(
            db.scalars(select(Violation).where(Violation.control_case_id == case.id))
        )
        print(f"  нарушений: {len(violations)}")
        for violation in violations:
            print(f"    id={violation.id} {describe(violation, limit=6)}")

        packages = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"  пакетов: {len(packages)}")
        for package in packages:
            documents = list(
                db.scalars(select(Document).where(Document.package_id == package.id))
            )
            print(f"    пакет id={package.id} состояние={package.status} "
                  f"документов={len(documents)} создан={package.created_at}")
            for document in documents:
                print(f"      документ id={document.id} вид={document.document_type.code} "
                      f"номер={document.number!r} файл={document.generated_file_id}")

        print("\n--- проверка готовности ---")
        from app.api.incidents import _ready_package  # noqa: PLC0415

        kind_code, readiness = _ready_package(db, case)
        print(f"вид пакета по состоянию заявки: {kind_code!r}")
        if not kind_code:
            print("пакет пока не предлагается — заявка не в том состоянии")
            return 0
        print(f"документов в пакете: {readiness.get('documents')}")
        print(f"готово к сборке: {readiness.get('is_ready')}")
        issues = readiness.get("issues", [])
        if issues:
            print(f"\nне хватает ({len(issues)}):")
            for issue in issues:
                print(f"  [{issue.get('document') or '—'}] {issue.get('field')}: "
                      f"{issue.get('message')}")
        else:
            print("\nзамечаний нет")
        templates = readiness.get("missing_templates", [])
        if templates:
            print(f"\nнет шаблонов: {templates}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
