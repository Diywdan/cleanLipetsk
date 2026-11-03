"""Выгрузка всех действующих шаблонов из базы в отдельный каталог.

Файлы берутся из хранилища: в базе лежат именно они, каталог templates
система не читает. Рядом кладётся опись с контрольными суммами — по ней
видно, что именно поменялось после правок.

Запуск: PYTHONPATH=/app python scripts/export_all_templates.py /data/export/<куда>
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType, StoredFile
from app.services import generation, pages, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)

# Понятное имя файла для заказчика: код типа документа -> название.
TITLES = {
    "assignment": "Задание-на-выездное-обследование",
    "act": "Акт-выездного-обследования",
    "inspection_protocol": "Протокол-осмотра",
    "decision": "Решение-по-результатам-мероприятия",
    "prescription": "Предписание-об-устранении-нарушения",
    "direction": "Направление-предписания",
    "appearance_notice": "Уведомление-о-явке",
    "administrative_protocol": "Протокол-об-административном-правонарушении",
    "act_direction": "О-направлении-акта-обследования",
}


def shape(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        text = "".join(node.text or "" for node in root.iter(f"{W}t"))
        tables = len(root.findall(f".//{W}tbl"))
        rows = len(root.findall(f".//{W}tr"))
        headers = [
            name
            for name in archive.namelist()
            if re.search(r"word/(header|footer)\d*\.xml$", name)
        ]
    tags = sorted({t.strip() for t in TAG.findall(text)})
    return {
        "tags": len(tags),
        "tables": tables,
        "rows": rows,
        "headers": len(headers),
        "weak": sum(1 for t in tags if "is defined" in t),
        "text_length": len(text),
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/export/templates")
    out.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        types = list(
            db.scalars(
                select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
            )
        )
        manifest = []
        print(f"{'вид документа':26} {'верс':5} {'листов':>6} {'табл':>5} {'строк':>5} "
              f"{'подстан':>7} {'байт':>7}")
        print("-" * 76)
        for dt in types:
            template = generation._active_template(db, dt.id)
            if template is None or template.file is None:
                print(f"{dt.code:26} нет действующего шаблона")
                continue
            sf: StoredFile = template.file
            data = storage.read_bytes(sf)
            digest = hashlib.sha256(data).hexdigest()
            info = shape(data)
            info["pages"] = pages.count_pages(data) if pages.available() else None
            name = f"{TITLES.get(dt.code, dt.code)}-{template.version}.docx"
            (out / name).write_bytes(data)
            print(f"{dt.code:26} {template.version:5} "
                  f"{info['pages'] if info['pages'] is not None else '—':>6} "
                  f"{info['tables']:>5} {info['rows']:>5} {info['tags']:>7} "
                  f"{len(data):>7}")
            manifest.append(
                {
                    "code": dt.code,
                    "title": dt.name,
                    "version": template.version,
                    "template_id": template.id,
                    "file_id": template.file_id,
                    "file": name,
                    "bytes": len(data),
                    "sha256": digest,
                    **info,
                }
            )
        (out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print()
        print(f"всего бланков: {len(manifest)}; каталог: {out}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
