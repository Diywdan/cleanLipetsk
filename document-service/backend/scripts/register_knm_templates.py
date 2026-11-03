"""Register the repository's current KNM DOCX templates.

Dry-run by default. Apply with ``--apply``. For each KNM document type this
activates exactly one selected repository version and leaves other versions
registered but inactive.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.models.enums import FileKind
from app.services import storage


TEMPLATES = {
    "act": ("v7", Path("/app/templates/act/v7.docx")),
    "inspection_protocol": ("v5", Path("/app/templates/inspection_protocol/v5.docx")),
    "prescription": ("v4", Path("/app/templates/prescription/v4.docx")),
    "direction": ("v3", Path("/app/templates/direction/v3.docx")),
}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def is_docx(path: Path) -> bool:
    try:
        with ZipFile(path) as archive:
            return "word/document.xml" in archive.namelist()
    except (BadZipFile, OSError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="register and activate templates")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan = []
        for code, (version, path) in TEMPLATES.items():
            if not path.is_file() or not is_docx(path):
                raise SystemExit(f"Нет корректного DOCX-шаблона: {path}")
            document_type = db.scalar(select(DocumentType).where(DocumentType.code == code))
            if document_type is None:
                raise SystemExit(f"Нет типа документа в базе: {code}")
            template = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.version == version,
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
            plan.append((code, version, path, document_type, template, active))
            print(
                f"{code}: кандидат={path.name}, версия={version}, "
                f"запись={'есть' if template else 'будет создана'}, "
                f"сейчас активно={','.join(item.version for item in active) or 'ничего'}"
            )

        if not args.apply:
            print("План без изменений. Для применения добавьте --apply.")
            return

        for code, version, path, document_type, template, active in plan:
            stored_file = storage.save_bytes(
                db,
                path.read_bytes(),
                path.name,
                kind=FileKind.TEMPLATE,
                mime_type=DOCX_MIME,
                commit=False,
            )
            if template is None:
                template = DocumentTemplate(
                    document_type_id=document_type.id,
                    code=code,
                    name=document_type.name,
                    version=version,
                    file_id=stored_file.id,
                    is_active=True,
                )
                db.add(template)
            else:
                template.file_id = stored_file.id
                template.is_active = True
            for other in active:
                if other.id != template.id:
                    other.is_active = False
            db.flush()
            print(f"Активирован шаблон {code} {version}")

        db.commit()
        print("Шаблоны КНМ зарегистрированы; генерация документов не запускалась.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
