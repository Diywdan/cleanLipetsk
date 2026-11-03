"""Откуда система берёт бланки: только из файлов в базе или есть жёсткие копии.

Проверяем по коду, что рендер идёт от файла шаблона, и ищем места, где
структура документа могла бы быть зашита в коде (сборка DOCX из кода,
собственные XML-заготовки, вписанные строки бланка).
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path("/app/app")


def main() -> None:
    print("=== где читается файл шаблона ===")
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "read_bytes(template.file)" in text or "template.file" in text:
            for number, line in enumerate(text.splitlines(), 1):
                if "template.file" in line or "read_bytes(template" in line:
                    print(f"  {path.relative_to(APP)}:{number}: {line.strip()[:100]}")

    print()
    print("=== есть ли сборка DOCX из кода, а не из файла ===")
    suspicious = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = []
        if "docx.Document()" in text or "Document()" in text:
            hits.append("создание документа с нуля")
        if re.search(r"<w:document", text) or re.search(r"w:body", text):
            hits.append("XML-заготовка Word в коде")
        if "add_paragraph(" in text and "template" not in path.name:
            hits.append("сборка абзацев кодом")
        if hits:
            suspicious.append((path.relative_to(APP), hits))
    if suspicious:
        for path, hits in suspicious:
            print(f"  {path}: {', '.join(hits)}")
    else:
        print("  нет: документы собираются только из файлов шаблонов")

    print()
    print("=== генератор: как получается бланк ===")
    generation = (APP / "services" / "generation.py").read_text(encoding="utf-8")
    for number, line in enumerate(generation.splitlines(), 1):
        if "def build_document_bytes" in line:
            for offset in range(number - 1, min(number + 22, len(generation.splitlines()))):
                print(f"  {offset + 1}: {generation.splitlines()[offset]}")
            break


if __name__ == "__main__":
    main()
