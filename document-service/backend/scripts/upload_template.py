"""Загрузка исправленного бланка новой версией — как это делает интерфейс.

Файл кладётся в хранилище, в базе появляется новая версия шаблона, прежняя
выключается. Старая версия остаётся в базе: по ней воспроизводится уже
напечатанный документ.

Сначала проверяем файл: это документ Word, подстановки не разорваны правкой,
ослабленного режима нет, листов столько же, сколько было (или сообщаем разницу).

По умолчанию — только проверка. Загрузить: --apply

Запуск:
    PYTHONPATH=/app python scripts/upload_template.py <файл.docx> <код_типа> [--apply]
"""
from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.models.enums import FileKind
from app.services import generation, pages, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def document_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        return "".join(node.text or "" for node in root.iter(f"{W}t"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("code")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"нет файла {path}")
        return 1
    data = path.read_bytes()
    print(f"файл: {path.name}, {len(data)} байт, тип документа {args.code}")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            print("ЭТО НЕ DOCX: нет word/document.xml")
            return 1
        content_types = archive.read("[Content_Types].xml").decode("utf-8", "replace")
    print("объявлен документом Word:",
          "wordprocessingml.document.main+xml" in content_types)

    text = document_text(data)
    tags = sorted({t.strip() for t in TAG.findall(text)})
    print(f"подстановок: {len(tags)}")
    if not tags:
        print("В БЛАНКЕ НЕТ ПОДСТАНОВОК — проверьте файл")
        return 1
    if "is defined" in text:
        print("в бланке ослабленный режим (is defined) — так нельзя")
        return 1

    db = SessionLocal()
    try:
        dt = db.scalar(select(DocumentType).where(DocumentType.code == args.code))
        if dt is None:
            print(f"нет типа документа {args.code!r}")
            return 1
        current = generation._active_template(db, dt.id)
        versions = [
            t.version
            for t in db.scalars(
                select(DocumentTemplate).where(DocumentTemplate.document_type_id == dt.id)
            )
        ]
        numbers = [int(v.lstrip("v")) for v in versions if v.lstrip("v").isdigit()]
        version = f"v{max(numbers) + 1 if numbers else 1}"

        old_pages = new_pages = None
        if current is not None and current.file is not None:
            old_pages = pages.count_pages(storage.read_bytes(current.file))
            print(f"действует: {current.version} (id={current.id}, "
                  f"file_id={current.file_id}, листов {old_pages})")
        new_pages = pages.count_pages(data)
        print(f"новый файл: листов {new_pages}, версия будет {version}")
        if old_pages is not None and new_pages is not None and old_pages != new_pages:
            print(f"  ВНИМАНИЕ: число листов изменилось: {old_pages} -> {new_pages}")

        if not args.apply:
            print("\nЭто проверка. Для загрузки добавьте --apply")
            return 0

        file = storage.save_bytes(
            db,
            data,
            f"{args.code}-{version}.docx",
            kind=FileKind.TEMPLATE,
            mime_type=DOCX_MIME,
            commit=False,
        )
        template = DocumentTemplate(
            document_type_id=dt.id,
            code=dt.code,
            name=dt.name,
            version=version,
            file_id=file.id,
            is_active=True,
        )
        db.add(template)
        for other in db.scalars(
            select(DocumentTemplate).where(DocumentTemplate.document_type_id == dt.id)
        ):
            if other is not template:
                other.is_active = False
        db.commit()
        active = generation._active_template(db, dt.id)
        print(f"\nзагружено: {active.version} (id={active.id}, file_id={active.file_id}), "
              f"sha256={str(file.sha256)[:12]}")
        print(f"выключена прежняя версия: {current.version if current else '—'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
