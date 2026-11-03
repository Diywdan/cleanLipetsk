"""Задача 3: что именно содержит действующая версия протокола осмотра (v3).

Проверяем по элементам (python-docx + lxml), в том числе колонтитулы:
часть подстановок живёт там. Файл читается из базы, а не с диска.
"""
from __future__ import annotations

import io
import re
import zipfile

from docx import Document as DocxDocument

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)

# Что должно быть в v3 — по описанию правок в задании.
CHECKS = {
    "место из данных (control_object.address)": r"control_object\.address",
    "дата из данных (case.actual_start_date_words)": r"case\.actual_start_date_words",
    "инспектор необязателен": r"if inspector",
    "старой константы «Теперика, д.3» нет": r"(?!)",
}


def all_text(data: bytes) -> str:
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist()
                 if n.startswith("word/") and n.endswith(".xml")]
        for name in names:
            parts.append(zf.read(name).decode("utf-8", "replace"))
    return "\n".join(parts)


def main() -> int:
    db = SessionLocal()
    try:
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "inspection_protocol")
        )
        template = generation._active_template(db, dt.id)
        data = storage.read_bytes(template.file)
        text = all_text(data)
        print(f"действующая версия: {template.version} (id={template.id}, "
              f"file_id={template.file_id}, {len(data)} байт)")
        print()

        for label, pattern in CHECKS.items():
            hits = re.findall(pattern, text)
            mark = "да" if hits else "НЕТ"
            print(f"  {mark:>3}  {label}")

        print()
        print("  подстановки, относящиеся к месту и дате:")
        for tag in sorted(set(TAG.findall(text))):
            if any(k in tag for k in ("address", "date", "control_object", "case.")):
                print(f"    {tag[:110]}")

        print()
        print("  обращение к инспектору:")
        for tag in sorted(set(TAG.findall(text))):
            if "inspector" in tag:
                print(f"    {tag[:110]}")

        print()
        print("  остатки старой константы:")
        for needle in ("Теперика, д.3", "Теперика, д. 3", "2861945", "22» сентября 2026"):
            count = text.count(needle)
            print(f"    «{needle}»: {count}")

        print()
        print("  подписей под фотографиями в приложении:")
        document = DocxDocument(io.BytesIO(data))
        print(f"    абзацев в документе: {len(document.paragraphs)}, "
              f"таблиц: {len(document.tables)}")
        captions = [
            p.text.strip() for p in document.paragraphs
            if p.text.strip() and "фотоматериал" in p.text.lower()
        ]
        for caption in captions:
            print(f"    «{caption[:90]}»")

        print()
        print(f"  всего тегов в шаблоне: {len(set(TAG.findall(text)))}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
