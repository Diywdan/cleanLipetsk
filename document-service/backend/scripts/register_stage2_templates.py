"""Register the stage-2 assignment and decision templates.

Dry-run by default. Apply with ``--apply``. Only v1 is activated for the two
document types; any other versions remain registered but inactive.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.models.enums import FileKind
from app.services import storage


TEMPLATES = {
    "assignment": Path("/app/templates/assignment/v1.docx"),
    "decision": Path("/app/templates/decision/v1.docx"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="register and activate templates")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan = []
        for code, path in TEMPLATES.items():
            if not path.is_file():
                raise SystemExit(f"Нет файла шаблона: {path}")
            document_type = db.scalar(
                select(DocumentType).where(DocumentType.code == code)
            )
            if document_type is None:
                raise SystemExit(f"Нет типа документа в базе: {code}")
            template = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.version == "v1",
                )
            )
            active = list(
                db.scalars(
                    select(DocumentTemplate).where(
                        DocumentTemplate.document_type_id == document_type.id,
                        DocumentTemplate.is_active.is_(True),
                    )
                )
            )
            plan.append((code, path, document_type, template, active))
            print(
                f"{code}: файл={path.name}, версия=v1, "
                f"запись={'есть' if template else 'будет создана'}, "
                f"сейчас активно={','.join(item.version for item in active) or 'ничего'}"
            )

        if not args.apply:
            print("План без изменений. Для применения добавьте --apply.")
            return

        for code, path, document_type, template, active in plan:
            file = storage.save_bytes(
                db,
                path.read_bytes(),
                path.name,
                kind=FileKind.TEMPLATE,
                commit=False,
            )
            if template is None:
                template = DocumentTemplate(
                    document_type_id=document_type.id,
                    code=code,
                    name=document_type.name,
                    version="v1",
                    file_id=file.id,
                    is_active=True,
                )
                db.add(template)
            else:
                template.file_id = file.id
                template.is_active = True
            for other in active:
                if other.id != template.id:
                    other.is_active = False
            db.flush()
            print(f"Зарегистрирован активный шаблон {code} v1 (file_id={file.id})")

        db.commit()
        print("Шаблоны этапа 2 зарегистрированы; генерация документов не запускалась.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
