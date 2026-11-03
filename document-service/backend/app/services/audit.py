"""Журнал действий: кто и что изменил.

Записи складываются в ту же транзакцию, что и само изменение: если сохранение
не прошло, в журнале не останется ложного следа.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


# Человекочитаемые названия действий и таблиц — для страницы журнала.
ACTION_TITLES = {
    "create": "создание",
    "update": "изменение",
    "delete": "удаление",
    "generate": "формирование документов",
    "login": "вход в систему",
    "logout": "выход из системы",
    "password": "смена пароля",
    "block": "блокировка",
    "unblock": "разблокировка",
    "role_grant": "выдача роли",
    "role_revoke": "снятие роли",
    "session_revoke": "закрытие сессии",
}

ENTITY_TITLES = {
    "control_cases": "заявка",
    "document_packages": "пакет документов",
    "documents": "документ",
    "organizations": "организация",
    "organization_units": "подразделение",
    "organization_signatories": "представитель организации",
    "organization_roles": "роль организации",
    "inspectors": "инспектор",
    "control_body_signatories": "утверждающее лицо",
    "addresses": "адрес",
    "control_objects": "объект контроля",
    "areas": "управа",
    "area_addresses": "адреса управы",
    "area_inspectors": "инспекторы управы",
    "users": "пользователь",
    "user_sessions": "сессия",
}


def title(mapping: dict[str, str], code: str | None) -> str:
    if not code:
        return "—"
    return mapping.get(code, code)


def field_changes(before: dict[str, Any], after: dict[str, Any]) -> dict:
    """Что именно изменилось: только отличающиеся поля."""

    changes: dict[str, dict[str, Any]] = {}
    for field, old_value in before.items():
        new_value = after.get(field)
        if old_value != new_value:
            changes[field] = {
                "было": _short(old_value),
                "стало": _short(new_value),
            }
    return changes


def _short(value: Any, limit: int = 200) -> Any:
    # Даты приводим к строке: словарь изменений хранится в JSONB.
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None:
        return None
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def record(
    db: Session,
    *,
    actor: User | None,
    entity_table: str,
    action: str,
    entity_id: int | None = None,
    comment: str | None = None,
    changes: dict | None = None,
) -> AuditLog:
    """Добавляет запись в журнал. Фиксирует вызывающий код."""

    entry = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        entity_table=entity_table,
        entity_id=entity_id,
        action=action,
        comment=comment,
        changes=changes or None,
    )
    db.add(entry)
    return entry


def case_snapshot(case) -> dict[str, Any]:
    """Поля заявки, которые важно отслеживать в журнале."""

    return {
        "номер мероприятия": case.erp_number,
        "внутренний номер": case.case_number,
        "вид контроля": case.control_kind_id,
        "форма мероприятия": case.control_form_id,
        "орган контроля": case.control_body_id,
        "контролируемое лицо": case.controlled_organization_id,
        "подразделение": case.controlled_unit_id,
        "ответственный": case.responsible_organization_id,
        "объект контроля": case.control_object_id,
        "цель": case.purpose,
        "предмет": case.subject,
        "статус": case.status_id,
        "номер задания": case.assignment_number,
        "дата задания": _short(case.assignment_date),
        "фактическое начало": _short(case.actual_start_at),
        "фактическое окончание": _short(case.actual_end_at),
        "акт составлен": _short(case.act_composed_at),
    }
