"""Выгрузка действующих бланков в файлы для правки."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.services import storage


def main() -> None:
    db = SessionLocal()
    try:
        for code, name in (
            ("administrative_protocol", "admin-current.docx"),
            ("appearance_notice", "notice-current.docx"),
        ):
            document_type = db.scalar(
                select(DocumentType).where(DocumentType.code == code)
            )
            template = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.is_active.is_(True),
                )
            )
            data = storage.read_bytes(template.file)
            target = Path("/app") / name
            target.write_bytes(data)
            print(f"{code}: {template.version}, {len(data)} байт → {target}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
