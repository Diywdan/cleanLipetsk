"""Все подстановки действующего шаблона протокола осмотра — по порядку и с местом."""
from __future__ import annotations

import io
import re
import zipfile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

TAG = re.compile(r"\{\{(.{0,300}?)\}\}", re.S)


def main() -> int:
    db = SessionLocal()
    try:
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "inspection_protocol")
        )
        template = generation._active_template(db, dt.id)
        data = storage.read_bytes(template.file)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist()
                     if n.startswith("word/") and n.endswith(".xml")]
            for name in names:
                text = zf.read(name).decode("utf-8", "replace")
                found = TAG.findall(text)
                if not found:
                    continue
                print(f"=== {name}: {len(found)} подстановок ===")
                for item in found:
                    print(f"   {{{{{item}}}}}")
                print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
