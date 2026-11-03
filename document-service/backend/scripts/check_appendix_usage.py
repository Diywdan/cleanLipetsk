"""Где в бланках используется «Приложение»."""
from __future__ import annotations

import io
import re
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
        for code in ("appearance_notice", "administrative_protocol"):
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
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = etree.fromstring(archive.read("word/document.xml"))
            text = "".join(n.text or "" for n in root.iter(f"{W}t"))
            hits = [
                match.group(0)
                for match in re.finditer(
                    r"[^ ]{0,30}\{\{[^}]*appendix[^}]*\}\}", text
                )
            ]
            print(f"{code} ({template.version}) -> {hits}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
