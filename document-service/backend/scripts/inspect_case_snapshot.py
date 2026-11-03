"""Что было у заявки 122313 по снимку данных: осмотр, фото, предписание."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentPackage, ControlActionFile, StoredFile


def main() -> None:
    db = SessionLocal()
    try:
        snapshots = list(
            db.scalars(
                select(DataSnapshot)
                .where(DataSnapshot.entity_kind == "package")
                .order_by(DataSnapshot.id.desc())
                .limit(3)
            )
        )
        for snapshot in snapshots:
            package = db.get(DocumentPackage, snapshot.entity_id)
            print(f"снимок {snapshot.id}: пакет {snapshot.entity_id}, "
                  f"дело {package.control_case_id if package else '?'}")
        snapshot = snapshots[0]
        payload = snapshot.payload

        print()
        print("=== осмотр ===")
        print(json.dumps(payload.get("inspection"), ensure_ascii=False, indent=2)[:1200])
        print()
        print("=== действия ===")
        print(json.dumps(payload.get("actions"), ensure_ascii=False, indent=2)[:1500])
        print()
        print("=== фото протокола ===")
        photos = (payload.get("protocol") or {}).get("photos") or []
        for photo in photos:
            print(" ", json.dumps(photo, ensure_ascii=False)[:200])
        print()
        print("=== предписание ===")
        prescription = payload.get("prescription") or {}
        for key in ("number", "issued_on", "due_on", "status"):
            print(f"  {key} = {prescription.get(key)!r}")
        print()
        print("=== файлы без связи с действием ===")
        orphans = list(
            db.scalars(
                select(StoredFile)
                .where(StoredFile.kind.in_(["photo", "image", "control_action"]))
                .order_by(StoredFile.id.desc())
                .limit(10)
            )
        )
        for item in orphans:
            print(f"  файл {item.id}: {item.original_name} ({item.kind}, {item.size} б)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
