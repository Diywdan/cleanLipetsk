"""Проблема на КП от жителей (datagateway.waste_site_problem) → дело CRM.

Источник сегодня один — Домовой ГЖИ: разбирает домовые чаты в MAX и шлёт проблему в DG,
DG приводит её к канонической форме и доставляет сюда тем же конвертом, что и события бота ДРТ.

Одна проблема источника — одно дело (ключ «<источник>:<problem_id>»): первая ревизия заводит
его, следующие дописывают новые сообщения и фото. Статус дела ведёт инспектор: «решено»
от жителей уходит в хронику, а дело не закрывает.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import kp
from app.db import utc_now
from app.models import Case, CaseHistory, Executor, IncomingEvent, ViolationType

# Источник проблемы → источник дела во фронте (IncidentSource) и подпись в хронике
SOURCES = {"domovoy": ("HOUSE_CHATS", "Домовой (ГЖИ)")}

# Тема ЕДС → тип нарушения CRM (код из справочника бота). Известна по примерам ГЖИ от 15.10.2026.
EDS_THEME_TYPES = {"14:434134994": "ekoprom.waste_removal"}

# Сообщений жителей в хронику за одну ревизию; остальные остаются в событии DG
MESSAGES_PER_REVISION = 30


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _org_key(name: str) -> str:
    """«АО "ЭкоПром-Липецк"» и «АО «ЭКОПРОМ-ЛИПЕЦК»» — одна организация."""
    text = re.sub(r"[«»\"'“”„]", " ", name.lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", text).strip()


def _short_address(address: str | None) -> str:
    """«398902, Россия, Липецкая обл, г. Липецк, ул. Ангарская, д. 27» → «г. Липецк, ул. Ангарская, д. 27»."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    parts = [p for p in parts if not p.isdigit() and p != "Россия" and "обл" not in p]
    return ", ".join(parts) or "адрес дома не указан"


def _violation_type(db: Session, theme: dict[str, Any]) -> tuple[ViolationType | None, str | None]:
    code = EDS_THEME_TYPES.get(theme.get("eds_code") or "")
    vtype = db.scalars(select(ViolationType).where(ViolationType.code == code)).first() if code else None
    if vtype is None or not vtype.is_active:
        title = theme.get("name") or theme.get("short_name") or theme.get("eds_code") or "без темы"
        return None, f"тема ЕДС «{title}» не сопоставлена с типом нарушения"
    return vtype, None


def _executor(db: Session, problem: dict[str, Any], vtype: ViolationType | None) -> tuple[Executor | None, str | None]:
    """Исполнитель по подсказке источника (название организации), без подсказки — единственный владелец типа."""
    active = list(db.scalars(select(Executor).where(Executor.is_active.is_(True)).order_by(Executor.executor_id)))
    organizations = ((problem.get("responsible_hint") or {}).get("organizations")) or []
    if organizations:
        index: dict[str, Executor] = {}
        for x in active:
            for name in (x.name, x.full_name):
                if name:
                    index.setdefault(_org_key(name), x)
        for org in organizations:
            if (found := index.get(_org_key(org["name"]))) is not None:
                return found, None
        names = ", ".join(org["name"] for org in organizations)
        return None, f"исполнитель из подсказки источника ({names}) не найден в справочнике"
    owners = [x for x in active if vtype is not None and vtype in x.violation_types]
    if len(owners) == 1:
        return owners[0], None
    return None, "исполнитель не определён"


def _link_kp(db: Session, case: Case, site: dict[str, Any] | None) -> None:
    """Площадка — по GUID ФГИС УТКО из источника; не нашлась — ближайшая к точке, как у дел с обхода."""
    if case.kp_method == "manual":
        return
    utko_id = (site or {}).get("utko_id")
    card = kp.find(db, utko_id, include_deleted=False) if utko_id else None
    if card is not None:
        case.kp_id, case.kp_score, case.kp_method = card.kp_id, 1.0, kp.UTKO_LINK
        return
    if case.kp_method == kp.UTKO_LINK:
        case.kp_method = None  # GUID сменился или карточка удалена — ищем заново по точке
    kp.link_case(db, case)


def _messages(event: dict[str, Any], seen: set[str]) -> list[CaseHistory]:
    """Новые сообщения жителей с текстом — в хронику; сообщения только с фото видны в фото дела."""
    found: list[tuple[datetime, CaseHistory]] = []
    for house in event["houses"]:
        where = _short_address(house.get("address"))
        for message in house["messages"]:
            if message["message_id"] in seen:
                continue
            seen.add(message["message_id"])
            text = (message.get("text") or "").strip()
            if not text:
                continue
            at = _parse(message.get("sent_at")) or utc_now()
            found.append((at, CaseHistory(
                action="RESIDENT_MESSAGE", at=at, actor_type="SYSTEM", actor_name=message.get("author"),
                title="Сообщение в чате дома", description=f"{where}: «{text}»",
            )))
    found.sort(key=lambda item: item[0])
    entries = [entry for _, entry in found[:MESSAGES_PER_REVISION]]
    if len(found) > MESSAGES_PER_REVISION:
        entries.append(CaseHistory(
            action="RESIDENT_MESSAGE", at=found[MESSAGES_PER_REVISION][0], actor_type="SYSTEM",
            title="Ещё сообщения в чатах", description=f"И ещё {len(found) - MESSAGES_PER_REVISION} — в событии DG.",
        ))
    return entries


def _counts(problem: dict[str, Any]) -> str:
    parts = [f"{label}: {problem[key]}" for key, label in
             (("houses_count", "домов"), ("messages_count", "сообщений"), ("residents_count", "жителей"))
             if problem.get(key) is not None]
    return (", ".join(parts).capitalize() + ".") if parts else ""


def _external(event: dict[str, Any], seen: set[str]) -> dict[str, Any]:
    problem = event["problem"]
    return {
        "source": event["source"],
        "waste_site": event.get("waste_site"),
        "theme": problem["theme"],
        "status": problem["status"],
        "resolved_at": event["timestamps"].get("resolved_at"),
        "counts": {k: problem.get(k) for k in ("houses_count", "messages_count", "residents_count", "media_count")},
        "responsible_hint": problem.get("responsible_hint"),
        "houses": [{"fias": h.get("fias"), "address": h.get("address"), "distance_to_site_m": h.get("distance_to_site_m")}
                   for h in event["houses"]],
        "message_ids": sorted(seen),
    }


def _create(db: Session, row: IncomingEvent, event: dict[str, Any], key: str) -> Case:
    source, problem = event["source"], event["problem"]
    front_source, title = SOURCES.get(source["type"], ("HOUSE_CHATS", source["type"]))
    vtype, type_note = _violation_type(db, problem["theme"])
    executor, executor_note = _executor(db, problem, vtype)
    errors = [note for note in (type_note, executor_note) if note]
    if executor is not None and vtype is not None and vtype not in executor.violation_types:
        errors.append("исполнитель не отвечает за этот тип нарушения")
    coords = event["location"]["coordinates"]
    reported_at = _parse(event["timestamps"].get("first_reported_at"))
    seen: set[str] = set()
    case = Case(
        event_id=row.event_id, external_key=key, external_revision=source["revision"],
        executor_id=executor.executor_id if executor else None,
        type_violation_id=vtype.type_violation_id if vtype else None,
        latitude=coords["latitude"], longitude=coords["longitude"], address=event["location"].get("address"),
        comment=problem.get("summary"), media=event.get("media") or [], reported_at=reported_at,
        status="NEW", review_reason="; ".join(errors) or None, source=front_source,
    )
    theme = problem["theme"].get("short_name") or problem["theme"].get("name") or "тема не указана"
    case.history.append(CaseHistory(
        action="CREATED", at=reported_at or utc_now(), actor_type="AI", actor_name=title,
        title="Проблема из домовых чатов",
        description=" ".join(p for p in (f"{theme}: {(problem.get('summary') or 'без описания').rstrip('.')}.",
                                         _counts(problem)) if p),
    ))
    case.history.extend(_messages(event, seen))
    if errors:
        case.history.append(CaseHistory(
            action="REVIEW", at=utc_now(), actor_type="SYSTEM", title="Не сходится со справочниками",
            description="; ".join(errors) + ". Выберите при подтверждении.",
        ))
    case.external = _external(event, seen)
    _link_kp(db, case, event.get("waste_site"))
    db.add(case)
    return case


def _update(db: Session, case: Case, event: dict[str, Any]) -> None:
    source, problem = event["source"], event["problem"]
    previous = case.external or {}
    seen = set(previous.get("message_ids") or [])
    # Keep the source's event order in the case timeline: a revision may arrive
    # later, while its new resident messages have their own earlier send times.
    now = _parse(event["timestamps"].get("updated_at") or event["timestamps"].get("received_at")) or utc_now()
    case.history.append(CaseHistory(
        action="SOURCE_UPDATE", at=now, actor_type="AI", actor_name=SOURCES.get(source["type"], ("", source["type"]))[1],
        title="Обновление из домовых чатов",
        description=" ".join(p for p in (f"Ревизия {source['revision']}.", _counts(problem)) if p),
    ))
    case.history.extend(_messages(event, seen))
    known = {item.get("id") for item in case.media or []}
    fresh = [item for item in event.get("media") or [] if item.get("id") not in known]
    if fresh:
        case.media = [*(case.media or []), *fresh]  # новый список — иначе изменение JSON не попадёт в базу
    if problem.get("summary"):
        case.comment = problem["summary"]
    resolved_at = event["timestamps"].get("resolved_at")
    if resolved_at and not previous.get("resolved_at"):
        case.history.append(CaseHistory(
            action="SOURCE_RESOLVED", at=_parse(resolved_at) or now, actor_type="SYSTEM",
            title="Жители сообщают: проблема решена", description="Статус дела не меняется — решает инспектор.",
        ))
    case.external_revision = source["revision"]
    case.external = _external(event, seen)
    _link_kp(db, case, event.get("waste_site"))


def case_key(source: dict[str, Any]) -> str:
    """Ключ дела по проблеме источника: все её ревизии ведут в одно дело."""
    return f"{source['type']}:{source['problem_id']}"


def accept(db: Session, row: IncomingEvent) -> tuple[Case | None, str, str | None]:
    """Завести или обновить дело по проблеме: (дело или None, статус входящего, пометка)."""
    event = row.canonical
    source = event["source"]
    key = case_key(source)
    case = db.scalars(select(Case).where(Case.external_key == key).with_for_update()).first()
    if case is None:
        case = _create(db, row, event, key)
        return case, "NEEDS_REVIEW" if case.review_reason else "PROCESSED", case.review_reason
    if source["revision"] <= (case.external_revision or 0):  # пришла позже более новой — дело не трогаем
        return None, "PROCESSED", f"ревизия {source['revision']} уже учтена в деле {case.id}"
    _update(db, case, event)
    return case, "PROCESSED", None
