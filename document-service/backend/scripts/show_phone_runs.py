"""Показывает, по каким кускам разложен вписанный телефон в бланке."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def q(tag: str) -> str:
    return f"{W}{tag}"


def main() -> None:
    data = Path(sys.argv[1]).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    for index, paragraph in enumerate(root.iter(q("p")), 1):
        text = "".join(n.text or "" for n in paragraph.iter(q("t")))
        if "38-77-75" not in text and "4742" not in text:
            continue
        print(f"--- абзац {index}: {text!r}")
        for node in paragraph.iter(q("t")):
            print(f"    t: {node.text!r}")


if __name__ == "__main__":
    main()
