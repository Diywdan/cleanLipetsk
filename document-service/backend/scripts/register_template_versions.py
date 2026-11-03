"""Регистрация исправленных бланков новой версией.

Делает то же, что интерфейс при загрузке шаблона: файл идёт в хранилище,
в базе появляется новая версия, старая выключается. Так на любой документ
можно сослаться версией, по которой он напечатан.

По умолчанию — только показать план. Применить: --apply

Запуск: PYTHONPATH=/app python scripts/register_template_versions.py [--apply]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.models.enums import FileKind
from app.services import generation, storage

DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# Код типа документа -> файл новой версии, лежащий рядом с черновиками.
NEW_VERSIONS = {
    "direction": Path("/app/templates/direction/v2.docx"),
    "act_direction": Path("/app/templates/act_direction/v2.docx"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        for code, path in NEW_VERSIONS.items():
            if not path.exists():
                print(f"{code}: нет файла {path}")
                continue
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            if dt is None:
                print(f"{code}: нет типа документа")
                continue
            current = generation._active_template(db, dt.id)
            version = path.stem  # «v2»
            print(f"=== {code} ===")
            print(f"  новый файл: {path} ({path.stat().st_size} б), версия {version}")
            print(f"  сейчас действует: {current.version} (id={current.id})")

            existing = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == dt.id,
                    DocumentTemplate.version == version,
                )
            )
            if existing is not None:
                print(f"  версия {version} уже есть (id={existing.id}) — обновим файл")

            if not args.apply:
                continue

            file = storage.save_bytes(
                db,
                path.read_bytes(),
                f"{code}-{version}.docx",
                kind=FileKind.TEMPLATE,
                mime_type=DOCX_MIME,
                commit=False,
            )
            if existing is None:
                template = DocumentTemplate(
                    document_type_id=dt.id,
                    code=dt.code,
                    name=dt.name,
                    version=version,
                    file_id=file.id,
                    is_active=True,
                )
                db.add(template)
            else:
                template = existing
                template.file_id = file.id
                template.is_active = True

            # Включённой остаётся одна версия: старая выключается.
            for other in db.scalars(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == dt.id
                )
            ):
                if other is not template:
                    other.is_active = False

            db.flush()
            print(f"  загружено: file_id={file.id} sha={str(file.sha256)[:12]}")

        if args.apply:
            db.commit()
            print("\nизменения записаны")
            for code in NEW_VERSIONS:
                dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
                active = generation._active_template(db, dt.id)
                print(f"  {code}: действует {active.version}, "
                      f"file_id={active.file_id}")
        else:
            print("\nЭто план. Для записи добавьте --apply")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
