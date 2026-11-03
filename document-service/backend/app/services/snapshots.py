"""Снимки данных: неизменяемая основа для повторной печати документов.

Пакет документов нельзя пересобирать «из текущих справочников»: если у
организации сменились реквизиты или подписант, уже выданный документ
обязан остаться прежним. Поэтому значения подстановки собираются один раз,
сохраняются как jsonb и хэшируются вместе с версией шаблона.
"""

import hashlib
import json
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdministrativeCase,
    ControlAction,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    ControlCaseParty,
    DataSnapshot,
    Decision,
    NpaArticle,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationSignatory,
    Prescription,
    Violation,
)
from app.models.enums import (
    CasePartyKind,
    ContactKind,
    FileKind,
    InspectionKind,
    InspectionResult,
    PhotoKind,
    SnapshotEntityKind,
)

from app.core.config import settings
from app.services import ru, violation_text


SCHEMA_VERSION = "1.0"


# Названия контрольных действий так, как они печатаются в акте и задании.
ACTION_TYPE_NAMES = {
    "inspection": "осмотр",
    "instrumental_survey": "инструментальное обследование",
    "sampling": "отбор проб (образцов)",
    "testing": "испытание",
    "expertise": "экспертиза",
    "photo_fixation": "фотофиксация",
    "video_recording": "видеозапись",
}


def _parse_iso_date(value) -> date | None:
    """Дата из строки «2026-09-22» — в словаре предписания она строкой."""

    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        # В документы и снимок момент попадает уже в местном времени.
        return ru.to_display(value).isoformat()
    return str(value)


def _address_line(address) -> str | None:
    return address.full_address if address is not None else None


def _current_requisites(
    db: Session, organization_id: int, unit_id: int | None
) -> OrganizationRequisite | None:
    stmt = (
        select(OrganizationRequisite)
        .where(
            OrganizationRequisite.organization_id == organization_id,
            OrganizationRequisite.valid_to.is_(None),
        )
        .order_by(OrganizationRequisite.valid_from.desc())
    )
    if unit_id is None:
        stmt = stmt.where(OrganizationRequisite.unit_id.is_(None))
    else:
        stmt = stmt.where(OrganizationRequisite.unit_id == unit_id)
    found = db.scalars(stmt).first()
    if found is not None:
        return found
    # У дела из CRM часто нет филиала, а в справочнике заполнены только
    # реквизиты подразделения — или наоборот. Без запасного варианта
    # инспектор видит реквизиты на карточке, а пакет всё равно не собирается.
    return db.scalars(
        select(OrganizationRequisite)
        .where(
            OrganizationRequisite.organization_id == organization_id,
            OrganizationRequisite.valid_to.is_(None),
        )
        .order_by(OrganizationRequisite.valid_from.desc())
    ).first()


def _current_signatory(
    db: Session, organization_id: int, unit_id: int | None
) -> OrganizationSignatory | None:
    stmt = (
        select(OrganizationSignatory)
        .where(
            OrganizationSignatory.organization_id == organization_id,
            OrganizationSignatory.valid_to.is_(None),
        )
        .order_by(OrganizationSignatory.valid_from.desc())
    )
    if unit_id is None:
        stmt = stmt.where(OrganizationSignatory.unit_id.is_(None))
    else:
        stmt = stmt.where(OrganizationSignatory.unit_id == unit_id)
    return db.scalars(stmt).first()


def _contacts(db: Session, organization_id: int, unit_id: int | None) -> list[str]:
    stmt = select(OrganizationContact).where(
        OrganizationContact.organization_id == organization_id,
        OrganizationContact.kind == ContactKind.EMAIL,
        OrganizationContact.is_active.is_(True),
    )
    if unit_id is None:
        stmt = stmt.where(OrganizationContact.unit_id.is_(None))
    else:
        stmt = stmt.where(OrganizationContact.unit_id == unit_id)
    return [contact.value for contact in db.scalars(stmt)]


def _person_block(
    db: Session,
    organization,
    unit,
    requisites: OrganizationRequisite | None = None,
    signatory: OrganizationSignatory | None = None,
) -> dict | None:
    """Лицо для подстановки в документ: организация с филиалом и реквизитами.

    Применяется и к контролируемому лицу, и к ответственному за устранение:
    это может быть одна и та же организация, а может быть разной.
    """

    if organization is None:
        return None

    unit_id = unit.id if unit is not None else None
    if requisites is None:
        requisites = _current_requisites(db, organization.id, unit_id)
    if signatory is None:
        signatory = _current_signatory(db, organization.id, unit_id)

    # Реквизиты и контакты головной организации: направление уходит и ей тоже.
    organization_requisites = _current_requisites(db, organization.id, None)
    unit_emails = _contacts(db, organization.id, unit_id)
    organization_emails = _contacts(db, organization.id, None)

    representation = organization.short_name
    if unit is not None:
        # «в лице филиала …» — подразделение в родительном падеже.
        representation = (
            f"{organization.short_name} в лице "
            f"{ru.unit_in_genitive(unit.name, unit.kind.value)}"
        )

    return {
        "representation": representation,
        # Есть ли у лица обособленное подразделение. Блок филиала в бланках
        # напечатан отдельным получателем, и при отсутствии филиала его надо
        # не печатать целиком: «Законному представителю» без получателя —
        # пустое место в официальном документе. Проверять по unit_in_genitive
        # нельзя: он бывает пуст и при заполненном филиале.
        "has_unit": unit is not None,
        "unit_in_genitive": (
            ru.unit_in_genitive(unit.name, unit.kind.value) if unit is not None else None
        ),
        "unit_email": unit_emails[0] if unit_emails else None,
        "organization_email": organization_emails[0] if organization_emails else None,
        "organization_legal_address": (
            _address_line(organization_requisites.legal_address)
            if organization_requisites is not None
            else None
        ),
        "organization": {
            "short_name": organization.short_name,
            "full_name": organization.full_name,
            "inn": organization.inn,
            "ogrn": organization.ogrn,
            "kpp": organization.kpp,
            "kind": organization.kind.value,
        },
        "unit": (
            {
                "name": unit.name,
                "kind": unit.kind.value,
                "address": _address_line(unit.address),
            }
            if unit is not None
            else None
        ),
        # Always provide the mapping: stage-2 templates read nested INN and
        # address fields. Readiness blocks generation when requisites are
        # absent/incomplete, while this shape avoids an opaque None-attribute
        # rendering exception if a caller bypasses readiness checks.
        "requisites": {
            "inn": (requisites.inn if requisites else None) or organization.inn or "",
            "kpp": (requisites.kpp if requisites else None) or organization.kpp or "",
            "ogrn": (requisites.ogrn if requisites else None) or organization.ogrn or "",
            "legal_address": (
                _address_line(requisites.legal_address)
                if requisites and requisites.legal_address
                else ""
            ),
            "postal_address": (
                _address_line(requisites.postal_address)
                if requisites and requisites.postal_address
                else ""
            ),
            "email": requisites.email if requisites and requisites.email else "",
            "phone": requisites.phone if requisites and requisites.phone else "",
        },
        "signatory": (
            {
                "full_name": signatory.full_name,
                "short_name": ru.short_name(signatory.full_name),
                "position": signatory.position,
            }
            if signatory is not None
            else None
        ),
        "contacts": _contacts(db, organization.id, unit_id),
    }


# Пустые части даты: бланк печатает пустое место вместо падения, когда дата
# документа ещё не заполнена (например, протокол собран, а номер и дата
# появятся позже).
_EMPTY_PARTS: dict = {
    "day": "",
    "month_words": "",
    "year": "",
    "hour": "",
    "minute": "",
    "second": "",
    "date_short": "",
    "date_words": "",
    "time_short": "",
    "time_official": "",
}


def _datetime_parts(value: datetime | None) -> dict | None:
    """Момент времени, разложенный по ячейкам бланка.

    В акте день, месяц, год, часы и минуты стоят в отдельных ячейках таблицы,
    поэтому подстановка идёт по частям, а не готовой строкой.
    """

    if value is None:
        return None
    local = ru.to_display(value)
    if isinstance(local, datetime):
        hour, minute, second = local.hour, local.minute, local.second
    else:
        # Дата без времени: в бланке часы и минуты остаются нулями.
        hour = minute = second = 0
    return {
        "day": f"{local.day:02d}",
        "month_words": ru.date_words(local, with_year=False).split()[-1],
        "year": str(local.year),
        "hour": f"{hour:02d}",
        "minute": f"{minute:02d}",
        "second": f"{second:02d}",
        "date_short": ru.date_short(local),
        "date_words": ru.date_words(local),
        "time_short": ru.time_short(local) if isinstance(local, datetime) else "",
        "time_official": (
            ru.time_official(local) if isinstance(local, datetime) else ""
        ),
    }


def _reference_genitive(article: NpaArticle | None) -> str | None:
    """«пункта 5.2 части 5 статьи 5» — форма для оборота «в нарушении …».

    Склоняются только слова «пункт», «часть», «статья» — они всегда стоят
    в родительном падеже, поэтому форма собирается из частей нормы, а не
    хранится отдельной строкой.
    """

    if article is None:
        return None
    parts = []
    if article.point_number:
        parts.append(f"пункта {article.point_number}")
    if article.part_number:
        parts.append(f"части {article.part_number}")
    if article.article_number:
        parts.append(f"статьи {article.article_number}")
    return " ".join(parts) or article.reference_template


def _basis_phrase(base: ControlCaseBase) -> str | None:
    """Готовая формулировка основания для бланка задания.

    Инструкция по пакету перечисляет ровно эти варианты: проверка фактов из
    материала МУ, из обращения жителя, требований ранее выданного
    предписания, требования прокуратуры.
    """

    kind = base.kind.value
    number = base.document_number
    date_words = ru.date_words(base.document_date)
    tail = " ".join(part for part in (f"№ {number}" if number else "", f"от {date_words}" if date_words else "") if part)

    if kind == "mu_material":
        subject = base.description or "материале"
        phrase = f"проверка фактов, изложенных в материале {subject}"
    elif kind == "appeal":
        phrase = "проверка фактов, изложенных в обращении жителя"
    elif kind == "prescription":
        phrase = "проверка требований, указанных в ранее выданном предписании"
    elif kind == "prosecutor_request":
        phrase = "проверка фактов, изложенных в требовании прокуратуры"
    elif kind == "plan":
        return "проведение планового контрольного мероприятия"
    else:
        return base.description

    return f"{phrase} {tail}".strip() if tail else phrase


def _administrative_block(
    row,
    controlled_person: dict,
    prescription: dict | None,
    body_name: str | None,
    measure_date_short: str | None,
    prior_basis: str | None = None,
    object_address: str | None = None,
    measure_date: datetime | None = None,
    default_place: str | None = None,
    area_office: str | None = None,
) -> dict | None:
    """Данные административного производства для бланков уведомления и протокола.

    Часть строк собирается здесь: в бланках это связный юридический текст
    с несколькими подстановками, а не набор отдельных полей.
    """

    if row is None:
        return None

    article = row.offense_article or "частью 1 статьи 19.5"

    # Дата протокола — дата повторного осмотра, на котором выявлено
    # неисполнение: протокол составляют по его итогам. Место составления —
    # адрес управы (или органа контроля), он есть в справочнике.
    protocol_date = row.protocol_date or measure_date
    protocol_place = row.protocol_place or default_place
    # Ранее выданное предписание: если оператор его не заполнил, берём
    # предписание самой заявки — протокол по ст. 19.5 описывает именно его
    # неисполнение. Тогда в протоколе стоят даты наших документов, а не
    # вписанные руками.
    prior_prescription = prescription or {}
    prior_number = (
        row.prior_prescription_number or prior_prescription.get("number")
    )
    prior_date = row.prior_prescription_date or _parse_iso_date(
        prior_prescription.get("issued_on")
    )
    prior_due = row.prior_prescription_due or _parse_iso_date(
        prior_prescription.get("due_on")
    )
    requisites = controlled_person.get("requisites") or {}
    organization = controlled_person.get("organization") or {}
    unit = controlled_person.get("unit") or {}

    inn = requisites.get("inn") or organization.get("inn")
    ogrn = requisites.get("ogrn") or organization.get("ogrn")

    addresses: list[str] = []
    for value in (
        requisites.get("legal_address"),
        controlled_person.get("organization_legal_address"),
        unit.get("address") if unit else None,
    ):
        if value and value not in addresses:
            addresses.append(value)

    entity_bits = [
        f"в отношении юридического лица {controlled_person.get('representation')}"
    ]
    requisites_bits = []
    if inn:
        requisites_bits.append(f"ИНН {inn}")
    if ogrn:
        requisites_bits.append(f"ОГРН {ogrn}")
    if requisites_bits:
        entity_bits.append("(" + ", ".join(requisites_bits) + ")")
    if addresses:
        entity_bits.append("зарегистрированное по адресу: " + "; ".join(addresses))

    # Место явки — адрес из справочника: если оператор его не выбрал, берём
    # место составления протокола (адрес управы). Вписывать адрес руками не
    # нужно, он уже есть в заявке.
    appearance_place = row.appearance_place or protocol_place

    appearance_date_short = ru.date_short(row.appearance_date)
    notice_date_short = ru.date_short(row.notice_date)
    appearance_note = row.appearance_note
    if not appearance_note:
        place = appearance_place or ""
        office = f", каб. {row.appearance_office}" if row.appearance_office else ""
        department = f"{body_name} " if body_name else ""
        appearance_note = (
            f"Явка законного представителя "
            f"{controlled_person.get('representation')} или уполномоченного "
            f"представителя с надлежащим образом оформленной доверенностью "
            f"{appearance_date_short or ''} в {row.appearance_time or ''} "
            f"в {department}({place}{office}) для участия в мероприятии по "
            f"составлению протокола об административном правонарушении не "
            f"обеспечена. Уведомлено надлежащим образом — уведомлением от "
            f"{notice_date_short or ''}."
        )

    # Приложение не заполняется вручную: это всегда акт и протокол осмотра
    # нашего мероприятия, и дата у них одна. Значение собирается здесь, чтобы
    # в протоколе не появилось чужой или устаревшей даты.
    appendix_note = "акт выездного обследования и протокол осмотра" + (
        f" от {measure_date_short}" if measure_date_short else ""
    )

    return {
        # Номер присваивают при составлении протокола: пока его нет, в бланке
        # остаётся пустое место, а не слово «None».
        "protocol_number": row.protocol_number or "",
        "protocol_date": _iso(protocol_date),
        "protocol_date_short": ru.date_short(protocol_date),
        "protocol_date_words": ru.date_words(row.protocol_date),
        "protocol_date_parts": _datetime_parts(protocol_date) or _EMPTY_PARTS,
        "protocol_place": protocol_place,
        "appearance_date": _iso(row.appearance_date),
        "appearance_date_short": appearance_date_short,
        "appearance_date_parts": _datetime_parts(row.appearance_date),
        "appearance_time": row.appearance_time,
        "appearance_place": appearance_place,
        # Кабинет — из карточки управы: он один для всех заявок её территории.
        "appearance_office": area_office,
        "notice_number": row.notice_number,
        "notice_date": _iso(row.notice_date),
        "notice_date_short": notice_date_short,
        "notice_date_words": ru.date_words(row.notice_date),
        "offense_article": article,
        "offense_date": _iso(row.offense_date),
        "offense_date_short": ru.date_short(row.offense_date),
        "offense_date_words": ru.date_words(row.offense_date),
        "offense_time": row.offense_time,
        # «07.08.2026 в 00 ч. 01 мин.» — одной строкой: в протоколе дата и
        # время правонарушения печатаются в одной строке после подписи.
        "offense_when": " ".join(
            part
            for part in (
                ru.date_short(row.offense_date),
                f"в {row.offense_time}" if row.offense_time else None,
            )
            if part
        ),
        # Место правонарушения по ст. 19.5 — адрес объекта, где не выполнили
        # работы. Если оператор его не заполнил, печатается адрес объекта
        # контроля: он и так есть в заявке, вписывать второй раз не нужно.
        "offense_place": row.offense_place or object_address,
        # Прежний ручной текст: остался у заявок, заполненных до справочников.
        # В бланках он больше не печатается — событие собирается из дат.
        "offense_description": row.offense_description,
        # Ранее выданное предписание: протокол по ст. 19.5 описывает именно
        # его неисполнение. Даты и номер печатаются в трёх видах, как и
        # остальные даты бланков.
        "prior_prescription_number": prior_number,
        "prior_prescription_date": _iso(prior_date),
        "prior_prescription_date_short": ru.date_short(prior_date),
        "prior_prescription_date_words": ru.date_words(prior_date),
        "prior_prescription_date_parts": _datetime_parts(prior_date),
        "prior_prescription_due": _iso(prior_due),
        "prior_prescription_due_short": ru.date_short(prior_due),
        "prior_prescription_due_words": ru.date_words(prior_due),
        "prior_prescription_basis": (
            row.prior_prescription_basis
            or prior_basis
            or "требованиями ранее выданного предписания"
        ),
        # Событие правонарушения собирается из дат наших документов: когда
        # проводилось прежнее мероприятие, когда выявлены нарушения, какой
        # срок был дан и что предписание не исполнено.
        "circumstances": violation_text.administrative_circumstances(
            ru.date_short(prior_date), ru.date_short(prior_due), measure_date_short
        ),
        # Что попадёт в строку «Приложение:»: поле формы или собранный текст.
        "appendix_effective": appendix_note,
        "representative_info": row.representative_info or "—",
        "entity_line": " ".join(entity_bits),
        "appearance_note": appearance_note,
        "appendix_note": appendix_note,
    }


def _area_of_case(db: Session, case: ControlCase):
    """Управа заявки: определяется её адресом."""

    from app.services import areas as areas_service

    for area in areas_service.case_areas(db, case):
        return area
    return None


def _appearance_office(db: Session, case: ControlCase) -> str | None:
    """Номер кабинета управы — печатается в уведомлении о явке."""

    area = _area_of_case(db, case)
    if area is not None and area.office:
        return area.office.strip()
    return None


def _protocol_place(db: Session, case: ControlCase) -> str | None:
    """Адрес управы для места составления протокола.

    Управу заявки определяет её адрес; если управы нет — берётся адрес органа
    контроля. Так в бланке оказывается адрес из справочника, а не набранный
    руками.
    """

    from app.services import areas as areas_service

    for area in areas_service.case_areas(db, case):
        if area.address is not None and area.address.full_address:
            return area.address.full_address
    if case.control_body is not None and case.control_body.address is not None:
        return case.control_body.address.full_address
    return None


def _notice_block(
    case,
    body: dict | None,
    controlled_person: dict,
    control_object: dict | None,
    prescription: dict | None,
    administrative: dict | None,
) -> dict | None:
    """Готовые строки уведомления о явке."""

    if administrative is None:
        return None

    department = (body or {}).get("name") or "орган контроля"
    object_address = (control_object or {}).get("address")
    prescription_note = ""
    if prescription:
        number = prescription.get("number")
        issued = prescription.get("issued_on_short")
        if issued or number:
            prescription_note = f"({issued or ''} № {number or ''})".replace("  ", " ")

    measures_text = (
        f"{department} {ru.date_short(case.actual_start_at) or ''} проведено "
        f"контрольное (надзорное) мероприятие "
        f"({case.control_form.name.lower() if case.control_form and case.control_form.name else ''}) "
        f"с целью проверки исполнения ранее выданного предписания "
        f"{prescription_note} по адресу: {object_address or ''}."
    ).replace("  ", " ")

    parts = administrative.get("protocol_date_parts") or {}
    appearance_parts = administrative.get("appearance_date_parts")
    hour, minute = "", ""
    if administrative.get("appearance_time"):
        bits = administrative["appearance_time"].replace(".", ":").split(":")
        hour = bits[0].zfill(2) if bits else ""
        minute = bits[1].zfill(2) if len(bits) > 1 else ""
    elif appearance_parts:
        hour, minute = appearance_parts.get("hour", ""), appearance_parts.get("minute", "")

    appearance_text = (
        f"С целью возбуждения дела об административном правонарушении, "
        f"предусмотренного {administrative.get('offense_article')}, полного и "
        f"всестороннего установления обстоятельств по данному вопросу требую "
        f"от Вас прибыть лично с паспортом, либо обеспечить явку законного "
        f"представителя (с надлежащим образом оформленной доверенностью и "
        f"паспортом) для составления протокола об административном "
        f"правонарушении в административное здание {department} по адресу: "
        f"{administrative.get('appearance_place') or ''}"
        f"{', каб. № ' + administrative.get('appearance_office') if administrative.get('appearance_office') else ''} "
        f"«{appearance_parts.get('day') if appearance_parts else ''}» "
        f"{appearance_parts.get('month_words') if appearance_parts else ''} "
        f"{appearance_parts.get('year') if appearance_parts else ''} года "
        f"в «{hour}» час. «{minute}» мин., и предоставить надлежащим образом "
        f"заверенные копии следующих документов:"
    ).replace("  ", " ")

    # Адреса для строки «АДРЕС»: юридический адрес, адрес подразделения и
    # контакты. Повторы убираем — один и тот же адрес может прийти и из
    # реквизитов, и из карточки организации.
    address_values: list[str] = []
    for value in (
        (controlled_person.get("requisites") or {}).get("legal_address"),
        controlled_person.get("organization_legal_address"),
        (controlled_person.get("unit") or {}).get("address"),
        *(controlled_person.get("contacts") or []),
    ):
        if value and value not in address_values:
            address_values.append(value)
    addresses_line = "АДРЕС: " + "; ".join(address_values) if address_values else "АДРЕС:"

    recipient_line = (
        f"КОМУ: Законному представителю {controlled_person.get('representation')}"
    )
    inn = (controlled_person.get("requisites") or {}).get("inn") or (
        controlled_person.get("organization") or {}
    ).get("inn")
    if inn:
        recipient_line += f", ИНН {inn}"

    return {
        "date_words": administrative.get("notice_date_words"),
        "place": case_context_place(),
        "recipient_line": recipient_line,
        "addresses_line": addresses_line,
        "measures_text": measures_text,
        "appearance_text": appearance_text,
    }


def case_context_place() -> str:
    """Город, который печатается в бланках («г. Липецк»)."""

    return f"г. {settings.document_place}"


def _qr_block(case: ControlCase) -> dict | None:
    """QR-код из прокуратуры для снимка данных.

    Сам код система не создаёт: портал прокуратуры выдаёт картинку вместе с
    номером мероприятия. В снимок попадают путь и хэш файла — по ним документ
    собирается заново, даже если код потом заменят другим.
    """

    file = case.qr_file
    if file is None:
        return None
    return {
        "file_id": file.id,
        "storage_path": file.storage_path,
        "sha256": file.sha256,
        "original_name": file.original_name,
    }


def build_case_context(
    db: Session, case_id: int, inspection: ControlAction | None = None
) -> dict:
    """Собирает все значения, которые подставляются в документы пакета."""

    case = db.get(ControlCase, case_id)
    if case is None:
        raise ValueError(f"дело {case_id} не найдено")

    organization = case.controlled_organization
    unit = case.controlled_unit
    body = case.control_body
    control_object = case.control_object

    # Код города для телефонов: в направлении печатается «(4742) 38-77-75».
    phone_code = ""
    if body is not None and body.phone:
        match = re.search(r"\(\d+\)", body.phone)
        if match:
            phone_code = match.group(0)

    # Конкретные версии реквизитов и подписанта: если дело уже зафиксировало
    # их в control_case_parties, берём именно их, иначе — действующие сейчас.
    party = db.scalars(
        select(ControlCaseParty).where(
            ControlCaseParty.control_case_id == case.id,
            ControlCaseParty.party_kind == CasePartyKind.CONTROLLED,
        )
    ).first()

    if party is not None and party.requisite is not None:
        requisites = party.requisite
    elif organization is not None:
        requisites = _current_requisites(
            db, organization.id, unit.id if unit is not None else None
        )
    else:
        requisites = None

    if party is not None and party.signatory is not None:
        signatory = party.signatory
    elif organization is not None:
        signatory = _current_signatory(
            db, organization.id, unit.id if unit is not None else None
        )
    else:
        signatory = None

    inspectors = []
    for link in db.scalars(
        select(ControlCaseInspector).where(
            ControlCaseInspector.control_case_id == case.id
        )
    ):
        inspector = link.inspector
        if inspector is None:
            continue
        inspectors.append(
            {
                "id": inspector.id,
                "role": link.role.value,
                "full_name": inspector.full_name,
                "short_name": ru.short_name(inspector.full_name),
                "short_name_before": ru.short_name_before(inspector.full_name),
                "position": inspector.position,
                # В протоколе осмотра должность печатается с заглавной буквы.
                "position_capitalized": (
                    inspector.position[0].upper() + inspector.position[1:]
                    if inspector.position
                    else inspector.position
                ),
                # Творительный падеж для протокола осмотра; если оператор
                # его не заполнил — печатаем именительный, но это заметно
                # в документе, поэтому поля стоит заполнять.
                "full_name_instrumental": (
                    inspector.full_name_instrumental or inspector.full_name
                ),
                "position_instrumental": (
                    inspector.position_instrumental or inspector.position
                ),
                # То же в творительном падеже, но со строчной буквы: в
                # протоколе об административном правонарушении должность
                # идёт внутри предложения.
                "position_instrumental_lower": (
                    (
                        inspector.position_instrumental or inspector.position or ""
                    )[:1].lower()
                    + (
                        inspector.position_instrumental or inspector.position or ""
                    )[1:]
                ),
                "phone": inspector.phone,
                "phone_with_code": (
                    f"{phone_code} {inspector.phone}".strip()
                    if inspector.phone
                    else None
                ),
                "email": inspector.email,
                "certificate_number": inspector.certificate_number,
            }
        )

    approver = case.assignment_approved_by
    # Адреса электронной почты для отметки о направлении: и подразделение,
    # и головная организация.
    delivery_emails: list[str] = []
    if organization is not None:
        for value in _contacts(
            db, organization.id, None
        ) + _contacts(db, organization.id, unit.id if unit is not None else None):
            if value not in delivery_emails:
                delivery_emails.append(value)
    bases = []
    basis_phrases = []
    for base in db.scalars(
        select(ControlCaseBase).where(ControlCaseBase.control_case_id == case.id)
    ):
        phrase = _basis_phrase(base)
        if phrase:
            basis_phrases.append(phrase)
        bases.append(
            {
                "kind": base.kind.value,
                "document_number": base.document_number,
                "document_date": _iso(base.document_date),
                "document_date_words": ru.date_words(base.document_date),
                "appeal_id": base.appeal_id,
                "prescription_id": base.prescription_id,
                "description": base.description,
                "phrase": phrase,
            }
        )

    actions = []
    # Отметка в протоколе осмотра: применялась ли видеозапись или фотофиксация.
    video_note = "не применялась"
    # Фотоматериал приложения к протоколу осмотра. Печатаются снимки того
    # осмотра, по которому собирается пакет: в повторном протоколе снимок
    # первичного осмотра был бы неуместен. Из двух файлов осмотра берётся
    # размеченная копия — исходный снимок нужен только для повторной разметки.
    protocol_photos: list[dict] = []
    # Действия дела целиком: из них шаблон акта берёт даты первого действия.
    case_actions = list(
        db.scalars(
            select(ControlAction)
            .where(ControlAction.control_case_id == case.id)
            .order_by(ControlAction.sequence_no)
        )
    )
    photo_actions = [inspection] if inspection is not None else case_actions
    for action in photo_actions:
        if action is None:
            continue
        for attachment in action.files:
            if attachment.file is None:
                continue
            if attachment.file.kind == FileKind.PHOTO:
                video_note = "фотофиксация"
            elif attachment.file.kind == FileKind.VIDEO:
                video_note = "видеозапись"
            if attachment.file.kind not in (FileKind.PHOTO, FileKind.VIDEO):
                continue
            if (
                attachment.file.kind == FileKind.PHOTO
                and attachment.photo_kind == PhotoKind.ORIGINAL
            ):
                continue
            captured = attachment.file.captured_at
            protocol_photos.append(
                {
                    "file_id": attachment.file.id,
                    "storage_path": attachment.file.storage_path,
                    "sha256": attachment.file.sha256,
                    "kind": attachment.file.kind.value,
                    "caption": "",
                    "captured_at": _iso(captured),
                    "captured_at_words": ru.date_words(captured),
                    "captured_at_short": ru.date_short(captured),
                    "captured_time": ru.time_short(captured),
                    "place": (
                        _address_line(attachment.file.address)
                        or _address_line(action.place_address)
                    ),
                    "sequence_no": attachment.sequence_no,
                    "action_sequence_no": action.sequence_no,
                }
            )
    for action in case_actions:
        actions.append(_action_block(action))

    violations = []
    violation_provisions_genitive: list[str] = []
    # Сырые ссылки на нормы: из них собирается квалификация в разных
    # падежах — родительном для «в нарушении», творительном для «в
    # соответствии с …».
    violation_references: list[str] = []
    violation_npa_titles: list[str] = []
    violation_npa_titles_genitive: list[str] = []
    for violation in db.scalars(
        select(Violation).where(Violation.control_case_id == case.id)
    ):
        provisions = []
        for provision in violation.provisions:
            article: NpaArticle = provision.npa_article
            titles = None
            if article is not None and article.npa is not None:
                titles = article.npa.title
                if titles not in violation_npa_titles:
                    violation_npa_titles.append(titles)
                title_genitive = article.npa.title_genitive or article.npa.title
                if title_genitive not in violation_npa_titles_genitive:
                    violation_npa_titles_genitive.append(title_genitive)
            if article is not None and article.reference_template:
                if article.reference_template not in violation_references:
                    violation_references.append(article.reference_template)
            genitive = _reference_genitive(article)
            if genitive and genitive not in violation_provisions_genitive:
                violation_provisions_genitive.append(genitive)
            provisions.append(
                {
                    "reference": article.reference_template if article else None,
                    "reference_genitive": genitive,
                    "article_number": article.article_number if article else None,
                    "part_number": article.part_number if article else None,
                    "point_number": article.point_number if article else None,
                    "npa_title": titles,
                    "npa_title_genitive": (
                        (article.npa.title_genitive or article.npa.title)
                        if article is not None and article.npa is not None
                        else None
                    ),
                    "npa_number": article.npa.number if article and article.npa else None,
                    "npa_adopted_on": _iso(article.npa.adopted_on)
                    if article and article.npa
                    else None,
                    "npa_adopted_by": article.npa.adopted_by
                    if article and article.npa
                    else None,
                    # «утверждённых решением …» — только у актов, которые
                    # утверждены решением органа власти.
                    "npa_adopted_by_genitive": article.npa.adopted_by_genitive
                    if article and article.npa
                    else None,
                }
            )
        violations.append(
            {
                "description": violation.description,
                "detected_at": _iso(violation.detected_at),
                "detected_at_words": ru.date_words(violation.detected_at),
                "address": _address_line(violation.address),
                "provisions": provisions,
                "is_eliminated": violation.is_eliminated,
                # Работы с объёмами: по ним собираются и описание нарушения, и
                # требование предписания. Хранятся у нарушения один раз.
                "works": [
                    {
                        "code": item.work.code if item.work else None,
                        "name": item.work.name if item.work else None,
                        "name_accusative": item.work.name_accusative if item.work else None,
                        "unit": item.work.unit if item.work else None,
                        "quantity": (
                            float(item.quantity) if item.quantity is not None else None
                        ),
                        "line": violation_text.work_line(item.work, item.quantity),
                        "line_accusative": violation_text.work_line(
                            item.work, item.quantity, accusative=True
                        ),
                    }
                    for item in violation.works
                ],
                "violation_type_name": (
                    violation.violation_type.name
                    if violation.violation_type is not None
                    else None
                ),
                "violation_type_accusative": (
                    violation.violation_type.name_accusative
                    if violation.violation_type is not None
                    else None
                ),
                "requirement_object": (
                    violation.violation_type.requirement_object
                    if violation.violation_type is not None
                    else None
                ),
                "default_action": (
                    violation.violation_type.default_action
                    if violation.violation_type is not None
                    else None
                ),
            }
        )
    # Описание нарушения собирается позже, когда известен объект контроля:
    # «На земельном участке … не восстановлено нарушенное благоустройство …,
    # а именно: асфальт – 4 кв.м., грунт – 20 кв.м., бордюр – 4 шт.».
    # Если работ нет — печатается прежний текст, введённый вручную.

    prescription = db.scalars(
        select(Prescription)
        .where(Prescription.control_case_id == case.id)
        .order_by(Prescription.issued_on.desc())
    ).first()
    prescription_data = None
    if prescription is not None:
        prescription_data = {
            "id": prescription.id,
            "number": prescription.number,
            "issued_on": _iso(prescription.issued_on),
            "issued_on_short": ru.date_short(prescription.issued_on),
            "issued_on_words": ru.date_words(prescription.issued_on),
            "due_on": _iso(prescription.due_on),
            "due_on_words": ru.date_words(prescription.due_on),
            "status": prescription.status.code if prescription.status else None,
            "parent_prescription_id": prescription.parent_prescription_id,
            # Ключ называется requirements, а не items: в шаблонах
            # prescription.items разрешился бы в метод словаря dict.items.
            "requirements": [
                {
                    "sequence_no": item.sequence_no,
                    # Что предписано сделать с работами нарушения: «восстановить».
                    "action_code": item.action_code,
                    "action_verb": violation_text.action_verb(item.action_code),
                    "requirement_text": item.requirement_text,
                    "work_name": item.work_name,
                    "quantity": float(item.quantity) if item.quantity is not None else None,
                    "unit": item.unit,
                    "due_on": _iso(item.due_on),
                    "due_on_short": ru.date_short(item.due_on),
                    "due_on_words": ru.date_words(item.due_on),
                }
                for item in prescription.items
            ],
        }

    decision = db.scalars(
        select(Decision)
        .where(Decision.control_case_id == case.id)
        .order_by(Decision.decision_date.desc())
    ).first()
    decision_data = None
    if decision is not None:
        decision_data = {
            "id": decision.id,
            "number": decision.number,
            "decision_date": _iso(decision.decision_date),
            "decision_date_short": ru.date_short(decision.decision_date),
            "decision_date_words": ru.date_words(decision.decision_date),
            "parts": _datetime_parts(decision.decision_date),
            "decision_kind": decision.decision_kind,
            "content": decision.content,
            # Также не items — см. пояснение выше про prescription.
            "points": [
                {
                    "sequence_no": item.sequence_no,
                    "kind": item.kind.value,
                    "description": item.description,
                }
                for item in decision.items
            ],
        }

    controlled_person = _person_block(db, organization, unit, requisites, signatory)
    # Данные административного производства заполняются вручную, поэтому
    # могут отсутствовать — тогда документы этого вида не собираются.
    administrative = db.scalars(
        select(AdministrativeCase).where(
            AdministrativeCase.control_case_id == case.id
        )
    ).first()

    body_context = (
        {
            "name": body.name,
            "full_name": body.full_name,
            "phone": body.phone,
            "email": body.email,
            "address": _address_line(body.address),
        }
        if body
        else None
    )
    object_context = (
        {
            "id": control_object.id,
            "type": control_object.object_type.name if control_object else None,
            "name": control_object.name,
            "name_genitive": control_object.name_genitive or control_object.name,
            "name_genitive_lower": (
                (control_object.name_genitive or control_object.name)[0].lower()
                + (control_object.name_genitive or control_object.name)[1:]
            ),
            # Предложный падеж для описания нарушения: «на земельном участке,
            # расположенном по адресу …». Если оператор его не заполнил —
            # берём родительный: текст будет неточным, но документ соберётся.
            "name_prepositional": (
                control_object.name_prepositional
                or control_object.name_genitive
                or control_object.name
            ),
            "address": _address_line(control_object.address),
            "cadastral_number": control_object.cadastral_number,
            "attributes": control_object.attributes,
            "works_note": (
                ", на котором проводились земляные работы по "
                + str((control_object.attributes or {}).get("работы"))
                if (control_object.attributes or {}).get("работы")
                else ""
            ),
        }
        if control_object
        else None
    )

    administrative_block = _administrative_block(
        administrative,
        controlled_person,
        prescription_data,
        body.name if body else None,
        ru.date_short(case.actual_start_at),
        # Норма, по которой выдано предписание: если оператор её не заполнил,
        # в протоколе напечатается квалификация нарушения.
        prior_basis=violation_text.provisions_instrumental(violation_references),
        # Адрес объекта контроля: он же место правонарушения, если оператор
        # своё место не указал.
        object_address=(object_context or {}).get("address"),
        # Дата повторного осмотра и адрес управы: из них собираются дата и
        # место составления протокола, если их не заполнили руками.
        measure_date=(
            inspection.started_at
            if inspection is not None
            else case.actual_start_at
        ),
        default_place=_protocol_place(db, case),
        # Кабинет управы: место явки и кабинет больше не заполняются в
        # административном производстве.
        area_office=_appearance_office(db, case),
    )
    # Снимки, сделанные до появления полей о прошлом предписании, их не
    # содержат. Документ по такому снимку должен собираться: шаблон получит
    # пустые значения и напечатает пустое место, а не упадёт с ошибкой.
    if administrative_block is not None:
        for key in (
            "prior_prescription_number",
            "prior_prescription_date",
            "prior_prescription_date_short",
            "prior_prescription_date_words",
            "prior_prescription_date_parts",
            "prior_prescription_due",
            "prior_prescription_due_short",
            "prior_prescription_due_words",
            "prior_prescription_basis",
        ):
            administrative_block.setdefault(key, None)
    notice_block = _notice_block(
        case,
        body_context,
        controlled_person,
        object_context,
        prescription_data,
        administrative_block,
    )

    case_context = {
        "schema_version": SCHEMA_VERSION,        "case": {
            "id": case.id,
            "case_number": case.case_number,
            # Номер, код и ссылку на карточку мероприятия присваивает портал
            # прокуратуры, и до этого момента они пустые: в бланке должно
            # остаться место, а не слово «None».
            "erp_number": case.erp_number or "",
            "erp_code": case.erp_code or "",
            "erp_url": case.erp_url or "",
            "purpose": case.purpose,
            "subject": case.subject,
            "result": case.result,
            "is_repeat": case.is_repeat,
            "status": case.status.code if case.status else None,
            "control_kind": case.control_kind.name if case.control_kind else None,
            "control_kind_genitive": (
                (case.control_kind.name_genitive or case.control_kind.name)
                if case.control_kind
                else None
            ),
            "control_form": case.control_form.name if case.control_form else None,
            "control_form_genitive": (
                (case.control_form.name_genitive or case.control_form.name)
                if case.control_form
                else None
            ),
            # «выездное обследование» — форма печатается со строчной буквы
            # в подписи приложения к протоколу осмотра.
            "control_form_lower": (
                case.control_form.name[0].lower() + case.control_form.name[1:]
                if case.control_form and case.control_form.name
                else None
            ),
            "control_form_without_interaction": (
                case.control_form.is_without_interaction
                if case.control_form
                else None
            ),
            "planned_start_at": _iso(case.planned_start_at),
            "planned_end_at": _iso(case.planned_end_at),
            "actual_start_at": _iso(case.actual_start_at),
            "actual_end_at": _iso(case.actual_end_at),
            "act_composed_at": _iso(case.act_composed_at),
            # Части даты для бланков акта, где день, месяц, год, часы и минуты
            # стоят в отдельных ячейках.
            "planned_start_parts": _datetime_parts(case.planned_start_at),
            "planned_end_parts": _datetime_parts(case.planned_end_at),
            "actual_start_parts": _datetime_parts(case.actual_start_at),
            "actual_end_parts": _datetime_parts(case.actual_end_at),
            "act_composed_parts": _datetime_parts(case.act_composed_at),
            "delivery_emails": ", ".join(delivery_emails),
            "planned_start_short": ru.date_short(case.planned_start_at),
            "planned_end_short": ru.date_short(case.planned_end_at),
            "actual_start_short": ru.date_short(case.actual_start_at),
            "actual_end_short": ru.date_short(case.actual_end_at),
            "planned_start_date_words": ru.date_words(case.planned_start_at),
            "planned_end_date_words": ru.date_words(case.planned_end_at),
            "actual_start_date_words": ru.date_words(case.actual_start_at),
            "actual_end_date_words": ru.date_words(case.actual_end_at),
            "planned_start_time": ru.time_short(case.planned_start_at),
            "planned_end_time": ru.time_short(case.planned_end_at),
            "actual_start_time": ru.time_short(case.actual_start_at),
            "actual_end_time": ru.time_short(case.actual_end_at),
            # «08 час. 30 мин.» — формат бланков задания и акта.
            "planned_start_time_official": ru.time_official(case.planned_start_at),
            "planned_end_time_official": ru.time_official(case.planned_end_at),
            "actual_start_time_official": ru.time_official(case.actual_start_at),
            "actual_end_time_official": ru.time_official(case.actual_end_at),
            "assignment_number": case.assignment_number,
            "assignment_date": _iso(case.assignment_date),
            "assignment_date_short": ru.date_short(case.assignment_date),
            "assignment_date_words": ru.date_words(case.assignment_date),
        },
        "control_body": body_context,
        "controlled_person": controlled_person,
        # Ответственный за устранение выбирается вручную в деле; если не
        # выбран, документы печатают контролируемое лицо.
        "responsible_person": _person_block(
            db,
            case.responsible_organization or organization,
            case.responsible_unit or (unit if case.responsible_organization is None else None),
        ),
        "responsible_is_selected": case.responsible_organization_id is not None,
        "control_object": object_context,
        "inspectors": inspectors,
        "approver": {
            "id": approver.id,
            "full_name": approver.full_name,
            "short_name": ru.short_name(approver.full_name),
            # В бланках подпись печатается инициалами перед фамилией:
            # «Т.Н. Инютина».
            "short_name_before": ru.short_name_before(approver.full_name),
            "position": approver.position,
            "position_genitive": approver.position_genitive or approver.position,
            "short_name_genitive": (
                approver.short_name_genitive
                or ru.short_name_genitive(approver.full_name)
            ),
        }
        if approver
        else None,
        "bases": bases,
        # Готовые формулировки для бланка задания: цель и основания.
        "task": {
            "basis_phrase": "; ".join(basis_phrases) or None,
            "basis_count": len(basis_phrases),
        },
        # Данные протокола осмотра: описание нарушения с квалификацией.
        "protocol": {
            "video_note": video_note,
            "photos": protocol_photos,
            "photo_count": len(protocol_photos),
            "violation_description": (
                violations[0]["description"] if violations else None
            ),
            # Нормы в родительном падеже, с объединением общих статей:
            # «пункта 5.2 части 5 статьи 5, частей 7 и 12 статьи 14».
            "violation_provisions_genitive": violation_text.provisions_genitive(
                violation_provisions_genitive
            ),
            "violation_npa_titles": ", ".join(violation_npa_titles) or None,
            "violation_npa_titles_genitive": (
                ", ".join(violation_npa_titles_genitive) or None
            ),
            "violation_description_lower": (
                violations[0]["description"][0].lower()
                + violations[0]["description"][1:]
                if violations and violations[0]["description"]
                else None
            ),
        },
        # Данные акта: первое контрольное действие и место его проведения.
        "inspection": {
            "first_action": actions[0] if actions else None,
            "action_count": len(actions),
            "action_place": actions[0]["place"] if actions else None,
        },
        "actions": actions,
        "violations": violations,
        "prescription": prescription_data,
        "decision": decision_data,
        # Должностное лицо, составившее документы административного
        # производства: в бланках это первый инспектор по заявке.
        "official": {
            "full_name": inspectors[0]["full_name"] if inspectors else None,
            "position": inspectors[0]["position"] if inspectors else None,
            "short_name": (
                ru.short_name(inspectors[0]["full_name"])
                if inspectors and inspectors[0]["full_name"]
                else None
            ),
        },
        # Уведомление о явке: строки собираются здесь, потому что в бланке
        # это связный юридический текст, а не набор отдельных полей.
        "notice": notice_block,
        "administrative": administrative_block,
        # QR-код из прокуратуры: None, пока пользователь его не приложил.
        "qr_code": _qr_block(case),
        "meta": {
            "built_at": datetime.now().isoformat(),
            # Город и другие константы бланка входят в снимок: иначе
            # перегенерация зависела бы от текущих настроек.
            "document_place": settings.document_place,
        },
    }

    # Время мероприятия печатается по осмотру: осмотр и есть выход на объект,
    # а поля заявки — это план. Если осмотр заведён, документы берут его дату.
    _apply_inspection_time(case_context["case"], inspection)
    # Данные осмотра дополняют блок контрольных действий: шаблоны акта уже
    # читают из него первое действие, и подменять его нельзя.
    inspection_block = _inspection_block(inspection)
    if inspection_block:
        case_context["inspection"].update(inspection_block)

    # Тексты нарушения и требования собираются из справочников: работы берутся
    # у нарушения, нормы — из его квалификации, реквизиты акта — из карточки
    # НПА. Ручной текст остаётся только там, где работ не заполнили: так
    # воспроизводятся уже выданные документы.
    _assemble_violation_texts(case_context)
    return case_context


def _assemble_violation_texts(case_context: dict) -> None:
    """Подставляет собранные описания нарушения и требования.

    Собранный текст кладётся в те же ключи, которые печатают бланки
    (`violations[].description`, `protocol.violation_description`,
    `prescription.requirements[].requirement_text`), поэтому сами бланки
    менять не нужно.
    """

    violations = case_context.get("violations") or []
    if not violations:
        return
    object_context = case_context.get("control_object") or {}
    # Место в описании нарушения — предложный падеж: «на земельном участке».
    object_prepositional = object_context.get("name_prepositional")

    used_works_text = None
    for violation in violations:
        works = violation.get("works") or []
        works_text = ", ".join(
            item["line_accusative"] for item in works if item.get("line_accusative")
        ) or None
        if not works_text or not object_prepositional:
            continue
        assembled = violation_text.violation_description(
            object_prepositional,
            works_text,
            violation_type_name=violation.get("violation_type_accusative"),
            action=violation.get("default_action"),
        )
        if assembled:
            violation["description"] = assembled
            violation["works_text"] = works_text
            used_works_text = works_text

    # Описание для протокола осмотра: собирается из того же источника.
    protocol = case_context.get("protocol") or {}
    if violations and violations[0].get("description"):
        description = violations[0]["description"]
        protocol["violation_description"] = description
        protocol["violation_description_lower"] = (
            description[0].lower() + description[1:] if description else None
        )
    case_context["protocol"] = protocol

    # Требование предписания: нормы и реквизиты акта уже есть в контексте.
    prescription = case_context.get("prescription") or {}
    requirements = prescription.get("requirements") or []
    if not requirements:
        return
    first_violation = violations[0]
    references = [
        item.get("reference") for item in first_violation.get("provisions") or []
    ]
    first_requirement = requirements[0].get("action_code")
    action = first_requirement or first_violation.get("default_action")
    # Реквизиты акта: берём тот, на который ссылаются нормы нарушения.
    npa = None
    for provision in first_violation.get("provisions") or []:
        if provision.get("npa_title_genitive"):
            npa = {
                "title_genitive": provision.get("npa_title_genitive"),
                "adopted_on": provision.get("npa_adopted_on"),
                "number": provision.get("npa_number"),
                "adopted_by_genitive": provision.get("npa_adopted_by_genitive"),
            }
            break
    works_text = first_violation.get("works_text") or used_works_text
    if not works_text:
        return
    # Адрес в требовании — обычный адрес объекта: «по адресу: г. Липецк,
    # ул. Теперика, д.3». Название объекта тут не нужно, оно уже сказано в
    # описании нарушения.
    address_text = case_context.get("control_object", {}).get("address")
    requirement_object = first_violation.get("requirement_object")
    for item in requirements:
        assembled = violation_text.requirement_from_data(
            references,
            npa,
            item.get("action_code") or action,
            address_text,
            works_text,
            requirement_object=requirement_object,
        )
        if assembled:
            item["requirement_text_assembled"] = assembled
            # Собранный текст подставляется в то же поле, которое печатает
            # бланк. Прежний текст остаётся рядом: по нему видно, что было
            # введено вручную, и он нужен для старых снимков.
            item["requirement_text_legacy"] = item.get("requirement_text")
            item["requirement_text"] = assembled


def _apply_inspection_time(case_block: dict, inspection: ControlAction | None) -> None:
    """Подменяет фактические сроки мероприятия сроками осмотра."""

    if inspection is None or inspection.started_at is None:
        return

    started = inspection.started_at
    ended = inspection.ended_at or started
    case_block["actual_start_at"] = _iso(started)
    case_block["actual_start_parts"] = _datetime_parts(started)
    case_block["actual_start_short"] = ru.date_short(started)
    case_block["actual_start_date_words"] = ru.date_words(started)
    case_block["actual_start_time"] = ru.time_short(started)
    case_block["actual_start_time_official"] = ru.time_official(started)
    case_block["actual_end_at"] = _iso(ended)
    case_block["actual_end_parts"] = _datetime_parts(ended)
    case_block["actual_end_short"] = ru.date_short(ended)
    case_block["actual_end_date_words"] = ru.date_words(ended)
    case_block["actual_end_time"] = ru.time_short(ended)
    case_block["actual_end_time_official"] = ru.time_official(ended)


def _action_block(action: ControlAction) -> dict:
    """Данные контрольного действия.

    Из них акт печатает сроки мероприятия: «с «22» сентября 2026 09 ч 20 мин.
    по «22» сентября 2026 09 ч 45 мин.».
    """

    return {
        "sequence_no": action.sequence_no,
        "type": action.action_type.value,
        "type_name": ACTION_TYPE_NAMES.get(
            action.action_type.value, action.action_type.value
        ),
        "started_at": _iso(action.started_at),
        "ended_at": _iso(action.ended_at),
        "started_time": ru.time_short(action.started_at),
        "ended_time": ru.time_short(action.ended_at),
        "started_time_official": ru.time_official(action.started_at),
        "ended_time_official": ru.time_official(action.ended_at),
        "started_date_words": ru.date_words(action.started_at),
        "ended_date_words": ru.date_words(action.ended_at),
        "started_parts": _datetime_parts(action.started_at),
        "ended_parts": _datetime_parts(action.ended_at),
        "place": _address_line(action.place_address),
        "result_text": action.result_text,
        "is_violation_found": action.is_violation_found,
    }


def _inspection_block(inspection: ControlAction | None) -> dict | None:
    """Осмотр, по которому собирается пакет: первичный или повторный."""

    if inspection is None:
        return None

    result_titles = {
        InspectionResult.FIXED.value: "нарушение устранено",
        InspectionResult.NOT_FIXED.value: "нарушение не устранено",
    }
    result = (
        inspection.inspection_result.value
        if inspection.inspection_result is not None
        else None
    )
    return {
        "id": inspection.id,
        # Акт печатает сроки первого действия: для пакета это сроки того
        # осмотра, по которому он собирается, а не первого осмотра дела.
        "first_action": _action_block(inspection),
        "sequence_no": inspection.sequence_no,
        "is_repeat": inspection.inspection_kind == InspectionKind.REPEAT,
        "kind": inspection.inspection_kind.value,
        "started_at": _iso(inspection.started_at),
        "parts": _datetime_parts(inspection.started_at),
        "date_short": ru.date_short(inspection.started_at),
        "date_words": ru.date_words(inspection.started_at),
        "time_short": ru.time_short(inspection.started_at),
        "place": (
            _address_line(inspection.place_address)
            if inspection.place_address is not None
            else None
        ),
        "result": result,
        "result_title": result_titles.get(result) if result else None,
        "result_text": inspection.result_text,
        "action_type": inspection.action_type.value,
    }


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def payload_digest(payload: dict, template_version: str | None = None) -> str:
    """Хэш снимка вместе с версией шаблона.

    Так можно доказать, что документ собран именно из этих данных и именно
    этой версией формы.
    """

    material = canonical_json(payload)
    if template_version:
        material = f"{template_version}\n{material}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def save_snapshot(
    db: Session,
    payload: dict,
    entity_kind: SnapshotEntityKind,
    entity_id: int | None = None,
    template_version: str | None = None,
    created_by_user_id: int | None = None,
    commit: bool = True,
) -> DataSnapshot:
    snapshot = DataSnapshot(
        entity_kind=entity_kind,
        entity_id=entity_id,
        schema_version=payload.get("schema_version", SCHEMA_VERSION),
        payload=payload,
        sha256=payload_digest(payload, template_version),
        created_by_user_id=created_by_user_id,
    )
    db.add(snapshot)
    if commit:
        db.commit()
        db.refresh(snapshot)
    else:
        db.flush()
    return snapshot
