"""Подстановка настоящего QR-кода на место заглушки в документе.

В бланках решения, протокола осмотра, предписания и акта на месте кода стоит
заготовка «qr-placeholder» того же размера. Здесь заготовка заменяется
картинкой кода, если она загружена в карточку заявки.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PLACEHOLDER_TAG = "qr-placeholder"

REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".wmf": "image/x-wmf",
}


def has_placeholder(data: bytes) -> bool:
    """Есть ли в документе заготовка под код."""

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
    except (KeyError, zipfile.BadZipFile, etree.XMLSyntaxError):
        return False
    for doc_pr in root.iter(f"{WP}docPr"):
        if (doc_pr.get("name") or "") == PLACEHOLDER_TAG:
            return True
    return False


def replace_placeholder(data: bytes, image: bytes, name: str = "qr.png") -> bytes:
    """Ставит картинку кода вместо заготовки.

    Размер рисунка при этом не меняется: он задан в бланке (3.39 см и 1.75 см
    в протоколе осмотра), а картинка вписывается в него.
    """

    suffix = PurePosixPath(name).suffix.lower() or ".png"
    mime = IMAGE_TYPES.get(suffix, "image/png")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        parts = {item: archive.read(item) for item in names}

    root = etree.fromstring(parts["word/document.xml"])
    rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
    rel_map = {rel.get("Id"): rel for rel in rels if rel.get("Id")}

    target_rid = None
    for doc_pr in root.iter(f"{WP}docPr"):
        if (doc_pr.get("name") or "") != PLACEHOLDER_TAG:
            continue
        # Находим рисунок, к которому относится это описание.
        drawing = doc_pr.getparent()
        while drawing is not None and etree.QName(drawing).localname != "drawing":
            drawing = drawing.getparent()
        if drawing is None:
            continue
        for blip in drawing.iter(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        ):
            target_rid = blip.get(f"{R}embed")
            if target_rid:
                break
        if target_rid:
            break

    if not target_rid or target_rid not in rel_map:
        return data

    rel = rel_map[target_rid]
    old_target = rel.get("Target") or ""
    old_part = f"word/{old_target}"
    if old_part not in parts:
        return data

    stem = PurePosixPath(old_target).stem
    new_target = f"media/{stem}{suffix}"
    new_part = f"word/{new_target}"
    # Если расширение прежнее — просто меняем байты на месте.
    parts[old_part] = image
    # Пометка на рисунке: теперь это настоящий код, а не место под него.
    for doc_pr in root.iter(f"{WP}docPr"):
        if (doc_pr.get("name") or "") == PLACEHOLDER_TAG:
            doc_pr.set("name", "qr-code")
            doc_pr.set("descr", "QR-код из прокуратуры")
    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    if new_part != old_part:
        parts[new_part] = image
        del parts[old_part]
        rel.set("Target", new_target)
        names = [new_part if n == old_part else n for n in names]
        parts["word/_rels/document.xml.rels"] = etree.tostring(
            rels, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        # Объявление типа содержимого для нового расширения.
        content_types = etree.fromstring(parts["[Content_Types].xml"])
        has_ext = any(
            item.get("Extension", "").lower() == suffix.lstrip(".")
            for item in content_types.iter(f"{CT_NS}Default")
        )
        if not has_ext:
            element = etree.SubElement(content_types, f"{CT_NS}Default")
            element.set("Extension", suffix.lstrip("."))
            element.set("ContentType", mime)
            parts["[Content_Types].xml"] = etree.tostring(
                content_types, xml_declaration=True, encoding="UTF-8", standalone=True
            )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        for item in names:
            output.writestr(item, parts[item])
    return buffer.getvalue()


def read_image_size(data: bytes) -> tuple[int, int] | None:
    """Размер картинки в точках — для отчёта о подставленном коде."""

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height
    if data[:2] == b"\xff\xd8":
        index = 2
        while index < len(data) - 9:
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            length = int.from_bytes(data[index + 2:index + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                height = int.from_bytes(data[index + 5:index + 7], "big")
                width = int.from_bytes(data[index + 7:index + 9], "big")
                return width, height
            index += 2 + length
    return None
