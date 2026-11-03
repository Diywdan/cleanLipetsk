"""Сохранение значений справочников.

Одни и те же функции используют страницы справочников, форма заявки
(значение добавляется, не уходя со страницы) и программный интерфейс.
Поэтому разбор полей и правила заполнения живут здесь, а не в обработчиках.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forms import clean, parse_date, parse_int
from app.models import (
    Address,
    ControlBodySignatory,
    ControlObject,
    Inspector,
    Organization,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationRole,
    OrganizationSignatory,
    OrganizationUnit,
)
from app.models.enums import (
    ContactKind,
    ContactPurpose,
    OrganizationKind,
    OrganizationRoleCode,
    OrganizationUnitKind,
    SignatoryBasisKind,
)
from app.services import addresses as address_service


def text(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    return clean(value if isinstance(value, str) else None)


def number(data: Mapping[str, Any], name: str) -> int | None:
    value = data.get(name)
    return parse_int(value if isinstance(value, str) else None)


def coordinate(data: Mapping[str, Any], name: str) -> Decimal | None:
    """Координата из формы: «52,6089» и «52.6089» — одно и то же.

    Пустое поле значением не считается: иначе правка адреса без координат
    стирала бы уже введённые.
    """

    value = text(data, name)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def save_address(
    db: Session, data: Mapping[str, Any], address: Address | None = None
) -> Address | None:
    """Адрес заводится по строке; дубли не создаются."""

    full_address = text(data, "full_address")
    if address is not None:
        # Правка существующего: строка могла измениться, ключ пересчитываем.
        address.full_address = full_address or address.full_address
        address.search_key = address_service.normalize(address.full_address)
    else:
        address = address_service.resolve(db, full_address)
        if address is None:
            return None

    for field in (
        "postal_code",
        "region",
        "district",
        "locality",
        "street",
        "house",
        "building",
        "structure",
        "apartment",
        "notes",
        "fias_guid",
        "gar_guid",
    ):
        value = text(data, field)
        if value is not None:
            setattr(address, field, value)

    # Координаты нужны интерфейсу диспетчера: по ним обращение встаёт на карту.
    # Пустое поле не затирает уже введённые координаты: их заполняют один раз.
    latitude = coordinate(data, "latitude")
    longitude = coordinate(data, "longitude")
    if latitude is not None:
        address.latitude = latitude
    if longitude is not None:
        address.longitude = longitude
    return address


def save_organization(
    db: Session, data: Mapping[str, Any], organization: Organization | None = None
) -> Organization | None:
    short_name = text(data, "short_name")
    if organization is None:
        if not short_name:
            return None
        organization = Organization(
            kind=OrganizationKind(text(data, "kind") or "legal_entity"),
            short_name=short_name,
        )
        db.add(organization)
    elif short_name:
        organization.short_name = short_name

    for field in ("full_name", "inn", "kpp", "ogrn"):
        value = text(data, field)
        if value is not None:
            setattr(organization, field, value)

    if text(data, "kind"):
        try:
            organization.kind = OrganizationKind(text(data, "kind"))
        except ValueError:
            pass

    db.flush()
    save_requisites(db, organization, data)
    save_contact(db, organization, number(data, "unit_id"), data)
    return organization


def save_requisites(
    db: Session,
    organization: Organization,
    data: Mapping[str, Any],
    unit_id: int | None = None,
) -> OrganizationRequisite | None:
    """Реквизиты организации или её филиала.

    Реквизиты филиала хранятся отдельно: у него свой ИНН и КПП, и именно они
    печатаются в акте, если мероприятие проводится в отношении филиала.
    """

    unit_id = unit_id if unit_id is not None else number(data, "unit_id")
    inn = text(data, "inn")
    kpp = text(data, "kpp")
    # Карточка организации хранит ИНН отдельно от таблицы реквизитов.
    # Если в форме ИНН не пришёл, но он уже есть у организации, всё равно
    # заводим действующую запись: иначе пакет видит «реквизиты не заполнены»,
    # хотя на карточке ИНН уже указан.
    if unit_id is None:
        inn = inn or organization.inn
        kpp = kpp or organization.kpp
    legal_address_text = text(data, "legal_address")
    legal_address_id = number(data, "legal_address_id")
    if legal_address_text:
        resolved = address_service.resolve(db, legal_address_text)
        legal_address_id = resolved.id if resolved is not None else legal_address_id
    email = text(data, "email")
    if not any((inn, kpp, legal_address_id, email)):
        return None

    requisites = db.scalars(
        select(OrganizationRequisite)
        .where(
            OrganizationRequisite.organization_id == organization.id,
            OrganizationRequisite.valid_to.is_(None),
            OrganizationRequisite.unit_id.is_(None)
            if unit_id is None
            else OrganizationRequisite.unit_id == unit_id,
        )
        .order_by(OrganizationRequisite.valid_from.desc())
    ).first()
    if requisites is None:
        requisites = OrganizationRequisite(
            organization_id=organization.id,
            unit_id=unit_id,
            valid_from=parse_date(data.get("valid_from")) or date.today(),
        )
        db.add(requisites)

    requisites.inn = inn or (organization.inn if unit_id is None else None)
    requisites.kpp = kpp or (organization.kpp if unit_id is None else None)
    if legal_address_id is not None:
        requisites.legal_address_id = legal_address_id
    if email:
        requisites.email = email
    db.flush()
    return requisites


def save_contact(
    db: Session,
    organization: Organization,
    unit_id: int | None,
    data: Mapping[str, Any],
) -> OrganizationContact | None:
    """Электронная почта для отправки документов."""

    email = text(data, "email")
    if not email:
        return None
    existing = db.scalars(
        select(OrganizationContact).where(
            OrganizationContact.organization_id == organization.id,
            OrganizationContact.unit_id.is_(None)
            if unit_id is None
            else OrganizationContact.unit_id == unit_id,
            OrganizationContact.kind == ContactKind.EMAIL,
            OrganizationContact.value == email,
        )
    ).first()
    if existing is not None:
        return existing

    contact = OrganizationContact(
        organization_id=organization.id,
        unit_id=unit_id,
        kind=ContactKind.EMAIL,
        purpose=ContactPurpose.DOCUMENT_DELIVERY,
        value=email,
    )
    db.add(contact)
    db.flush()
    return contact


def save_inspector(
    db: Session, data: Mapping[str, Any], inspector: Inspector | None = None
) -> Inspector | None:
    full_name = text(data, "full_name")
    position = text(data, "position")
    if inspector is None:
        if not full_name or not position:
            return None
        inspector = Inspector(full_name=full_name, position=position)
        db.add(inspector)
    else:
        if full_name:
            inspector.full_name = full_name
        if position:
            inspector.position = position

    for field in (
        "full_name_instrumental",
        "position_instrumental",
        "full_name_genitive",
        "position_genitive",
        "phone",
        "email",
    ):
        value = text(data, field)
        if value is not None:
            setattr(inspector, field, value)
    db.flush()
    return inspector


def save_signatory(
    db: Session,
    data: Mapping[str, Any],
    signatory: ControlBodySignatory | None = None,
) -> ControlBodySignatory | None:
    full_name = text(data, "full_name")
    position = text(data, "position")
    control_body_id = number(data, "control_body_id")
    if signatory is None:
        if not full_name or not position or not control_body_id:
            return None
        signatory = ControlBodySignatory(
            control_body_id=control_body_id, full_name=full_name, position=position
        )
        db.add(signatory)
    else:
        if full_name:
            signatory.full_name = full_name
        if position:
            signatory.position = position
        if control_body_id:
            signatory.control_body_id = control_body_id

    for field in ("position_genitive", "short_name_genitive"):
        value = text(data, field)
        if value is not None:
            setattr(signatory, field, value)
    valid_from = parse_date(data.get("valid_from"))
    if valid_from:
        signatory.valid_from = valid_from
    db.flush()
    return signatory


def save_object(
    db: Session,
    data: Mapping[str, Any],
    control_object: ControlObject | None = None,
) -> ControlObject | None:
    name = text(data, "name")
    object_type_id = number(data, "object_type_id")
    if control_object is None:
        if not name or not object_type_id:
            return None
        control_object = ControlObject(object_type_id=object_type_id, name=name)
        db.add(control_object)
    else:
        if name:
            control_object.name = name
        if object_type_id:
            control_object.object_type_id = object_type_id

    for field in ("name_genitive", "cadastral_number", "purpose", "notes"):
        value = text(data, field)
        if value is not None:
            setattr(control_object, field, value)

    operating = number(data, "operating_organization_id")
    if operating is not None:
        control_object.operating_organization_id = operating or None

    address_text = text(data, "address")
    address_id = number(data, "address_id")
    if address_text:
        resolved = address_service.resolve(db, address_text)
        address_id = resolved.id if resolved is not None else address_id
    if address_id is not None:
        control_object.address_id = address_id or None
    db.flush()
    return control_object


def save_unit(
    db: Session,
    organization: Organization,
    data: Mapping[str, Any],
    unit: OrganizationUnit | None = None,
) -> OrganizationUnit | None:
    name = text(data, "name")
    if unit is None:
        if not name:
            return None
        unit = OrganizationUnit(
            organization_id=organization.id,
            kind=OrganizationUnitKind(text(data, "kind") or "branch"),
            name=name,
        )
        db.add(unit)
    elif name:
        unit.name = name

    address_text = text(data, "address")
    address_id = number(data, "address_id")
    if address_text:
        resolved = address_service.resolve(db, address_text)
        address_id = resolved.id if resolved is not None else address_id
    if address_id is not None:
        unit.address_id = address_id or None
    db.flush()
    save_contact(db, organization, unit.id, data)
    save_requisites(db, organization, data, unit_id=unit.id)
    return unit


def save_representative(
    db: Session,
    organization: Organization,
    data: Mapping[str, Any],
    representative: OrganizationSignatory | None = None,
) -> OrganizationSignatory | None:
    full_name = text(data, "full_name")
    position = text(data, "position")
    if representative is None:
        if not full_name or not position:
            return None
        representative = OrganizationSignatory(
            organization_id=organization.id, full_name=full_name, position=position
        )
        db.add(representative)
    else:
        if full_name:
            representative.full_name = full_name
        if position:
            representative.position = position

    basis_kind = text(data, "basis_kind")
    if basis_kind:
        try:
            representative.basis_kind = SignatoryBasisKind(basis_kind)
        except ValueError:
            pass
    for field in ("basis_number",):
        value = text(data, field)
        if value is not None:
            setattr(representative, field, value)
    basis_date = parse_date(data.get("basis_date"))
    if basis_date:
        representative.basis_date = basis_date
    # Дата начала действия обязательна: без неё запись не сохранится,
    # а по умолчанию считаем, что полномочия действуют с сегодняшнего дня.
    valid_from = parse_date(data.get("valid_from"))
    representative.valid_from = (
        valid_from or representative.valid_from or date.today()
    )
    unit_id = number(data, "unit_id")
    if unit_id is not None:
        representative.unit_id = unit_id or None
    db.flush()
    return representative


def save_role(
    db: Session,
    organization: Organization,
    data: Mapping[str, Any],
    role: OrganizationRole | None = None,
) -> OrganizationRole | None:
    code = text(data, "role")
    if role is None:
        if not code:
            return None
        try:
            role = OrganizationRole(
                organization_id=organization.id,
                role=OrganizationRoleCode(code),
                unit_id=number(data, "unit_id"),
                valid_from=parse_date(data.get("valid_from")) or date.today(),
            )
        except ValueError:
            return None
        db.add(role)
    else:
        if code:
            try:
                role.role = OrganizationRoleCode(code)
            except ValueError:
                pass
        unit_id = number(data, "unit_id")
        if unit_id is not None:
            role.unit_id = unit_id or None
    db.flush()
    return role


# --- Подписи значений для списков и подсказок ------------------------------


def organization_label(organization: Organization) -> str:
    return organization.short_name


def inspector_label(inspector: Inspector) -> str:
    position = f" — {inspector.position}" if inspector.position else ""
    return f"{inspector.full_name}{position}"


def signatory_label(signatory: ControlBodySignatory) -> str:
    position = f" — {signatory.position}" if signatory.position else ""
    return f"{signatory.full_name}{position}"


def object_label(control_object: ControlObject) -> str:
    return control_object.name or f"объект №{control_object.id}"


def address_label(address: Address) -> str:
    return address.full_address


def unit_label(unit: OrganizationUnit) -> str:
    return unit.name
