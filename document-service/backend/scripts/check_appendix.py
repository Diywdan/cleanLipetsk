"""Что печатается в строке «Приложение» протокола."""
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


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "render_check", Path("/app/scripts/check_all_templates_render.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        payload = snapshots.build_case_context(db, case.id)
        payload["documents"] = module._documents_meta(db, case)
        administrative = payload.get("administrative") or {}
        print("appendix_note в данных:", repr(administrative.get("appendix_note")))

        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = generation._active_template(db, document_type.id)
        data = generation.build_document_bytes(
            payload, "administrative_protocol", storage.read_bytes(template.file)
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        for paragraph in root.iter(f"{W}p"):
            text = "".join(n.text or "" for n in paragraph.iter(f"{W}t"))
            if "Приложение" in text:
                print("в документе:", repr(text))
    finally:
        db.close()


if __name__ == "__main__":
    main()
