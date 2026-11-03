"""Русскоязычное форматирование значений для подстановки в документы."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


# Фиксированное смещение — запасной вариант, если в образе нет базы часовых
# поясов. Москва переходит на летнее время с 2014 года, смещение постоянно.
try:
    DISPLAY_TZ: timezone | ZoneInfo = ZoneInfo(settings.display_timezone)
except (ZoneInfoNotFoundError, ValueError):
    DISPLAY_TZ = timezone(timedelta(hours=3))


def to_display(value: datetime | date | None) -> datetime | date | None:
    """Переводит момент времени в часовой пояс документов.

    В базе моменты хранятся в UTC, а в документах печатается местное время:
    без этого «с 08 ч 30 мин.» превращается в «с 05 ч 30 мин.».
    """

    if value is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DISPLAY_TZ)


def date_words(value: date | datetime | None, with_year: bool = True) -> str:
    """«22 сентября 2026 г.» — так дата печатается в разобранных формах."""

    value = to_display(value)
    if value is None:
        return ""
    day = value.day
    month = MONTHS_GENITIVE[value.month - 1]
    if with_year:
        return f"{day} {month} {value.year} г."
    return f"{day} {month}"


def date_short(value: date | datetime | None) -> str:
    """«22.09.2026»."""

    value = to_display(value)
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def time_short(value: datetime | None) -> str:
    """«08 ч 30 мин.»."""

    value = to_display(value)
    if value is None:
        return ""
    return f"{value.hour:02d} ч {value.minute:02d} мин."


def time_official(value: datetime | None) -> str:
    """«08 час. 30 мин.» — формат бланков задания и акта."""

    value = to_display(value)
    if value is None:
        return ""
    return f"{value.hour:02d} час. {value.minute:02d} мин."


def _split_name(full_name: str | None) -> tuple[str, str, str]:
    if not full_name:
        return "", "", ""
    parts = full_name.split()
    surname = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""
    patronymic = parts[2] if len(parts) > 2 else ""
    return surname, name, patronymic


def _initial(part: str) -> str:
    """«Евгения» → «Е.», «Т.Н.» → «Т.Н.» (имя уже сокращено)."""

    if not part:
        return ""
    if "." in part:
        return part if part.endswith(".") else f"{part}."
    return f"{part[0].upper()}."


def initials(name: str | None) -> str:
    """«Е.Ю.»"""

    _, first, patronymic = _split_name(name)
    return f"{_initial(first)}{_initial(patronymic)}"


def short_name(full_name: str | None) -> str:
    """«Комолых Е.Ю.» — фамилия с инициалами после неё."""

    surname, _, _ = _split_name(full_name)
    return f"{surname} {initials(full_name)}".strip()


def short_name_before(full_name: str | None) -> str:
    """«Е.Ю. Комолых» — инициалы перед фамилией."""

    surname, _, _ = _split_name(full_name)
    return f"{initials(full_name)} {surname}".strip()


def surname_genitive(surname: str | None) -> str:
    """Фамилия в родительном падеже: «Инютина» → «Инютиной».

    Это подстраховка для случаев, когда падежная форма не заполнена явно:
    правило покрывает фамилии на -а/-я, -ий и мужские на согласную, но
    фамилии вроде «Комолых» не склоняются, поэтому у подписанта есть
    отдельное поле для точной формы.
    """

    if not surname:
        return ""
    if surname.endswith(("а", "я")):
        return surname[:-1] + "ой"
    if surname.endswith("ий"):
        return surname[:-2] + "ого"
    if surname.endswith(("ъ", "ь", "й", "о", "е", "у", "ю", "ы", "и", "э")):
        return surname
    return surname + "а"


def short_name_genitive(full_name: str | None) -> str:
    """«Инютиной Т.Н.» — фамилия с инициалами в родительном падеже."""

    surname, _, _ = _split_name(full_name)
    return f"{surname_genitive(surname)} {initials(full_name)}".strip()


# В конструкцию «в лице …» подразделение входит в родительном падеже:
# «АО «РИР Энерго» в лице филиала АО «РИР Энерго»-«Липецкая генерация»».
UNIT_GENITIVE_PREFIXES: dict[str, tuple[str, str]] = {
    "branch": ("филиал", "филиала"),
    "representation": ("представительство", "представительства"),
    "separate_unit": ("обособленное подразделение", "обособленного подразделения"),
}


def unit_in_genitive(name: str | None, kind: str | None) -> str:
    """«филиал АО …» → «филиала АО …» для оборота «в лице …»."""

    if not name:
        return ""
    pair = UNIT_GENITIVE_PREFIXES.get(kind or "")
    if pair is None:
        return name
    nominative, genitive = pair
    if name.lower().startswith(nominative):
        return genitive + name[len(nominative) :]
    return name
