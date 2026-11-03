"""Что печатает протокол об административном правонарушении после правки."""
from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, DocumentType
from app.services import generation, snapshots, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _render_check():
    spec = importlib.util.spec_from_file_location(
        "render_check", Path("/app/scripts/check_all_templates_render.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        payload = snapshots.build_case_context(db, case.id)
        payload["documents"] = _render_check()._documents_meta(db, case)
        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = generation._active_template(db, document_type.id)
        print(f"шаблон: {template.version}")
        data = generation.build_document_bytes(
            payload, "administrative_protocol", storage.read_bytes(template.file)
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        texts = [
            "".join(n.text or "" for n in p.iter(f"{W}t"))
            for p in root.iter(f"{W}p")
        ]
        for text in texts:
            if any(key in text for key in ("выразилось", "22.09.2026", "06.07.2026",
                                           "Дата правонарушения",
                                           "Место правонарушения", "Однако")):
                print()
                print(" •", text[:600])
    finally:
        db.close()


if __name__ == "__main__":
    main()
