"""Диагностика шаблонов: что реально активно и какие подстановки внутри файлов."""
from __future__ import annotations

import io
import re
import zipfile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType, StoredFile
from app.services import storage


WEAK = re.compile(r"\{\{[^{}]*\bif\b[^{}]*\bis defined\b[^{}]*\}\}")


def docx_text(data: bytes) -> str:
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(".xml"):
                out.append(zf.read(name).decode("utf-8", "replace"))
    return "\n".join(out)


def main() -> None:
    db = SessionLocal()
    try:
        types = list(db.scalars(select(DocumentType).order_by(DocumentType.id)))
        templates = list(db.scalars(select(DocumentTemplate).order_by(DocumentTemplate.id)))
        by_type: dict[int, list[DocumentTemplate]] = {}
        for t in templates:
            by_type.setdefault(t.document_type_id, []).append(t)

        print("=" * 96)
        for dt in types:
            rows = by_type.get(dt.id, [])
            if not rows:
                print(f"{dt.code:26} -- шаблонов нет --")
                continue
            print(f"{dt.code:26} [{dt.name}]")
            for t in rows:
                sf = db.get(StoredFile, t.file_id) if t.file_id else None
                flag = "АКТИВЕН" if t.is_active else "       "
                fname = sf.original_name if sf else "?"
                size = sf.size_bytes if sf else 0
                print(f"   id={t.id:<4} v{t.version:<3} {flag} file={t.file_id} {fname} {size}b")
        print("=" * 96)

        print("\nСодержимое АКТИВНЫХ шаблонов:")
        for dt in types:
            for t in by_type.get(dt.id, []):
                if not t.is_active:
                    continue
                sf = db.get(StoredFile, t.file_id) if t.file_id else None
                if sf is None:
                    print(f"  {dt.code} v{t.version}: НЕТ ФАЙЛА (file_id={t.file_id})")
                    continue
                try:
                    data = storage.read_bytes(sf)
                except Exception as exc:  # noqa: BLE001
                    print(f"  {dt.code} v{t.version}: ошибка чтения: {exc}")
                    continue
                text = docx_text(data)
                weak = WEAK.findall(text)
                print(f"  {dt.code:26} v{t.version:<3} file={t.file_id} sha={str(sf.sha256)[:12]} ослабленных={len(weak)}")
                for w in weak[:2]:
                    print(f"        пример: {w[:110]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
