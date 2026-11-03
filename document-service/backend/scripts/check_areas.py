"""Проверка управ: адреса, инспекторы и видимость заявок.

Проверяется:
  * управа создаётся, в неё добавляются адреса и инспекторы;
  * заявка по адресу управы показывает управу в списке и в карточке;
  * правило видимости: при включённом ограничении инспектор видит заявки
    только по адресам своей управы, руководитель и администратор — все;
  * пока управы не заполнены, ограничение никого не отсекает (иначе
    инспектор увидел бы пустой список и решил бы, что система сломана);
  * удаление неиспользуемой управы и архивирование используемой.

Ограничение включается настройкой RESTRICT_CASES_BY_UPRAVA; в проверке она
переключается прямо в процессе, чтобы не менять настройки сервера.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_areas.py
"""

import http.cookiejar
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlCase,
    ControlObject,
    ControlObjectType,
    Inspector,
    Role,
    Area,
    User,
    UserRole,
)
from app.services import auth as auth_service
from app.services import areas


BASE = "http://127.0.0.1:8000"
ADMIN_EMAIL = "check-areas-admin@local"
ADMIN_PASSWORD = "check-areas-password-2026"
INSPECTOR_EMAIL = "check-areas-inspector@local"
INSPECTOR_PASSWORD = "check-areas-inspector-2026"
AREA_NAME = "Управа проверки"
OUTSIDE_ADDRESS = "398000, Липецкая область, г Липецк, ул. Чужая, д 99"


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def request(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with client.open(req, timeout=240) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.url
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.url


def ensure_user(db, email: str, password: str, role: str, full_name: str) -> int:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        # Снимаем связь со стороны инспектора, чтобы не мешала удалению.
        for linked in db.scalars(select(Inspector).where(Inspector.user_id == user.id)):
            linked.user_id = None
        db.delete(user)
        db.commit()
    user = User(
        full_name=full_name,
        email=email,
        password_hash=auth_service.hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role_row = db.scalar(select(Role).where(Role.code == role))
    if role_row is not None:
        db.add(UserRole(user_id=user.id, role_id=role_row.id))
    db.commit()
    return user.id


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    made: dict[str, object] = {}
    flag_before = settings.restrict_cases_by_uprava
    try:
        demo_case = db.scalar(select(ControlCase).order_by(ControlCase.id))
        if demo_case is None or demo_case.control_object is None:
            print("нет заявки с объектом контроля — проверять нечего")
            return 1
        case_address_id = demo_case.control_object.address_id
        print(f"--- заявка {demo_case.id}, адрес объекта #{case_address_id}")

        # Адрес и заявка вне управы: инспектор не должен их видеть.
        outside = db.scalar(select(Address).where(Address.full_address == OUTSIDE_ADDRESS))
        if outside is None:
            outside = Address(
                full_address=OUTSIDE_ADDRESS, search_key="адрес вне управы для проверки"
            )
            db.add(outside)
            db.commit()
            made["outside_address"] = outside.id
        object_type = db.scalar(
            select(ControlObjectType).order_by(ControlObjectType.sort_order)
        )
        outside_object = ControlObject(
            object_type_id=object_type.id,
            name="объект вне управы (проверка)",
            address_id=outside.id,
        )
        db.add(outside_object)
        db.flush()
        made["outside_object"] = outside_object.id
        outside_case = ControlCase(
            erp_number="00000000000000000001", control_object_id=outside_object.id
        )
        db.add(outside_case)
        db.commit()
        made["outside_case"] = outside_case.id

        inspector = db.scalar(select(Inspector).order_by(Inspector.id))
        if inspector is None:
            print("в справочнике нет инспекторов")
            return 1

        made["admin"] = ensure_user(
            db, ADMIN_EMAIL, ADMIN_PASSWORD, "administrator", "Проверка управ"
        )
        inspector_user_id = ensure_user(
            db, INSPECTOR_EMAIL, INSPECTOR_PASSWORD, "inspector", "Инспектор управы"
        )
        made["inspector_user"] = inspector_user_id
        # Связь учётной записи с сотрудником хранится в карточке инспектора.
        inspector.user_id = inspector_user_id
        db.commit()

        client, _ = make_client()
        _, _, url = request(
            client, "POST", "/ui/login",
            {"login": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if "/ui/login" in url:
            print("не удалось войти")
            return 1
        print("--- вход выполнен")

        # 1. Раздел управ открывается.
        status, html, _ = request(client, "GET", "/ui/areas")
        print(f"--- раздел «Управы»: HTTP {status}")
        if status != 200 or "Новая управа" not in html:
            failures.append("раздел управ не открывается")

        # 2. Управа, адрес и инспектор.
        status, html, url = request(client, "POST", "/ui/areas", {"name": AREA_NAME})
        area = db.scalar(select(Area).where(Area.name == AREA_NAME))
        print(f"--- создание управы: HTTP {status}, номер {area.id if area else None}")
        if area is None:
            failures.append("управа не создана")
            return 1
        made["area"] = area.id

        status, html, url = request(
            client, "POST", f"/ui/areas/{area.id}/addresses",
            {"address_id": str(case_address_id)},
        )
        db.expire_all()
        area = db.get(Area, area.id)
        print(f"--- адрес в управе: HTTP {status}, адресов {len(area.addresses)}")
        if not area.addresses:
            failures.append("адрес не добавился в управу")

        status, html, url = request(
            client, "POST", f"/ui/areas/{area.id}/inspectors",
            {"inspector_id": str(inspector.id)},
        )
        db.expire_all()
        area = db.get(Area, area.id)
        print(
            f"--- инспектор закреплён: HTTP {status}, закреплений {len(area.inspectors)}"
        )
        if not area.inspectors:
            failures.append("инспектор не закрепился за управой")

        # 3. Управа видна в списке заявок и в карточке.
        status, html, _ = request(client, "GET", "/ui")
        in_list = AREA_NAME in html
        status_card, card, _ = request(client, "GET", f"/ui/cases/{demo_case.id}")
        in_card = AREA_NAME in card
        print(f"--- управа в списке заявок: {in_list}, в карточке: {in_card}")
        if not in_list:
            failures.append("управа не показана в списке заявок")
        if not in_card:
            failures.append("управа не показана в карточке заявки")

        # 4. Правило видимости.
        inspector_user = db.get(User, inspector_user_id)
        admin_user = db.get(User, made["admin"])

        settings.restrict_cases_by_uprava = False
        off = areas.visible_address_ids(db, inspector_user)
        settings.restrict_cases_by_uprava = True
        on = areas.visible_address_ids(db, inspector_user)
        for_admin = areas.visible_address_ids(db, admin_user)
        print(
            f"--- ограничение выключено: {off}; включено: адресов {len(on or [])}; "
            f"у администратора: {for_admin}"
        )
        if off is not None:
            failures.append("при выключенной настройке ограничение всё равно работает")
        if not on or case_address_id not in on:
            failures.append("инспектор не получил адрес своей управы")
        if for_admin is not None:
            failures.append("ограничение применилось к администратору")

        db.refresh(demo_case)
        own = areas.can_view_case(db, inspector_user, demo_case)
        foreign = areas.can_view_case(
            db, inspector_user, db.get(ControlCase, made["outside_case"])
        )
        print(
            f"--- заявка своей управы видна: {own}; "
            f"заявка с чужого адреса видна: {foreign}"
        )
        if not own:
            failures.append("инспектор не видит заявку своей управы")
        if foreign:
            failures.append("инспектор видит заявку с чужого адреса")

        # Инспектор без управ не должен остаться без заявок вовсе.
        free_user = User(full_name="Инспектор без управ", is_active=True)
        db.add(free_user)
        db.commit()
        free = areas.visible_address_ids(db, free_user)
        print(f"--- инспектор без управ: ограничений нет — {free is None}")
        if free is not None:
            failures.append("инспектор без управ остался без заявок")
        db.delete(free_user)
        db.commit()

        # 5. Удаление неиспользуемой управы и архив используемой.
        request(client, "POST", "/ui/areas", {"name": "Управа без адресов"})
        empty = db.scalar(select(Area).where(Area.name == "Управа без адресов"))
        empty_id = empty.id  # запомним до удаления: после него объект уже не читается
        status, html, url = request(
            client, "POST", f"/ui/dictionaries/areas/{empty_id}/delete", {}
        )
        db.expire_all()
        deleted = db.get(Area, empty_id) is None
        print(f"--- удаление управы без адресов: HTTP {status}, удалена: {deleted}")
        if not deleted:
            failures.append("неиспользуемая управа не удалилась")

        status, html, url = request(
            client, "POST", f"/ui/dictionaries/areas/{area.id}/delete", {}
        )
        db.expire_all()
        after = db.get(Area, area.id)
        print(
            f"--- удаление управы с адресами: HTTP {status}, осталась: "
            f"{after is not None}, в архиве: {after is not None and not after.is_active}"
        )
        if after is None:
            failures.append("используемая управа удалена вместо архива")
        elif after.is_active:
            failures.append("используемая управа не переведена в архив")
        request(client, "POST", f"/ui/dictionaries/areas/{area.id}/restore", {})
        db.expire_all()
        if not db.get(Area, area.id).is_active:
            failures.append("управа не вернулась из архива")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  управы: адреса, инспекторы и правило видимости работают")
        return 0
    finally:
        settings.restrict_cases_by_uprava = flag_before
        for key, model in (
            ("outside_case", ControlCase),
            ("outside_object", ControlObject),
            ("area", Area),
            ("outside_address", Address),
        ):
            if key in made:
                entity = db.get(model, made[key])
                if entity is not None:
                    db.delete(entity)
        db.commit()
        empty = db.scalar(select(Area).where(Area.name == "Управа без адресов"))
        if empty is not None:
            db.delete(empty)
            db.commit()
        for key in ("admin", "inspector_user"):
            if key in made:
                user = db.get(User, made[key])
                if user is not None:
                    for linked in db.scalars(
                        select(Inspector).where(Inspector.user_id == user.id)
                    ):
                        linked.user_id = None
                    db.delete(user)
        db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
