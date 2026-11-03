"""Сравнение подстановок и колонтитулов у всех версий шаблона протокола осмотра."""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)


def analyse(path: Path) -> tuple[list[str], list[str], list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        document = etree.fromstring(archive.read("word/document.xml"))
        text = "".join(node.text or "" for node in document.iter(f"{W}t"))
        tags = TAG.findall(text)
        headers = sorted(
            n for n in names if re.search(r"word/(header|footer)\d*\.xml$", n)
        )
        header_text = []
        for name in headers:
            root = etree.fromstring(archive.read(name))
            header_text.append(
                f"{name}: " + "".join(n.text or "" for n in root.iter(f"{W}t"))[:70]
            )
    return tags, headers, header_text


def short(tags: list[str]) -> str:
    return ", ".join(t.strip() for t in tags)


def main() -> None:
    files = [Path(p) for p in sys.argv[1:]]
    data = {}
    for path in files:
        tags, headers, header_text = analyse(path)
        data[path] = (tags, headers, header_text)
        print(f"=== {path.name} ({path.stat().st_size} б) ===")
        print(f"  подстановок: {len(tags)}")
        print(f"  колонтитулы: {headers}")
        for line in header_text:
            print(f"    {line}")
        print()

    print("=== какие подстановки есть только в новом файле ===")
    if len(files) >= 2:
        newest = data[files[-1]][0]
        others: set[str] = set()
        for path in files[:-1]:
            others.update(t.strip() for t in data[path][0])
        only_new = sorted({t.strip() for t in newest} - others)
        for tag in only_new:
            print(f"  {tag}")
        lost = sorted(others - {t.strip() for t in newest})
        print("=== какие подстановки потеряны (были в других версиях) ===")
        for tag in lost:
            print(f"  {tag}")


if __name__ == "__main__":
    main()
