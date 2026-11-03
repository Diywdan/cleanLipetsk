"""Сколько листов занимает каждый документ пакета.

Правка шаблонов — это в первую очередь работа над оформлением: чаще всего
нужно, чтобы документ влезал на одну страницу. На глаз это не проверить:
разбивка зависит от шрифтов, полей и высоты строк таблиц, а в Word и в
LibreOffice (которым считает система) она может отличаться.

Скрипт собирает документы заново по данным последнего пакета заявки, беря
текущие шаблоны, и печатает число листов каждого документа. Ничего в базе
при этом не меняется: пакет не создаётся, документы не сохраняются — это
измерительный инструмент для правки бланков.

Заодно проверяется, что шаблон вообще собирается: если при правке разорвался
тег или пропало поле, рендер упадёт, и это будет видно сразу.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/template_pages.py [номер_заявки] [код_пакета]

По умолчанию — демонстрационная заявка 7 и первичный пакет.
"""

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, Document, DocumentPackage, PackageKind
from app.services import generation, pages, storage


CASE_ID = 7
PACKAGE_KIND = "primary_prescription"

# Документы, к которым система сама дописывает приложение с фотографиями:
# у них вторая страница — это приложение, а не переполнение бланка.
PHOTO_APPENDIX_CODES = generation.PHOTO_APPENDIX_CODES


def main() -> int:
    case_id = int(sys.argv[1]) if len(sys.argv) > 1 else CASE_ID
    kind_code = sys.argv[2] if len(sys.argv) > 2 else PACKAGE_KIND

    db = SessionLocal()
    try:
        if not pages.available():
            print("нечем считать листы: в образе нет LibreOffice или pdfinfo")
            return 1

        kind = db.scalar(select(PackageKind).where(PackageKind.code == kind_code))
        if kind is None:
            print(f"нет вида пакета {kind_code!r}")
            return 1

        package = db.scalars(
            select(DocumentPackage)
            .where(
                DocumentPackage.control_case_id == case_id,
                DocumentPackage.package_kind_id == kind.id,
            )
            .order_by(DocumentPackage.id.desc())
        ).first()
        if package is None:
            print(f"по заявке {case_id} нет пакета «{kind.name}»")
            return 1

        print(f"заявка {case_id} | пакет №{package.id} «{kind.name}»")
        print()

        documents = list(
            db.scalars(
                select(Document)
                .where(Document.package_id == package.id)
                .order_by(Document.id)
            )
        )

        overflow: list[str] = []
        broken: list[str] = []
        print(f"{'код':<22} {'документ':<34} {'шаблон':<8} {'листов':>6}")
        for document in documents:
            code = document.document_type.code
            name = document.document_type.name
            template = generation._active_template(db, document.document_type_id)
            if template is None or template.file is None:
                print(f"{code:<22} {name:<34} {'—':<8} {'нет шаблона':>6}")
                broken.append(code)
                continue

            snapshot = db.get(DataSnapshot, document.snapshot_id)
            if snapshot is None:
                print(f"{code:<22} {name:<34} {template.version:<8} {'нет снимка':>6}")
                continue

            try:
                data = generation.build_document_bytes(
                    snapshot.payload, code, storage.read_bytes(template.file)
                )
            except Exception as error:  # noqa: BLE001 — показываем причину как есть
                print(
                    f"{code:<22} {name:<34} {template.version:<8} "
                    f"НЕ СОБИРАЕТСЯ: {type(error).__name__}"
                )
                print(f"{'':<22} {error}")
                broken.append(code)
                continue

            count = pages.count_pages(data)
            note = ""
            if count is not None and count > 1:
                if code in PHOTO_APPENDIX_CODES:
                    note = "  ← приложение с фотоматериалом"
                else:
                    note = "  ← не влезает на одну страницу"
                    overflow.append(code)
            if count is None:
                note = "  ← не удалось посчитать"
            print(f"{code:<22} {name:<34} {template.version:<8} {count if count is not None else '—':>6}{note}")

        print()
        if broken:
            print("шаблоны с ошибками:", ", ".join(broken))
        if overflow:
            print("не влезают на одну страницу:", ", ".join(overflow))
        if not broken and not overflow:
            print("все документы собираются и влезают на одну страницу")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
