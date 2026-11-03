"""Управы: какие адреса за кем закреплены.

Управа — это список адресов и список инспекторов, отвечающих за них.
Адреса берутся из справочника адресов (поиск по улице и дому), а не вводятся
строкой: иначе один дом, записанный по-разному, попал бы в разные управы,
и заявка по нему оказалась бы не у того инспектора.
"""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.forms import parse_date, parse_int
from app.models import (
    Address,
    ControlBody,
    Inspector,
    Area,
    AreaAddress,
    AreaInspector,
)
from app.services import addresses as address_service
from app.services import audit
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui-areas"])


def _addresses_for_choice(db: Session) -> list[Address]:
    """Адреса из справочника для выбора адреса управы.

    Кроме адресов органов контроля показываются уже выбранные адреса управ:
    иначе после сохранения свой адрес не нашёлся бы в списке, если он ещё не
    привязан ни к одному органу.
    """

    result: dict[int, Address] = {}
    for body in db.scalars(select(ControlBody).order_by(ControlBody.name)):
        if body.address is not None:
            result[body.address.id] = body.address
    for area in db.scalars(select(Area).order_by(Area.name)):
        if area.address is not None:
            result[area.address.id] = area.address
    return sorted(result.values(), key=lambda address: address.full_address or "")
BACK = "/ui/areas"


@router.get("/areas", response_class=HTMLResponse)
def areas_page(
    request: Request,
    db: Session = Depends(get_db),
    q: str | None = None,
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    areas = list(
        db.scalars(select(Area).order_by(Area.is_active.desc(), Area.name))
    )
    return templates.TemplateResponse(
        request,
        "areas.html",
        {
            "areas": areas,
            "control_bodies": list(db.scalars(select(ControlBody).order_by(ControlBody.name))),
            "inspectors": list(
                db.scalars(
                    select(Inspector)
                    .where(Inspector.is_active.is_(True))
                    .order_by(Inspector.full_name)
                )
            ),
            # Поиск адреса для добавления в управу.
            # Адреса для выбора места составления протокола: адрес органа
            # контроля (департамента) и уже закреплённые за управами.
            # Адреса для выбора места составления протокола: адрес органа
            # контроля (департамента) и адреса, уже закреплённые за управами.
            # Подсказки для поля адреса управы: весь справочник адресов, а не
            # только уже закреплённые. Иначе новый адрес не подсказать.
            "addresses_for_choice": address_service.search(
                db, None, limit=500, include_archived=False
            ) or _addresses_for_choice(db),
            "address_query": q or "",
            "found_addresses": address_service.search(db, q, limit=30) if q else [],
            "ok": ok,
            "err": err,
        },
    )


@router.post("/areas")
async def save_area(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    area = None
    existing = parse_int(form.get("id"))
    if existing:
        area = db.get(Area, existing)
        if area is None:
            return RedirectResponse(f"{BACK}?err=Управа не найдена", status_code=303)

    name = (form.get("name") or "").strip()
    if not name:
        return RedirectResponse(f"{BACK}?err=Укажите название управы", status_code=303)

    if area is None:
        area = Area(name=name)
        db.add(area)
    else:
        area.name = name
    area.control_body_id = parse_int(form.get("control_body_id"))
    # Адрес управы — место составления протокола по её заявкам. Выбирается из
    # справочника адресов, а не вводится строкой.
    # Адрес управы вводится строкой, как адрес в заявке: запись находится в
    # справочнике или заводится, если её там ещё нет. Выбор только из готового
    # списка не годится — адреса управ в справочнике может не быть.
    address = address_service.resolve(db, form.get("area_address"))
    area.address_id = address.id if address is not None else None
    area.office = (form.get("office") or "").strip() or None
    db.flush()

    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="areas",
        entity_id=area.id,
        action="update" if existing else "create",
        comment=f"{'изменена' if existing else 'создана'} управа: {area.name}",
    )
    db.commit()
    return RedirectResponse(
        f"{BACK}?ok=" + quote(f"Управа «{area.name}» сохранена"), status_code=303
    )


@router.post("/areas/{area_id}/addresses")
async def add_area_address(
    area_id: int, request: Request, db: Session = Depends(get_db)
):
    """Добавляет адрес в управу; адрес заводится по строке, если его нет."""

    area = db.get(Area, area_id)
    if area is None:
        return RedirectResponse(f"{BACK}?err=Управа не найдена", status_code=303)

    form = await request.form()
    address_id = parse_int(form.get("address_id"))
    if address_id:
        address = db.get(Address, address_id)
    else:
        address = address_service.resolve(db, (form.get("full_address") or "").strip())
    if address is None:
        return RedirectResponse(f"{BACK}?err=Укажите адрес", status_code=303)

    exists = db.scalar(
        select(AreaAddress).where(
            AreaAddress.area_id == area_id,
            AreaAddress.address_id == address.id,
        )
    )
    if exists is not None:
        return RedirectResponse(
            f"{BACK}?err=" + quote(f"Адрес уже в управе «{area.name}»"),
            status_code=303,
        )

    db.add(AreaAddress(area_id=area_id, address_id=address.id))
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="area_addresses",
        entity_id=area_id,
        action="create",
        comment=f"в управу «{area.name}» добавлен адрес: {address.full_address}",
    )
    db.commit()
    return RedirectResponse(
        f"{BACK}?ok=" + quote(f"Адрес добавлен в управу «{area.name}»"),
        status_code=303,
    )


@router.post("/areas/{area_id}/addresses/{link_id}/delete")
async def remove_area_address(
    area_id: int, link_id: int, request: Request, db: Session = Depends(get_db)
):
    link = db.get(AreaAddress, link_id)
    if link is None or link.area_id != area_id:
        return RedirectResponse(f"{BACK}?err=Адрес в управе не найден", status_code=303)
    label = link.address.full_address if link.address else f"#{link.address_id}"
    db.delete(link)
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="area_addresses",
        entity_id=area_id,
        action="delete",
        comment=f"из управы убран адрес: {label}",
    )
    db.commit()
    return RedirectResponse(f"{BACK}?ok=Адрес убран из управы", status_code=303)


@router.post("/areas/{area_id}/inspectors")
async def add_area_inspector(
    area_id: int, request: Request, db: Session = Depends(get_db)
):
    area = db.get(Area, area_id)
    if area is None:
        return RedirectResponse(f"{BACK}?err=Управа не найдена", status_code=303)

    form = await request.form()
    inspector_id = parse_int(form.get("inspector_id"))
    if not inspector_id:
        return RedirectResponse(f"{BACK}?err=Выберите инспектора", status_code=303)

    exists = db.scalar(
        select(AreaInspector).where(
            AreaInspector.area_id == area_id,
            AreaInspector.inspector_id == inspector_id,
        )
    )
    if exists is not None:
        return RedirectResponse(
            f"{BACK}?err=Инспектор уже закреплён за управой", status_code=303
        )

    db.add(
        AreaInspector(
            area_id=area_id,
            inspector_id=inspector_id,
            valid_from=parse_date(form.get("valid_from")) or date.today(),
        )
    )
    inspector = db.get(Inspector, inspector_id)
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="area_inspectors",
        entity_id=area_id,
        action="create",
        comment=(
            f"за управой «{area.name}» закреплён инспектор: "
            f"{inspector.full_name if inspector else inspector_id}"
        ),
    )
    db.commit()
    return RedirectResponse(f"{BACK}?ok=Инспектор закреплён за управой", status_code=303)


@router.post("/areas/{area_id}/inspectors/{link_id}/delete")
async def remove_area_inspector(
    area_id: int, link_id: int, request: Request, db: Session = Depends(get_db)
):
    link = db.get(AreaInspector, link_id)
    if link is None or link.area_id != area_id:
        return RedirectResponse(f"{BACK}?err=Закрепление не найдено", status_code=303)
    # Не удаляем запись, а закрываем период: по прошлым заявкам должно быть
    # видно, кто отвечал за управу на тот момент.
    link.valid_to = date.today()
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="area_inspectors",
        entity_id=area_id,
        action="update",
        comment=f"закрыт период закрепления инспектора за управой №{area_id}",
    )
    db.commit()
    return RedirectResponse(
        f"{BACK}?ok=Период закрепления закрыт (запись сохранена в истории)",
        status_code=303,
    )
