"""Где в бланке подсветка: цвет текста, highlight, заливка ячеек и абзацев."""
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

        print()
        print("=== подсветка текста (highlight) ===")
        for index, run in enumerate(root.iter(f"{W}r")):
            highlight = run.find(f"{W}rPr/{W}highlight")
            if highlight is None:
                continue
            text = "".join(n.text or "" for n in run.iter(f"{W}t"))
            print(f"  run {index}: {highlight.get(f'{W}val')!r} текст={text[:100]!r}")

        print()
        print("=== заливка абзацев и ячеек (shd) ===")
        for tag in ("p", "tc"):
            for index, element in enumerate(root.iter(f"{W}{tag}")):
                for shd in element.iter(f"{W}shd"):
                    fill = shd.get(f"{W}fill")
                    if not fill or fill in ("auto", "FFFFFF"):
                        continue
                    text = "".join(n.text or "" for n in element.iter(f"{W}t"))
                    print(
                        f"  {tag} {index}: заливка {fill!r} текст={text[:100]!r}"
                    )
                    break

        print()
        print("=== красный текст ===")
        for index, run in enumerate(root.iter(f"{W}r")):
            color = run.find(f"{W}rPr/{W}color")
            if color is None or color.get(f"{W}val") != "FF0000":
                continue
            text = "".join(n.text or "" for n in run.iter(f"{W}t"))
            print(f"  run {index}: текст={text[:120]!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
