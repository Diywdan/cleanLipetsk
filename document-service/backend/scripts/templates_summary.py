"""Сводка по действующим шаблонам: листы, структура, подстановки, сверка с репозиторием.

Запуск: PYTHONPATH=/app python scripts/templates_summary.py [каталог_черновиков]
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, pages, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)
DRAFTS = Path("/app/templates")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyse(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        text = "".join(node.text or "" for node in root.iter(f"{W}t"))
        tables = len(root.findall(f".//{W}tbl"))
        rows = len(root.findall(f".//{W}tr"))
        paragraphs = [
            "".join(node.text or "" for node in p.iter(f"{W}t")).strip()
            for p in root.iter(f"{W}p")
        ]
    first = next((line for line in paragraphs if len(line) > 6), "")
    tags = sorted({t.strip() for t in TAG.findall(text)})
    return {
        "tables": tables,
        "rows": rows,
        "tags": tags,
        "first": first,
        "weak": sum(1 for t in tags if "is defined" in t),
    }


def main() -> int:
    db = SessionLocal()
    try:
        types = list(
            db.scalars(
                select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
            )
        )
        rows = []
        for dt in types:
            template = generation._active_template(db, dt.id)
            if template is None or template.file is None:
                rows.append((dt, None, None, None))
                continue
            data = storage.read_bytes(template.file)
            info = analyse(data)
            info["bytes"] = len(data)
            info["sha"] = sha(data)
            info["pages"] = pages.count_pages(data) if pages.available() else None
            draft = DRAFTS / dt.code / f"{template.version}.docx"
            info["draft"] = (
                "совпадает"
                if draft.exists() and sha(draft.read_bytes()) == info["sha"]
                else ("черновик есть, но отличается" if draft.exists() else "нет черновика")
            )
            rows.append((dt, template, info, data))

        print(f"{'вид документа':26} {'верс':4} {'листов':>6} {'табл':>5} {'строк':>5} "
              f"{'подстан':>7} {'байт':>7}  исходник из репозитория")
        print("-" * 128)
        for dt, template, info, _ in rows:
            if info is None:
                print(f"{dt.code:26} нет действующего шаблона")
                continue
            print(f"{dt.code:26} {template.version:4} "
                  f"{info['pages'] if info['pages'] is not None else '—':>6} "
                  f"{info['tables']:>5} {info['rows']:>5} {len(info['tags']):>7} "
                  f"{info['bytes']:>7}  {info['draft']}")
        print()
        print("Ослабленных подстановок (is defined):",
              sum(info["weak"] for _, _, info, _ in rows if info))
        print()
        for dt, template, info, _ in rows:
            if info is None:
                continue
            print(f"\n### {dt.code} — {dt.name}")
            print(f"    версия {template.version}, листов {info['pages']}, "
                  f"таблиц {info['tables']}, подстановок {len(info['tags'])}")
            print(f"    начинается с: {info['first'][:80]}")
            for tag in info["tags"]:
                print(f"      {{{{{tag}}}}}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
