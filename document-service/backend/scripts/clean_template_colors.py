"""Убирает следы заполнения бланка: красный текст и жёлтую подсветку.

Это разметка исходного документа: заказчик помечал ею поля, которые нужно
заполнить. В готовом документе она печатается как есть — красным текстом и
жёлтыми полосами.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    data = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names}

    root = etree.fromstring(parts["word/document.xml"])
    reds = 0
    highlights = 0

    for run in root.iter(f"{W}r"):
        color = run.find(f"{W}rPr/{W}color")
        if color is not None and color.get(f"{W}val") == "FF0000":
            color.set(f"{W}val", "auto")
            reds += 1
        highlight = run.find(f"{W}rPr/{W}highlight")
        if highlight is not None:
            run.find(f"{W}rPr").remove(highlight)
            highlights += 1

    print(f"красных фрагментов перекрашено: {reds}")
    print(f"подсветок убрано: {highlights}")

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, parts[name])
    target.write_bytes(buffer.getvalue())
    print(f"записано: {target} ({len(buffer.getvalue())} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
