"""Проверка подстановки QR-кода маленькой картинкой — как будет на деле."""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def make_code() -> Path:
    target = Path("/tmp/qr-test.png")
    image = Image.new("RGB", (120, 120), (255, 255, 255))
    for x in range(0, 120, 6):
        for y in range(0, 120, 6):
            if (x // 6 + y // 6) % 2 == 0:
                image.putpixel((x, y), (0, 0, 0))
                image.putpixel((x + 1, y), (0, 0, 0))
    image.save(target, "PNG")
    return target


def report(label: str, data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        media = {
            name: len(archive.read(name))
            for name in archive.namelist()
            if name.startswith("word/media/")
        }
    for drawing in root.iter(f"{W}drawing"):
        doc_pr = drawing.find(f".//{WP}docPr")
        if doc_pr is None:
            continue
        name = doc_pr.get("name") or ""
        extent = drawing.find(f".//{WP}extent")
        size = ""
        if extent is not None:
            size = (f"{round(int(extent.get('cx')) / 360000, 2)}x"
                    f"{round(int(extent.get('cy')) / 360000, 2)} см")
        if "qr" in name.lower():
            print(f"    {label}: {name!r} {size}")
    print(f"    {label}: байт {len(data)}, картинок {len(media)}")


def main() -> None:
    code_file = make_code()
    blob = code_file.read_bytes()
    print(f"картинка кода для опыта: {len(blob)} байт, "
          f"sha {hashlib.sha256(blob).hexdigest()[:10]}")
    # Кладём в хранилище, чтобы сработал обычный путь через снимок.
    db = SessionLocal()
    try:
        from app.models.enums import FileKind

        stored = storage.save_bytes(db, blob, "qr-test.png", kind=FileKind.ATTACHMENT)
        print(f"в хранилище: file id {stored.id}, путь {stored.storage_path}")

        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = snapshot.payload

        for code in ("decision", "inspection_protocol", "prescription", "act"):
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            template = generation._active_template(db, dt.id)
            raw = storage.read_bytes(template.file)
            print(f"  {code} ({template.version})")
            data = dict(payload)
            data["qr_code"] = {
                "storage_path": stored.storage_path,
                "sha256": stored.sha256,
            }
            built = generation.build_document_bytes(data, code, raw)
            report("с кодом", built)

            # Убираем код из данных — должен остаться место.
            data["qr_code"] = {}
            without = generation.build_document_bytes(data, code, raw)
            report("без кода", without)
    finally:
        db.close()


if __name__ == "__main__":
    main()
