"""Замена нарисованного QR-кода в бланках на заготовку-место.

В решении, протоколе осмотра, предписании и акте нарисован квадрат QR-кода.
Кода быть не должно, но и место под него терять нельзя: когда придёт код из
прокуратуры, он встанет на это место без сдвига вёрстки.

Размеры у бланков разные — в решении, предписании и акте 3.39 см, в протоколе
осмотра 1.75 см. Поэтому заготовка подгоняется под размер каждого рисунка.

По умолчанию только показать. Записать: --apply

Запуск: PYTHONPATH=/app python scripts/insert_qr_placeholder.py [--apply]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

PLACEHOLDER = Path("/app/qr-placeholder.png")
PLACEHOLDER_TAG = "qr-placeholder"
EMU_PER_CM = 360000

# Куда кладём исправленные бланки: рядом с черновиками, следующей версией.
# Имя файла соответствует номеру новой версии в базе.
NEXT_VERSION = {
    "decision": "v2",
    "inspection_protocol": "v5",
    "prescription": "v4",
    "act": "v6",
}


def q(tag: str) -> str:
    return f"{W}{tag}"


def qr_drawings(root) -> list:
    """Рисунки-квадраты с картинкой: в бланках это и есть QR-код.

    Логотип управления тоже картинка, но не квадрат (1.3 x 1.61), а линии
    в шапке предписания вообще без картинки.
    """

    found = []
    for drawing in root.iter(f"{W}drawing"):
        blips = list(drawing.iter(f"{A}blip"))
        if not blips:
            continue
        extent = drawing.find(f".//{WP}extent")
        if extent is None:
            continue
        cx, cy = int(extent.get("cx")), int(extent.get("cy"))
        if abs(cx - cy) < 40000:  # квадрат с точностью до долей миллиметра
            found.append(drawing)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    placeholder = PLACEHOLDER.read_bytes()
    print(f"заготовка: {PLACEHOLDER} ({len(placeholder)} байт, "
          f"sha {hashlib.sha256(placeholder).hexdigest()[:12]})")

    db = SessionLocal()
    try:
        for code, version in NEXT_VERSION.items():
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            template = generation._active_template(db, dt.id)
            data = storage.read_bytes(template.file)
            print(f"\n=== {code}: действует {template.version}, "
                  f"{len(data)} байт, file_id={template.file_id} ===")

            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                parts = {name: archive.read(name) for name in names}
            root = etree.fromstring(parts["word/document.xml"])
            rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
            rel_map = {
                rel.get("Id"): rel.get("Target") for rel in rels if rel.get("Id")
            }

            drawings = qr_drawings(root)
            if not drawings:
                print("  рисунков-квадратов нет — правка не нужна")
                continue

            replaced = 0
            for drawing in drawings:
                extent = drawing.find(f".//{WP}extent")
                cx = int(extent.get("cx"))
                cy = int(extent.get("cy"))
                size_cm = round(cx / EMU_PER_CM, 2)
                for blip in drawing.iter(f"{A}blip"):
                    rid = blip.get(f"{R}embed")
                    target_name = rel_map.get(rid)
                    # Путь в связях относительный («media/image1.png»),
                    # в пакете — «word/media/image1.png».
                    part_name = (
                        f"word/{target_name}" if target_name else None
                    )
                    if part_name and part_name in parts:
                        parts[part_name] = placeholder
                        print(f"  {part_name}: квадрат {size_cm} см -> заготовка")
                    else:
                        print(f"  ! картинка {target_name!r} не найдена в пакете")
                # Второй extent — «эффективный» размер, его тоже правим.
                for node in drawing.iter(f"{A}ext"):
                    if node.get("cx"):
                        node.set("cx", str(cx))
                        node.set("cy", str(cy))
                # Пометка в описании: по ней видно место и находит замена.
                doc_pr = drawing.find(f".//{WP}docPr")
                if doc_pr is not None:
                    doc_pr.set("descr", f"{PLACEHOLDER_TAG} {size_cm} см")
                    doc_pr.set("name", PLACEHOLDER_TAG)
                replaced += 1

            parts["word/document.xml"] = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in names:
                    archive.writestr(name, parts[name])
            result = buffer.getvalue()
            print(f"  результат: {len(result)} байт, "
                  f"рисунков заменено {replaced}")
            if args.apply:
                target = Path(f"/app/templates/{code}/{version}.docx")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(result)
                print(f"  записано: {target}")

        if not args.apply:
            print("\nЭто проверка. Для записи добавьте --apply")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
