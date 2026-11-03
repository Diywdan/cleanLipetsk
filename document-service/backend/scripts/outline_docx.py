"""Что изменилось в вёрстке протокола: разрывы страниц и структура документа."""
from __future__ import annotations

import sys
import zipfile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def outline(path: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{W}body")
    lines: list[str] = []
    for index, child in enumerate(body, 1):
        kind = etree.QName(child).localname
        text = "".join(node.text or "" for node in child.iter(f"{W}t")).strip()
        page_breaks = len(child.findall(f".//{W}br[@{W}type='page']"))
        last_rendered = child.findall(f".//{W}lastRenderedPageBreak")
        marks = []
        if page_breaks:
            marks.append(f"РАЗРЫВ СТРАНИЦЫ x{page_breaks}")
        if last_rendered:
            marks.append(f"начало страницы x{len(last_rendered)}")
        # Плавающая позиция таблицы.
        if kind == "tbl":
            tbl_pr = child.find(f"{W}tblPr")
            pos = tbl_pr.find(f"{W}tblpPr") if tbl_pr is not None else None
            if pos is not None:
                marks.append("плавающая таблица")
            rows = child.findall(f"{W}tr")
            marks.append(f"строк {len(rows)}")
        # Разрыв раздела.
        if child.find(f"{W}pPr/{W}sectPr") is not None:
            marks.append("КОНЕЦ РАЗДЕЛА")
        line = f"{index:>3} {kind:<6} {' | '.join(marks):<38} {text[:60]}"
        lines.append(line)
    return lines


def main() -> None:
    paths = sys.argv[1:]
    for path in paths:
        print(f"########## {path} ##########")
        for line in outline(path):
            print(line)
        print()


if __name__ == "__main__":
    main()
