"""QR-код в бланках: где он, какого размера, встроен картинкой или рисунком."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

KNOWN = ("qr_code", "qrcode", "qr-код", "QR")


def emu_to_cm(value: str | None) -> float | None:
    try:
        return round(int(value) / 360000, 2)
    except (TypeError, ValueError):
        return None


def inspect(data: bytes, label: str) -> None:
    print(f"########## {label} ##########")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        document = etree.fromstring(archive.read("word/document.xml"))
        rels = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
        rel_map = {
            rel.get("Id"): rel.get("Target") for rel in rels if rel.get("Id")
        }

        media = [n for n in names if n.startswith("word/media/")]
        print(f"  картинок в документе: {len(media)}")
        for name in media:
            size = len(archive.read(name))
            print(f"    {name}: {size} байт")

        # Рисунки в теле: размеры и то, где стоят.
        for kind, tag in (
            ("современный (drawing)", ".//" + W + "drawing"),
            ("старый (pict/VML)", ".//" + W + "pict"),
        ):
            found = document.findall(tag)
            if not found:
                continue
            print(f"  рисунки, {kind}: {len(found)}")
            for index, item in enumerate(found, 1):
                extents = item.findall(".//" + WP + "extent")
                shapes = item.findall(".//" + V + "shape")
                blip_ids = [
                    node.get(f"{R}embed")
                    for node in item.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
                ]
                targets = [rel_map.get(rid, "?") for rid in blip_ids if rid]
                sizes = []
                for extent in extents:
                    sizes.append(
                        (emu_to_cm(extent.get("cx")), emu_to_cm(extent.get("cy")))
                    )
                for shape in shapes:
                    style = shape.get("style") or ""
                    size_match = re.search(
                        r"width:([\d.]+)pt;height:([\d.]+)pt", style
                    )
                    if size_match:
                        sizes.append(
                            (
                                round(float(size_match.group(1)) * 2.54 / 72, 2),
                                round(float(size_match.group(2)) * 2.54 / 72, 2),
                            )
                        )
                # Текст абзаца, в котором стоит рисунок — для привязки к месту.
                paragraph = item
                while paragraph is not None and etree.QName(paragraph).localname != "p":
                    paragraph = paragraph.getparent()
                context = ""
                if paragraph is not None:
                    context = "".join(
                        n.text or "" for n in paragraph.iter(f"{W}t")
                    )[:60]
                print(f"    {index}: {targets} размеры(см) {sizes} "
                      f"рядом текст: {context!r}")

        # Теги QR в тексте шаблона (если картинку заменяют подстановкой).
        text = "".join(n.text or "" for n in document.iter(f"{W}t"))
        for needle in KNOWN:
            if needle.lower() in text.lower():
                for match in re.finditer(needle, text, re.I):
                    print(f"  в тексте найдено «{needle}»: "
                          f"{text[max(0, match.start()-50):match.start()+60]!r}")


def main() -> None:
    db = SessionLocal()
    try:
        for code in ("decision", "inspection_protocol", "prescription", "act",
                     "administrative_protocol", "appearance_notice", "direction",
                     "act_direction", "assignment"):
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            if dt is None:
                continue
            template = generation._active_template(db, dt.id)
            if template is None or template.file is None:
                continue
            data = storage.read_bytes(template.file)
            inspect(data, f"{code} ({template.version})")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
