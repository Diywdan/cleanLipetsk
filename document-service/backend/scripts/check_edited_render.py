"""Что печатают правленые бланки: телефон в подписи и число листов."""
from __future__ import annotations

import io
import subprocess
import zipfile
import sys
from pathlib import Path

from lxml import etree

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentType
from app.services import generation, pages, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
EXPORT = Path("/data/export/edited-check")


def phone_lines(data: bytes) -> list[str]:
    lines: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    for paragraph in root.iter(f"{W}p"):
        text = "".join(n.text or "" for n in paragraph.iter(f"{W}t")).strip()
        if "38-77-75" in text or "Телефон" in text or "@" in text:
            lines.append(text)
    for table in root.iter(f"{W}tbl"):
        for cell in table.iter(f"{W}tc"):
            for paragraph in cell.findall(f"{W}p"):
                text = "".join(n.text or "" for n in paragraph.iter(f"{W}t")).strip()
                if ("38-77-75" in text or "Телефон" in text) and text not in lines:
                    lines.append(text)
    return lines


def main() -> int:
    cases = {}
    for arg in sys.argv[2:]:
        code, path = arg.split("=", 1)
        cases[code] = Path(path)

    db = SessionLocal()
    try:
        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = snapshot.payload
        EXPORT.mkdir(parents=True, exist_ok=True)
        for code, path in cases.items():
            data = generation.build_document_bytes(
                payload, code, path.read_bytes()
            )
            count = pages.count_pages(data)
            target = EXPORT / f"{code}.docx"
            target.write_bytes(data)
            print(f"=== {code} ({path.name}) ===")
            print(f"    листов: {count}, байт: {len(data)}")
            for line in phone_lines(data):
                print(f"    {line!r}")
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir",
                 str(EXPORT), str(target)],
                capture_output=True, check=False,
            )
            pdf = target.with_suffix(".pdf")
            if pdf.exists():
                print(f"    PDF: {pdf.name}")
            print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
