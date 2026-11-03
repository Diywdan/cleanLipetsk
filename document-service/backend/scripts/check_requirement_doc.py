"""Проверка: что попало в предписание и как разбирается форма работ."""
from __future__ import annotations

import io
import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, DocumentType
from app.services import generation, snapshots, storage
from app.web import router

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Номера и даты документов пакета: бланк предписания печатает их в шапке.
def _documents_meta(db, case) -> dict:
    from datetime import date
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "render_check", Path("/app/scripts/check_all_templates_render.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._documents_meta(db, case)


class FakeForm:
    """Минимальная форма: только getlist и get."""

    def __init__(self, data: dict[str, list[str]]):
        self.data = data

    def getlist(self, key: str) -> list[str]:
        return self.data.get(key, [])

    def get(self, key: str, default=None):
        values = self.data.get(key)
        return values[0] if values else default


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))

        print("=== разбор работ из формы ===")
        form = FakeForm(
            {
                "violation_work_ids": ["1", "", "3", "1"],
                "violation_work_quantities": ["4", "", "2,5", "9"],
                "violation_type_id": ["4"],
            }
        )
        rows = router._work_rows(form)
        print(f"  строки: {rows} (пустая пропущена, повтор отброшен)")
        print(f"  описание: {router._assembled_description(db, case, rows, form)}")

        print()
        print("=== текст предписания в документе ===")
        payload = snapshots.build_case_context(db, case.id)
        payload["documents"] = _documents_meta(db, case)
        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "prescription")
        )
        template = generation._active_template(db, document_type.id)
        data = generation.build_document_bytes(
            payload, "prescription", storage.read_bytes(template.file)
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
            text = "".join(n.text or "" for n in root.iter(f"{W}t"))
        index = text.find("В целях")
        print(text[index:index + 720] if index >= 0 else "  требования нет")
    finally:
        db.close()


if __name__ == "__main__":
    main()
