"""Полный список видов документов и их активных шаблонов — контроль полноты."""
from __future__ import annotations

import io
import re
import zipfile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType, StoredFile
from app.services import storage

TAG = re.compile(r"\{\{[^{}]*\}\}")


def tags(data: bytes) -> list[str]:
    found: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                text = zf.read(name).decode("utf-8", "replace")
                found.extend(m.group(0) for m in TAG.finditer(text))
    return found


def main() -> None:
    db = SessionLocal()
    try:
        types = list(
            db.scalars(select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id))
        )
        print(f"видов документов в системе: {len(types)}")
        print()
        for dt in types:
            rows = list(
                db.scalars(
                    select(DocumentTemplate)
                    .where(DocumentTemplate.document_type_id == dt.id)
                    .order_by(DocumentTemplate.id)
                )
            )
            active = [t for t in rows if t.is_active]
            print(f"{dt.code:24} [{dt.name[:52]}]")
            print(f"    версий: {len(rows)}, включено: {len(active)}")
            for template in active:
                sf = db.get(StoredFile, template.file_id) if template.file_id else None
                if sf is None:
                    print(f"    v{template.version}: НЕТ ФАЙЛА")
                    continue
                data = storage.read_bytes(sf)
                found = tags(data)
                weak = [t for t in found if "is defined" in t]
                print(f"    v{template.version} file={template.file_id} "
                      f"{sf.original_name} {len(data)}б "
                      f"подстановок {len(found)} ослабленных {len(weak)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
