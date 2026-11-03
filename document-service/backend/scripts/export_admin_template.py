"""Выгрузка действующего бланка протокола в файл — для правки."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.services import storage


def main() -> None:
    db = SessionLocal()
    try:
        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = db.scalar(
            select(DocumentTemplate).where(
                DocumentTemplate.document_type_id == document_type.id,
                DocumentTemplate.is_active.is_(True),
            )
        )
        data = storage.read_bytes(template.file)
        target = Path("/app/admin-v4.docx")
        target.write_bytes(data)
        print(f"выгружен {template.version}, файл {template.file_id}, "
              f"{len(data)} байт → {target}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
