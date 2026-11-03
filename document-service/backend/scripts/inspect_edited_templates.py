"""Разбор двух правленых бланков: строки, телефоны, разметка страниц."""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)
PHONE = re.compile(r"[+8][\s(-]*\d{3,4}[\s)-]*\d{2}[\s-]*\d{2}[\s-]*\d{2,3}")


def body_lines(data: bytes) -> list[tuple[int, str, str]]:
    """Абзацы и ячейки таблиц в порядке документа."""
    lines: list[tuple[int, str, str]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W}body")
    index = 0
    for child in body:
        kind = etree.QName(child).localname
        if kind == "tbl":
            for row in child.findall(f"{W}tr"):
                for cell in row.findall(f"{W}tc"):
                    for paragraph in cell.findall(f"{W}p"):
                        text = "".join(
                            n.text or "" for n in paragraph.iter(f"{W}t")
                        ).strip()
                        if text:
                            index += 1
                            lines.append((index, f"tbl:{kind}", text))
        elif kind == "p":
            text = "".join(n.text or "" for n in child.iter(f"{W}t")).strip()
            if text:
                index += 1
                lines.append((index, "p", text))
    return lines


def main() -> None:
    for path in sys.argv[1:]:
        data = Path(path).read_bytes()
        print(f"########## {Path(path).name} ({len(data)} б) ##########")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            root = etree.fromstring(archive.read("word/document.xml"))
            text = "".join(n.text or "" for n in root.iter(f"{W}t"))
            sect = root.find(f".//{W}sectPr")
            margins = {}
            if sect is not None:
                pg = sect.find(f"{W}pgMar")
                if pg is not None:
                    margins = {k.replace(W, ""): v for k, v in pg.attrib.items()}
            marks = len(root.findall(f".//{W}lastRenderedPageBreak"))
        print(f"  подстановок: {len(set(TAG.findall(text)))}")
        print(f"  поля: {margins}")
        print(f"  отметок о начале страницы от Word: {marks}")
        phones = PHONE.findall(text)
        print(f"  телефоны в тексте: {phones}")
        print("  строки:")
        for number, kind, line in body_lines(data):
            flag = ""
            if PHONE.search(line):
                flag = "   <<< ТЕЛЕФОН"
            if "{{" in line and line.count("{") < 2:
                flag += "   <<< ТЕГ РАЗОРВАН"
            print(f"    {number:>3} {kind:<6} {line[:100]!r}{flag}")
        print()


if __name__ == "__main__":
    main()
