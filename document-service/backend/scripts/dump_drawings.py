"""Все рисунки действующих бланков с размерами и окружением."""
from __future__ import annotations

import io
import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def main() -> None:
    db = SessionLocal()
    try:
        for code in ("decision", "inspection_protocol", "prescription", "act"):
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            template = generation._active_template(db, dt.id)
            data = storage.read_bytes(template.file)
            print(f"=== {code} (действует {template.version}, {len(data)} б) ===")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = etree.fromstring(archive.read("word/document.xml"))
                rels = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
                rel_map = {
                    rel.get("Id"): rel.get("Target") for rel in rels if rel.get("Id")
                }
                media = {
                    name: len(archive.read(name))
                    for name in archive.namelist()
                    if name.startswith("word/media/")
                }
            print(f"  файлы картинок: {media}")
            for index, drawing in enumerate(root.iter(f"{W}drawing"), 1):
                extent = drawing.find(f".//{WP}extent")
                size = None
                if extent is not None:
                    size = (
                        round(int(extent.get("cx")) / 360000, 2),
                        round(int(extent.get("cy")) / 360000, 2),
                    )
                blips = [
                    rel_map.get(b.get(f"{R}embed"), b.get(f"{R}embed"))
                    for b in drawing.iter(f"{A}blip")
                ]
                doc_pr = drawing.find(f".//{WP}docPr")
                descriptions = ""
                if doc_pr is not None:
                    descriptions = (
                        f"name={doc_pr.get('name')!r} "
                        f"descr={doc_pr.get('descr')!r}"
                    )
                # Абзац и ячейка, в которых стоит рисунок.
                node = drawing
                cell_text = ""
                while node is not None and etree.QName(node).localname != "tc":
                    node = node.getparent()
                if node is not None:
                    cell_text = "".join(
                        n.text or "" for n in node.iter(f"{W}t")
                    ).strip()[:50]
                print(f"  {index}: размер(см) {size} картинка {blips} {descriptions}")
                if cell_text:
                    print(f"      в ячейке: {cell_text!r}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
