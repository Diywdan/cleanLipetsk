"""Выгрузка действующего шаблона протокола осмотра и образца заполненного документа.

Шаблон меняется только в базе, поэтому забирать его надо именно из хранилища:
файл в backend/templates/ система не читает.

Запуск: PYTHONPATH=/app python scripts/export_protocol.py /tmp
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Document, DocumentType
from app.services import generation, storage


OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")


def main() -> int:
    db = SessionLocal()
    try:
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "inspection_protocol")
        )
        template = generation._active_template(db, dt.id)
        if template is None or template.file is None:
            print("нет активного шаблона протокола осмотра")
            return 1
        data = storage.read_bytes(template.file)
        # Имена файлов латиницей: в консоли Windows кириллица в путях ломается.
        target = OUT / f"inspection_protocol-template-{template.version}.docx"
        target.write_bytes(data)
        print(f"шаблон: id={template.id} версия={template.version} file_id={template.file_id}")
        print(f"  {template.file.original_name}, {len(data)} байт -> {target}")

        # Образец: последний собранный протокол — видно, что подставляется.
        document = db.scalars(
            select(Document)
            .where(Document.document_type_id == dt.id)
            .order_by(Document.id.desc())
        ).first()
        if document and document.generated_file:
            sample = storage.read_bytes(document.generated_file)
            case = db.get(ControlCase, document.package.control_case_id)
            number = case.case_number if case else "?"
            path = OUT / f"inspection_protocol-sample-case-{number}.docx"
            path.write_bytes(sample)
            print(f"образец: документ {document.id}, заявка {number}, "
                  f"{len(sample)} байт -> {path}")
        else:
            print("образец: собранных протоколов нет")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
