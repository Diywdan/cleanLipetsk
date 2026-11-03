"""Проверка шаблона протокола осмотра до загрузки в базу.

Смотрит то, что легко потерять при правке в Word: подстановки (их можно
разорвать форматированием), поля страницы, таблицу и её позиционирование,
колонтитулы. Ничего не меняет — только читает файл.

Запуск:
    python scripts/check_protocol_file.py <файл.docx> [эталон.docx]
"""
from __future__ import annotations

import re
import sys
import zipfile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)


def q(tag: str) -> str:
    return f"{W}{tag}"


def read(path: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        parts = {
            name: archive.read(name)
            for name in names
            if name.startswith("word/") and name.endswith(".xml")
        }
    document = etree.fromstring(parts["word/document.xml"])
    # Подстановка может быть разбита на несколько runs — склеиваем текст.
    text = "".join(node.text or "" for node in document.iter(q("t")))
    tables = document.findall(f".//{q('tbl')}")
    sect = document.find(f".//{q('sectPr')}")
    margins = {}
    if sect is not None:
        pg = sect.find(q("pgMar"))
        if pg is not None:
            margins = {k.replace(W, ""): v for k, v in pg.attrib.items()}
    positions = []
    for table in tables:
        tbl_pr = table.find(q("tblPr"))
        pos = tbl_pr.find(q("tblpPr")) if tbl_pr is not None else None
        positions.append(
            {k.replace(W, ""): v for k, v in pos.attrib.items()} if pos is not None else None
        )
    return {
        "parts": sorted(parts),
        "text": text,
        "tables": [(len(t.findall(q("tr"))), len(t.findall(q("tc")))) for t in tables],
        "margins": margins,
        "positions": positions,
        "media": sorted(n for n in names if n.startswith("word/media/")),
        "headers": sorted(
            n for n in names if re.search(r"word/(header|footer)\d*\.xml$", n)
        ),
    }


def report(path: str, reference: dict | None = None) -> int:
    info = read(path)
    problems: list[str] = []
    print(f"=== {path} ===")
    print(f"частей XML: {len(info['parts'])}; таблиц: {len(info['tables'])} "
          f"{info['tables']}; картинок: {len(info['media'])}")
    print(f"колонтитулы: {info['headers']}")
    print(f"поля страницы: {info['margins']}")
    for index, position in enumerate(info["positions"], 1):
        print(f"  таблица {index}: позиционирование {position}")

    print("\nподстановки:")
    found = TAG.findall(info["text"])
    for tag in found:
        print(f"  {{{{{tag}}}}}")
    if not found:
        problems.append("в документе нет ни одной подстановки — теги потеряны")
    if "is defined" in info["text"]:
        problems.append("в шаблоне ослабленный режим (is defined) — так нельзя")

    if reference is not None:
        print("\nсравнение с эталоном:")
        pairs = [
            ("поля страницы", reference["margins"], info["margins"]),
            ("таблиц", len(reference["tables"]), len(info["tables"])),
            (
                "строк первой таблицы",
                reference["tables"][0][0] if reference["tables"] else None,
                info["tables"][0][0] if info["tables"] else None,
            ),
            (
                "позиционирование первой таблицы",
                reference["positions"][0] if reference["positions"] else None,
                info["positions"][0] if info["positions"] else None,
            ),
            ("картинок", len(reference["media"]), len(info["media"])),
            ("колонтитулов", reference["headers"], info["headers"]),
        ]
        for label, was, now in pairs:
            mark = "= " if was == now else "!="
            print(f"  {mark} {label}: {was} -> {now}")
            if was != now and label in ("поля страницы", "таблиц"):
                problems.append(f"{label} изменились: {was} -> {now}")

    print()
    if problems:
        print("замечания:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("проверка пройдена")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    reference = read(sys.argv[2]) if len(sys.argv) > 2 else None
    return report(sys.argv[1], reference)


if __name__ == "__main__":
    raise SystemExit(main())
