"""Удаление и архивирование значений справочников.

Правило простое: значение, на которое нигде не ссылаются, удаляется;
значение, которое уже вошло в документы, удалять нельзя — оно уходит в архив
и перестаёт предлагаться в списках, но остаётся в уже созданных заявках
и документах.

Удалять «насовсем» используемое значение нельзя не из-за аккуратности,
а по существу: документы формируются по снимкам данных, и ссылка на
удалённую запись сломала бы и карточку заявки, и повторную сборку пакета.

Способ архивирования берётся из самой модели: где есть `is_active`, снимается
этот признак; где периоды действия (`valid_to`), проставляется дата окончания.
Так не приходится заводить второй механизм для того же смысла.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Address,
    ControlBodySignatory,
    ControlObject,
    Inspector,
    Organization,
    OrganizationRole,
    OrganizationSignatory,
    OrganizationUnit,
    Area,
)
from app.models.base import Base


# Виды значений, которыми управляет раздел справочников.
DICTIONARY_MODELS: dict[str, type] = {
    "organizations": Organization,
    "units": OrganizationUnit,
    "representatives": OrganizationSignatory,
    "roles": OrganizationRole,
    "inspectors": Inspector,
    "signatories": ControlBodySignatory,
    "addresses": Address,
    "objects": ControlObject,
    "areas": Area,
}

TITLES = {
    "organizations": "организация",
    "units": "подразделение",
    "representatives": "представитель",
    "roles": "роль организации",
    "inspectors": "инспектор",
    "signatories": "утверждающее лицо",
    "addresses": "адрес",
    "objects": "объект контроля",
    "areas": "управа",
}


def model_for(kind: str) -> type | None:
    return DICTIONARY_MODELS.get(kind)


def references(db: Session, entity) -> list[tuple[str, int]]:
    """Где и сколько раз используется запись.

    Перебираются все внешние ключи схемы, поэтому список не устареет, когда
    в базе появится новая таблица со ссылкой на справочник.
    """

    target = entity.__table__
    found: list[tuple[str, int]] = []
    for table in Base.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table is not target:
                continue
            column = foreign_key.parent
            try:
                count = db.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(column == entity.id)
                )
            except Exception:  # pragma: no cover — защита от неожиданной схемы
                continue
            if count:
                found.append((table.name, count))
    return found


def _uses_period(entity) -> bool:
    return hasattr(entity, "valid_to")


def _uses_flag(entity) -> bool:
    return hasattr(entity, "is_active")


def is_archived(entity) -> bool:
    if _uses_flag(entity):
        return not entity.is_active
    if _uses_period(entity):
        return entity.valid_to is not None and entity.valid_to <= date.today()
    return False


def archive(db: Session, entity) -> bool:
    """Убирает значение из списков, не удаляя саму запись."""

    if _uses_flag(entity):
        entity.is_active = False
    elif _uses_period(entity):
        entity.valid_to = date.today()
    else:
        return False
    db.flush()
    return True


def restore(db: Session, entity) -> bool:
    if _uses_flag(entity):
        entity.is_active = True
    elif _uses_period(entity):
        entity.valid_to = None
    else:
        return False
    db.flush()
    return True


def delete_or_archive(db: Session, entity) -> dict:
    """Удаляет неиспользуемое значение, используемое — отправляет в архив."""

    used_by = references(db, entity)
    if used_by:
        archive(db, entity)
        return {"action": "archived", "references": used_by}
    db.delete(entity)
    db.flush()
    return {"action": "deleted", "references": []}


def describe_references(used_by: list[tuple[str, int]]) -> str:
    """Человеческое пояснение, где используется значение."""

    parts = []
    for table, count in used_by:
        human = TABLE_TITLES.get(table, table)
        parts.append(f"{human} — {count}")
    return "; ".join(parts)


TABLE_TITLES = {
    "control_cases": "заявки",
    "control_case_inspectors": "участие в заявках",
    "control_action_inspectors": "участие в действиях",
    "control_actions": "контрольные действия",
    "control_objects": "объекты контроля",
    "areas": "управы",
    "area_addresses": "адреса управ",
    "area_inspectors": "закреплённые инспекторы",
    "violations": "нарушения",
    "decisions": "решения",
    "prescriptions": "предписания",
    "documents": "документы",
    "organization_units": "подразделения",
    "organization_requisites": "реквизиты",
    "organization_contacts": "контакты",
    "organization_roles": "роли организации",
    "organization_signatories": "представители",
    "control_body_signatories": "утверждающие лица",
    "control_case_experts": "эксперты по заявкам",
    "works": "работы",
    "control_object_organizations": "привязка организаций к объектам",
}
