"""Сквозная проверка: дело -> пакет -> DOCX.

Формирует документы по демонстрационному делу и проверяет готовые файлы:
подставленные значения на месте, теги шаблонов не остались, а повторная
сборка из снимка даёт тот же файл.

Запуск: PYTHONPATH=/app python scripts/check_generation.py [код ...]
"""

import io
import sys

from docx import Document as DocxDocument
from docx.table import _Cell

from app.db.session import SessionLocal
from app.models import ControlCase, DataSnapshot, Document
from app.services import generation, storage


# Демонстрационное дело: в нём заполнены поля, по которым собираются документы.
DEMO_CASE_ID = 7

# Срок исполнения нарушения в предписании подставляется из данных дела.
# Зашитая дата устаревает, как только дело поправят через интерфейс, поэтому
# в списке ожиданий стоит метка, а дата берётся из заявки.
PRESCRIPTION_DUE = "«срок исполнения нарушения»"


# Что обязательно должно быть в готовом документе.
EXPECTED = {
    "act": [
        "1. Выездное обследование проведено в соответствии с заданием заместителя председателя",
        "Инютиной Т.Н. от 21.09.2026",
        "2. Выездное обследование проведено в рамках Муниципального контроля",
        "1)  Комолых Евгения Юрьевна – главный консультант",
        "5. Выездное обследование проведено в отношении: земельный участок",
        "6. Выездное обследование проведено по адресу (местоположению): г. Липецк, ул. Теперика, д.3",
        "7. Контролируемое лицо: АО «РИР Энерго» в лице филиала",
        "1)  осмотр",
        "по результатам которого составлен: протокол осмотра от 22.09.2026",
        "1)  протокол осмотра от 22.09.2026",
        "Комолых Евгения Юрьевна                       _________________________",
        "Отметка о направлении акта в электронном виде (адрес электронной почты): tula@quadra.ru, knc@lipetsk.quadra.ru",
    ],
    "assignment": [
        "Т.Н. Инютина",
        "Оценка соблюдения контролируемым лицом (АО «РИР Энерго» в лице филиала",
        "Муниципального контроля в сфере благоустройства",
        "Земельного участка, расположенного по адресу: г. Липецк, ул. Теперика, д.3",
        "проверка фактов, изложенных в материале МУ «Управление главного смотрителя",
        "Комолых Евгения Юрьевна – главный консультант",
        "08 час. 30 мин.",
        "17 час. 30 мин.",
        "телефон 38-77-75",
    ],
    "decision": [
        "Заместитель председателя департамента развития территории администрации города Липецка",
        "Т.Н. Инютина",
        "22 сентября 2026 г.",
        "проведено контрольное (надзорное) мероприятие — выездное обследование по адресу: г. Липецк, ул. Теперика, д.3.",
        "2. На рассмотрение вопросов, связанных с проведением инспекционного мероприятия по месту нахождения земельного участка",
        "уполномочен главный консультант управления муниципального контроля",
        "Комолых Евгения Юрьевна",
        "3. Рассмотрение проводится в отношении земельного участка, расположенного по адресу",
        "4. Контролируемое(ые) лицо(а): АО «РИР Энерго» в лице филиала",
        "По результатам проведенного выездного обследования в соответствии со ст. 90",
        "выдать предписание об устранении нарушений.",
        "Главный консультант управления муниципального контроля департамента развития территории администрации города Липецка",
        "– Е.Ю. Комолых",
    ],
    "direction": [
        "Советская ул., д.68, г.Липецк, 398001",
        "Телефон/факс (4742) 22 13 30",
        "E-mail: depterr@lipetskcity.ru",
        "филиала АО «РИР Энерго»-«Липецкая генерация»",
        "knc@lipetsk.quadra.ru",
        "АО «РИР Энерго»",
        "tula@quadra.ru",
        "119017, г. Москва, вн. тер. г. Муниципальный округ Якиманка",
        "направляет акт выездного обследования от 22.09.2026 № 48001704800001509034 и предписание об устранении нарушения от 22.09.2026 № 48001704800001509034",
        "Приложение: 1. Акт выездного обследования от 22.09.2026 № 48001704800001509034 на ___ л. в 1 экз.;",
        "2. Предписание об устранении нарушения от 22.09.2026 № 48001704800001509034 на ___ л. в 1 экз.",
        "Заместитель председателя департамента развития территории администрации города Липецка",
        "Т.Н. Инютина",
        "Комолых Евгения Юрьевна",
        "(4742) 38-77-75",
    ],
    "inspection_protocol": [
        "1. Вид муниципального контроля:",
        "Муниципальный контроль в сфере благоустройства на территории города Липецка",
        "2. Осмотр проведен:",
        "Главным консультантом управления муниципального контроля",
        "Комолых Евгенией Юрьевной",
        "3. Осмотр проведен в отношении:",
        "1) Земельного участка, расположенного по адресу: г. Липецк, ул. Теперика, д.3",
        ", на котором проводились земляные работы по аварийному ремонту теплоснабжения",
        "2) в нарушении пункта 5.2 части 5 статьи 5",
        "Правил благоустройства территорий города Липецка",
        "Главный консультант управления муниципального контроля",
        "Е.Ю. Комолых",
        "Приложение к протоколу осмотра по адресу: г. Липецк, ул. Теперика, д.3",
        "(выездное обследование 22.09.2026)",
        "Отметка о применении или неприменении видеозаписи*",
        "фотофиксация",
        "Фотоматериал к протоколу осмотра",
        "Общий вид участка после земляных работ",
    ],
    "prescription": [
        "6829012680",
        "г. Липецк, ул. Теперика, д.3",
        "Е.Ю. Комолых",
        PRESCRIPTION_DUE,
        "восстановить асфальт",
    ],
}


# Даты и время в бланке акта разложены по отдельным ячейкам: проверяем их
# по координатам, иначе совпадение цифр ничего не доказывает.
ACT_TIME_CELLS = {
    1: {"day": 1, "month_words": 3, "year": 5, "hour": 7, "minute": 9, "second": 11},
    2: {"day": 3, "month_words": 5, "year": 7, "hour": 9, "minute": 11},
    3: {"day": 2, "month_words": 4, "year": 6, "hour": 8, "minute": 10},
    4: {"day": 2, "month_words": 4, "year": 6, "hour": 8, "minute": 10},
    5: {"day": 7, "month_words": 9, "year": 11, "hour": 13, "minute": 15},
}
ACT_TIME_EXPECTED = {
    1: {"day": "22", "month_words": "сентября", "year": "2026", "hour": "17",
        "minute": "00", "second": "00"},
    2: {"day": "22", "month_words": "сентября", "year": "2026", "hour": "08",
        "minute": "30"},
    3: {"day": "22", "month_words": "сентября", "year": "2026", "hour": "13",
        "minute": "00"},
    4: {"day": "22", "month_words": "сентября", "year": "2026", "hour": "12",
        "minute": "20"},
    5: {"day": "22", "month_words": "сентября", "year": "2026", "hour": "12",
        "minute": "45"},
}


DECISION_TIME_CELLS = {2: {"day": 1, "month_words": 3, "year": 5}}
DECISION_TIME_EXPECTED = {
    2: {"day": "22", "month_words": "сентября", "year": "2026"}
}


def check_positional_tables(
    data: bytes,
    cells: dict,
    expected_all: dict,
    failures: list[str],
    label: str,
) -> None:
    document = DocxDocument(io.BytesIO(data))
    for table_index, expected in expected_all.items():
        table = document.tables[table_index]
        row = table._tbl.tr_lst[0]
        actual = {
            key: _Cell(row.tc_lst[cell_index], table).paragraphs[0].text.strip()
            for key, cell_index in cells[table_index].items()
        }
        if actual == expected:
            print(f"  таблица {table_index}: {actual} — ок")
        else:
            print(f"  таблица {table_index}: НЕ СОВПАЛО {actual}")
            failures.append(
                f"{label}: таблица {table_index} содержит {actual}, "
                f"ожидалось {expected}"
            )


def check_act_tables(data: bytes, failures: list[str]) -> None:
    check_positional_tables(
        data, ACT_TIME_CELLS, ACT_TIME_EXPECTED, failures, "act"
    )


def extract_text(data: bytes) -> list[str]:
    document = DocxDocument(io.BytesIO(data))
    lines: list[str] = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for tr in table._tbl.tr_lst:
            for tc in tr.tc_lst:
                for paragraph in _Cell(tc, table).paragraphs:
                    if paragraph.text.strip():
                        lines.append(paragraph.text)
    return lines


def check_document(db, created, failures: list[str]) -> None:
    document = db.get(Document, created.document_id)
    code = document.document_type.code
    data = storage.read_bytes(document.generated_file)
    lines = extract_text(data)

    print(f"--- {code} ---")
    print("  файл:", document.generated_file.original_name,
          "| байт:", document.generated_file.size_bytes,
          "| sha256:", document.generated_file.sha256[:16])
    print("  номер:", document.number, "| дата:", document.document_date,
          "| шаблон:", document.template.code, document.template.version,
          "| снимок:", document.snapshot_id)

    leftover = [line for line in lines if "{{" in line or "{%" in line]
    if leftover:
        failures.append(f"{code}: в документе остались теги шаблона: {leftover[:2]}")
        print("  теги не заменены:", leftover[:2])
    else:
        print("  теги шаблона: не остались")

    for needle in EXPECTED.get(code, []):
        if any(needle in line for line in lines):
            print(f"  ок: {needle[:60]!r}")
        else:
            failures.append(f"{code}: не найдено {needle!r}")
            print(f"  НЕ НАЙДЕНО: {needle[:60]!r}")

    if code == "act":
        check_act_tables(data, failures)
    if code == "decision":
        check_positional_tables(
            data, DECISION_TIME_CELLS, DECISION_TIME_EXPECTED, failures, "decision"
        )

    snapshot = db.get(DataSnapshot, document.snapshot_id)
    rebuilt = generation.build_document_bytes(
        snapshot.payload, code, storage.read_bytes(document.template.file)
    )
    reproducible = storage.sha256_of(rebuilt) == document.generated_file.sha256
    print("  воспроизводимость из снимка:", reproducible)
    if not reproducible:
        failures.append(f"{code}: пересборка из снимка даёт другой файл")


def main() -> int:
    codes = sys.argv[1:] or ["assignment", "prescription"]

    db = SessionLocal()
    failures: list[str] = []
    try:
        # Демонстрационное дело: в нём заполнены все поля, по которым
        # собираются документы. «Последняя заявка в базе» не подходит —
        # ею может оказаться заявка без документов.
        case = db.get(ControlCase, DEMO_CASE_ID)
        if case is None:
            print(f"нет демонстрационного дела {DEMO_CASE_ID}")
            return 1
        case_id = case.id
        print(f"дело: {case_id} | документы: {', '.join(codes)}")

        # Срок исполнения нарушения берём из заявки: в предписании печатается
        # он, а не значение из константы.
        due_on = None
        if case.prescriptions and case.prescriptions[0].items:
            due_on = case.prescriptions[0].items[0].due_on
        if due_on is not None:
            EXPECTED["prescription"] = [
                line.replace(PRESCRIPTION_DUE, due_on.strftime("%d.%m.%Y"))
                for line in EXPECTED["prescription"]
            ]
            print(f"срок исполнения нарушения в заявке: {due_on:%d.%m.%Y}")

        result = generation.generate_package(
            db,
            case_id,
            package_kind_code="primary_prescription",
            only_codes=codes,
        )
        print("пакет:", result.package_id,
              "| сформировано:", [d.code for d in result.created],
              "| нет шаблона:", result.missing_templates)

        for created in result.created:
            check_document(db, created, failures)

        # Проверка печатает документы по демонстрационному делу и оставляет
        # после себя пакет — иногда неполный (проверялись не все документы).
        # Чтобы дело не осталось с обрывком пакета, собираем первичный пакет
        # целиком — так же, как это делает делопроизводитель.
        restored = generation.generate_package(
            db, case_id, package_kind_code="primary_prescription"
        )
        print("демонстрационное дело: первичный пакет пересобран целиком,",
              "документов:", len(restored.created))

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  все проверки пройдены")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
