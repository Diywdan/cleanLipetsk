"""Задача 1: вернуть исходные шаблоны из репозитория в базу.

Прошлая сессия разом ослабила строгий режим: подстановки вида
`{{ obj.field }}` превратились в `{{ obj.field if obj is defined and obj else '' }}`.
Испорченные файлы были загружены в хранилище и подставлены записям
DocumentTemplate. Здесь берём исходные файлы из /app/templates (каталог
backend/templates репозитория), кладём их в хранилище и подставляем записям
шаблонов. Лишние включённые версии выключаем: включённой остаётся одна
версия на тип документа.

По умолчанию — только показать план. Применить: --apply

Запуск: PYTHONPATH=/app python scripts/restore_templates_from_repo.py [--apply]
"""
from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentTemplate, DocumentType, StoredFile
from app.models.enums import FileKind
from app.services import storage


TEMPLATES_DIR = Path("/app/templates")
WEAK = re.compile(r"\{\{[^{}]*\bif\b[^{}]*\bis defined\b[^{}]*\}\}")

# Испорченные типы и версии: код типа -> версии, которые надо вернуть к
# исходным файлам репозитория. Протокол осмотра здесь нет: у него включена
# версия v3 с правками заказчика, а v1 и v2 отключены и смотрят на исходники.
DAMAGED: dict[str, tuple[str, ...]] = {
    "act": ("1", "2", "3", "4"),
    "assignment": ("1", "2"),
    "decision": ("1",),
    "direction": ("1", "2"),
    "prescription": ("1", "2", "3"),
    "administrative_protocol": ("1",),
    "appearance_notice": ("1",),
    "act_direction": ("1",),
}

# Какая версия остаётся включённой (так было до ослабления режима).
ACTIVE: dict[str, str] = {code: "1" for code in DAMAGED}


def weak_count(data: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            text = "\n".join(
                zf.read(n).decode("utf-8", "replace")
                for n in zf.namelist()
                if n.endswith(".xml")
            )
    except Exception:  # noqa: BLE001
        return -1
    return len(WEAK.findall(text))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="применить изменения")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan: list[tuple[DocumentTemplate, Path]] = []
        for code, versions in DAMAGED.items():
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            if dt is None:
                print(f"!! нет типа документа {code}")
                continue
            for version in versions:
                path = TEMPLATES_DIR / code / f"v{version}.docx"
                if not path.exists():
                    print(f"!! нет исходного файла {path}")
                    continue
                template = db.scalar(
                    select(DocumentTemplate).where(
                        DocumentTemplate.document_type_id == dt.id,
                        DocumentTemplate.version == f"v{version}",
                    )
                )
                if template is None:
                    print(f"!! нет записи шаблона {code} v{version}")
                    continue
                plan.append((template, path))

        print(f"{'тип':24} {'версия':7} {'было file':>9} {'ослаб':>6} ->  {'станет':>9} "
              f"{'ослаб':>6}  включён")
        print("-" * 92)
        for template, path in plan:
            dt = db.get(DocumentType, template.document_type_id)
            old = db.get(StoredFile, template.file_id) if template.file_id else None
            old_weak = weak_count(storage.read_bytes(old)) if old else -1
            new_bytes = path.read_bytes()
            will_be_active = template.version == f"v{ACTIVE[dt.code]}"
            print(
                f"{dt.code:24} {template.version:7} {template.file_id if template.file_id else '-':>9} "
                f"{old_weak:>6} ->  {'(новый)':>9} {weak_count(new_bytes):>6}  "
                f"{'да' if will_be_active else 'нет'}"
            )

        if not args.apply:
            print("\nЭто план. Для применения добавьте --apply")
            return

        changed = 0
        for template, path in plan:
            dt = db.get(DocumentType, template.document_type_id)
            data = path.read_bytes()
            file = storage.save_bytes(
                db,
                data,
                path.name,
                kind=FileKind.TEMPLATE,
                commit=False,
            )
            template.file_id = file.id
            template.is_active = template.version == f"v{ACTIVE[dt.code]}"
            changed += 1
            print(f"{dt.code} {template.version}: file_id={file.id} "
                  f"sha={str(file.sha256)[:12]} включён={template.is_active}")
        db.commit()
        print(f"\nобновлено записей: {changed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
