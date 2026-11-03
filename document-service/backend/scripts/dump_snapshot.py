"""Выгрузка снимка заявки 122313 в файл — чтобы восстановить связи."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentPackage


def main() -> None:
    db = SessionLocal()
    try:
        package = db.scalars(
            select(DocumentPackage)
            .where(DocumentPackage.control_case_id == 7)
            .order_by(DocumentPackage.id.desc())
        ).first()
        snapshot = db.scalars(
            select(DataSnapshot)
            .where(
                DataSnapshot.entity_kind == "package",
                DataSnapshot.entity_id == package.id,
            )
            .order_by(DataSnapshot.id.desc())
        ).first()
        target = Path("/app/case-122313-snapshot.json")
        target.write_text(
            json.dumps(snapshot.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"пакет {package.id}, снимок {snapshot.id}, "
              f"ключей: {len(snapshot.payload)}")
        print("ключи:", ", ".join(sorted(snapshot.payload.keys())))
        print(f"записано: {target} ({target.stat().st_size} байт)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
