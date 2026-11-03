"""Цветной текст и заливка в бланке протокола об административном правонарушении."""
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
        print(f"шаблон {template.version}, {len(data)} байт")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))

        for index, paragraph in enumerate(root.iter(f"{W}p")):
            text = "".join(n.text or "" for n in paragraph.iter(f"{W}t"))
            colors = set()
            fills = set()
            for run in paragraph.iter(f"{W}r"):
                color = run.find(f"{W}rPr/{W}color")
                if color is not None and color.get(f"{W}val"):
                    colors.add(color.get(f"{W}val"))
                shading = run.find(f"{W}rPr/{W}shd")
                if shading is not None and shading.get(f"{W}fill"):
                    fills.add(shading.get(f"{W}fill"))
            for shd in paragraph.iter(f"{W}shd"):
                if shd.get(f"{W}fill"):
                    fills.add(shd.get(f"{W}fill"))
            if colors or fills:
                print(
                    f"  абзац {index}: цвета={sorted(colors)} заливка={sorted(fills)}"
                )
                print(f"    текст: {text[:160]!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
