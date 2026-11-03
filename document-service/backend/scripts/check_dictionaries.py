"""Проверка справочников: добавление из формы, правка, адреса.

Проверяется то, ради чего справочники переделывались:
  * значение добавляется из формы заявки, не уходя со страницы (JSON-адреса);
  * значение можно поправить, а не только создать;
  * адрес вводится строкой и заводится сам, повторный ввод не плодит дубли;
  * адреса ищутся по части строки — улице и дому.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_dictionaries.py
"""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlBody,
    ControlBodySignatory,
    ControlCaseInspector,
    ControlObject,
    ControlObjectType,
    Inspector,
    Organization,
    OrganizationSignatory,
    OrganizationUnit,
    Role,
    User,
    UserRole,
)
from app.services import addresses as address_service
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-dict@local"
CHECK_PASSWORD = "check-dict-password-2026"

NEW_ADDRESS = "398600, Липецкая область, г Липецк, ул. Справочная, д 7"
SAME_ADDRESS_OTHER_SPELLING = "398600, липецкая область, г. Липецк, ул. Справочная, д. 7"
ORG_NAME = "ООО «Проверка добавления»"


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


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    made: dict[str, object] = {}
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка справочников",
            email=CHECK_EMAIL,
            password_hash=auth_service.hash_password(CHECK_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "inspector"))
        if role is not None:
            db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        made["user"] = user.id

        client, _ = make_client()
        _, _, url = request(
            client, "POST", "/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD},
        )
        if "/ui/login" in url:
            print("не удалось войти")
            return 1
        print("--- вход выполнен")

        # 1. Добавление значения из формы: тот же адрес, что использует форма.
        status, body, _ = request(
            client, "POST", "/api/dictionaries/inspectors",
            {
                "full_name": "Добавленный Из Формы",
                "position": "консультант",
                "field": "inspector_id",
            },
        )
        payload = json.loads(body) if status == 200 else {}
        print(
            f"--- добавление инспектора через API: HTTP {status}, "
            f"номер {payload.get('id')}, подпись «{payload.get('label')}», "
            f"поле {payload.get('field')}"
        )
        if status != 200 or not payload.get("id"):
            failures.append(f"значение не добавилось из формы: {body[:200]}")
        else:
            made["inspector"] = payload["id"]
            if payload.get("field") != "inspector_id":
                failures.append("ответ не указал поле формы для подстановки")

        status, body, _ = request(
            client, "POST", "/api/dictionaries/organizations",
            {
                "short_name": ORG_NAME,
                "inn": "4800000011",
                "legal_address": NEW_ADDRESS,
                "email": "dict-check@example.ru",
            },
        )
        result = json.loads(body) if status == 200 else {}
        print(f"--- добавление организации через API: HTTP {status}, номер {result.get('id')}")
        if status != 200:
            failures.append(f"организация не добавилась: {body[:200]}")
        else:
            made["organization"] = result["id"]
            organization = db.get(Organization, result["id"])
            requisites = [
                item for item in organization.requisites if item.valid_to is None
            ]
            if not requisites:
                failures.append("реквизиты не завелись вместе с организацией")
            else:
                print(
                    f"    реквизиты: ИНН {requisites[0].inn}, "
                    f"адрес #{requisites[0].legal_address_id}"
                )
                if requisites[0].legal_address_id is None:
                    failures.append("юридический адрес не привязался")

        # 2. Адрес заводится сам и не дублируется. Адрес уже мог появиться при
        #    создании организации (он же был её юридическим адресом), поэтому
        #    считаем не прирост, а число записей об этом адресе.
        ids = []
        for text in (NEW_ADDRESS, SAME_ADDRESS_OTHER_SPELLING):
            status, body, _ = request(
                client, "POST", "/api/dictionaries/addresses", {"full_address": text}
            )
            if status != 200:
                failures.append(f"адрес не сохранился: {body[:200]}")
            else:
                ids.append(json.loads(body)["id"])

        key = address_service.normalize(NEW_ADDRESS)
        matches = db.scalar(
            select(func.count()).select_from(Address).where(Address.search_key == key)
        )
        print(
            f"--- адрес строкой: записей об этом адресе {matches}, "
            f"обе записи — #{ids} (одна и та же запись, дублей нет)"
        )
        if matches != 1:
            failures.append(f"об одном адресе заведено записей: {matches}")
        if len(set(ids)) != 1:
            failures.append(f"разное написание дало разные записи: {ids}")

        found = address_service.find_by_text(db, NEW_ADDRESS)
        if found is None:
            failures.append("адрес не находится по строке")
        else:
            made["address"] = found.id

        # 3. Правка значения, а не только создание.
        inspector_id = made.get("inspector")
        status, body, _ = request(
            client, "POST", "/ui/dictionaries/inspectors",
            {
                "id": str(inspector_id),
                "full_name": "Добавленный Из Формы",
                "position": "главный консультант",
                "position_instrumental": "главным консультантом",
            },
        )
        db.expire_all()
        inspector = db.get(Inspector, inspector_id)
        print(
            f"--- правка инспектора: HTTP {status}, должность теперь "
            f"«{inspector.position}»"
        )
        if inspector.position != "главный консультант":
            failures.append("правка значения не сохранилась")
        if inspector.position_instrumental != "главным консультантом":
            failures.append("дополнительное поле при правке не сохранилось")

        # 4. Правка объекта: адрес меняется строкой.
        object_type = db.scalar(select(ControlObjectType).order_by(ControlObjectType.sort_order))
        status, body, _ = request(
            client, "POST", "/api/dictionaries/objects",
            {
                "object_type_id": str(object_type.id),
                "name": "объект для проверки справочника",
                "name_genitive": "объекта для проверки справочника",
                "address": NEW_ADDRESS,
            },
        )
        result = json.loads(body) if status == 200 else {}
        print(f"--- объект с адресом строкой: HTTP {status}, номер {result.get('id')}")
        if status != 200:
            failures.append(f"объект не добавился: {body[:200]}")
        else:
            made["object"] = result["id"]
            control_object = db.get(ControlObject, result["id"])
            if control_object.address_id is None:
                failures.append("адрес объекта не привязался по строке")

        # 5. Поиск по улице и дому.
        status, html, _ = request(
            client, "GET", "/ui/dictionaries?q=" + urllib.parse.quote("Справочная")
        )
        print(f"--- поиск адреса по улице: HTTP {status}")
        if "Справочная" not in html:
            failures.append("адрес не находится поиском по улице")
        if "Советская" in html:
            failures.append("поиск показывает адреса, не подходящие под запрос")

        status, html, _ = request(
            client, "GET", "/ui/dictionaries?q=" + urllib.parse.quote("справочная 7")
        )
        print(f"--- поиск по улице и дому: HTTP {status}, найден: {'Справочная' in html}")
        if "Справочная" not in html:
            failures.append("поиск по улице и дому не работает")

        # 6. Форма заявки: адрес теперь поле с подсказками, а рядом со списками
        #    есть кнопка добавления значения.
        status, html, _ = request(client, "GET", "/ui/cases/7/edit")
        for needle, title in (
            ('list="address-options"', "поле адреса с подсказками"),
            ("data-add-submit", "кнопки добавления значений"),
            ("/api/dictionaries/", "адрес программного интерфейса справочников"),
        ):
            found_flag = needle in html
            print(f"    форма заявки, {title}: {'есть' if found_flag else 'НЕТ'}")
            if not found_flag:
                failures.append(f"в форме заявки нет: {title}")

        # 7. Удаление неиспользуемого и архивирование используемого значения.
        status, body, _ = request(
            client, "POST", "/api/dictionaries/inspectors",
            {"full_name": "Никем Не Используемый", "position": "специалист"},
        )
        unused_id = json.loads(body)["id"] if status == 200 else None
        print(f"--- неиспользуемый инспектор: номер {unused_id}")
        if unused_id is None:
            failures.append("не удалось создать инспектора для проверки удаления")
        else:
            status, html, url = request(
                client, "POST", f"/ui/dictionaries/inspectors/{unused_id}/delete", {}
            )
            db.expire_all()
            gone = db.get(Inspector, unused_id) is None
            print(f"--- удаление неиспользуемого: HTTP {status}, запись удалена: {gone}")
            if not gone:
                failures.append("неиспользуемое значение не удалилось")

        # Инспектор из уже созданной заявки удалён быть не может.
        used_id = db.scalar(
            select(ControlCaseInspector.inspector_id).order_by(ControlCaseInspector.id)
        )
        if used_id is None:
            print("--- нет заявок с инспекторами: проверка архива пропущена")
        else:
            used = db.get(Inspector, used_id)
            before_references = db.scalar(
                select(func.count())
                .select_from(ControlCaseInspector)
                .where(ControlCaseInspector.inspector_id == used_id)
            )
            status, html, url = request(
                client, "POST", f"/ui/dictionaries/inspectors/{used_id}/delete", {}
            )
            db.expire_all()
            used = db.get(Inspector, used_id)
            archived = used is not None and not used.is_active
            print(
                f"--- удаление используемого инспектора №{used_id}: HTTP {status}, "
                f"остался в базе: {used is not None}, в архиве: {archived}"
            )
            if used is None:
                failures.append("используемое значение удалено — история сломана")
            elif not archived:
                failures.append("используемое значение не переведено в архив")
            if "архив" not in urllib.parse.unquote(url):
                failures.append("в сообщении не сказано, что значение ушло в архив")

            after_references = db.scalar(
                select(func.count())
                .select_from(ControlCaseInspector)
                .where(ControlCaseInspector.inspector_id == used_id)
            )
            print(
                f"    ссылки в заявках сохранены: {before_references} → {after_references}"
            )
            if before_references != after_references:
                failures.append("ссылки из заявок пропали при архивировании")

            status, html, _ = request(client, "GET", "/ui/cases/new")
            # Ищем строго внутри списка инспекторов: такой же номер может
            # встретиться в другом списке (например, у организации).
            select_html = re.search(
                r'name="inspector_id".*?</select>', html, re.S
            )
            option_present = select_html is not None and (
                f'value="{used_id}"' in select_html.group(0)
            )
            print(
                f"--- архивный инспектор в списке формы заявки: "
                f"{'виден' if option_present else 'скрыт'}"
            )
            if option_present:
                failures.append("архивное значение предлагается при создании заявки")

            status, html, url = request(
                client, "POST", f"/ui/dictionaries/inspectors/{used_id}/restore", {}
            )
            db.expire_all()
            used = db.get(Inspector, used_id)
            print(f"--- возврат из архива: HTTP {status}, активен: {used.is_active}")
            if not used.is_active:
                failures.append("значение не вернулось из архива")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  справочники: добавление из формы, правка, адреса и поиск работают")
        return 0
    finally:
        # Страховка: если проверка прервалась на середине, инспектор из
        # существующей заявки не должен остаться в архиве.
        used_id = db.scalar(
            select(ControlCaseInspector.inspector_id).order_by(ControlCaseInspector.id)
        )
        if used_id is not None:
            person = db.get(Inspector, used_id)
            if person is not None and not person.is_active:
                person.is_active = True
                db.commit()
                print("инспектор из заявки возвращён из архива (страховка)")
        for key, model in (
            ("object", ControlObject),
            ("organization", Organization),
            ("inspector", Inspector),
        ):
            if key in made:
                entity = db.get(model, made[key])
                if entity is not None:
                    db.delete(entity)
        db.commit()
        if "user" in made:
            user = db.get(User, made["user"])
            if user is not None:
                db.delete(user)
                db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
