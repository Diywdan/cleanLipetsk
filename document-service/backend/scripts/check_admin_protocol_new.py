"""Проверка подстановок нового бланка административного протокола.

Собирает документ на реальных данных и проверяет, что каждая подстановка
разрешилась. Данные о прошлом предписании подставляются в пробный снимок:
у заявки их пока нет, а проверить бланк нужно до загрузки.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentType
from app.services import generation

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)


def document_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        return "".join(n.text or "" for n in root.iter(f"{W}t"))


def main() -> int:
    path = Path(sys.argv[1])
    raw = path.read_bytes()
    print(f"бланк: {path.name} ({len(raw)} байт)")

    # Подстановки в бланке.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = document_text(raw)
    tags = sorted({t.strip() for t in TAG.findall(text)})
    print(f"подстановок: {len(tags)}")

    db = SessionLocal()
    try:
        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = dict(snapshot.payload)

        # Пробные данные о прошлом предписании.
        adm = dict(payload.get("administrative") or {})
        if adm.get("prior_prescription_number") is None:
            adm.update(
                {
                    "prior_prescription_number": "48001704800001209198",
                    "prior_prescription_date_short": "06.07.2026",
                    "prior_prescription_due_short": "06.08.2026",
                    "prior_prescription_basis": "части 1,2 статьи 4",
                    "offense_date_short": "07.08.2026",
                    "offense_time": "00 ч. 01 мин.",
                    "offense_place": "г. Москва, ул. 3-я Песчаная, д. 2А",
                    "offense_article": "частью 1 статьи 19.5",
                }
            )
            payload["administrative"] = adm
            print("  (данные о прошлом предписании подставлены для проверки)")

        try:
            built = generation.build_document_bytes(payload, "administrative_protocol", raw)
        except Exception as exc:  # noqa: BLE001
            print(f"НЕ СОБИРАЕТСЯ: {type(exc).__name__}: {exc}")
            return 1

        result_text = document_text(built)
        left = TAG.findall(result_text)
        print(f"собрался: {len(built)} байт, неподставленных тегов: {len(left)}")
        for tag in left[:5]:
            print(f"  остался: {tag}")

        print("\n=== текст протокола (фрагмент про правонарушение) ===")
        start = result_text.find("Административное правонарушение выразилось")
        fragment = result_text[start:start + 1600] if start >= 0 else result_text[:1200]
        for line in fragment.splitlines():
            if line.strip():
                print(f"  {line.strip()[:110]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
