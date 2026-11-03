"""Задача 1, проверка: собирается ли каждый вид документа.

Берём активный шаблон каждого вида документа и пробуем собрать документ из
снимка данных реального пакета. В базе ничего не меняем: пакеты не создаём,
файлы не сохраняем.

Запуск: PYTHONPATH=/app python scripts/check_all_templates_render.py
"""
from __future__ import annotations

import io
import re
import zipfile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, DataSnapshot, Document, DocumentPackage, DocumentType
from app.services import generation, pages, snapshots, storage


TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)


def template_tags(data: bytes) -> list[str]:
    """Неподставленные теги шаблона в XML-частях документа.

    Ищем именно в XML: в приложенных картинках байты «{{» встречаются
    случайно, и проверка по всему zip даёт ложные срабатывания.
    """
    found: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            text = zf.read(name).decode("utf-8", "replace")
            found.extend(m.group(0) for m in TAG.finditer(text))
    return found


def _documents_meta(db, case) -> dict:
    """Блок documents: номера, даты и число листов по каждому виду документа.

    Повторяет то, что делает generate_package, но без сборки пакета:
    проверке нужны только данные для подстановки.
    """

    meta: dict = {}
    first_action = case.actions[0] if case.actions else None
    for dt in db.scalars(select(DocumentType).order_by(DocumentType.id)):
        number, document_date = generation._document_identity(case, dt.code, first_action)
        pages = generation._document_pages(db, case.id, dt.code)
        meta[dt.code] = {
            "code": dt.code,
            "name": dt.name,
            "name_lower": (dt.name[0].lower() + dt.name[1:]) if dt.name else dt.name,
            "number": number or "",
            "issued_on": document_date.isoformat() if document_date else None,
            "issued_on_short": generation.ru.date_short(document_date),
            "issued_on_words": generation.ru.date_words(document_date),
            "pages": pages,
            "pages_text": f" на {pages} л." if pages else " на ___ л.",
        }
    return meta


def main() -> int:
    db = SessionLocal()
    try:
        types = list(
            db.scalars(
                select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
            )
        )

        # Образец данных: свежий снимок по заявке, пересобранный заново.
        #
        # Раньше брался готовый снимок из базы целиком. Это неверно: снимки,
        # сделанные до появления новых полей, их не содержат, и проверка
        # падала на шаблоне, который на актуальных данных собирается. Снимок
        # здесь пересобирается тем же кодом, которым собирается при печати.
        sample = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        if sample is None:
            print("нет ни одного снимка данных — не из чего собирать")
            return 1
        # Заявка для образца: та, по которой есть хоть один пакет, иначе
        # последняя созданная. У снимка пакета entity_id ссылается на пакет,
        # поэтому заявку ищем отдельно.
        package_case = db.scalars(
            select(ControlCase)
            .join(
                DocumentPackage,
                DocumentPackage.control_case_id == ControlCase.id,
            )
            .order_by(DocumentPackage.id.desc())
        ).first()
        if package_case is None:
            package_case = db.scalars(
                select(ControlCase).order_by(ControlCase.id.desc())
            ).first()
        if package_case is None:
            print(f"снимок {sample.id}: заявок нет — беру снимок как есть")
            payload = sample.payload
        else:
            payload = snapshots.build_case_context(db, package_case.id)
            # Номера и даты документов пакета сборка кладёт в снимок перед
            # печатью (generate_package). Без этого блока бланки акта,
            # предписания и направлений ссылаться не на что.
            payload["documents"] = _documents_meta(db, package_case)
            print(f"образец данных: заявка {package_case.case_number} "
                  f"(снимок {sample.id} пересобран)")
        print()

        ok, bad = [], []
        print(f"{'тип документа':26} {'шаблон':8} {'байт':>8} {'листов':>7}  результат")
        print("-" * 78)
        for dt in types:
            template = generation._active_template(db, dt.id)
            if template is None or template.file is None:
                print(f"{dt.code:26} {'—':8} {'—':>8} {'—':>7}  НЕТ АКТИВНОГО ШАБЛОНА")
                bad.append((dt.code, "нет активного шаблона"))
                continue
            try:
                data = generation.build_document_bytes(
                    payload, dt.code, storage.read_bytes(template.file)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{dt.code:26} {template.version:8} {'—':>8} {'—':>7}  "
                      f"НЕ СОБИРАЕТСЯ: {type(exc).__name__}: {str(exc)[:90]}")
                bad.append((dt.code, f"{type(exc).__name__}: {exc}"))
                continue
            count = pages.count_pages(data) if pages.available() else None
            tags = template_tags(data)
            note = "ок"
            if tags:
                note = f"ОСТАЛИСЬ ТЕГИ ШАБЛОНА: {tags[0][:60]!r}"
                bad.append((dt.code, f"остались теги: {tags[0][:60]!r}"))
            else:
                ok.append(dt.code)
            print(f"{dt.code:26} {template.version:8} {len(data):>8} "
                  f"{count if count is not None else '—':>7}  {note}")

        print()
        print(f"собирается: {len(ok)} из {len(types)}")
        for code, why in bad:
            print(f"  проблема: {code} — {why}")

        # Отдельно: какие виды документов вообще есть в пакетах.
        used = list(
            db.scalars(
                select(DocumentType.code)
                .join(Document, Document.document_type_id == DocumentType.id)
                .distinct()
            )
        )
        print()
        print("виды документов, встречающиеся в собранных пакетах:", ", ".join(sorted(used)))
        unused = [dt.code for dt in types if dt.code not in used]
        if unused:
            print("ещё ни разу не собирались:", ", ".join(unused))
        return 0 if not bad else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
