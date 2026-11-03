"""Задача 2: загрузка исправленного шаблона протокола осмотра в базу.

Файл Word может прийти с другим Content-Type, чем ждёт проверка загрузки,
поэтому сначала убеждаемся, что шаблон проходит ту же проверку, что и при
загрузке через интерфейс. Затем кладём файл в хранилище и заводим НОВУЮ
версию шаблона (как это делает интерфейс), старую выключаем.

По умолчанию — только проверка. Загрузить: --apply

Запуск: PYTHONPATH=/app python scripts/upload_protocol_template.py <файл.docx> [--apply]
"""
from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType, StoredFile
from app.models.enums import FileKind
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)

DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# Что обязательно должно остаться в шаблоне после правки.
REQUIRED_TAGS = [
    "control_body.name",
    "control_object.address",
    "case.actual_start_date_words",
    "case.control_kind",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    data = path.read_bytes()
    print(f"файл: {path.name}, {len(data)} байт")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            print("ЭТО НЕ DOCX: нет word/document.xml")
            return 1
        content_types = archive.read("[Content_Types].xml").decode("utf-8", "replace")
    if "[Content_Types].xml" not in names:
        print("нет [Content_Types].xml — Word может отказаться открыть файл")
    declared = (
        "wordprocessingml.document.main+xml" in content_types
    )
    print(f"Content-Type объявлен как документ Word: {declared}")

    text = ""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        from lxml import etree

        root = etree.fromstring(archive.read("word/document.xml"))
        text = "".join(node.text or "" for node in root.iter(f"{W}t"))
    missing = [tag for tag in REQUIRED_TAGS if tag not in text]
    if missing:
        print(f"НЕ ХВАТАЕТ ПОДСТАНОВОК: {missing}")
        return 1
    if "is defined" in text:
        print("в шаблоне ослабленный режим (is defined)")
        return 1
    print("подстановки на месте, ослабленного режима нет")

    db = SessionLocal()
    try:
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "inspection_protocol")
        )
        current = generation._active_template(db, dt.id)
        print(f"\nдействующая версия: {current.version} (id={current.id}, "
              f"file_id={current.file_id})")
        versions = [
            t.version
            for t in db.scalars(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == dt.id
                )
            )
        ]
        numbers = [int(v.lstrip("v")) for v in versions if v.lstrip("v").isdigit()]
        new_version = f"v{max(numbers) + 1 if numbers else 1}"
        print(f"версии в базе: {sorted(versions)} -> новая будет {new_version}")

        if not args.apply:
            print("\nЭто проверка. Для загрузки добавьте --apply")
            return 0

        file = storage.save_bytes(
            db,
            data,
            f"inspection_protocol-{new_version}.docx",
            kind=FileKind.TEMPLATE,
            mime_type=DOCX_MIME,
            commit=False,
        )
        current.is_active = False
        template = DocumentTemplate(
            document_type_id=dt.id,
            code=dt.code,
            name=dt.name,
            version=new_version,
            file_id=file.id,
            is_active=True,
        )
        db.add(template)
        db.commit()
        print(f"\nзагружено: версия {new_version}, file_id={file.id}, "
              f"sha256={str(file.sha256)[:12]}")
        print(f"выключена версия: {current.version} (id={current.id})")

        check = generation._active_template(db, dt.id)
        print(f"теперь действует: {check.version} (id={check.id}, "
              f"file_id={check.file_id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
