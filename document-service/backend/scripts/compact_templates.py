"""Поджать бланки направления и предписания до одного листа.

Правка идёт по XML внутри DOCX, а не через Word: текст тегов при этом не
затрагивается вообще, меняются только свойства абзацев, высоты строк таблиц
и поля страницы. Что именно меняется по каждому бланку — в спецификациях
ниже; результат складывается рядом с исходником как следующая версия
(v1.docx -> v2.docx), после чего шаблоны регистрируются обычным порядком:

    PYTHONPATH=/app python scripts/compact_templates.py
    PYTHONPATH=/app python scripts/register_templates.py
    PYTHONPATH=/app python scripts/template_pages.py   # проверка числа листов

Скрипт идемпотентен: он всегда читает v1 и заново собирает v2, поэтому его
можно перезапускать после правок спецификации.
"""

import copy
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Рисунки живут в отдельных пространствах имён: размер картинки задаётся
# в wordprocessingDrawing, а не в основном.
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
DOCUMENT = "word/document.xml"

# Размер QR-кода прокуратуры в исходных бланках: 1219200 EMU = 3.39 см.
# Столько места и резервируем — под этот размер подгоняется загруженная
# картинка, поэтому документ с кодом выглядит как раньше.
QR_EXTENT_EMU = 1219200
QR_LINE_TWIPS = 1920  # те же 3.39 см в твипах — высота строки под код
QR_TAG = "{{ qr_code }}"

# templates лежит рядом со scripts и в контейнере (/app/templates), и в
# репозитории (backend/templates) — путь считается от самого скрипта.
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def q(tag: str) -> str:
    return f"{W}{tag}"


def tables(body):
    return [child for child in body if etree.QName(child).localname == "tbl"]


def paragraphs(body):
    return [child for child in body if etree.QName(child).localname == "p"]


def set_row_height(table, row_number: int, value: int) -> tuple[int, int]:
    """Меняет высоту строки таблицы (нумерация с единицы)."""

    row = table.findall(q("tr"))[row_number - 1]
    properties = row.find(q("trPr"))
    if properties is None:
        properties = etree.SubElement(row, q("trPr"))
        row.insert(0, properties)
    height = properties.find(q("trHeight"))
    if height is None:
        height = etree.SubElement(properties, q("trHeight"))
    before = int(height.get(q("val")) or 0)
    height.set(q("val"), str(value))
    height.set(q("hRule"), "atLeast")
    return before, value


def set_line_spacing(paragraph, line: int | None, after: int | None = None) -> None:
    properties = paragraph.find(q("pPr"))
    if properties is None:
        properties = etree.Element(q("pPr"))
        paragraph.insert(0, properties)
    spacing = properties.find(q("spacing"))
    if spacing is None:
        spacing = etree.SubElement(properties, q("spacing"))
    if line is not None:
        spacing.set(q("line"), str(line))
        spacing.set(q("lineRule"), "auto")
    if after is not None:
        spacing.set(q("after"), str(after))


def drop_paragraph(body, paragraph) -> None:
    body.remove(paragraph)


def shrink_paragraph(paragraph, size_half_points: int) -> None:
    """Уменьшает кегль абзаца: пустая строка перестаёт съедать место."""

    properties = paragraph.find(q("pPr"))
    if properties is None:
        properties = etree.Element(q("pPr"))
        paragraph.insert(0, properties)
    run_properties = properties.find(q("rPr"))
    if run_properties is None:
        run_properties = etree.SubElement(properties, q("rPr"))
    size = run_properties.find(q("sz"))
    if size is None:
        size = etree.SubElement(run_properties, q("sz"))
    size.set(q("val"), str(size_half_points))
    size_cs = run_properties.find(q("szCs"))
    if size_cs is None:
        size_cs = etree.SubElement(run_properties, q("szCs"))
    size_cs.set(q("val"), str(size_half_points))


def compact_direction(body, parts: dict) -> list[str]:
    """Направление: убрать «воздух» вокруг текста и поджать блок подписи."""

    changes: list[str] = []
    letterhead, signature = tables(body)
    paragraphs_list = paragraphs(body)

    for table, row, value, why in (
        (letterhead, 8, 283, "пустая распорка в шапке: 1 см -> 0.5 см"),
        (signature, 1, 900, "место под подпись утверждающего: 2.3 см -> 1.6 см"),
        (signature, 3, 800, "место под подписью инспектора: 2.5 см -> 1.4 см"),
    ):
        before, after = set_row_height(table, row, value)
        changes.append(f"таблица: {why} ({before} -> {after})")

    # Полуторный интервал в официальном письме оставляем, но чуть плотнее:
    # 360 (1.5) -> 300 (1.25). Это освобождает около сантиметра на весь текст.
    tight = 0
    for paragraph in paragraphs_list:
        spacing = paragraph.find(f"{q('pPr')}/{q('spacing')}")
        if spacing is not None and spacing.get(q("line")) == "360":
            set_line_spacing(paragraph, 300)
            tight += 1
    changes.append(f"межстрочный интервал 1.5 -> 1.25 у {tight} абзацев")

    # Два пустых абзаца подряд перед приложением — один лишний.
    empty = [
        paragraph
        for paragraph in paragraphs_list
        if not "".join(node.text or "" for node in paragraph.iter(q("t"))).strip()
    ]
    removed = 0
    for first, second in zip(empty, empty[1:]):
        if paragraphs_list.index(second) == paragraphs_list.index(first) + 1:
            drop_paragraph(body, second)
            removed += 1
            break
    changes.append(f"убран лишний пустой абзац: {removed}")
    return changes


def shrink_style_spacing(parts: dict, style_id: str, before: int, after: int) -> list[str]:
    """Меняет интервалы у стиля абзацев: они действуют на десятки абзацев сразу."""

    styles = etree.fromstring(parts["word/styles.xml"])
    for style in styles.findall(q("style")):
        if style.get(q("styleId")) != style_id:
            continue
        properties = style.find(q("pPr"))
        if properties is None:
            properties = etree.SubElement(style, q("pPr"))
        spacing = properties.find(q("spacing"))
        if spacing is None:
            spacing = etree.SubElement(properties, q("spacing"))
        was = {key.replace(W, ""): value for key, value in spacing.attrib.items()}
        spacing.set(q("before"), str(before))
        spacing.set(q("after"), str(after))
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        return [f"стиль {style_id}: интервалы {was} -> before={before} after={after}"]
    return [f"стиль {style_id} не найден"]


def tighten_paragraph_spacing(
    body,
    after_mapping: dict[int, int],
    before_mapping: dict[int, int] | None = None,
) -> list[str]:
    """Уменьшает интервалы до и после абзацев: 240 -> 120 и так далее.

    Пустота вокруг абзаца — основной запас места в бланке: строки текста
    остаются как есть, а разрывы между пунктами становятся плотнее.
    """

    counts: dict[str, int] = {}
    for paragraph in body.iter(q("p")):
        properties = paragraph.find(q("pPr"))
        if properties is None:
            continue
        spacing = properties.find(q("spacing"))
        if spacing is None:
            continue
        for key, mapping in (("after", after_mapping), ("before", before_mapping)):
            if mapping is None:
                continue
            value = spacing.get(q(key))
            if value is None or not value.isdigit():
                continue
            number = int(value)
            if number in mapping:
                spacing.set(q(key), str(mapping[number]))
                label = f"{key}={number} -> {mapping[number]}"
                counts[label] = counts.get(label, 0) + 1
    return (
        [f"абзацев с {label}: {count}" for label, count in sorted(counts.items())]
        or ["абзацев с заданными интервалами не найдено"]
    )


def drop_hyperlinks(body, needles: tuple[str, ...]) -> list[str]:
    """Убирает гиперссылки с забытыми значениями.

    В бланке от исходного документа остались гиперссылки с адресами почты:
    значения и так подставляются тегами, а гиперссылка печатает адрес второй
    раз — в документе получается «…@quadra.ru…@quadra.ru».
    """

    removed: list[str] = []
    for hyperlink in list(body.iter(q("hyperlink"))):
        text = "".join(node.text or "" for node in hyperlink.iter(q("t"))).strip()
        if any(needle in text for needle in needles):
            hyperlink.getparent().remove(hyperlink)
            removed.append(text)
    return [f"убрана забытая гиперссылка: {text}" for text in removed] or [
        "забытых гиперссылок не найдено"
    ]


def glue_missing_space(body, pairs: tuple[tuple[str, str], ...]) -> list[str]:
    """Возвращает пробел между соседними run'ами, если он потерялся.

    В бланке слово разбито на два run'а, и пробел остался за границей: в
    документе выходит «в соответствиис единым» вместо «в соответствии с».
    """

    fixed: list[str] = []
    for first_tail, second_head in pairs:
        for paragraph in body.iter(q("p")):
            runs = paragraph.findall(q("r"))
            for previous, current in zip(runs, runs[1:]):
                left = previous.findall(q("t"))
                right = current.findall(q("t"))
                if not left or not right:
                    continue
                if (left[-1].text or "").rstrip().endswith(first_tail) and (
                    right[0].text or ""
                ).lstrip().startswith(second_head):
                    if not (left[-1].text or "").endswith(" "):
                        left[-1].text = (left[-1].text or "") + " "
                        fixed.append(f"пробел восстановлен: {first_tail} + {second_head}")
    return fixed or ["потерянных пробелов не найдено"]


def move_endnotes_into_text(body, parts: dict) -> list[str]:
    """Переносит концевые сноски в конец текста документа.

    LibreOffice печатает концевые сноски отдельным листом, даже когда внизу
    последней страницы есть место: из-за ссылок на законы акт получает лишний
    лист. Переносим текст сносок в документ: печатается то же самое, но сразу
    за текстом, а маркер сноски в тексте остаётся на месте — он и так набран
    обычным знаком, а не полем.

    Переносятся только те сноски, на которые есть ссылки: в бланке остались
    ещё и непривязанные дубликаты, которые сейчас не печатаются.
    """

    document = body.getroottree().getroot()
    endnotes = etree.fromstring(parts["word/endnotes.xml"])

    referenced: list[str] = []
    for reference in document.findall(f".//{q('endnoteReference')}"):
        note_id = reference.get(q("id"))
        if note_id is not None and note_id not in referenced:
            referenced.append(note_id)

    by_id = {
        note.get(q("id")): note
        for note in endnotes.findall(q("endnote"))
        if note.get(q("id")) not in ("-1", "0")
    }

    section = body.find(q("sectPr"))
    moved = 0
    if referenced:
        # Разделитель перед сносками: в документе его рисует Word, а после
        # переноса он должен быть обычной линией над первой сноской.
        separator = etree.Element(q("p"))
        properties = etree.SubElement(separator, q("pPr"))
        borders = etree.SubElement(properties, q("pBdr"))
        top = etree.SubElement(borders, q("top"))
        top.set(q("val"), "single")
        top.set(q("sz"), "6")
        top.set(q("space"), "1")
        top.set(q("color"), "auto")
        body.insert(list(body).index(section), separator)

    for note_id in referenced:
        note = by_id.get(note_id)
        if note is None:
            continue
        for paragraph in note.findall(q("p")):
            duplicate = copy.deepcopy(paragraph)
            for ref in duplicate.findall(f".//{q('endnoteRef')}"):
                ref.getparent().remove(ref)
            body.insert(list(body).index(section), duplicate)
            moved += 1

    # Сами ссылки в тексте убираем: маркер сноски набран обычным знаком рядом,
    # а без определения сноски ссылка осталась бы «висячей».
    for reference in list(document.findall(f".//{q('endnoteReference')}")):
        reference.getparent().remove(reference)

    # В части сносок оставляем только разделители: печатать больше нечего.
    for note in list(endnotes.findall(q("endnote"))):
        if note.get(q("id")) not in ("-1", "0"):
            endnotes.remove(note)

    parts["word/endnotes.xml"] = etree.tostring(
        endnotes, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    return [
        f"концевые сноски перенесены в текст: ссылок {len(referenced)}, "
        f"абзацев {moved}"
    ]


def replace_qr_with_placeholder(body) -> list[str]:
    """Убирает нарисованный QR-код, оставляя под него место и метку.

    QR-код выдаёт портал прокуратуры вместе с номером мероприятия, поэтому в
    бланке он не нужен: на его место встаёт метка, а в документ попадает
    загруженная картинка того же размера.
    """

    for drawing in list(body.iter(q("drawing"))):
        extent = drawing.find(f"{WP}inline/{WP}extent")
        if extent is None or extent.get("cx") != str(QR_EXTENT_EMU):
            continue
        run = drawing.getparent()
        paragraph = run.getparent()
        run.remove(drawing)
        # Метка должна лежать в одном run: иначе docxtpl её не найдёт.
        for text in run.findall(q("t")):
            run.remove(text)
        text = etree.SubElement(run, q("t"))
        text.text = QR_TAG

        cell = paragraph.getparent()
        row = cell.getparent() if cell is not None else None
        if row is not None and etree.QName(row).localname == "tr":
            # QR стоит в шапке таблицы: держим высоту строки по размеру кода,
            # чтобы без картинки шапка не «схлопывалась».
            properties = row.find(q("trPr"))
            if properties is None:
                properties = etree.Element(q("trPr"))
                row.insert(0, properties)
            height = properties.find(q("trHeight"))
            if height is None:
                height = etree.SubElement(properties, q("trHeight"))
            height.set(q("val"), str(QR_LINE_TWIPS))
            height.set(q("hRule"), "atLeast")
            where = "в строке шапки"
        else:
            # В акте код стоит отдельным абзацем: резервируем высоту строки.
            set_line_spacing(paragraph, QR_LINE_TWIPS)
            spacing = paragraph.find(f"{q('pPr')}/{q('spacing')}")
            spacing.set(q("lineRule"), "atLeast")
            where = "в абзаце"
        return [f"QR-код убран, место {QR_EXTENT_EMU / 360000:.2f} см сохранено ({where})"]
    return ["QR-код в шаблоне не найден"]


def use_document_number(body) -> list[str]:
    """Печатает номер документа, а не поле заявки напрямую.

    Номер мероприятия вводят один раз в карточке, и он же попадает в акт
    и предписание. Но у каждого документа номер может быть уточнён, поэтому
    бланк должен брать готовый номер документа: иначе уточнение акта
    не напечатается.
    """

    replaced = 0
    for text in body.iter(q("t")):
        if text.text and "case.erp_number" in text.text:
            text.text = text.text.replace("{{ case.erp_number }}", "{{ document.number }}")
            replaced += 1
    return [f"номер берётся из документа, а не из поля заявки: {replaced} мест"]


def compact_act(body, parts: dict) -> list[str]:
    """Акт: подтянуть текст и убрать пустоту между пунктами."""

    changes: list[str] = []

    # Сначала правим то, что в бланке осталось от исходного документа:
    # забытые гиперссылки с почтой и два слова без пробела.
    changes += drop_hyperlinks(body, ("knc@lipetsk.quadra.ru", "tula@quadra.ru"))
    changes += glue_missing_space(
        body,
        (
            ("в соответствии", "с единым реестром"),
            ("подготовившего акт", "выездной проверки"),
        ),
    )

    # Интервалы после абзацев — основной запас: строки не трогаем, а разрывы
    # между пунктами становятся вдвое плотнее.
    changes += tighten_paragraph_spacing(
        body, {720: 360, 600: 300, 360: 240, 240: 120, 120: 60}
    )

    # Концевые сноски со ссылками на законы печатаются в конце акта. В бланке
    # стоит флаг «не печатать сноски в этом разделе»: LibreOffice сноски всё
    # равно печатает, но выносит их на отдельный лист. Флаг убираем — тогда
    # они идут сразу за текстом.
    section = body.find(q("sectPr"))
    for child in list(section):
        if etree.QName(child).localname == "noEndnote":
            section.remove(child)
            changes.append("снят запрет печати концевых сносок: они идут за текстом")
            break

    # Интервалы по умолчанию: у абзацев без своих настроек было 10 пт после.
    styles = etree.fromstring(parts["word/styles.xml"])
    defaults = styles.find(f"{q('docDefaults')}//{q('spacing')}")
    if defaults is not None:
        was = {key.replace(W, ""): value for key, value in defaults.attrib.items()}
        defaults.set(q("after"), "100")
        defaults.set(q("line"), "240")
        defaults.set(q("lineRule"), "auto")
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        changes.append(f"интервалы по умолчанию: {was} -> after=100 line=240")

    # Сноски со ссылками на законы печатаются отдельным листом — переносим их
    # в текст последним шагом, чтобы форматирование осталось как в бланке.
    changes += move_endnotes_into_text(body, parts)
    # QR-код прокуратуры в бланке не печатается: вместо него метка и место.
    changes += replace_qr_with_placeholder(body)
    # Номер акта может быть уточнён: печатаем номер документа.
    changes += use_document_number(body)
    return changes


def compact_assignment(body, parts: dict) -> list[str]:
    """Задание: убрать пустоту в шапке и между пунктами."""

    changes: list[str] = []

    # Блок «УТВЕРЖДАЮ»: семь строк по 17-18 пт под строку текста — это шапка
    # на четверть страницы.
    for table in tables(body):
        first = "".join(node.text or "" for node in table.iter(q("t")))
        if "УТВЕРЖДАЮ" in first:
            heights = []
            for number in range(1, len(table.findall(q("tr"))) + 1):
                before, after = set_row_height(table, number, 240)
                heights.append(f"{before}->{after}")
            changes.append("шапка «УТВЕРЖДАЮ»: высоты строк " + ", ".join(heights))
        if "Цель проведения выездного обследования" in first:
            # Первая строка таблицы с пунктами и дата утверждения набраны
            # крупными строками — поджимаем до высоты текста.
            for row, value in ((2, 100), (3, 250)):
                before, after = set_row_height(table, row, value)
                changes.append(f"строка {row} таблицы пунктов: {before} -> {after}")
            # Пустые строки-распорки держатся не высотой, а абзацем внутри:
            # у абзаца кегль 14 пт, поэтому строка занимает целую строку.
            spacers = 0
            for row in table.findall(q("tr")):
                if "".join(node.text or "" for node in row.iter(q("t"))).strip():
                    continue
                for paragraph in row.iter(q("p")):
                    shrink_paragraph(paragraph, 4)
                spacers += 1
            changes.append(f"пустые строки-распорки сжаты до 2 пт: {spacers}")

    # Отступы вокруг пунктов заданы не стилем, а прямо у абзацев: 280 твипов
    # (14 пт) сверху и снизу у каждого. Именно они растягивают задание на
    # лишний лист — поджимаем их до 5 пт, оставляя видимый разрыв.
    changes += tighten_paragraph_spacing(
        body, {280: 100, 200: 100}, {280: 100, 240: 100}
    )

    # Отступ перед абзацами: стиль consplusnonformat давал 14 пт сверху
    # каждому абзацу — на сорока с лишним абзацах это полстраницы.
    changes += shrink_style_spacing(parts, "consplusnonformat", before=60, after=0)
    return changes


def tighten_default_spacing(parts: dict) -> list[str]:
    """Уменьшает интервалы по умолчанию: они действуют на все абзацы таблицы.

    В бланке у каждого абзаца после себя 8 пт пустоты и межстрочный 1.08 —
    на длинной таблице это даёт несколько сантиметров.
    """

    styles = etree.fromstring(parts["word/styles.xml"])
    spacing = styles.find(f"{q('docDefaults')}//{q('spacing')}")
    if spacing is None:
        return ["интервалы по умолчанию не найдены"]
    before = {
        key.replace(W, ""): value for key, value in spacing.attrib.items()
    }
    spacing.set(q("after"), "80")
    spacing.set(q("line"), "240")
    spacing.set(q("lineRule"), "auto")
    parts["word/styles.xml"] = etree.tostring(
        styles, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    return [f"интервалы по умолчанию: было {before}, стало after=80 line=240"]


def compact_prescription(body, parts: dict) -> list[str]:
    """Предписание: подтянуть нижние строки на первый лист."""

    changes: list[str] = tighten_default_spacing(parts)
    table = tables(body)[0]

    for row, value, why in (
        (4, 60, "пустая распорка под шапкой: 0.9 см -> 0.1 см"),
        (22, 600, "шапка таблицы мероприятий: 1.4 см -> 1.05 см"),
        (27, 60, "пустая распорка перед блоком подписи"),
        (32, 150, "пояснение под подписью: 0.42 см -> 0.26 см"),
        (36, 200, "пояснение под реквизитами вручения: 0.55 см -> 0.35 см"),
        (37, 60, "пустая распорка перед отметкой об исполнении: 0.4 см -> 0.1 см"),
        (42, 240, "место под подписью инспектора: 0.55 см -> 0.42 см"),
    ):
        before, after = set_row_height(table, row, value)
        changes.append(f"строка {row}: {why} ({before} -> {after})")

    # Пустой абзац после таблицы — обязательный (иначе Word считает файл
    # повреждённым), но он занимает строку: уменьшаем кегль до 2 пт.
    tail = paragraphs(body)
    if tail and not "".join(node.text or "" for node in tail[-1].iter(q("t"))).strip():
        shrink_paragraph(tail[-1], 4)
        changes.append("пустой абзац после таблицы сжат до 2 пт")

    # QR-код из прокуратуры: место в шапке сохраняем, сам код подставляется.
    changes += replace_qr_with_placeholder(body)

    # Колонтитулы в бланке пустые (ни текста, ни номеров страниц), но под них
    # зарезервировано по 36 пт сверху и снизу — это и есть нехватка места.
    section = body.find(q("sectPr"))
    margins = section.find(q("pgMar"))
    before_margins = {key.replace(W, ""): value for key, value in margins.attrib.items()}
    margins.set(q("footer"), "227")  # 36 пт -> 11 пт
    margins.set(q("header"), "227")  # 36 пт -> 11 пт
    margins.set(q("top"), "170")     # 14 пт -> 8.5 пт
    changes.append(
        f"поля страницы: {before_margins} -> "
        f"{ {k.replace(W, ''): v for k, v in margins.attrib.items()} }"
    )
    return changes


# Код бланка -> (правка, версия результата). Версия v3 у тех бланков, где
# нарисованный QR-код заменён меткой: это уже другое содержимое формы.
SPECS = {
    "direction": (compact_direction, "v2"),
    "prescription": (compact_prescription, "v3"),
    "assignment": (compact_assignment, "v2"),
    "act": (compact_act, "v4"),
}


def main() -> None:
    for code, (compact, version) in SPECS.items():
        source = TEMPLATES / code / "v1.docx"
        target = TEMPLATES / code / f"{version}.docx"
        with zipfile.ZipFile(source) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
            order = archive.namelist()

        document = etree.fromstring(parts[DOCUMENT])
        body = document.find(q("body"))
        changes = compact(body, parts)
        parts[DOCUMENT] = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        # Отметки времени в архиве фиксированы: иначе один и тот же шаблон
        # после каждого запуска давал бы разные байты и попадал бы в git как
        # изменение. Так же нормализует готовые документы генератор.
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as result:
            for name in order:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                result.writestr(info, parts[name])

        print(f"=== {code}: {source.name} -> {target.name} ===")
        for change in changes:
            print("   ", change)
        print(f"    размер: {source.stat().st_size} -> {target.stat().st_size} байт")


if __name__ == "__main__":
    main()
