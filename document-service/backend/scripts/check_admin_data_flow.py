"""Сквозная проверка: поля прошлого предписания доходят до документа.

Заполняет данные производства по заявке, собирает протокол об
административном правонарушении и проверяет, что в тексте появились дата,
номер и срок прошлого предписания. Изменения откатываются.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AdministrativeCase, ControlCase, DocumentType
from app.services import generation, snapshots, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_of(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        return "".join(n.text or "" for n in root.iter(f"{W}t"))


def main() -> int:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        row = db.scalar(
            select(AdministrativeCase).where(
                AdministrativeCase.control_case_id == case.id
            )
        )
        created = row is None
        if row is None:
            row = AdministrativeCase(control_case_id=case.id)
            db.add(row)

        row.prior_prescription_number = "48001704800001209198"
        row.prior_prescription_date = date(2026, 7, 6)
        row.prior_prescription_due = date(2026, 8, 6)
        row.prior_prescription_basis = "части 1,2 статьи 4"
        row.offense_date = date(2026, 8, 7)
        row.offense_time = "00 ч. 01 мин."
        row.offense_place = "г. Москва, ул. 3-я Песчаная, д. 2А"
        row.protocol_number = "48-АП-000123"
        row.protocol_date = date(2026, 8, 12)
        row.protocol_place = "г. Липецк, ул. Механизаторов, 15"
        db.flush()
        print(f"данные производства {'созданы' if created else 'обновлены'}")

        payload = snapshots.build_case_context(db, case.id)
        adm = payload["administrative"]
        for key in (
            "prior_prescription_number",
            "prior_prescription_date_short",
            "prior_prescription_due_short",
            "prior_prescription_basis",
            "offense_date_short",
            "offense_place",
        ):
            print(f"  {key} = {adm.get(key)!r}")

        payload["documents"] = {}
        dt = db.scalar(
            select(DocumentType).where(DocumentType.code == "administrative_protocol")
        )
        template = generation._active_template(db, dt.id)
        data = generation.build_document_bytes(
            payload, "administrative_protocol", storage.read_bytes(template.file)
        )
        print(f"\nпротокол собран: {len(data)} байт, шаблон {template.version}")

        text = text_of(data)
        checks = {
            "номер прошлого предписания": "48001704800001209198",
            "дата прошлого предписания": "06.07.2026",
            "срок исполнения": "06.08.2026",
            "норма выдачи": "части 1,2 статьи 4",
            "дата правонарушения": "07.08.2026",
            "место правонарушения": "Песчаная",
        }
        print("\nчто попало в документ:")
        for label, needle in checks.items():
            print(f"  {'да' if needle in text else 'НЕТ':>3}  {label} ({needle})")

        print("\nчужого дела в документе:",
              "нет" if "ПОЧТА РОССИИ" not in text else "ЕСТЬ 'ПОЧТА РОССИИ'")

        start = text.find("Административное правонарушение выразилось")
        fragment = text[start:start + 1300] if start >= 0 else ""
        print("\n=== текст про правонарушение ===")
        for line in fragment.splitlines():
            if line.strip():
                print(f"  {line.strip()[:110]}")

        db.rollback()
        print("\nизменения откатаны")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
