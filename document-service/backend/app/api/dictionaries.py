"""Справочники: добавление и правка значений.

Те же адреса, что и у страниц справочников, но ответ — JSON. Это позволяет
добавлять значение прямо из формы заявки: страница не перезагружается,
введённые данные не теряются, а новое значение сразу появляется в списке.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.forms import parse_int
from app.models import (
    Address,
    ControlBodySignatory,
    ControlObject,
    Inspector,
    Organization,
    OrganizationSignatory,
    OrganizationUnit,
)
from app.services import dictionaries


router = APIRouter(tags=["dictionaries"])


def _existing_id(data) -> int | None:
    value = data.get("id")
    return parse_int(value if isinstance(value, str) else None)


def _result(entity, label: str, data) -> dict:
    field = data.get("field")
    return {
        "id": entity.id,
        "label": label,
        "field": field if isinstance(field, str) else None,
    }


@router.post("/dictionaries/organizations")
async def save_organization(request: Request, db: Session = Depends(get_db)) -> dict:
    data = await request.form()
    organization = None
    existing = _existing_id(data)
    if existing:
        organization = db.get(Organization, existing)
        if organization is None:
            raise HTTPException(status_code=404, detail="организация не найдена")
    organization = dictionaries.save_organization(db, data, organization)
    if organization is None:
        raise HTTPException(status_code=422, detail="укажите краткое наименование")
    db.commit()
    return _result(organization, dictionaries.organization_label(organization), data)


@router.post("/dictionaries/inspectors")
async def save_inspector(request: Request, db: Session = Depends(get_db)) -> dict:
    data = await request.form()
    inspector = None
    existing = _existing_id(data)
    if existing:
        inspector = db.get(Inspector, existing)
        if inspector is None:
            raise HTTPException(status_code=404, detail="инспектор не найден")
    inspector = dictionaries.save_inspector(db, data, inspector)
    if inspector is None:
        raise HTTPException(status_code=422, detail="укажите ФИО и должность")
    db.commit()
    return _result(inspector, dictionaries.inspector_label(inspector), data)


@router.post("/dictionaries/signatories")
async def save_signatory(request: Request, db: Session = Depends(get_db)) -> dict:
    data = await request.form()
    signatory = None
    existing = _existing_id(data)
    if existing:
        signatory = db.get(ControlBodySignatory, existing)
        if signatory is None:
            raise HTTPException(status_code=404, detail="подписант не найден")
    signatory = dictionaries.save_signatory(db, data, signatory)
    if signatory is None:
        raise HTTPException(
            status_code=422,
            detail="укажите орган контроля, ФИО и должность",
        )
    db.commit()
    return _result(signatory, dictionaries.signatory_label(signatory), data)


@router.post("/dictionaries/objects")
async def save_object(request: Request, db: Session = Depends(get_db)) -> dict:
    data = await request.form()
    control_object = None
    existing = _existing_id(data)
    if existing:
        control_object = db.get(ControlObject, existing)
        if control_object is None:
            raise HTTPException(status_code=404, detail="объект не найден")
    control_object = dictionaries.save_object(db, data, control_object)
    if control_object is None:
        raise HTTPException(status_code=422, detail="укажите вид и описание объекта")
    db.commit()
    return _result(control_object, dictionaries.object_label(control_object), data)


@router.post("/dictionaries/addresses")
async def save_address(request: Request, db: Session = Depends(get_db)) -> dict:
    data = await request.form()
    address = None
    existing = _existing_id(data)
    if existing:
        address = db.get(Address, existing)
        if address is None:
            raise HTTPException(status_code=404, detail="адрес не найден")
    address = dictionaries.save_address(db, data, address)
    if address is None:
        raise HTTPException(status_code=422, detail="укажите адрес")
    db.commit()
    return _result(address, dictionaries.address_label(address), data)


@router.post("/dictionaries/organizations/{organization_id}/units")
async def save_unit(
    organization_id: int, request: Request, db: Session = Depends(get_db)
) -> dict:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="организация не найдена")
    data = await request.form()
    unit = None
    existing = _existing_id(data)
    if existing:
        unit = db.get(OrganizationUnit, existing)
        if unit is None or unit.organization_id != organization_id:
            raise HTTPException(status_code=404, detail="подразделение не найдено")
    unit = dictionaries.save_unit(db, organization, data, unit)
    if unit is None:
        raise HTTPException(status_code=422, detail="укажите название подразделения")
    db.commit()
    return _result(unit, dictionaries.unit_label(unit), data)


@router.post("/dictionaries/organizations/{organization_id}/representatives")
async def save_representative(
    organization_id: int, request: Request, db: Session = Depends(get_db)
) -> dict:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="организация не найдена")
    data = await request.form()
    representative = None
    existing = _existing_id(data)
    if existing:
        representative = db.get(OrganizationSignatory, existing)
        if representative is None or representative.organization_id != organization_id:
            raise HTTPException(status_code=404, detail="представитель не найден")
    representative = dictionaries.save_representative(db, organization, data, representative)
    if representative is None:
        raise HTTPException(status_code=422, detail="укажите ФИО и должность")
    db.commit()
    return _result(representative, representative.full_name, data)
