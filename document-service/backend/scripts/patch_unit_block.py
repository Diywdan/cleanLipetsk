"""Правка бланков направления: блок филиала становится необязательным.

Зачем: если у контролируемого лица нет филиала, шаблон печатает
«Законному представителю» и пустую строку вместо получателя. Правка
оборачивает блок филиала условием — нет филиала, нет и блока.

Правка идёт по XML внутри DOCX (lxml), текст и форматирование не
затрагиваются: добавляются только два тега условия, а в письме о направлении
акта строка дополнительно разбивается на абзацы так же, как в направлении.

По умолчанию — только показать, что получится. Применить: --apply

Запуск: PYTHONPATH=/app python scripts/patch_unit_block.py [--apply]
"""
from __future__ import annotations

import argparse
import copy
import re
import shutil
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{(.{0,200}?)\}\}", re.S)

# Бланки, которые правятся, и куда кладётся результат.
TARGETS = {
    "direction": Path("/app/templates/direction/v2.docx"),
    "act_direction": Path("/app/templates/act_direction/v2.docx"),
}

IF_TAG = "{% if controlled_person.has_unit %}"
ENDIF_TAG = "{% endif %}"

UNIT_MARK = "controlled_person.unit_in_genitive"
UNIT_EMAIL_MARK = "controlled_person.unit_email"


def q(tag: str) -> str:
    return f"{W}{tag}"


def paragraph_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.iter(q("t")))


def paragraphs_of_cells(root) -> list[list]:
    """Все ячейки документа и их абзацы — в порядке обхода."""
    cells: list[list] = []
    for table in root.iter(q("tbl")):
        for row in table.findall(q("tr")):
            for cell in row.findall(q("tc")):
                paragraphs = cell.findall(q("p"))
                if paragraphs:
                    cells.append(paragraphs)
    return cells


def append_text(paragraph, text: str) -> None:
    """Дописывает текст в конец абзаца, сохраняя форматирование последнего run."""
    runs = paragraph.findall(q("r"))
    if runs:
        last = runs[-1]
        node = etree.SubElement(last, q("t"))
        node.text = text
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return
    run = etree.SubElement(paragraph, q("r"))
    node = etree.SubElement(run, q("t"))
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def split_run_by_breaks(paragraph, base_rpr) -> None:
    """Разбивает единственный run по разрывам строки на отдельные абзацы.

    Нужно письму о направлении акта: там весь адресный блок — один абзац
    с разрывами строки, и обернуть условием часть строк невозможно.
    """
    parent = paragraph.getparent()
    index = list(parent).index(paragraph)
    ppr = paragraph.find(q("pPr"))

    # Содержимое абзаца может лежать и в run-ах, и вне них (например, br).
    lines: list[list] = [[]]
    base_rpr = None
    for child in paragraph:
        name = etree.QName(child).localname
        if name == "pPr":
            continue
        if name == "r":
            rpr = child.find(q("rPr"))
            if rpr is not None and base_rpr is None:
                base_rpr = rpr
            for node in child:
                inner = etree.QName(node).localname
                if inner == "br":
                    lines.append([])
                elif inner == "t":
                    lines[-1].append(node.text or "")
        elif name == "br":
            lines.append([])
        elif name == "t":
            lines[-1].append(child.text or "")

    if len(lines) < 2:
        return

    new_paragraphs = []
    for parts in lines:
        text = "".join(parts)
        paragraph_new = etree.Element(q("p"))
        if ppr is not None:
            paragraph_new.append(copy.deepcopy(ppr))
        if text:
            run_new = etree.SubElement(paragraph_new, q("r"))
            if base_rpr is not None:
                run_new.append(copy.deepcopy(base_rpr))
            node = etree.SubElement(run_new, q("t"))
            node.text = text
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        new_paragraphs.append(paragraph_new)

    # Первый абзац остаётся на месте, остальные вставляются следом.
    parent.remove(paragraph)
    for offset, paragraph_new in enumerate(new_paragraphs):
        parent.insert(index + offset, paragraph_new)


def split_paragraph_at(paragraph, needle: str) -> None:
    """Делит абзац на два по началу подстроки.

    Нужно письму о направлении акта: там «Законному представителю» и
    подстановка филиала стоят в одном абзаце, и чтобы обернуть условием
    только вторую строку, абзац надо разделить по тексту.
    """
    parent = paragraph.getparent()
    index = list(parent).index(paragraph)
    ppr = paragraph.find(q("pPr"))

    # Собираем плоский список кусков: текст и разрывы.
    pieces: list[tuple[str, object]] = []
    for child in paragraph:
        name = etree.QName(child).localname
        if name == "pPr":
            continue
        if name == "r":
            for node in child:
                inner = etree.QName(node).localname
                if inner == "br":
                    pieces.append(("break", None))
                elif inner == "t":
                    pieces.append(("text", node.text or ""))
        elif name == "br":
            pieces.append(("break", None))
        elif name == "t":
            pieces.append(("text", child.text or ""))

    # Ищем позицию разделения по склеенному тексту.
    joined = "".join(value for kind, value in pieces if kind == "text")
    position = joined.find(needle)
    if position <= 0:
        return

    # Раскладываем обратно на две группы: до позиции и после.
    groups: list[list[tuple[str, object]]] = [[], []]
    consumed = 0
    for kind, value in pieces:
        if kind == "break":
            groups[1 if consumed >= position else 0].append((kind, value))
            continue
        text = str(value)
        start = consumed
        end = consumed + len(text)
        if end <= position:
            groups[0].append((kind, text))
        elif start >= position:
            groups[1].append((kind, text))
        else:
            groups[0].append((kind, text[: position - start]))
            groups[1].append((kind, text[position - start:]))
        consumed = end

    run_template = next(
        (child for child in paragraph if etree.QName(child).localname == "r"), None
    )
    rpr = run_template.find(q("rPr")) if run_template is not None else None

    new_paragraphs = []
    for group in groups:
        paragraph_new = etree.Element(q("p"))
        if ppr is not None:
            paragraph_new.append(copy.deepcopy(ppr))
        run_new = None
        for kind, value in group:
            if kind == "break":
                if run_new is None:
                    run_new = etree.SubElement(paragraph_new, q("r"))
                    if rpr is not None:
                        run_new.append(copy.deepcopy(rpr))
                etree.SubElement(run_new, q("br"))
            else:
                if run_new is None:
                    run_new = etree.SubElement(paragraph_new, q("r"))
                    if rpr is not None:
                        run_new.append(copy.deepcopy(rpr))
                node = etree.SubElement(run_new, q("t"))
                node.text = str(value)
                node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        new_paragraphs.append(paragraph_new)

    parent.remove(paragraph)
    for offset, paragraph_new in enumerate(new_paragraphs):
        parent.insert(index + offset, paragraph_new)


def patch(path: Path, label: str) -> tuple[bytes, list[str]]:
    notes: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names}

    root = etree.fromstring(parts["word/document.xml"])

    # 1. Если адресный блок собран в один абзац с разрывами строки — разбиваем
    #    его на абзацы: иначе условием нельзя охватить только строки филиала.
    #    Сначала находим такие ячейки, потом правим: при обходе менять
    #    структуру нельзя, список ячеек устаревает.
    to_split = []
    for paragraphs in paragraphs_of_cells(root):
        if len(paragraphs) != 1:
            continue
        text = paragraph_text(paragraphs[0])
        if UNIT_MARK in text and UNIT_EMAIL_MARK in text:
            to_split.append(paragraphs[0])
    for paragraph in to_split:
        run = paragraph.find(q("r"))
        rpr = run.find(q("rPr")) if run is not None else None
        cell = paragraph.getparent()
        before = len(list(cell.findall(q("p"))))
        split_run_by_breaks(paragraph, rpr)
        after = len(list(cell.findall(q("p"))))
        notes.append(f"адресный блок разбит по строкам: {before} -> {after}")

    # 1б. Если строка «Законному представителю» склеена с подстановкой в одном
    #     абзаце — делим абзац, чтобы условие начиналось с отдельной строки.
    for paragraphs in paragraphs_of_cells(root):
        for paragraph in list(paragraphs):
            text = paragraph_text(paragraph)
            if UNIT_MARK in text and not text.strip().startswith("{{"):
                split_paragraph_at(paragraph, "{{")
                notes.append("абзац со строкой филиала разделён по тексту")
                break

    # 2. Оборачиваем блок филиала условием.
    patched = False
    for paragraphs in paragraphs_of_cells(root):
        texts = [paragraph_text(p) for p in paragraphs]
        if not any(UNIT_MARK in t for t in texts):
            continue
        unit_index = next(i for i, t in enumerate(texts) if UNIT_MARK in t)
        email_index = next(
            (i for i, t in enumerate(texts) if UNIT_EMAIL_MARK in t), None
        )
        if unit_index == 0:
            notes.append(f"{label}: блок филиала уже в начале ячейки — пропуск")
            break
        if any(IF_TAG in t or ENDIF_TAG in t for t in texts):
            notes.append(f"{label}: условие уже стоит — пропуск")
            patched = True
            break
        append_text(paragraphs[unit_index - 1], IF_TAG)
        append_text(paragraphs[email_index], ENDIF_TAG)
        notes.append(
            f"{label}: условие охватывает абзацы "
            f"{unit_index}–{email_index + 1} из {len(paragraphs)}"
        )
        patched = True
        break

    if not patched:
        raise SystemExit(f"{label}: блок филиала не найден — правка не сделана")

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, parts[name])
    return buffer.getvalue(), notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    for code, target in TARGETS.items():
        source = Path(f"/app/templates/{code}/v1.docx")
        if not source.exists():
            print(f"{code}: нет исходного файла {source}")
            continue
        data, notes = patch(source, code)
        print(f"=== {code} ===")
        print(f"  источник: {source} ({source.stat().st_size} б)")
        for note in notes:
            print(f"  {note}")
        print(f"  результат: {len(data)} б -> {target}")

        if not args.apply:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if not args.apply:
        print("\nЭто проверка. Для записи файлов добавьте --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
