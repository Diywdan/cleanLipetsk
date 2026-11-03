"""Осмотры объекта по заявке.

Осмотр — отдельный шаг, а не часть сборки пакета: инспектор выходит на
объект, отмечает дату, время, место и фотографию, и только потом по заявке
собирается пакет документов. Между этими шагами данные успевают появиться,
поэтому «сделать осмотр» и «сформировать пакет» — разные действия.

Повторный осмотр заводится копией первичного (место, вид действия,
инспектор — всё можно изменить) и заканчивается результатом: устранено
нарушение, устранено частично или не устранено. Результат решает, какой
пакет собирать дальше.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.forms import parse_date, parse_datetime, parse_int, to_input, work_rows
from app.models import (
    ControlAction,
    ControlActionFile,
    ControlActionInspector,
    ControlCase,
    Inspector,
    Organization,
    Violation,
    ViolationType,
    ViolationTypeWork,
    Work,
)
from app.models.enums import (
    ControlActionType,
    FileKind,
    InspectionKind,
    InspectionResult,
    PhotoKind,
)
from app.services import audit, inspections, photo_marking, storage, violations
from app.services import addresses as address_service
from app.services import auto_dates
from app.web.router import _actor, _resolve_address_id, _text
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui-inspections"])


# Результат повторного осмотра: из него следует, какой пакет собирать.
# «Устранено частично» нет намеренно: от результата зависит, какой пакет
# собирать, а частичный результат не даёт однозначного ответа.
RESULT_CHOICES: list[tuple[str, str]] = [
    (InspectionResult.FIXED.value, "нарушение устранено"),
    (InspectionResult.NOT_FIXED.value, "нарушение не устранено"),
]

# Виды контрольных действий, которые могут быть у осмотра.
ACTION_TYPES: list[tuple[str, str]] = [
    (ControlActionType.INSPECTION.value, "осмотр"),
    (ControlActionType.INSTRUMENTAL_SURVEY.value, "инструментальное обследование"),
    (ControlActionType.PHOTO_FIXATION.value, "фотофиксация"),
]


def _link_photo(
    db: Session,
    inspection: ControlAction,
    file,
    *,
    photo_kind: PhotoKind,
    color: str | None = None,
    caption: str | None = None,
    sequence_no: int = 0,
) -> ControlActionFile:
    """Привязывает файл к осмотру, не заводя второй ссылки на тот же файл.

    Файлы хранятся по sha256: одна и та же фотография — одна запись. На паре
    «осмотр + файл» стоит уникальность, поэтому такую ссылку не вставляют
    второй раз, а обновляют: иначе повторное нажатие кнопки «Нанести разметку
    заново» тем же цветом падало бы с ошибкой базы.
    """

    existing = db.scalar(
        select(ControlActionFile).where(
            ControlActionFile.control_action_id == inspection.id,
            ControlActionFile.file_id == file.id,
        )
    )
    if existing is not None:
        existing.photo_kind = photo_kind
        existing.annotation_color = color
        existing.caption = caption
        existing.sequence_no = sequence_no
        return existing

    link = ControlActionFile(
        control_action_id=inspection.id,
        file_id=file.id,
        photo_kind=photo_kind,
        annotation_color=color,
        caption=caption,
        sequence_no=sequence_no,
    )
    db.add(link)
    return link


def _inspectors(db: Session, case: ControlCase) -> list[Inspector]:
    """Инспекторы для выбора: сначала закреплённые за заявкой."""

    case_inspectors = [
        link.inspector
        for link in case.inspectors
        if link.inspector is not None and link.inspector.is_active
    ]
    if case_inspectors:
        return case_inspectors
    return list(
        db.scalars(
            select(Inspector).where(Inspector.is_active.is_(True)).order_by(Inspector.full_name)
        )
    )


def _work_kinds(db: Session) -> dict[int, list[int]]:
    """Какие виды нарушений ссылаются на каждую работу.

    По этой карте список работ на странице осмотра сужается до выбранного
    вида нарушения — так же, как в карточке заявки.
    """

    result: dict[int, list[int]] = {}
    for link in db.scalars(select(ViolationTypeWork)):
        result.setdefault(link.work_id, []).append(link.violation_type_id)
    return result


def _set_inspector(db: Session, inspection: ControlAction, inspector_id: int) -> None:
    """У осмотра один инспектор: прежняя связь заменяется."""

    for link in list(inspection.inspectors):
        db.delete(link)
    db.add(
        ControlActionInspector(
            control_action_id=inspection.id, inspector_id=inspector_id
        )
    )


def _annotation_lines(inspection: ControlAction) -> list[str]:
    address = (
        inspection.place_address.full_address
        if inspection.place_address is not None
        else None
    )
    return photo_marking.annotation_text(inspection, address)


@router.post("/cases/{case_id}/inspections")
async def create_inspection(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Кнопка «Сделать осмотр»: заводит первичный или повторный осмотр."""

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    form = await request.form()
    try:
        kind = InspectionKind(_text(form, "kind") or InspectionKind.PRIMARY.value)
    except ValueError:
        return RedirectResponse(
            f"/ui/cases/{case_id}?err={quote('Неизвестный вид осмотра')}", status_code=303
        )

    allowed, reason = inspections.can_start(db, case_id, kind)
    if not allowed:
        return RedirectResponse(f"/ui/cases/{case_id}?err={quote(reason)}", status_code=303)

    inspector_id = parse_int(form.get("inspector_id"))
    inspection = inspections.start(
        db,
        case,
        kind=kind,
        inspector=db.get(Inspector, inspector_id) if inspector_id else None,
    )
    # Осмотр завели — сразу проставляем, сколько он длится, и даты задания
    # и решения по дню осмотра: делопроизводителю не нужно набирать их руками.
    if inspection.ended_at is None:
        inspection.ended_at = auto_dates.default_end(inspection.started_at)
    derived = auto_dates.apply_after_inspection(db, case, inspection)
    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_actions",
        entity_id=inspection.id,
        action="create",
        comment=(
            f"заведён {'повторный' if kind == InspectionKind.REPEAT else 'первичный'} "
            f"осмотр по заявке {case.erp_number or case.id}"
            + (f"; {', '.join(derived)}" if derived else "")
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/inspections/{inspection.id}?ok="
        f"{quote('Осмотр заведён: заполните дату, место и фотографию')}",
        status_code=303,
    )


@router.get("/inspections/{inspection_id}", response_class=HTMLResponse)
def inspection_page(
    request: Request,
    inspection_id: int,
    db: Session = Depends(get_db),
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    """Карточка осмотра: дата, место, инспектор, фотография и результат."""

    inspection = db.get(ControlAction, inspection_id)
    if inspection is None:
        return RedirectResponse("/ui?err=Осмотр не найден", status_code=303)

    case = inspection.control_case
    violation = db.scalars(
        select(Violation)
        .where(Violation.control_case_id == case.id)
        .order_by(Violation.id)
    ).first()
    prescription = case.prescriptions[0] if case.prescriptions else None
    return templates.TemplateResponse(
        request,
        "inspection.html",
        {
            "inspection": inspection,
            "case": case,
            "violation": violation,
            "prescription": prescription,
            "organizations": list(
                db.scalars(select(Organization).order_by(Organization.short_name))
            ),
            "case_inspections": inspections.inspections(db, case.id),
            "available_inspection_kind": inspections.available_kind(db, case.id),
            "inspectors": _inspectors(db, case),
            "result_choices": RESULT_CHOICES,
            "action_types": ACTION_TYPES,
            "colors": inspections.ANNOTATION_COLORS,
            "started_at_value": to_input(inspection.started_at),
            # Окончание ещё не заполнено — показываем начало плюс 15 минут:
            # столько осмотр длится по умолчанию.
            "ended_at_value": to_input(
                inspection.ended_at
                or auto_dates.default_end(inspection.started_at)
            ),
            "addresses": address_service.search(db, None, limit=500, include_archived=False),
            "photo_original": inspections.photo_file(inspection, PhotoKind.ORIGINAL),
            "photo_marked": inspections.photo_file(inspection, PhotoKind.ANNOTATED),
            # Работы по нарушению вводятся здесь же, что и в карточке заявки:
            # описание нарушения собирается из них, а не пишется текстом.
            "violation_types": list(
                db.scalars(select(ViolationType).order_by(ViolationType.sort_order))
            ),
            "works": list(
                db.scalars(
                    select(Work)
                    .where(Work.is_active.is_(True))
                    .order_by(Work.sort_order, Work.name)
                )
            ),
            "work_kinds": _work_kinds(db),
            "violation_works": (
                [
                    {
                        "work_id": item.work_id,
                        "quantity": (
                            float(item.quantity) if item.quantity is not None else ""
                        ),
                    }
                    for item in violation.works
                ]
                if violation is not None
                else []
            ),
            "violation_description": (
                violation.description if violation is not None else None
            ),
            "ok": ok,
            "err": err,
        },
    )


@router.post("/inspections/{inspection_id}")
async def save_inspection(
    request: Request, inspection_id: int, db: Session = Depends(get_db)
):
    """Сохранение осмотра: дата и время, место, инспектор, результат."""

    inspection = db.get(ControlAction, inspection_id)
    if inspection is None:
        return RedirectResponse("/ui?err=Осмотр не найден", status_code=303)

    form = await request.form()
    # Прежняя дата осмотра нужна, чтобы понять, какие даты система проставила
    # сама: их можно обновить, а введённые человеком — нет.
    previous_started_at = inspection.started_at
    started_at = parse_datetime(form.get("started_at"))
    if started_at is not None:
        inspection.started_at = started_at
    # Окончание не заполнили — осмотр по умолчанию длится 15 минут.
    inspection.ended_at = parse_datetime(form.get("ended_at")) or (
        auto_dates.default_end(inspection.started_at)
    )

    place_id = _resolve_address_id(db, form, "place")
    if place_id is not None:
        inspection.place_address_id = place_id
        # Адрес у заявки один: адрес осмотра и адрес объекта контроля — это
        # один и тот же адрес. Правка при осмотре меняет его и в заявке —
        # иначе в документах остался бы прежний адрес.
        control_object = inspection.control_case.control_object
        if control_object is not None:
            control_object.address_id = place_id

    action_type = _text(form, "action_type")
    if action_type:
        try:
            inspection.action_type = ControlActionType(action_type)
        except ValueError:
            pass

    inspection.result_text = _text(form, "result_text")
    result = _text(form, "result")
    # Результат есть только у повторного осмотра: первичный нарушение
    # выявляет, а не проверяет его устранение.
    if inspection.inspection_kind == InspectionKind.REPEAT:
        try:
            inspections.set_result(db, inspection, result)
        except ValueError:
            return RedirectResponse(
                f"/ui/inspections/{inspection_id}?err="
                f"{quote('Неизвестный результат осмотра')}",
                status_code=303,
            )

    inspector_id = parse_int(form.get("inspector_id"))
    if inspector_id:
        _set_inspector(db, inspection, inspector_id)

    # Нарушение, ответственное лицо и срок устранения удобнее заполнять сразу
    # после осмотра, не переходя в карточку заявки: инспектор только что с
    # объекта и помнит, что именно увидел.
    case = inspection.control_case
    violation_type_id = parse_int(form.get("violation_type_id"))
    rows = work_rows(form)
    description = violations.description_for(
        db, case, rows, violation_type_id
    )
    violation = db.scalars(
        select(Violation)
        .where(Violation.control_case_id == case.id)
        .order_by(Violation.id)
    ).first()
    # Нарушение заводится, если указан его вид или работы: описание теперь
    # собирается из них, отдельного текста нет.
    if violation_type_id or rows:
        if violation is None:
            violation = Violation(
                control_case_id=case.id,
                # Нарушение связывается с осмотром, который его выявил.
                control_action_id=inspection.id,
                description=description or "нарушение не описано",
                detected_at=inspection.started_at,
                address_id=inspection.place_address_id,
            )
            db.add(violation)
            db.flush()
        elif description:
            violation.description = description
        if violation_type_id:
            violation.violation_type_id = violation_type_id
        if violation.control_action_id is None:
            violation.control_action_id = inspection.id
        if violation.detected_at is None:
            violation.detected_at = inspection.started_at
        if rows:
            violations.save_works(db, violation, rows)
        # Описание пересобираем после сохранения работ: в нём список объёмов.
        assembled = violations.description_for(
            db, case, rows, violation_type_id
        )
        if assembled:
            violation.description = assembled
        db.flush()

    # Устранение нарушения отмечается по результату повторного осмотра:
    # отдельной галочки не нужно, результат осмотра и есть ответ.
    if violation is not None and inspection.inspection_kind == InspectionKind.REPEAT:
        eliminated = inspection.inspection_result == InspectionResult.FIXED
        violation.is_eliminated = eliminated
        violation.eliminated_at = inspection.started_at if eliminated else None

    # Ответственное лицо, квалификацию и срок устранения в осмотре не
    # заполняют: это работа делопроизводителя на шаге документов. В осмотре
    # остаётся только то, что инспектор видел на объекте.

    # Даты, которые следуют за днём осмотра: задание выдаётся накануне,
    # решение датируется протоколом. Их можно поправить руками — тогда
    # следующее сохранение осмотра трогать их не будет.
    derived = auto_dates.apply_after_inspection(
        db, case, inspection, previous_started_at
    )

    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_actions",
        entity_id=inspection.id,
        action="update",
        comment=(
            f"изменён осмотр №{inspection.sequence_no} по заявке "
            f"{inspection.control_case.erp_number or inspection.control_case_id}"
            + (f"; {', '.join(derived)}" if derived else "")
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/inspections/{inspection_id}?ok={quote('Осмотр сохранён')}",
        status_code=303,
    )


@router.post("/inspections/{inspection_id}/photo")
async def upload_photo(
    request: Request, inspection_id: int, db: Session = Depends(get_db)
):
    """Загрузка фотографии осмотра.

    Хранятся два файла: исходный снимок и размеченная копия с адресом и
    датой осмотра. Оригинал нужен, чтобы разметку можно было нанести заново —
    например, если дата осмотра изменится и документы переделывают.
    """

    inspection = db.get(ControlAction, inspection_id)
    if inspection is None:
        return RedirectResponse("/ui?err=Осмотр не найден", status_code=303)

    form = await request.form()
    upload = form.get("photo")
    if upload is None or not getattr(upload, "filename", ""):
        return RedirectResponse(
            f"/ui/inspections/{inspection_id}?err={quote('Файл не выбран')}",
            status_code=303,
        )

    data = await upload.read()
    if not data:
        return RedirectResponse(
            f"/ui/inspections/{inspection_id}?err={quote('Пустой файл')}",
            status_code=303,
        )

    color = _text(form, "annotation_color") or inspections.DEFAULT_ANNOTATION_COLOR
    # У осмотра одна фотография: прежние файлы заменяются.
    for item in list(inspection.files):
        db.delete(item)
    db.flush()

    original_file = storage.save_bytes(
        db,
        data,
        getattr(upload, "filename", "photo.jpg"),
        kind=FileKind.PHOTO,
        mime_type=getattr(upload, "content_type", None) or "image/jpeg",
        commit=False,
    )
    _link_photo(
        db, inspection, original_file, photo_kind=PhotoKind.ORIGINAL, sequence_no=0
    )

    lines = _annotation_lines(inspection)
    try:
        marked_bytes = photo_marking.mark_photo(data, lines, color=color)
    except Exception:  # noqa: BLE001 — снимок может быть нечитаемым
        db.rollback()
        return RedirectResponse(
            f"/ui/inspections/{inspection_id}?err="
            f"{quote('Не удалось разметить фотографию: файл не читается как изображение')}",
            status_code=303,
        )

    marked_file = storage.save_bytes(
        db,
        marked_bytes,
        "photo_marked.jpg",
        kind=FileKind.PHOTO,
        mime_type="image/jpeg",
        commit=False,
    )
    _link_photo(
        db,
        inspection,
        marked_file,
        photo_kind=PhotoKind.ANNOTATED,
        color=color,
        caption=" ".join(lines) or None,
        sequence_no=1,
    )

    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_actions",
        entity_id=inspection.id,
        action="update",
        comment=(
            f"загружена фотография осмотра №{inspection.sequence_no}, "
            f"надпись: {inspections.ANNOTATION_COLORS.get(color, color)}"
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/inspections/{inspection_id}?ok="
        f"{quote('Фотография загружена и размечена')}",
        status_code=303,
    )


@router.post("/inspections/{inspection_id}/photo/remark")
async def remark_photo(
    request: Request, inspection_id: int, db: Session = Depends(get_db)
):
    """Повторная разметка снимка другим цветом.

    Берётся исходная фотография, а не прежняя размеченная: надписи не
    накладываются одна на другую.
    """

    inspection = db.get(ControlAction, inspection_id)
    if inspection is None:
        return RedirectResponse("/ui?err=Осмотр не найден", status_code=303)

    form = await request.form()
    color = _text(form, "annotation_color") or inspections.DEFAULT_ANNOTATION_COLOR

    original = inspections.photo_file(inspection, PhotoKind.ORIGINAL)
    if original is None:
        return RedirectResponse(
            f"/ui/inspections/{inspection_id}?err="
            f"{quote('Сначала загрузите фотографию')}",
            status_code=303,
        )

    lines = _annotation_lines(inspection)
    data = storage.read_bytes(original.file)
    marked_bytes = photo_marking.mark_photo(data, lines, color=color)

    # Прежняя размеченная копия больше не нужна: у осмотра одна фотография.
    # Убираем её до новой привязки: файлы хранятся по sha256, поэтому разметка
    # тем же цветом даёт ровно тот же файл, а на паре «осмотр + файл» стоит
    # уникальность — вторая ссылка на него не вставилась бы.
    for item in list(inspection.files):
        if item.photo_kind == PhotoKind.ANNOTATED:
            db.delete(item)
    db.flush()

    marked_file = storage.save_bytes(
        db,
        marked_bytes,
        "photo_marked.jpg",
        kind=FileKind.PHOTO,
        mime_type="image/jpeg",
        commit=False,
    )
    marked = _link_photo(
        db,
        inspection,
        marked_file,
        photo_kind=PhotoKind.ANNOTATED,
        color=color,
        caption=" ".join(lines) or None,
        sequence_no=1,
    )
    db.flush()

    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_actions",
        entity_id=inspection.id,
        action="update",
        comment=(
            f"разметка фотографии осмотра №{inspection.sequence_no} нанесена заново, "
            f"цвет: {inspections.ANNOTATION_COLORS.get(color, color)}"
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/inspections/{inspection_id}?ok={quote('Разметка нанесена заново')}",
        status_code=303,
    )


@router.get("/inspections/{inspection_id}/photo/{kind}")
def photo_file(
    inspection_id: int, kind: str, db: Session = Depends(get_db)
) -> FileResponse:
    """Отдаёт фотографию осмотра: размеченную копию или исходный снимок."""

    inspection = db.get(ControlAction, inspection_id)
    if inspection is None:
        return RedirectResponse("/ui?err=Осмотр не найден", status_code=303)

    try:
        photo_kind = PhotoKind(kind)
    except ValueError:
        return RedirectResponse("/ui?err=Неизвестный вид снимка", status_code=303)

    item = inspections.photo_file(inspection, photo_kind)
    if item is None:
        return RedirectResponse("/ui?err=Снимок не найден", status_code=303)

    return FileResponse(
        path=storage.absolute_path(item.file.storage_path),
        media_type=item.file.mime_type or "image/jpeg",
        filename=item.file.original_name,
        # Адрес снимка не меняется при повторной разметке, поэтому браузер
        # обязан каждый раз спрашивать сервер: иначе он показывал бы прежнюю
        # картинку из своего кэша, и казалось бы, что разметка не нанеслась.
        headers={"Cache-Control": "no-cache"},
    )
