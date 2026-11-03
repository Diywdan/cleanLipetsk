"""Задача 6: оставить по одному пакету каждого вида, лишние убрать.

Перед удалением составляется опись: что именно убирается (пакеты, документы,
файлы). Опись складывается в /data/export/packages-cleanup-<номер>.json, чтобы
решение можно было проверить и, при необходимости, разобрать вручную.

По умолчанию — только показать план. Применить: --apply

Запуск: PYTHONPATH=/app python scripts/clean_case_packages.py 122313 [--apply]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlCase,
    Document,
    DocumentAttachment,
    DocumentDelivery,
    DocumentPackage,
    PackageKind,
    StoredFile,
)
from app.services import storage


EXPORT_DIR = Path("/data/export")


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
        by_kind: dict[str, list[DocumentPackage]] = {}
        for package in packages:
            kind = db.get(PackageKind, package.package_kind_id)
            by_kind.setdefault(kind.code if kind else "?", []).append(package)

        keep: list[DocumentPackage] = []
        remove: list[DocumentPackage] = []
        print(f"заявка {args.number} (id={case.id}): пакетов {len(packages)}")
        for code, items in sorted(by_kind.items()):
            keep.append(items[-1])
            remove.extend(items[:-1])
            print(f"  {code:26} всего {len(items):<4} оставить id={items[-1].id:<5} "
                  f"убрать {len(items) - 1}")
        print(f"\nоставить пакетов: {len(keep)}, убрать: {len(remove)}")

        # Опись удаляемого.
        inventory = {
            "case_number": args.number,
            "case_id": case.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kept_packages": [p.id for p in keep],
            "removed_packages": [],
        }
        removed_documents = 0
        for package in remove:
            documents = list(
                db.scalars(select(Document).where(Document.package_id == package.id))
            )
            removed_documents += len(documents)
            inventory["removed_packages"].append(
                {
                    "id": package.id,
                    "kind_id": package.package_kind_id,
                    "status": getattr(package.status, "value", str(package.status)),
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
                            "generated_file_id": document.generated_file_id,
                            "signed_file_id": document.signed_file_id,
                        }
                        for document in documents
                    ],
                }
            )
        inventory["removed_documents"] = removed_documents
        print(f"документов в удаляемых пакетах: {removed_documents}")

        # Что на удаляемые документы ссылается — иначе останутся битые ссылки.
        removed_ids = [
            d["id"] for package in inventory["removed_packages"] for d in package["documents"]
        ]
        if removed_ids:
            children = list(
                db.scalars(
                    select(Document).where(Document.parent_document_id.in_(removed_ids))
                )
            )
            outside = [d for d in children if d.package_id not in {p.id for p in remove}]
            print(f"документов, ссылающихся на удаляемые извне: {len(outside)}")
            for document in outside[:10]:
                print(f"    id={document.id} пакет={document.package_id} "
                      f"родитель={document.parent_document_id}")
            inventory["referencing_documents_outside"] = [
                {"id": d.id, "package_id": d.package_id,
                 "parent_document_id": d.parent_document_id}
                for d in outside
            ]
            attachments = list(
                db.scalars(
                    select(DocumentAttachment).where(
                        DocumentAttachment.document_id.in_(removed_ids)
                    )
                )
            )
            deliveries = list(
                db.scalars(
                    select(DocumentDelivery).where(
                        DocumentDelivery.document_id.in_(removed_ids)
                    )
                )
            )
            inventory["removed_attachments"] = len(attachments)
            inventory["removed_deliveries"] = len(deliveries)
            signed = [
                d for package in inventory["removed_packages"]
                for d in package["documents"] if d["signed_file_id"]
            ]
            print(f"подписанных документов среди удаляемых: {len(signed)}")

        if not args.apply:
            print("\nЭто план. Для применения добавьте --apply")
            return 0

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        inventory_path = EXPORT_DIR / f"packages-cleanup-{args.number}.json"
        inventory_path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nопись сохранена: {inventory_path}")

        # Удаляем пакеты: документы, приложения и отметки о направлении уходят
        # каскадом (правила в базе: CASCADE на document_packages, documents,
        # document_attachments, document_deliveries).
        for package in remove:
            db.delete(package)
        db.commit()
        print(f"удалено пакетов: {len(remove)}")

        left = list(
            db.scalars(
                select(DocumentPackage).where(DocumentPackage.control_case_id == case.id)
            )
        )
        print(f"осталось пакетов: {len(left)} (id: {sorted(p.id for p in left)})")

        # Сироты: файлы, на которые больше никто не ссылается.
        used: set[int] = set()
        for column in (
            Document.generated_file_id,
            Document.signed_file_id,
        ):
            used.update(
                value for value in db.scalars(select(column)) if value is not None
            )
        print(f"файлов ещё используется: {len(used)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
