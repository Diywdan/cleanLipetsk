"""Осмотры объекта по заявке.

Осмотр — это контрольное действие: у него есть дата и время, место,
инспекторы и фотоматериал. Первичный осмотр выявляет нарушение, повторный
проверяет, устранено ли оно. Поэтому отдельной сущности не заводится:
осмотр и есть контрольное действие с признаком вида осмотра.

Повторный осмотр по умолчанию повторяет первичный — место, вид действия,
инспектора. Это не «копия документа», а подсказка: инспектор может быть
другим, и всё перечисленное меняется вручную.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ControlAction,
    ControlActionFile,
    ControlActionInspector,
    ControlCase,
    Inspector,
)
from app.models.enums import (
    ControlActionType,
    InspectionKind,
    InspectionResult,
    PhotoKind,
)
from app.services import ru


# Цвет надписи на фотографии выбирает инспектор: белый виден не на каждом
# снимке. Контур всегда контрастен цвету текста и задаётся в разметке.
ANNOTATION_COLORS: dict[str, str] = {
    "white": "белый",
    "black": "чёрный",
    "yellow": "жёлтый",
    "red": "красный",
}

DEFAULT_ANNOTATION_COLOR = "white"

RESULT_TITLES: dict[str, str] = {
    InspectionResult.FIXED.value: "нарушение устранено",
    InspectionResult.NOT_FIXED.value: "нарушение не устранено",
}


def available_kind(db: Session, case_id: int) -> InspectionKind | None:
    """Какой осмотр можно завести по заявке.

    Осмотров не больше двух: первый выявляет нарушение, второй проверяет,
    устранено ли оно. Третий осмотр ничего не решает — по нему нечего
    собирать, поэтому и не предлагается.
    """

    kinds = {action.inspection_kind for action in inspections(db, case_id)}
    if InspectionKind.PRIMARY not in kinds:
        return InspectionKind.PRIMARY
    if InspectionKind.REPEAT not in kinds:
        return InspectionKind.REPEAT
    return None


def can_start(
    db: Session, case_id: int, kind: InspectionKind
) -> tuple[bool, str]:
    """Можно ли завести осмотр этого вида и что сказать, если нельзя."""

    allowed = available_kind(db, case_id)
    if allowed is None:
        return False, "По заявке уже сделаны оба осмотра — первичный и повторный"
    if kind != allowed:
        # Либо осмотр этого вида уже сделан, либо его время ещё не пришло.
        if kind == InspectionKind.REPEAT:
            return False, "Сначала нужен первичный осмотр"
        return False, "Первичный осмотр по заявке уже сделан"
    return True, ""


def inspections(db: Session, case_id: int) -> list[ControlAction]:
    """Все осмотры заявки по порядку."""

    return list(
        db.scalars(
            select(ControlAction)
            .where(ControlAction.control_case_id == case_id)
            .order_by(ControlAction.sequence_no, ControlAction.id)
        )
    )


def by_kind(db: Session, case_id: int, kind: InspectionKind) -> ControlAction | None:
    """Первый осмотр указанного вида."""

    return db.scalars(
        select(ControlAction)
        .where(
            ControlAction.control_case_id == case_id,
            ControlAction.inspection_kind == kind,
        )
        .order_by(ControlAction.sequence_no, ControlAction.id)
    ).first()


def primary(db: Session, case_id: int) -> ControlAction | None:
    return by_kind(db, case_id, InspectionKind.PRIMARY)


def repeat(db: Session, case_id: int) -> ControlAction | None:
    return by_kind(db, case_id, InspectionKind.REPEAT)


def latest(db: Session, case_id: int) -> ControlAction | None:
    """Последний осмотр заявки: по нему собирается очередной пакет."""

    return db.scalars(
        select(ControlAction)
        .where(ControlAction.control_case_id == case_id)
        .order_by(ControlAction.sequence_no.desc(), ControlAction.id.desc())
    ).first()


def photo_file(action: ControlAction, kind: PhotoKind) -> ControlActionFile | None:
    """Файл фотографии осмотра: размеченная копия или исходный снимок."""

    for item in action.files:
        if item.photo_kind == kind:
            return item
    # Снимок, загруженный до появления разметки, вида не имеет — считаем его
    # исходным: размеченную копию можно сделать из него в любой момент.
    if kind == PhotoKind.ORIGINAL and action.files:
        return action.files[0]
    return None


def start(
    db: Session,
    case: ControlCase,
    *,
    kind: InspectionKind,
    inspector: Inspector | None = None,
    started_at: datetime | None = None,
    place_address_id: int | None = None,
    action_type: ControlActionType | None = None,
    copy_from: ControlAction | None = None,
) -> ControlAction:
    """Заводит осмотр: первичный или повторный.

    Для повторного осмотра ``copy_from`` — первичный осмотр: из него берутся
    место, вид действия и инспектор, если их не выбрали явно.
    """

    if copy_from is None and kind == InspectionKind.REPEAT:
        copy_from = primary(db, case.id)

    # Правило «осмотров не больше двух» проверяется и здесь, а не только
    # в интерфейсе: осмотр заводят и скрипты, а третий осмотр по заявке
    # ничего не решает — по нему нечего собирать.
    allowed, reason = can_start(db, case.id, kind)
    if not allowed:
        raise ValueError(reason)

    last = db.scalar(
        select(func.max(ControlAction.sequence_no)).where(
            ControlAction.control_case_id == case.id
        )
    )
    sequence_no = (last or 0) + 1

    place = place_address_id
    if place is None and copy_from is not None:
        place = copy_from.place_address_id
    if place is None:
        control_object = case.control_object
        if control_object is not None and control_object.address is not None:
            place = control_object.address.id

    action = ControlAction(
        control_case_id=case.id,
        sequence_no=sequence_no,
        action_type=(
            action_type
            or (copy_from.action_type if copy_from is not None else None)
            or ControlActionType.INSPECTION
        ),
        started_at=started_at or datetime.now(timezone.utc),
        place_address_id=place,
        inspection_kind=kind,
    )
    db.add(action)
    db.flush()

    # Инспектор осмотра: выбранный, иначе — из первичного осмотра.
    if inspector is None and copy_from is not None:
        for link in copy_from.inspectors:
            db.add(
                ControlActionInspector(
                    control_action_id=action.id, inspector_id=link.inspector_id
                )
            )
    elif inspector is not None:
        db.add(
            ControlActionInspector(
                control_action_id=action.id, inspector_id=inspector.id
            )
        )

    db.flush()
    db.refresh(action)
    return action


def set_result(
    db: Session,
    action: ControlAction,
    result: InspectionResult | str | None,
    *,
    result_text: str | None = None,
) -> None:
    """Записывает результат осмотра.

    Результат есть только у повторного осмотра: первичный нарушение выявляет,
    а не проверяет его устранение.
    """

    if isinstance(result, str):
        result = InspectionResult(result) if result else None
    action.inspection_result = result
    if result_text is not None:
        action.result_text = result_text
    action.is_violation_found = result == InspectionResult.NOT_FIXED


def result_title(action: ControlAction) -> str | None:
    if action.inspection_result is None:
        return None
    return RESULT_TITLES.get(action.inspection_result.value)


def annotation_lines(action: ControlAction, address: str | None) -> list[str]:
    """Надписи на фотографии: адрес объекта и дата со временем осмотра.

    Время берётся то же, что печатается в документах: подпись на снимке
    должна совпадать с протоколом осмотра.
    """

    lines: list[str] = []
    if address:
        lines.append(address)
    if action.started_at is not None:
        lines.append(
            f"{ru.date_short(action.started_at)} {ru.time_short(action.started_at)}"
        )
    return lines
