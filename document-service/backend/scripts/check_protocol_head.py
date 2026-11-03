"""Что печатается в шапке протокола: номер, дата, место составления."""
from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, DocumentType
from app.services import generation, inspections, snapshots, storage

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
        inspection = inspections.repeat(db, case.id) or inspections.primary(db, case.id)
        print(f"осмотр: {inspection.inspection_kind.value}, {inspection.started_at}")

        payload = snapshots.build_case_context(db, case.id, inspection)
        payload["documents"] = module._documents_meta(db, case)
        administrative = payload["administrative"]
        print(f"  номер протокола: {administrative.get('protocol_number')!r}")
        print(f"  дата протокола:  {administrative.get('protocol_date_short')!r}")
        print(f"  место:           {administrative.get('protocol_place')!r}")

        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = generation._active_template(db, document_type.id)
        data = generation.build_document_bytes(
            payload, "administrative_protocol", storage.read_bytes(template.file)
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        paragraphs = [
            "".join(n.text or "" for n in p.iter(f"{W}t"))
            for p in root.iter(f"{W}p")
        ]
        print()
        print("в документе:")
        for text in paragraphs[:14]:
            if text.strip():
                print(f"  {text[:100]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
