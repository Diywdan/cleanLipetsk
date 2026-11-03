"""Поиск артефактов в шаблонах: приклеенные слова, латиница вплотную к кириллице.

Такие места появляются при сборке бланка: значение из старого документа
осталось в тексте рядом с тегом, слово потеряло пробел на переносе строки.
В готовом документе это выглядит как «услугtula@quadra.ru» или «актвыездной».
"""

import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def q(tag: str) -> str:
    return f"{W}{tag}"


def document_text(path: Path) -> list[str]:
    """Тексты абзацев шаблона; разрывы строки и табуляции — как перевод строки.

    Внутри одной ячейки таблицы несколько абзацев или разрывов строки дают в
    документе отдельные строки. Если их не учитывать, соседние строки выглядят
    как склеенные слова, и проверка ругается на исправный шаблон.
    """

    with zipfile.ZipFile(path) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    lines: list[str] = []
    for paragraph in document.iter(q("p")):
        parts: list[str] = []
        for node in paragraph.iter():
            name = etree.QName(node).localname
            if name == "t":
                parts.append(node.text or "")
            elif name in ("br", "tab", "cr"):
                parts.append("\n")
        text = "".join(parts)
        for line in text.split("\n"):
            if line.strip():
                lines.append(line)
    return lines


# Латинская буква вплотную к кириллице и наоборот: так выглядит приклеенное
# значение рядом со словом.
GLUED = re.compile(r"(?:[а-яёА-ЯЁ][a-zA-Z]|[a-zA-Z][а-яёА-ЯЁ])")
# Слово вплотную к тегу: «услуг{{ ... }}» — в документе получится «услугЗначение».
GLUED_TAG = re.compile(r"[а-яёА-ЯЁa-zA-Z0-9]\{\{|\}\}[а-яёА-ЯЁa-zA-Z0-9]")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/templates")
    found = 0
    for path in sorted(root.glob("*/*.docx")):
        problems: list[str] = []
        for line in document_text(path):
            # Теги не проверяем: внутри них латиница — это имена переменных.
            without_tags = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", line)
            if GLUED.search(without_tags):
                problems.append(f"приклеена латиница: {line[:110]!r}")
            if GLUED_TAG.search(line):
                problems.append(f"слово вплотную к тегу: {line[:110]!r}")
        if problems:
            found += len(problems)
            print(f"=== {path.parent.name}/{path.name} ===")
            for problem in problems:
                print("   ", problem)
    if not found:
        print(f"в {root} артефактов не найдено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
