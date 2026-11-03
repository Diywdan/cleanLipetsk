"""Что печатает действующий бланк административного протокола."""
from __future__ import annotations

import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.services import storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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
        print(f"шаблон {template.version}, файл {template.file_id}, {len(data)} байт")
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        for paragraph in root.iter(f"{W}p"):
            text = "".join(n.text or "" for n in paragraph.iter(f"{W}t"))
            if text.strip():
                print(" •", text[:150])
    finally:
        db.close()


if __name__ == "__main__":
    main()
