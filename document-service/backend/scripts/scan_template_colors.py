"""Красный текст и подсветка во всех действующих бланках."""
from __future__ import annotations

import io
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
        for document_type in db.scalars(
            select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
        ):
            template = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.is_active.is_(True),
                )
            )
            if template is None:
                continue
            data = storage.read_bytes(template.file)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = etree.fromstring(archive.read("word/document.xml"))

            reds = []
            highlights = []
            for run in root.iter(f"{W}r"):
                text = "".join(n.text or "" for n in run.iter(f"{W}t"))
                color = run.find(f"{W}rPr/{W}color")
                if color is not None and color.get(f"{W}val") == "FF0000":
                    reds.append(text[:60])
                highlight = run.find(f"{W}rPr/{W}highlight")
                if highlight is not None:
                    highlights.append(
                        f"{highlight.get(f'{W}val')}: {text[:50]}"
                    )
            if reds or highlights:
                print(f"{document_type.code} ({template.version}):")
                for text in reds:
                    print(f"  красный: {text!r}")
                for text in highlights:
                    print(f"  подсветка: {text!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
