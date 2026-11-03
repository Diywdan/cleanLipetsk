"""Сборка текстов нарушения и требования из справочников.

Раньше описание нарушения и требование предписания вписывались целиком: в них
повторялись адрес, перечень работ с объёмами, нормы и реквизиты акта. Теперь
работы с объёмами хранятся у нарушения, нормы — в связях нарушения, реквизиты
акта — в карточке акта, а текст собирается здесь.

Печать «асфальт – 4 кв.м.» и «восстановить асфальт – 4 кв.м.» идёт из одного
списка: меняется только падеж названия работы и глагол действия.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

# Действия, которые можно предписать: код и форма глагола.
ACTIONS: dict[str, str] = {
    "restore": "восстановить",
    "eliminate": "устранить",
    "remove": "убрать",
    "clean": "очистить",
    "repair": "отремонтировать",
    "install": "установить",
}

DEFAULT_ACTION = "restore"

# Как действие звучит в описании нарушения: «не восстановлено».
ACTION_PAST_NEUTER: dict[str, str] = {
    "restore": "восстановлено",
    "eliminate": "устранено",
    "remove": "убрано",
    "clean": "очищено",
    "repair": "отремонтировано",
    "install": "установлено",
}

# Склонение названия единицы нормы: «часть 5 статьи 5» -> «части 5 статьи 5».
_COUNTABLE = {
    "статья": "статьи",
    "часть": "части",
    "пункт": "пункта",
    "подпункт": "подпункта",
    "раздел": "раздела",
    "глава": "главы",
}

# Служебные слова нормы в нужном падеже. В обороте «в нарушении …» нужен
# родительный, в обороте «в соответствии с …» — творительный. Склоняется
# только первое слово каждой группы: «пунктом 5.2 части 5 статьи 5».
_CASE_WORDS: dict[str, dict[str, tuple[str, str]]] = {
    "genitive": {
        "статья": ("статьи", "статей"),
        "часть": ("части", "частей"),
        "пункт": ("пункта", "пунктов"),
        "подпункт": ("подпункта", "подпунктов"),
    },
    "instrumental": {
        "статья": ("статьёй", "статьями"),
        "часть": ("частью", "частями"),
        "пункт": ("пунктом", "пунктами"),
        "подпункт": ("подпунктом", "подпунктами"),
    },
}


def quantity_text(quantity: Decimal | float | None, unit: str | None) -> str:
    """«4 кв.м.», «2,5 кв.м.» — без лишних нулей после запятой."""

    if quantity is None:
        return ""
    if isinstance(quantity, float):
        quantity = Decimal(str(quantity))
    normalized = quantity.normalize()
    if normalized == normalized.to_integral():
        number = str(int(normalized))
    else:
        number = format(normalized, "f").replace(".", ",")
    return f"{number} {unit}".strip() if unit else number


def work_line(work, quantity, accusative: bool = False) -> str:
    """Одна работа с объёмом: «асфальт – 4 кв.м.»."""

    name = getattr(work, "name_accusative", None) if accusative else None
    name = name or getattr(work, "name", "") or ""
    amount = quantity_text(quantity, getattr(work, "unit", None))
    return f"{name} – {amount}" if amount else name


def works_line(works, accusative: bool = False, action: str | None = None) -> str:
    """Перечень работ: «асфальт – 4 кв.м., грунт – 20 кв.м., бордюр – 4 шт.»."""

    parts: list[str] = []
    for item in works or []:
        line = work_line(item.work, item.quantity, accusative=accusative)
        if action:
            line = f"{action} {line}"
        parts.append(line)
    return ", ".join(parts)


def action_verb(code: str | None) -> str:
    return ACTIONS.get(code or DEFAULT_ACTION, ACTIONS[DEFAULT_ACTION])


def action_past(code: str | None) -> str:
    return ACTION_PAST_NEUTER.get(
        code or DEFAULT_ACTION, ACTION_PAST_NEUTER[DEFAULT_ACTION]
    )


_REFERENCE = re.compile(
    r"^(?:(?P<point>пункт[а-я]*)\s+(?P<point_no>[\d.]+)\s+)?"
    r"(?:(?P<part>част[а-я]*)\s+(?P<part_no>[\d.]+)\s+)?"
    r"(?P<article>стать[а-я]*)\s+(?P<article_no>[\d.]+)$"
)


@dataclass
class _Norm:
    """Норма, разложенная на части — чтобы объединить общие статьи."""

    article: str
    parts: list[str] = field(default_factory=list)
    points: dict[str, list[str]] = field(default_factory=dict)


def _join_numbers(numbers: list[str]) -> str:
    """«7, 12» -> «7 и 12», по возрастанию номера."""

    unique: list[str] = []
    for number in numbers:
        if number not in unique:
            unique.append(number)
    unique.sort(key=_number_key)
    if len(unique) == 1:
        return unique[0]
    return ", ".join(unique[:-1]) + " и " + unique[-1]


def _number_key(value: str) -> tuple:
    """Сортировка номеров: «5.2» после «5», «12» после «7»."""

    parts = []
    for chunk in str(value).replace(",", ".").split("."):
        try:
            parts.append((0, int(chunk), ""))
        except ValueError:
            parts.append((1, 0, chunk))
    return tuple(parts)


def provisions_text(
    references: list[str] | None, case: str = "genitive"
) -> str | None:
    """«пункта 5.2 части 5 статьи 5, частей 7 и 12 статьи 14».

    Нормы в справочнике записаны в именительном падеже: «часть 12 статьи 14».
    В обороте «в нарушении …» нужен родительный падеж (case="genitive"), в
    обороте «в соответствии с …» — творительный (case="instrumental").

    Склоняется только первое слово каждой группы, остальные остаются в
    родительном: «пунктом 5.2 части 5 статьи 5, частями 7 и 12 статьи 14».
    Одинаковые статьи объединяются: «частей 7 и 12 статьи 14», а не «части 7
    статьи 14, части 12 статьи 14».
    """

    if not references:
        return None
    words = _CASE_WORDS.get(case, _CASE_WORDS["genitive"])
    by_article: dict[str, _Norm] = {}
    plain: list[str] = []
    for reference in references:
        text = (reference or "").strip()
        if not text:
            continue
        match = _REFERENCE.match(text)
        if match is None:
            # Нестандартная запись: склоняем только первое слово.
            plain.append(_decline_plain(text, case))
            continue
        article_no = match.group("article_no")
        norm = by_article.setdefault(article_no, _Norm(article=article_no))
        part_no = match.group("part_no")
        point_no = match.group("point_no")
        if part_no and part_no not in norm.parts:
            norm.parts.append(part_no)
        if point_no:
            norm.points.setdefault(part_no or "", []).append(point_no)

    pieces: list[str] = []
    for article_no in sorted(by_article, key=_number_key):
        norm = by_article[article_no]
        segments: list[tuple[str, str]] = []
        # Пункты печатаются со своей частью: «пунктом 5.2 части 5». Часть,
        # у которой уже названы пункты, второй раз не повторяем.
        parts_with_points = {
            part_no for part_no, points in norm.points.items() if part_no and points
        }
        for part_no in sorted(norm.points, key=_number_key):
            points = norm.points[part_no]
            if not points:
                continue
            numbers = _join_numbers(points)
            single = " и " not in numbers
            word = words["пункт"][0 if single else 1]
            tail = f"части {part_no}" if part_no else ""
            segments.append(("point", f"{word} {numbers}"))
            if tail:
                segments.append(("tail", tail))
        rest_parts = [p for p in norm.parts if p not in parts_with_points]
        if rest_parts:
            numbers = _join_numbers(rest_parts)
            single = " и " not in numbers
            segments.append(("part", f"{words['часть'][0 if single else 1]} {numbers}"))
        segments.append(("article", f"статьи {article_no}"))

        # Первое служебное слово группы — в выбранном падеже, остальные
        # остаются в родительном. Если у нормы нет ни пункта, ни части, то
        # ведущим становится само слово «статья»: «статьёй 90».
        leading_exists = any(kind in ("point", "part") for kind, _ in segments)
        text_parts: list[str] = []
        declined = False
        for kind, value in segments:
            if kind == "article" and not leading_exists:
                text_parts.append(f"{words['статья'][0]} {article_no}")
                continue
            if kind in ("point", "part") and not declined:
                text_parts.append(value)
                declined = True
            elif kind == "point":
                text_parts.append("пункта " + value.split(" ", 1)[1])
            elif kind == "part":
                text_parts.append("части " + value.split(" ", 1)[1])
            else:
                text_parts.append(value)
        pieces.append(" ".join(text_parts))
    if plain:
        pieces.extend(plain)
    return ", ".join(pieces) if pieces else None


def provisions_genitive(references: list[str] | None) -> str | None:
    """То же в родительном падеже: для «в нарушении …»."""

    return provisions_text(references, case="genitive")


def provisions_instrumental(references: list[str] | None) -> str | None:
    """То же в творительном падеже: для «в соответствии с …»."""

    return provisions_text(references, case="instrumental")


def _decline_plain(text: str, case: str) -> str:
    """Склоняет первое слово нормы, записанной не по шаблону."""

    words = _CASE_WORDS.get(case, _CASE_WORDS["genitive"])
    for nominative, forms in words.items():
        if text.startswith(nominative + " "):
            return forms[0] + text[len(nominative):]
    for nominative, genitive in _COUNTABLE.items():
        if text.startswith(nominative + " "):
            return genitive + text[len(nominative):]
    return text


def administrative_circumstances(
    prior_date_short: str | None,
    prior_due_short: str | None,
    measure_date_short: str | None = None,
) -> str | None:
    """Событие правонарушения для протокола об административном правонарушении.

    Раньше этот текст вписывали руками — с датами конкретного дела. Теперь он
    собирается из дат наших документов: когда проводилось прежнее мероприятие,
    какие нарушения выявлены, какой срок был дан на исполнение и что
    предписание не исполнено. Чем подтверждено — акт и протокол осмотра, тоже
    с датой нашего мероприятия.
    """

    if not prior_date_short or not prior_due_short:
        return None
    confirmed_by = "актом выездного обследования и протоколом осмотра"
    if measure_date_short:
        confirmed_by = f"{confirmed_by} от {measure_date_short}"
    return (
        f"{prior_date_short} департаментом проведено контрольное (надзорное) "
        "мероприятие без взаимодействия с контролируемым лицом — выездное "
        "обследование, в ходе которого выявлены нарушения Правил "
        "благоустройства и выдано предписание со сроком исполнения до "
        f"{prior_due_short}. В установленный срок предписание не исполнено, "
        f"что подтверждено {confirmed_by}."
    )


def requirement_from_data(
    references: list[str] | None,
    npa: dict | None,
    action: str | None,
    address_text: str | None,
    works_line_text: str | None,
    requirement_object: str | None = None,
) -> str | None:
    """Требование из «сырых» данных: нормы, акт, работы, адрес.

    Один и тот же расчёт нужен и в документах (по снимку), и в карточке
    заявки (по живым данным) — поэтому он здесь, а не в двух местах.
    `npa` — реквизиты акта: title_genitive, adopted_on, number,
    adopted_by_genitive.
    """

    if not works_line_text:
        return None
    npa = npa or {}
    adopted_on = npa.get("adopted_on")
    if adopted_on and len(str(adopted_on)) >= 10:
        value = str(adopted_on)
        adopted_on = f"{value[8:10]}.{value[5:7]}.{value[0:4]}"
    citation = act_citation(
        npa.get("title_genitive"),
        adopted_on=adopted_on,
        number=npa.get("number"),
        adopted_by=npa.get("adopted_by_genitive"),
    )
    return requirement_text(
        provisions_instrumental(references),
        citation,
        action,
        address_text,
        works_line_text,
        requirement_object=requirement_object,
    )


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _sentence(text: str) -> str:
    """Одна точка в конце, без «..» и без запятой перед ней."""

    text = text.rstrip(" .,")
    return f"{text}."


def violation_description(
    object_prepositional: str | None,
    works_line_text: str | None,
    violation_type_name: str | None = None,
    action: str | None = None,
) -> str | None:
    """«На земельном участке … не восстановлено нарушенное благоустройство …,
    а именно: асфальт – 4 кв.м., грунт – 20 кв.м., бордюр – 4 шт.».

    Место — в предложном падеже («на земельном участке»), что именно не
    сделано — из вида нарушения в винительном падеже.
    """

    if not object_prepositional or not works_line_text:
        return None
    subject = violation_type_name or "требования действующего законодательства"
    return _sentence(
        f"На {_lower_first(object_prepositional)}, "
        f"не {action_past(action)} {subject}, а именно: {works_line_text}"
    )


def act_citation(
    title_genitive: str | None,
    adopted_on: str | None = None,
    number: str | None = None,
    adopted_by: str | None = None,
) -> str | None:
    """«Правил … от 28.11.2024 № 836, утверждённых решением …».

    У федеральных актов дата и номер уже входят в название в родительном
    падеже («Федерального закона от 31.07.2020 № 248-ФЗ») — второй раз их
    не печатаем.
    """

    if not title_genitive:
        return None
    text = title_genitive.strip().rstrip(",")
    has_date = bool(adopted_on) and adopted_on in text
    has_number = bool(number) and number in text
    if adopted_on and not has_date and not has_number:
        # Название в родительном падеже, дата и номер — в обычном порядке:
        # «Правил … от 28.11.2024 № 836».
        text = f"{text} от {adopted_on}"
        if number:
            text = f"{text} № {number}"
    elif number and not has_number:
        text = f"{text} № {number}"
    if adopted_by:
        text = f"{text}, утверждённых решением {adopted_by}"
    return text


def requirement_text(
    provisions: str | None,
    act_citation_text: str | None,
    action: str | None,
    address_text: str | None,
    works_line_text: str | None,
    requirement_object: str | None = None,
) -> str | None:
    """Требование предписания целиком.

    «В целях соблюдения требований действующего законодательства, а именно:
    в соответствии с пункта 5.2 части 5 статьи 5, частей 7 и 12 статьи 14
    Правил …, восстановить нарушенное благоустройство … по адресу: г. Липецк,
    ул. Теперика, д.3, а именно: асфальт – 4 кв.м., …».
    """

    if not works_line_text:
        return None
    verb = action_verb(action)
    what = requirement_object or "работы по устранению нарушения"
    basis_parts = [part for part in (provisions, act_citation_text) if part]
    pieces = [
        "В целях соблюдения требований действующего законодательства, "
        "а именно:"
    ]
    if basis_parts:
        # «в соответствии с частей 7 и 12 статьи 14 Правил …» — название акта
        # идёт сразу за нормами, поэтому части соединяются пробелом.
        pieces.append("в соответствии с " + " ".join(basis_parts))
    tail = f"{verb} {what}"
    if address_text:
        tail = f"{tail} по адресу: {_lower_first(address_text)}"
    pieces.append(f"{tail}, а именно: {works_line_text}")
    # После двоеточия запятая не нужна: «а именно: в соответствии с …».
    text = pieces[0]
    for piece in pieces[1:]:
        text += (" " if text.endswith(":") else ", ") + piece
    return _sentence(text)
