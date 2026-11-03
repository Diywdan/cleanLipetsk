"""Регистрация DOCX-шаблонов из каталога templates.

Каталог templates/<код типа документа>/<версия>.docx. Файл попадает в
файловое хранилище (по sha256), а в базе появляется версия шаблона.
Версия обязательна: без неё нельзя воспроизвести документ после того,
как бланк поменяли приказом.

Запуск: PYTHONPATH=/app python scripts/register_templates.py
"""

from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType
from app.models.enums import FileKind
from app.services import storage


TEMPLATES_DIR = Path("/app/templates")


def main() -> None:
    db = SessionLocal()
    try:
        paths = sorted(TEMPLATES_DIR.glob("*/*.docx"))
        if not paths:
            print(f"в {TEMPLATES_DIR} нет шаблонов")
            return

        for path in paths:
            code = path.parent.name
            version = path.stem

            document_type = db.scalar(
                select(DocumentType).where(DocumentType.code == code)
            )
            if document_type is None:
                print(f"пропуск {path.name}: нет типа документа {code!r}")
                continue

            file = storage.save_bytes(
                db,
                path.read_bytes(),
                path.name,
                kind=FileKind.TEMPLATE,
                commit=False,
            )
            template = db.scalar(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.version == version,
                )
            )
            if template is None:
                template = DocumentTemplate(
                    document_type_id=document_type.id,
                    code=code,
                    name=document_type.name,
                    version=version,
                    file_id=file.id,
                    is_active=True,
                )
                db.add(template)
            else:
                template.file_id = file.id
                template.is_active = True
            db.flush()
            print(f"шаблон {code} {version}: file_id={file.id} sha256={file.sha256[:12]}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
