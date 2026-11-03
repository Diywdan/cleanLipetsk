"""Управы: закрепление адресов за инспекторами и видимость заявок.

Управа нужна ради двух вещей:

* понять, кто отвечает за адрес, — это видно в карточке заявки;
* показывать инспектору только заявки по его адресам.

Второе включается настройкой `RESTRICT_CASES_BY_UPRAVA` и по умолчанию
выключено: пока управы не заполнены, ограничение скрыло бы от инспекторов
все заявки. Руководитель и администратор видят все заявки независимо
от настройки.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ControlCase,
    ControlObject,
    Inspector,
    Area,
    AreaAddress,
    AreaInspector,
    User,
)
from app.services import auth


def areas_for_address(db: Session, address_id: int | None) -> list[Area]:
    """Действующие управы, в которые входит адрес."""

    if address_id is None:
        return []
    return list(
        db.scalars(
            select(Area)
            .join(AreaAddress, AreaAddress.area_id == Area.id)
            .where(
                AreaAddress.address_id == address_id,
                Area.is_active.is_(True),
            )
            .order_by(Area.name)
        )
    )


def case_address_id(case: ControlCase) -> int | None:
    """Адрес, по которому заявка относится к управе.

    Это адрес объекта контроля; если его нет — адрес нарушения.
    """

    if case.control_object is not None and case.control_object.address_id:
        return case.control_object.address_id
    violations = getattr(case, "violations", None) or []
    for violation in violations:
        if violation.address_id:
            return violation.address_id
    return None


def case_areas(db: Session, case: ControlCase) -> list[Area]:
    return areas_for_address(db, case_address_id(case))


def inspector_for_user(db: Session, user: User) -> Inspector | None:
    """Сотрудник, связанный с учётной записью.

    Связь хранится в справочнике инспекторов (`inspectors.user_id`), а не
    в пользователе: так учётная запись остаётся учётной записью, а сотрудник —
    сотрудником, и вторая связь между теми же таблицами не нужна.
    """

    if user is None:
        return None
    return db.scalars(
        select(Inspector).where(Inspector.user_id == user.id)
    ).first()


def inspector_areas(db: Session, inspector_id: int | None) -> list[Area]:
    """Действующие управы инспектора: период закрепления ещё не закончился."""

    if inspector_id is None:
        return []
    today = date.today()
    return list(
        db.scalars(
            select(Area)
            .join(AreaInspector, AreaInspector.area_id == Area.id)
            .where(
                AreaInspector.inspector_id == inspector_id,
                or_(
                    AreaInspector.valid_to.is_(None),
                    AreaInspector.valid_to >= today,
                ),
                Area.is_active.is_(True),
            )
            .order_by(Area.name)
        )
    )


def restriction_enabled() -> bool:
    return bool(getattr(settings, "restrict_cases_by_uprava", False))


def visible_address_ids(db: Session, user: User) -> list[int] | None:
    """Адреса, доступные пользователю. None — ограничений нет.

    Ограничение не применяется к администратору и руководителю: им нужен
    обзор по всем управам.
    """

    if not restriction_enabled():
        return None
    if user is None or auth.is_administrator(user) or auth.has_role(user, "manager"):
        return None

    inspector = inspector_for_user(db, user)
    if inspector is None:
        # Учётная запись не связана с сотрудником — ограничивать нечем.
        return None

    areas = inspector_areas(db, inspector.id)
    if not areas:
        # Управы не заданы — показываем всё, иначе инспектор не увидел бы
        # ни одной заявки и решил бы, что система пуста.
        return None

    area_ids = [area.id for area in areas]
    return list(
        db.scalars(
            select(AreaAddress.address_id).where(
                AreaAddress.area_id.in_(area_ids)
            )
        )
    )


def visible_cases_statement(db: Session, user: User, statement):
    """Ограничивает выборку заявок адресами управ пользователя."""

    address_ids = visible_address_ids(db, user)
    if address_ids is None:
        return statement

    object_ids = select(ControlObject.id).where(
        ControlObject.address_id.in_(address_ids)
    )
    return statement.where(ControlCase.control_object_id.in_(object_ids))


def can_view_case(db: Session, user: User, case: ControlCase) -> bool:
    address_ids = visible_address_ids(db, user)
    if address_ids is None:
        return True
    return case_address_id(case) in address_ids
