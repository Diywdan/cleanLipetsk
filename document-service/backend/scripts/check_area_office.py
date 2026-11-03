"""Проверка: адрес и кабинет берутся из управы.

Управа создаётся в транзакции и откатывается — данные не меняются.
"""
from __future__ import annotations

import io
import zipfile

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Address,
    Area,
    AreaAddress,
    ControlBody,
    ControlCase,
    DocumentTemplate,
    DocumentType,
)
from app.services import generation, snapshots, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        address = db.get(Address, case.control_object.address_id)
        body = db.get(ControlBody, case.control_body_id)
        print(f"адрес объекта: {address.full_address}")
        print(f"орган: {body.name if body else None}")

        # Управа на этот адрес, как это сделал бы оператор на странице «Управы».
        area = Area(
            name="Проверочная управа",
            control_body_id=case.control_body_id,
            address_id=body.address_id if body else None,
            office="207",
        )
        db.add(area)
        db.flush()
        db.add(AreaAddress(area_id=area.id, address_id=address.id))
        db.flush()

        payload = snapshots.build_case_context(db, case.id)
        administrative = payload["administrative"]
        print()
        print(f"  адрес управы: {area.address.full_address}")
        print(f"  кабинет управы: {area.office}")
        print(f"  место явки в данных: {administrative.get('appearance_place')!r}")
        print(f"  кабинет в данных:    {administrative.get('appearance_office')!r}")

        document_type = db.scalar(
            select(DocumentType).where(DocumentType.code == "appearance_notice")
        )
        template = db.scalar(
            select(DocumentTemplate).where(
                DocumentTemplate.document_type_id == document_type.id,
                DocumentTemplate.is_active.is_(True),
            )
        )
        payload["documents"] = {"appearance_notice": {"issued_on": "2026-10-27"}}
        data = generation.build_document_bytes(
            payload, "appearance_notice", storage.read_bytes(template.file)
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        text = "".join(n.text or "" for n in root.iter(f"{W}t"))
        start = text.find("административное здание")
        print()
        print("в уведомлении:", text[start:start + 160] if start >= 0 else "не найдено")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
