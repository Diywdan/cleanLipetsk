"""Поиск жёстко вписанных адресов и координат во всех бланках."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from lxml import etree

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Подстановки не считаем: там адрес приходит из данных.
TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)


def texts(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        return "".join(n.text or "" for n in root.iter(f"{W}t"))


def main() -> None:
    db = SessionLocal()
    try:
        print("=== адреса, вписанные в бланки текстом ===")
        found_any = False
        for dt in db.scalars(select(DocumentType).order_by(DocumentType.id)):
            template = generation._active_template(db, dt.id)
            if template is None or template.file is None:
                continue
            text = texts(storage.read_bytes(template.file))
            # Убираем подстановки, чтобы не ловить адреса внутри них.
            cleaned = TAG.sub(" ", text)
            emails = sorted(set(EMAIL.findall(cleaned)))
            if emails:
                found_any = True
                print(f"  {dt.code} ({template.version}):")
                for email in emails:
                    print(f"      {email}")
        if not found_any:
            print("  нет: во всех действующих бланках адреса приходят подстановкой")
    finally:
        db.close()


if __name__ == "__main__":
    main()
