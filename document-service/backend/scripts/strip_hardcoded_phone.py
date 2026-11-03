"""Правка бланка письма о направлении акта: убираем вписанный телефон.

В подписном блоке рядом с ФИО инспектора стояли два телефона: из справочника
({{ inspector.phone_with_code }}) и вписанный текстом «8 (4742) 38-77-75».
Вписанный убираем — он не обновляется при смене данных органа.

По умолчанию только показать. Записать: --apply

Запуск: PYTHONPATH=/app python scripts/strip_hardcoded_phone.py <файл> [--apply]
"""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PHONE = "8 (4742) 38-77-75"


def q(tag: str) -> str:
    return f"{W}{tag}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source = Path(args.path)
    data = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names}

    root = etree.fromstring(parts["word/document.xml"])
    removed = 0
    # Телефон может быть разложен по нескольким кускам текста в одном абзаце
    # («8 », «(4742) », «38-77-75»), поэтому ищем по склеенному тексту абзаца
    # и чистим все куски этого абзаца.
    for paragraph in root.iter(q("p")):
        text = "".join(n.text or "" for n in paragraph.iter(q("t")))
        if PHONE not in text:
            continue
        rest = text.replace(PHONE, "").strip()
        if rest:
            # В абзаце есть и другие данные — трогать не будем, покажем.
            print(f"  ВНИМАНИЕ: в абзаце кроме телефона есть: {rest!r}")
            continue
        print(f"  найден абзац только с телефоном: {text!r}")
        parents = []
        for node in paragraph.iter(q("t")):
            node.text = ""
            parent = node.getparent()
            if parent is not None and parent not in parents:
                parents.append(parent)
        # Пустые run-ы убираем, чтобы не оставлять мусор в разметке.
        for run in parents:
            if etree.QName(run).localname == "r" and not len(run):
                run.getparent().remove(run)
        removed += 1

    if not removed:
        print("вписанного телефона не найдено")
        return 0

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    text = "".join(n.text or "" for n in etree.fromstring(parts["word/document.xml"]).iter(q("t")))
    print(f"  после правки телефон в тексте: {PHONE in text}")
    print(f"  подстановка телефона на месте: {'inspector.phone_with_code' in text}")

    if not args.apply:
        print("\nЭто проверка. Для записи добавьте --apply")
        return 0

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, parts[name])
    target = source.with_name(source.stem + "-fixed.docx")
    target.write_bytes(buffer.getvalue())
    print(f"записано: {target} ({len(buffer.getvalue())} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
