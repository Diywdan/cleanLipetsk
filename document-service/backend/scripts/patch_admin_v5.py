"""Правка бланка протокола об административном правонарушении (v5).

Две правки:

* в бланке были вписаны дата и место правонарушения конкретного дела
  («07.08.2026 в 00 ч. 01 мин.», «г. Москва, ул. 3-я Песчаная, д. 2А») —
  заменяются подстановками;
* первый абзац описания был длинной фразой про текущее мероприятие —
  заменяется событием правонарушения, которое собирается из дат наших
  документов (прежнее мероприятие, срок предписания, неисполнение).
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Что заменить: ищем абзацы по началу текста.
REPLACEMENTS: list[tuple[str, str]] = [
    (
        "{{ administrative.protocol_date_short }} {{ inspector.position_instrumental_lower }}",
        "{{ administrative.circumstances }}",
    ),
    (
        "Дата правонарушения: 07.08.2026 в 00 ч. 01 мин.",
        "Дата правонарушения: {{ administrative.offense_when }}",
    ),
    (
        "Место правонарушения: г. Москва, ул. 3-я Песчаная, д. 2А",
        "Место правонарушения: {{ administrative.offense_place }}",
    ),
]


def paragraph_text(paragraph) -> str:
    return "".join(n.text or "" for n in paragraph.iter(f"{W}t"))


def replace_text(paragraph, text: str) -> None:
    """Меняет текст абзаца, сохраняя оформление первого run-а."""

    runs = paragraph.findall(f"{W}r")
    template_run = runs[0] if runs else None
    for run in runs[1:]:
        paragraph.remove(run)
    if template_run is None:
        template_run = etree.SubElement(paragraph, f"{W}r")
    for node in list(template_run):
        if etree.QName(node).localname != "rPr":
            template_run.remove(node)
    node = etree.SubElement(template_run, f"{W}t")
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    data = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names}

    root = etree.fromstring(parts["word/document.xml"])
    paragraphs = list(root.iter(f"{W}p"))

    for prefix, new_text in REPLACEMENTS:
        found = [p for p in paragraphs if paragraph_text(p).startswith(prefix)]
        if not found:
            print(f"НЕ НАЙДЕНО: {prefix[:60]}")
            continue
        for paragraph in found:
            print(f"  заменяю: {paragraph_text(paragraph)[:70]!r}")
            replace_text(paragraph, new_text)

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
