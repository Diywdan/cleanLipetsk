"""Задача 6: сколько пакетов накопилось по заявке и какие это виды.

Запуск: PYTHONPATH=/app python scripts/list_case_packages.py 122313
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Document, DocumentPackage, PackageKind


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1

        packages = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"заявка {number} (id={case.id}): пакетов {len(packages)}")
        print()
        by_kind: dict[str, list[DocumentPackage]] = {}
        for package in packages:
            kind = db.get(PackageKind, package.package_kind_id)
            by_kind.setdefault(kind.code if kind else "?", []).append(package)

        for code, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
            documents = 0
            for package in items:
                documents += len(
                    list(db.scalars(select(Document).where(Document.package_id == package.id)))
                )
            print(f"  {code:26} пакетов {len(items):<4} документов {documents}")
            first, last = items[0], items[-1]
            print(f"      первый id={first.id} ({first.created_at}), "
                  f"последний id={last.id} ({last.created_at})")

        print()
        print("  все пакеты по порядку:")
        for package in packages:
            kind = db.get(PackageKind, package.package_kind_id)
            documents = list(
                db.scalars(select(Document).where(Document.package_id == package.id))
            )
            print(f"    id={package.id:<6} {kind.code if kind else '?':26} "
                  f"состояние={package.status:<10} документов={len(documents):<3} "
                  f"{package.created_at}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
