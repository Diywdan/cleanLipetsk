"""Разбор вёрстки шаблона: почему документ не влезает на лист.

Показывает по каждому блоку бланка высоты строк таблиц, кегль, интервалы
и отступы, а также поля страницы. По этому разбору видно, где именно
занимает место «воздух»: пустые распорки, высокие строки под подпись,
межстрочный интервал или зарезервированные колонтитулы.

Запуск (файл можно взять из репозитория или из контейнера):
    python scripts/template_layout.py backend/templates/direction/v2.docx
"""

import sys
import zipfile
from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def q(tag: str) -> str:
    return f"{W}{tag}"


def text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(q("t"))).strip()


def main(path: str) -> None:
    with zipfile.ZipFile(path) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        styles = etree.fromstring(archive.read("word/styles.xml"))
        print(f"=== {path} ===")

        defaults = styles.find(q("docDefaults"))
        if defaults is not None:
            size = defaults.find(f".//{q('sz')}")
            fonts = defaults.find(f".//{q('rFonts')}")
            spacing = defaults.find(f".//{q('spacing')}")
            print(
                "по умолчанию:",
                "размер", size.get(q("val")) if size is not None else "?",
                "| шрифт", fonts.attrib if fonts is not None else "?",
                "| интервалы", {k.replace(W, ""): v for k, v in (spacing.attrib if spacing is not None else {}).items()},
            )

        body = document.find(q("body"))
        print("\nблоки и высоты строк:")
        for child in body:
            tag = etree.QName(child).localname
            if tag == "tbl":
                for number, row in enumerate(child.findall(q("tr")), start=1):
                    tr_pr = row.find(q("trPr"))
                    height = tr_pr.find(q("trHeight")) if tr_pr is not None else None
                    texts = " | ".join(text_of(cell)[:34] for cell in row.findall(q("tc")) if text_of(cell))
                    sizes = sorted({
                        run.find(q("rPr")).find(q("sz")).get(q("val"))
                        for run in row.iter(q("r"))
                        if run.find(q("rPr")) is not None and run.find(q("rPr")).find(q("sz")) is not None
                    })
                    height_value = height.get(q("val")) if height is not None else None
                    rule = (height.get(q("hRule")) if height is not None else None) or "-"
                    print(
                        f"  строка {number:>2} h={height_value if height_value is not None else '-':>5}"
                        f" правило={rule:<8}"
                        f" размеры={','.join(sizes) or '-':<10} {texts[:60]}"
                    )
            elif tag == "p":
                spacing = child.find(q("pPr") + "/" + q("spacing")) if child.find(q("pPr")) is not None else None
                sizes = sorted({
                    run.find(q("rPr")).find(q("sz")).get(q("val"))
                    for run in child.findall(q("r"))
                    if run.find(q("rPr")) is not None and run.find(q("rPr")).find(q("sz")) is not None
                })
                text = text_of(child)
                if text or spacing is not None:
                    print(
                        f"  абзац  {text[:50]!r:<54}"
                        f" интервалы={({k.replace(W, ''): v for k, v in (spacing.attrib if spacing is not None else {}).items()})}"
                        f" размеры={','.join(sizes) or '-'}"
                    )


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        main(argument)
