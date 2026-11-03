"""Проверка: без кода в данных остаётся заглушка, с кодом — картинка."""
from __future__ import annotations

import io
import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
TAG = "qr-placeholder"


def inspect(data: bytes) -> tuple[list[str], dict[str, int]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        media = {
            name: len(archive.read(name))
            for name in archive.namelist()
            if name.startswith("word/media/")
        }
    names = []
    for drawing in root.iter(f"{W}drawing"):
        doc_pr = drawing.find(f".//{WP}docPr")
        name = doc_pr.get("name") if doc_pr is not None else ""
        extent = drawing.find(f".//{WP}extent")
        size = ""
        if extent is not None:
            size = (f"{round(int(extent.get('cx')) / 360000, 2)}x"
                    f"{round(int(extent.get('cy')) / 360000, 2)} см")
        names.append(f"{name or '?'} {size}")
    return names, media


def main() -> None:
    db = SessionLocal()
    try:
        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = snapshot.payload

        # Код для опыта: возьмём любую картинку из хранилища (демонстрационную).
        sample = None
        from app.models import StoredFile

        for file in db.scalars(
            select(StoredFile)
            .where(StoredFile.mime_type == "image/png")
            .order_by(StoredFile.id.desc())
            .limit(5)
        ):
            path = storage.absolute_path(file.storage_path)
            if path.exists():
                sample = (file, path)
                break
        print(f"картинка для опыта: {sample[0].original_name if sample else 'нет'}")

        for code in ("decision", "inspection_protocol", "prescription", "act"):
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            template = generation._active_template(db, dt.id)
            raw = storage.read_bytes(template.file)
            for label, with_code in (("без кода", False), ("с кодом", True)):
                data = dict(payload)
                if with_code and sample is not None:
                    data["qr_code"] = {
                        "storage_path": sample[0].storage_path,
                        "sha256": sample[0].sha256,
                    }
                else:
                    data["qr_code"] = {}
                built = generation.build_document_bytes(data, code, raw)
                names, media = inspect(built)
                placeholders = [n for n in names if TAG in n]
                print(f"  {code} ({template.version}) {label}: "
                      f"заглушек {len(placeholders)}, картинок {len(media)}, "
                      f"{len(built)} байт")
                qr_sizes = [n for n in names if TAG in n or "qr" in n.lower()]
                for item in qr_sizes:
                    print(f"      {item}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
