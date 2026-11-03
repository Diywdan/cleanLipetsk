"""Разбор значений из форм.

Модуль вынесен на верхний уровень: им пользуются и страницы, и справочники,
и программный интерфейс — раньше он лежал внутри слоя страниц, и сервисам
приходилось бы зависеть от него.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

try:
    DISPLAY_TZ: timezone | ZoneInfo = ZoneInfo(settings.display_timezone)
except (ZoneInfoNotFoundError, ValueError):  # pragma: no cover
    from datetime import timedelta

    DISPLAY_TZ = timezone(timedelta(hours=3))


def parse_datetime(value: str | None) -> datetime | None:
    """«2026-09-22T08:30» из поля datetime-local.

    Даты вводятся в местном времени документов и хранятся с зоной.
    """

    if not value or not value.strip():
        return None
    text = value.strip().replace("Z", "")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=DISPLAY_TZ)
    return parsed


def parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def to_input(value: datetime | date | None) -> str:
    """Значение для поля datetime-local или date."""

    if value is None:
        return ""
    if isinstance(value, datetime):
        local = value.astimezone(DISPLAY_TZ)
        return local.strftime("%Y-%m-%dT%H:%M")
    return value.isoformat()


def work_rows(form) -> list[tuple[int, Decimal | None]]:
    """Работы из формы: список «работа, объём».

    Списки приходят параллельно: идентификаторы работ и объёмы стоят в одном
    порядке. Пустые строки пропускаются, повторы — тоже: по одной работе
    объём вводится один раз.

    Разбор общий для карточки заявки и страницы осмотра: работы вводятся в
    обоих местах одинаково.
    """

    work_ids = form.getlist("violation_work_ids")
    quantities = form.getlist("violation_work_quantities")
    rows: list[tuple[int, Decimal | None]] = []
    seen: set[int] = set()
    for index, raw in enumerate(work_ids):
        work_id = parse_int(raw)
        if not work_id or work_id in seen:
            continue
        seen.add(work_id)
        raw_quantity = quantities[index] if index < len(quantities) else ""
        quantity = None
        if raw_quantity and str(raw_quantity).strip():
            try:
                quantity = Decimal(str(raw_quantity).strip().replace(",", "."))
            except InvalidOperation:
                quantity = None
        rows.append((work_id, quantity))
    return rows
