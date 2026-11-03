"""Проверка документов административного производства.

Проверяется, что уведомление о явке и протокол об административном
правонарушении собираются из данных дела: в документах оказываются номер
и дата протокола, дата и место явки, статья КоАП, наименование лица,
должностное лицо, описание правонарушения.

Данные административного производства у демонстрационного дела заводятся
здесь же — иначе проверить документы не на чем. Запуск повторный: данные
перезаписываются.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_admin_documents.py
"""

import io
import sys
from datetime import date

from docx import Document as DocxDocument
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    AdministrativeCase,
    ControlCase,
    Document,
    DocumentPackage,
    DocumentType,
    PackageKind,
    PackageKindDocument,
)
from app.services import generation, snapshots, storage, validation


CASE_ID = 7
PROTOCOL_NUMBER = "769-П"
APPEARANCE_DATE = date(2026, 10, 14)
APPEARANCE_TIME = "11:30"
APPEARANCE_OFFICE = "207"
OFFENSE_ARTICLE = "частью 1 статьи 19.5"
OFFENSE_DESCRIPTION = (
    "06.07.2026 департаментом проведено контрольное (надзорное) мероприятие "
    "без взаимодействия с контролируемым лицом — выездное обследование, "
    "в ходе которого выявлены нарушения Правил благоустройства и выдано "
    "предписание со сроком исполнения до 06.08.2026. В установленный срок "
    "предписание не исполнено, что подтверждено актом выездного обследования "
    "и протоколом осмотра."
)


def document_text(db, document: Document) -> str:
    """Весь текст сформированного документа: абзацы и таблицы."""

    data = storage.read_bytes(document.generated_file)
    doc = DocxDocument(io.BytesIO(data))
    parts = [paragraph.text for paragraph in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    try:
        # Уведомление о явке и протокол об административном правонарушении
        # входят ТОЛЬКО во вторичный пакет: в первичном и в пакете об
        # исполнении предписания их быть не должно.
        membership: dict[str, list[str]] = {}
        for kind, type_code in db.execute(
            select(PackageKind.code, DocumentType.code)
            .join(PackageKindDocument, PackageKindDocument.package_kind_id == PackageKind.id)
            .join(DocumentType, DocumentType.id == PackageKindDocument.document_type_id)
        ):
            membership.setdefault(type_code, []).append(kind)

        for code in ("appearance_notice", "administrative_protocol"):
            packages = sorted(membership.get(code, []))
            only_secondary = packages == ["repeated_prescription"]
            print(f"--- {code} входит в пакеты: {packages} (только вторичный: {only_secondary})")
            if not only_secondary:
                failures.append(
                    f"{code} должен входить только во вторичный пакет, а входит в {packages}"
                )

        secondary = sorted(membership, key=lambda key: 0)
        secondary_codes = sorted(
            type_code
            for type_code, kinds in membership.items()
            if "repeated_prescription" in kinds
        )
        print(f"--- состав вторичного пакета: {len(secondary_codes)} документов")
        if len(secondary_codes) != 8:
            failures.append(
                f"во вторичном пакете {len(secondary_codes)} документов вместо 8"
            )
        for code in ("appearance_notice", "administrative_protocol"):
            if code not in secondary_codes:
                failures.append(f"{code} отсутствует во вторичном пакете")
        for code in ("assignment", "act", "inspection_protocol", "decision",
                     "prescription", "direction"):
            if code not in secondary_codes:
                failures.append(f"{code} отсутствует во вторичном пакете")

        case = db.get(ControlCase, CASE_ID)
        if case is None:
            print(f"дело {CASE_ID} не найдено")
            return 1

        # Данные административного производства.
        row = db.scalars(
            select(AdministrativeCase).where(
                AdministrativeCase.control_case_id == CASE_ID
            )
        ).first()
        if row is None:
            row = AdministrativeCase(control_case_id=CASE_ID)
            db.add(row)
        row.protocol_number = PROTOCOL_NUMBER
        row.protocol_date = date(2026, 10, 14)
        row.protocol_place = "г. Липецк, ул. Механизаторов, 15"
        row.appearance_date = APPEARANCE_DATE
        row.appearance_time = APPEARANCE_TIME
        row.appearance_place = "г. Липецк, ул. Механизаторов, д. 15"
        row.appearance_office = APPEARANCE_OFFICE
        row.notice_number = "12"
        row.notice_date = date(2026, 9, 29)
        row.offense_article = OFFENSE_ARTICLE
        row.offense_date = date(2026, 10, 7)
        row.offense_time = "00:01"
        row.offense_place = "г. Москва, ул. 3-я Песчаная, д. 2А"
        row.offense_description = OFFENSE_DESCRIPTION
        row.representative_info = "законный представитель не явился"
        # В базу НЕ записываем: это проверка, а не заполнение заявки. Раньше
        # здесь был commit, и демонстрационные значения (в том числе московский
        # адрес правонарушения) оставались в боевой заявке. Теперь всё
        # откатывается в конце, после проверок документов.
        db.flush()
        print(f"--- данные производства по делу {CASE_ID} заполнены (в памяти)")

        context = snapshots.build_case_context(db, CASE_ID)
        notice = context["notice"]
        print(f"--- строка «КОМУ»: {notice['recipient_line'][:80]}")
        print(f"--- явка: {context['administrative']['appearance_date_short']} "
              f"в {context['administrative']['appearance_time']}, "
              f"каб. {context['administrative']['appearance_office']}")

        # Готовность повторного пакета.
        readiness = validation.check_readiness(db, CASE_ID, "repeated_prescription")
        print(f"--- готовность повторного пакета: {readiness.is_ready}, "
              f"замечаний {len(readiness.issues)}")
        for issue in readiness.issues[:5]:
            print("      замечание:", issue.message)

        result = generation.generate_package(
            db, CASE_ID, package_kind_code="repeated_prescription"
        )
        print(f"--- пакет {result.package_id}: документов {len(result.created)}")

        package = db.get(DocumentPackage, result.package_id)
        by_code = {
            document.document_type.code: document
            for document in db.scalars(
                select(Document).where(Document.package_id == package.id)
            )
        }
        print("--- состав:", ", ".join(sorted(by_code)))

        notice_text = document_text(db, by_code["appearance_notice"])
        protocol_text = document_text(db, by_code["administrative_protocol"])

        checks = [
            ("уведомление: статья КоАП", OFFENSE_ARTICLE in notice_text),
            ("уведомление: место явки", "Механизаторов" in notice_text),
            ("уведомление: кабинет", APPEARANCE_OFFICE in notice_text),
            ("уведомление: номер протокола не нужен", True),
            ("протокол: номер", PROTOCOL_NUMBER in protocol_text),
            ("протокол: описание правонарушения", "Правил благоустройства" in protocol_text),
            ("протокол: статья", OFFENSE_ARTICLE in protocol_text),
            ("протокол: должностное лицо", "Комолых" in protocol_text),
        ]
        for title, ok in checks:
            print(f"    {title}: {'есть' if ok else 'НЕТ'}")
            if not ok:
                failures.append(title)

        # Повторная сборка должна дать те же файлы.
        again = generation.generate_package(
            db, CASE_ID, package_kind_code="repeated_prescription"
        )
        again_package = db.get(DocumentPackage, again.package_id)
        again_docs = {
            document.document_type.code: document
            for document in db.scalars(
                select(Document).where(Document.package_id == again_package.id)
            )
        }
        for code in ("appearance_notice", "administrative_protocol"):
            first = by_code[code].generated_file.sha256
            second = again_docs[code].generated_file.sha256
            same = first == second
            print(f"--- {code}: повторная сборка совпала побайтово: {same}")
            if not same:
                failures.append(f"{code}: повторная сборка дала другой файл")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  уведомление и протокол собираются из данных дела")
        return 0
    finally:
        # Проверка ничего не оставляет в базе: демонстрационные данные и
        # собранные пакеты откатываются.
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
