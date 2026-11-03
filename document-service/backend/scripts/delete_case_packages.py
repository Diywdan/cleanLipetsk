"""Удаление всех пакетов документов заявки: данные заявки остаются.

Нужно, чтобы проверить кнопку сборки в интерфейсе: пока пакета нет, она
предлагает «Собрать пакет документов». Осмотры, нарушения, документы-основания
и файлы не трогаются — удаляются только пакеты и собранные в них документы.

Опись удаляемого сохраняется, чтобы понимать, что именно ушло.

По умолчанию — только показать. Удалить: --apply

Запуск: PYTHONPATH=/app python scripts/delete_case_packages.py 122313 [--apply]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlAction,
    ControlCase,
    DataSnapshot,
    Document,
    DocumentPackage,
    PackageKind,
    Violation,
)

EXPORT = Path("/data/export")


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

        packages = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        actions = list(
            db.scalars(
                select(ControlAction).where(ControlAction.control_case_id == case.id)
            )
        )
        violations = list(
            db.scalars(select(Violation).where(Violation.control_case_id == case.id))
        )
        snapshots = db.scalar(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        )

        print(f"заявка {args.number} (id={case.id})")
        print(f"  осмотров: {len(actions)} — остаются")
        print(f"  нарушений: {len(violations)} — остаются")
        print(f"  пакетов: {len(packages)} — удаляются")
        if not packages:
            print("\nпакетов нет — кнопка в интерфейсе уже предлагает сборку")
            return 0

        inventory = {
            "case_number": args.number,
            "case_id": case.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kept": {
                "actions": [a.id for a in actions],
                "violations": [v.id for v in violations],
            },
            "removed_packages": [],
        }
        documents_total = 0
        for package in packages:
            kind = db.get(PackageKind, package.package_kind_id)
            documents = list(
                db.scalars(select(Document).where(Document.package_id == package.id))
            )
            documents_total += len(documents)
            print(f"  пакет id={package.id} {kind.code if kind else '?'} "
                  f"документов {len(documents)}")
            inventory["removed_packages"].append(
                {
                    "id": package.id,
                    "kind": kind.code if kind else None,
                    "created_at": package.created_at.isoformat()
                    if package.created_at
                    else None,
                    "documents": [
                        {
                            "id": document.id,
                            "code": document.document_type.code
                            if document.document_type
                            else None,
                            "number": document.number,
                        }
                        for document in documents
                    ],
                }
            )
        print(f"\nвсего документов уйдёт: {documents_total}")

        if not args.apply:
            print("\nЭто проверка. Для удаления добавьте --apply")
            return 0

        EXPORT.mkdir(parents=True, exist_ok=True)
        path = EXPORT / f"packages-removed-{args.number}.json"
        path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"опись сохранена: {path}")

        for package in packages:
            db.delete(package)
        db.commit()
        print(f"удалено пакетов: {len(packages)}")

        left = list(
            db.scalars(
                select(DocumentPackage).where(
                    DocumentPackage.control_case_id == case.id
                )
            )
        )
        actions_left = list(
            db.scalars(
                select(ControlAction).where(ControlAction.control_case_id == case.id)
            )
        )
        print(f"пакетов осталось: {len(left)}; осмотров осталось: {len(actions_left)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
