"""Даты, которые следуют за датой осмотра.

Заполнять их руками долго, а зависят они от одной даты — дня осмотра:

* окончание осмотра — начало плюс 15 минут;
* задание выдают накануне осмотра, причём накануне рабочего дня: если осмотр
  в понедельник, задание датируется пятницей;
* решение по результатам мероприятия датируется днём протокола осмотра.

Значения подставляются, когда осмотр заводят и когда его дату меняют. При
этом они остаются обычными полями формы: если человек поправил дату руками,
следующее сохранение осмотра её **не** перезапишет. Перезаписывается только
то, что система проставила сама, — то есть значение, которое совпадает
с расчётным для прошлой даты осмотра.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forms import DISPLAY_TZ, parse_datetime
from app.models import ControlAction, ControlCase, Decision


# Время, которым датируются документы: задание выдают в начале рабочего дня.
DOCUMENT_TIME = time(9, 0)

# Сколько длится осмотр по умолчанию: подставляется в поле окончания.
DEFAULT_DURATION = timedelta(minutes=15)

# Суббота и воскресенье. Праздники не учитываем: их список меняется каждый
# год, и ошибка в нём была бы хуже, чем суббота в дате задания.
WEEKEND = (5, 6)


def local_date(moment: datetime | None) -> date | None:
    """Дата в местном времени документов: по ней и считаются сроки."""

    if moment is None:
        return None
    return moment.astimezone(DISPLAY_TZ).date()


def previous_working_day(day: date) -> date:
    """Предыдущий рабочий день: выходные пропускаются."""

    candidate = day - timedelta(days=1)
    while candidate.weekday() in WEEKEND:
        candidate -= timedelta(days=1)
    return candidate


def assignment_moment(day: date) -> datetime:
    """Когда выдают задание: накануне осмотра, в начале рабочего дня."""

    return parse_datetime(
        f"{previous_working_day(day).isoformat()}T{DOCUMENT_TIME:%H:%M}"
    )


def default_end(started_at: datetime | None) -> datetime | None:
    """Осмотр по умолчанию длится 15 минут."""

    return started_at + DEFAULT_DURATION if started_at is not None else None


def apply_after_inspection(
    db: Session,
    case: ControlCase,
    inspection: ControlAction,
    previous_started_at: datetime | None = None,
) -> list[str]:
    """Проставляет даты, которые следуют за датой осмотра.

    ``previous_started_at`` — дата осмотра до правки: по ней видно, какие
    значения система проставила сама и, значит, может обновить.
    """

    day = local_date(inspection.started_at)
    if day is None:
        return []
    was = local_date(previous_started_at)
    changed: list[str] = []

    # Дата задания: подставляем, если поле пустое или хранит прошлый расчёт.
    target = assignment_moment(day)
    auto_before = assignment_moment(was) if was is not None else None
    if case.assignment_date is None or (
        auto_before is not None and case.assignment_date == auto_before
    ):
        if case.assignment_date != target:
            case.assignment_date = target
            changed.append(f"дата задания: {target.astimezone(DISPLAY_TZ):%d.%m.%Y}")

    # Дата решения: решение датируется днём протокола осмотра.
    decision = db.scalars(
        select(Decision)
        .where(Decision.control_case_id == case.id)
        .order_by(Decision.id)
    ).first()
    if decision is None:
        # Решение ещё не заводили: создаём с одной датой, остальное заполнит
        # делопроизводитель. Пустая заготовка документу не мешает.
        decision = Decision(control_case_id=case.id)
        db.add(decision)
    if decision.decision_date is None or (
        was is not None and decision.decision_date == was
    ):
        if decision.decision_date != day:
            decision.decision_date = day
            changed.append(f"дата решения: {day:%d.%m.%Y}")

    return changed
