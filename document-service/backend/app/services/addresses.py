"""Адреса: единый вид строки, поиск и «найти или создать».

Адрес остаётся отдельной таблицей, потому что на него ссылаются объект
контроля, место проведения действия, адрес нарушения и юридический адрес
организации, и одна и та же строка печатается в нескольких документах.
Но оператор не должен заводить адрес отдельным шагом: он вводит строку,
а запись при необходимости создаётся сама — по приведённому виду, чтобы
не появлялись дубли.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Address


_SPACES = re.compile(r"\s+")


def normalize(value: str | None) -> str:
    """Приводит адрес к виду для сравнения: регистр, пробелы, ё/е, точки."""

    if not value:
        return ""
    text = value.replace("ё", "е").replace("Ё", "Е")
    text = _SPACES.sub(" ", text).strip(" .,;")
    # Точки в сокращениях не должны мешать: «ул.» и «ул» — одно и то же.
    text = text.replace(".", "")
    text = _SPACES.sub(" ", text).strip()
    return text.lower()


def find_by_text(db: Session, full_address: str) -> Address | None:
    key = normalize(full_address)
    if not key:
        return None
    return db.scalars(
        select(Address).where(Address.search_key == key).order_by(Address.id)
    ).first()


def resolve(db: Session, full_address: str | None, **parts) -> Address | None:
    """Находит адрес по строке или заводит новый.

    Пустая строка означает «адрес не указан» — возвращается None.
    """

    text = (full_address or "").strip()
    if not text:
        return None

    address = find_by_text(db, text)
    if address is None:
        address = Address(full_address=text, search_key=normalize(text))
        db.add(address)
        db.flush()

    # Заполняем только те части, которые переданы и ещё пусты: уже известные
    # значения не затираем.
    for field, value in parts.items():
        if value and not getattr(address, field, None):
            setattr(address, field, value)
    if address.search_key != normalize(address.full_address):
        address.search_key = normalize(address.full_address)
    return address


def search(
    db: Session, query: str | None, limit: int = 200, include_archived: bool = True
) -> list[Address]:
    """Поиск по адресам: по улице и дому, по части строки, по индексу.

    В справочнике архивные адреса показываются (их можно вернуть), а в
    подсказках при вводе — нет.
    """

    statement = select(Address).order_by(Address.id.desc()).limit(limit)
    if not include_archived:
        statement = statement.where(Address.is_active.is_(True))
    key = normalize(query)
    if key:
        statement = statement.where(Address.search_key.like(f"%{key}%"))
    return list(db.scalars(statement))


def suggestions(db: Session, query: str | None, limit: int = 15) -> list[Address]:
    """Подсказки при вводе адреса в форме: только действующие адреса."""

    return search(db, query, limit=limit, include_archived=False)
