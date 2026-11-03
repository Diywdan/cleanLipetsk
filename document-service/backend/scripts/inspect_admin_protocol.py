"""Что зашито в бланке протокола об административном правонарушении.

Показывает текст бланка с отмеченными местами подстановок: всё, что не
подстановка, — вписано в бланк и печатается в каждом документе.
"""
from __future__ import annotations

import io
import re
import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)


def main() -> None:
    db = SessionLocal()
    try:
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = generation._active_template(db, dt.id)
        data = storage.read_bytes(template.file)
        print(f"бланк: {template.version}, file_id={template.file_id}, {len(data)} байт")

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
            lines = []
            for paragraph in root.iter(f"{W}p"):
                text = "".join(n.text or "" for n in paragraph.iter(f"{W}t"))
                if text.strip():
                    lines.append(text.strip())

        print("\n=== абзацы бланка (подстановки отмечены) ===")
        for index, line in enumerate(lines, 1):
            marked = TAG.sub(lambda m: f"[{m.group(0)[2:-2].strip()}]", line)
            print(f"  {index:>2} {marked[:150]}")

        full = "\n".join(lines)
        print("\n=== цифры и даты, вписанные в бланк ===")
        for match in re.finditer(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{5,}\b", full):
            start = max(0, match.start() - 60)
            end = min(len(full), match.end() + 40)
            print(f"  {match.group(0)!r}: ...{full[start:end]}...".replace("\n", " "))
    finally:
        db.close()


if __name__ == "__main__":
    main()
