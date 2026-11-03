"""Сквозная нумерация заявок.

Внутренний номер заявки присваивает система: он сквозной для всех
пользователей и не редактируется вручную. Номер выдаёт последовательность
Postgres, а не «максимум плюс один»: два оператора, создавшие заявку
одновременно, получат разные номера, а не один и тот же.

Номера не переиспользуются. Если заявку удалили или создание отменилось,
номер остаётся за ней — «дырка» в нумерации безопаснее, чем номер, который
уже ушёл в письмо или документ и достался другому делу.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ControlCase


# Имя последовательности в базе: создаётся миграцией.
CASE_NUMBER_SEQUENCE = "control_case_number_seq"

# Ширина номера: 000001, 000002, … Номер сортируется как текст и одинаково
# выглядит в интерфейсе, письме и разговоре.
CASE_NUMBER_WIDTH = 6


def format_case_number(value: int) -> str:
    """«123» -> «000123»."""

    return f"{value:0{CASE_NUMBER_WIDTH}d}"


def next_case_number(db: Session) -> str:
    """Следующий номер из сквозной последовательности."""

    value = db.scalar(select(func.nextval(CASE_NUMBER_SEQUENCE)))
    return format_case_number(int(value))


def assign_case_number(db: Session, case: ControlCase) -> str:
    """Присваивает заявке номер, если его ещё нет."""

    if case.case_number:
        return case.case_number
    case.case_number = next_case_number(db)
    return case.case_number
