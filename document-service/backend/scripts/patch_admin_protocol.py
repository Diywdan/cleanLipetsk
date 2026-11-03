"""Правка бланка протокола об административном правонарушении.

В бланке были абзацы, вписанные из конкретного дела (даты, номер предписания,
АО «ПОЧТА РОССИИ», адрес на 3-й Песчаной). Из-за них каждый протокол печатал
чужой случай. Здесь они заменяются текстом из данных заявки.

Правка идёт по элементам: находит абзацы с вписанным текстом, очищает их и
ставит текст с подстановками, сохраняя оформление абзаца (стиль, отступы).
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"\{\{.{0,200}?\}\}", re.S)

# Признаки абзацев, вписанных из чужого дела.
MARKERS = (
    "12.08.2026",
    "06.07.2026",
    "07.08.2026",
    "48001704800001209198",
    "ПОЧТА РОССИИ",
    "Песчаная",
    "60-летия СССР",
    "Комолых Евгенией",
)

# Старое место описания: текст собирается из полей производства, поэтому
# подстановку {{ administrative.offense_description }} из бланка убираем —
# иначе описание напечатается дважды.
DESCRIPTION_MARK = "administrative.offense_description"

# Новый текст по порядку абзацев.
NEW_TEXT = {
    "opening": (
        "{{ administrative.protocol_date_short }} "
        "{{ inspector.position_instrumental_lower }} "
        "{{ inspector.full_name_instrumental }} проведено контрольное "
        "(надзорное) мероприятие без взаимодействия с контролируемым лицом — "
        "выездное обследование с целью оценки исполнения ранее выданного "
        "законного предписания Департамента от "
        "{{ administrative.prior_prescription_date_short }} "
        "№ {{ administrative.prior_prescription_number }} со сроком исполнения "
        "до {{ administrative.prior_prescription_due_short }}, в ходе которого "
        "установлено следующее."
    ),
    "obliged": (
        "В соответствии с требованиями законного предписания Департамента от "
        "{{ administrative.prior_prescription_date_short }} "
        "№ {{ administrative.prior_prescription_number }} "
        "{{ controlled_person.representation }} обязано было в срок до "
        "{{ administrative.prior_prescription_due_short }} в соответствии с "
        "{{ administrative.prior_prescription_basis }} провести работы по "
        "устранению нарушения{{ control_object.works_note }}, расположенного по "
        "адресу: {{ control_object.address }}."
    ),
    "however": (
        "Однако, {{ case.actual_start_short }} в {{ case.actual_start_time }} "
        "установлено, что {{ controlled_person.representation }} не провело "
        "работы по устранению нарушения{{ control_object.works_note }}, "
        "расположенного по вышеуказанному адресу в срок, установленный законным "
        "предписанием департамента развития территории администрации города "
        "Липецка от {{ administrative.prior_prescription_date_short }} "
        "№ {{ administrative.prior_prescription_number }} со сроком исполнения "
        "до {{ administrative.prior_prescription_due_short }}."
    ),
    "not_executed": (
        "Таким образом, предписание Департамента от "
        "{{ administrative.prior_prescription_date_short }} "
        "№ {{ administrative.prior_prescription_number }} со сроком исполнения "
        "до {{ administrative.prior_prescription_due_short }} "
        "{{ controlled_person.representation }} не исполнило в установленный "
        "срок, что подтверждено "
        "{{ administrative.appendix_note }}."
    ),
    "signs": (
        "Таким образом, в действиях/бездействии "
        "{{ controlled_person.representation }} усматриваются признаки "
        "административного правонарушения, предусмотренного "
        "{{ administrative.offense_article }} Кодекса Российской Федерации об "
        "административных правонарушениях."
    ),
    # Строки с подписями уже правильные: подставляется только значение.
    "date": None,
    "place": None,
}
ORDER = ["opening", "obliged", "however", "not_executed", "signs", "date", "place"]


def q(tag: str) -> str:
    return f"{W}{tag}"


def paragraph_text(paragraph) -> str:
    return "".join(n.text or "" for n in paragraph.iter(q("t")))


def replace_text(paragraph, text: str) -> None:
    """Меняет текст абзаца, сохраняя оформление первого run-а."""

    runs = paragraph.findall(q("r"))
    template_run = runs[0] if runs else None
    for run in runs[1:]:
        paragraph.remove(run)
    if template_run is None:
        template_run = etree.SubElement(paragraph, q("r"))
    for node in list(template_run):
        if etree.QName(node).localname != "rPr":
            template_run.remove(node)
    node = etree.SubElement(template_run, q("t"))
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    data = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        parts = {name: archive.read(name) for name in names}

    root = etree.fromstring(parts["word/document.xml"])
    paragraphs = list(root.iter(q("p")))
    print(f"абзацев в бланке: {len(paragraphs)}")

    found: list = []
    for paragraph in paragraphs:
        text = paragraph_text(paragraph)
        if any(marker in text for marker in MARKERS):
            found.append(paragraph)
            print(f"  вписанный абзац: {text[:80]!r}")

    if len(found) < len(ORDER):
        print(f"ВНИМАНИЕ: найдено {len(found)} абзацев, ожидалось {len(ORDER)}")

    for paragraph, key in zip(found, ORDER):
        text = NEW_TEXT[key]
        if text is None:
            print(f"  -> {key}: строка с подписью остаётся как есть")
            continue
        print(f"  -> {key}: {text[:60]}...")
        replace_text(paragraph, text)

    # Убираем старое место описания: описание теперь собирается из полей
    # производства, а не вписывается целиком одним текстом.
    for paragraph in paragraphs:
        if DESCRIPTION_MARK in paragraph_text(paragraph):
            print(f"  -> убрано место описания из поля: "
                  f"{paragraph_text(paragraph)[:60]!r}")
            replace_text(paragraph, "")

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, parts[name])
    target.write_bytes(buffer.getvalue())
    print(f"записано: {target} ({len(buffer.getvalue())} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
