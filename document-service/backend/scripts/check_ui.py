"""Проверка входа и работы интерфейса: логин -> заявка -> пакет -> архив -> выход.

Скрипт проходит путь оператора целиком: проверяет, что без входа страницы
недоступны, входит под временным пользователем, копирует заявку, формирует
пакет, скачивает архив и выходит. Временный пользователь удаляется в конце.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_ui.py
"""

import http.cookiejar
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlAction,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    Decision,
    Document,
    Organization,
    Prescription,
    Role,
    User,
    UserRole,
    UserSession,
    Violation,
)
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-ui@local"
CHECK_PASSWORD = "check-ui-password-2026"
ADMIN_EMAIL = "check-admin@local"
ADMIN_PASSWORD = "check-admin-password-2026"
OPERATOR_EMAIL = "check-operator@local"
OBSERVER_EMAIL = "check-observer@local"
OBSERVER_PASSWORD = "check-observer-password-2026"

# Заявка-образец для копирования: демонстрационное дело, в котором заполнены
# все поля и уже собран первичный пакет — скопированная заявка сразу готова к
# сборке. «Последняя заявка в базе» для этого не годится: ею может оказаться
# заявка без документов, по которой пакет собирать и не должны.
SOURCE_CASE_ID = 7


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)
    ), jar


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


class FormParser(HTMLParser):
    """Собирает значения формы так, как их отправил бы браузер."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, object] = {}
        self._select: str | None = None
        self._select_multiple = False
        self._selected: list[str] = []
        self._textarea: str | None = None
        self._textarea_text: list[str] = []
        self._option_value: str | None = None
        self._option_selected = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input":
            name = attributes.get("name")
            if not name or attributes.get("type") in {"submit", "button"}:
                return
            if attributes.get("type") in {"checkbox", "radio"}:
                if "checked" in attributes:
                    self.fields[name] = attributes.get("value", "on")
                return
            self.fields[name] = attributes.get("value", "")
        elif tag == "select":
            self._select = attributes.get("name")
            self._select_multiple = "multiple" in attributes
            self._selected = []
        elif tag == "option" and self._select:
            self._option_value = attributes.get("value", "")
            self._option_selected = "selected" in attributes
        elif tag == "textarea":
            self._textarea = attributes.get("name")
            self._textarea_text = []

    def handle_data(self, data):
        if self._textarea:
            self._textarea_text.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._select and self._option_value is not None:
            if self._option_selected:
                self._selected.append(self._option_value)
            self._option_value = None
        elif tag == "select" and self._select:
            if self._select_multiple:
                self.fields[self._select] = list(self._selected)
            else:
                self.fields[self._select] = self._selected[0] if self._selected else ""
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.fields[self._textarea] = "".join(self._textarea_text).strip()
            self._textarea = None


def ensure_check_user(db, email: str, password: str, role_code: str, full_name: str) -> int:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
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
    role = db.scalar(select(Role).where(Role.code == role_code))
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user.id


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    new_case_id = None
    check_user_id = None
    organization_id = None
    try:
        source_id = db.get(ControlCase, SOURCE_CASE_ID)
        if source_id is None:
            print(f"нет заявки-образца {SOURCE_CASE_ID} для копирования")
            return 1
        source_id = source_id.id
        check_user_id = ensure_check_user(
            db, CHECK_EMAIL, CHECK_PASSWORD, "manager", "Проверка интерфейса"
        )
        admin_user_id = ensure_check_user(
            db, ADMIN_EMAIL, ADMIN_PASSWORD, "administrator", "Проверка администратора"
        )
        observer_user_id = ensure_check_user(
            db, OBSERVER_EMAIL, OBSERVER_PASSWORD, "observer", "Проверка наблюдателя"
        )
        print(
            f"--- временные пользователи: {check_user_id}, {admin_user_id}, "
            f"{observer_user_id}"
        )

        anon, _ = make_client()
        status, html, url = request(anon, "GET", "/ui")
        print(f"--- без входа /ui: HTTP {status}, итоговый адрес {url}")
        if "/ui/login" not in url:
            failures.append("страница заявок доступна без входа")

        status, html, _ = request(anon, "GET", "/ui/login")
        print(f"--- страница входа: HTTP {status}")
        if status != 200 or "Войти" not in html:
            failures.append("страница входа не отдаётся")

        status, html, _ = request(
            anon, "POST", "/ui/login",
            {"login": CHECK_EMAIL, "password": "неверный-пароль"},
        )
        print(f"--- вход с неверным паролем: HTTP {status}")
        if status != 401:
            failures.append(f"неверный пароль принят: HTTP {status}")

        client, jar = make_client()
        status, html, url = request(
            client, "POST", "/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD},
        )
        cookies = [cookie.name for cookie in jar]
        print(f"--- вход: HTTP {status}, адрес {url}, куки {cookies}")
        if "/ui/login" in url:
            failures.append("вход не выполнен")
        if auth_service.SESSION_COOKIE not in cookies:
            failures.append("сессионная кука не выдана")

        status, html, _ = request(client, "GET", "/ui")
        print(f"--- список заявок под сессией: HTTP {status}")
        if "Проверка интерфейса" not in html:
            failures.append("в шапке нет имени вошедшего пользователя")

        status, html, _ = request(client, "GET", f"/ui/cases/{source_id}/copy")
        parser = FormParser()
        parser.feed(html)
        fields = dict(parser.fields)
        fields["erp_number"] = "77770000888899990000"
        # Внутренний номер присваивает система: в форме его больше нет,
        # а присланное значение сервер игнорирует.
        fields["case_number"] = "000000-подделка"

        status, html, url = request(client, "POST", "/ui/cases", fields)
        match = re.search(r"/ui/cases/(\d+)", url)
        print(f"--- создание заявки копированием: HTTP {status}, {url}")
        if not match:
            failures.append("заявка не создана")
        else:
            new_case_id = int(match.group(1))

            # Документы формируются по требованию: только что созданная заявка
            # не должна выглядеть недоделанной. В карточке — спокойная строка и
            # кнопка, а списка «чего не хватает» по умолчанию нет: он
            # показывается, когда пакет собирают.
            for needle, title in (
                (
                    "Документы по заявке не формируются",
                    "строка «документы по заявке не формируются»",
                ),
                ("Создать пакет документов", "кнопка «Создать пакет документов»"),
            ):
                found = needle in html
                print(f"    {title}: {'есть' if found else 'НЕТ'}")
                if not found:
                    failures.append(f"в карточке новой заявки нет: {title}")
            for needle, title in (
                ("Пакет пока нельзя сформировать", "требование документов"),
                ("Пакет пока не собрался", "список недостающего до сборки"),
            ):
                if needle in html:
                    failures.append(f"карточка показывает {title}, хотя пакет не собирали")

            status, html, _ = request(
                client, "POST", f"/ui/cases/{new_case_id}/packages", {}
            )
            documents = re.findall(r"/api/documents/(\d+)/file", html)
            print(f"--- формирование пакета: HTTP {status}, документов {len(documents)}")
            if len(documents) != 6:
                failures.append(f"в карточке {len(documents)} документов вместо 6")

            # Сохранение в папку: кнопка показывается скриптом, поэтому на
            # странице должны быть и сама кнопка, и вызов выбора папки.
            for needle, title in (
                ('id="save-to-folder"', "кнопка сохранения в папку"),
                ("showDirectoryPicker", "выбор папки в браузере"),
                ("/files", "список файлов пакета"),
            ):
                found = needle in html
                print(f"    {title}: {'есть' if found else 'НЕТ'}")
                if not found:
                    failures.append(f"в карточке нет: {title}")

            archive_match = re.search(r"/api/packages/(\d+)/archive", html)
            if not archive_match:
                failures.append("нет ссылки на архив")
            else:
                req = urllib.request.Request(
                    BASE + f"/api/packages/{archive_match.group(1)}/archive"
                )
                with client.open(req, timeout=120) as response:
                    data = response.read()
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    names = archive.namelist()
                print(f"--- архив: {len(names)} файлов, папка {names[0].split('/')[0]}")
                if len([n for n in names if n.endswith(".docx")]) != 6:
                    failures.append("в архиве не 6 документов")

            # Число листов: проставляем у акта через интерфейс, пересобираем
            # пакет и проверяем, что направление печатает «на 5 л.»
            act_id = None
            for row_html in html.split("<tr>"):
                id_match = re.search(r"/ui/documents/(\d+)/pages", row_html)
                if not id_match:
                    continue
                cells = re.findall(r"<td>\s*([^<]*?)\s*</td>", row_html, re.S)
                if len(cells) > 1 and "Акт" in cells[1]:
                    act_id = int(id_match.group(1))

            if act_id is None:
                failures.append("в карточке не найден документ «Акт»")
            else:
                status, html, url = request(
                    client, "POST", f"/ui/documents/{act_id}/pages", {"pages": "5"}
                )
                document = db.get(Document, act_id)
                print(f"--- число листов акта: HTTP {status}, в базе: {document.pages}")
                if document.pages != 5:
                    failures.append("число листов не сохранилось")

                status, html, _ = request(
                    client, "POST", f"/ui/cases/{new_case_id}/packages", {}
                )
                archive_match = re.search(r"/api/packages/(\d+)/archive", html)
                if not archive_match:
                    failures.append("после пересборки нет ссылки на архив")
                else:
                    req = urllib.request.Request(
                        BASE + f"/api/packages/{archive_match.group(1)}/archive"
                    )
                    with client.open(req, timeout=120) as response:
                        data = response.read()
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        direction_name = [
                            n for n in archive.namelist() if "Направление" in n
                        ]
                        direction_text = ""
                        if direction_name:
                            from docx import Document as DocxDocument

                            doc = DocxDocument(io.BytesIO(archive.read(direction_name[0])))
                            direction_text = "\n".join(
                                paragraph.text for paragraph in doc.paragraphs
                            )
                    # Направление должно печатать фактическое число листов,
                    # а не место для рукописной записи. Сравниваем с числом,
                    # посчитанным у акта в этом же (новом) пакете.
                    printed = re.search(r"на (\d+) л\.", direction_text)
                    new_package_id = int(archive_match.group(1))
                    act_in_package = next(
                        (
                            item
                            for item in db.scalars(
                                select(Document).where(
                                    Document.package_id == new_package_id
                                )
                            )
                            if item.document_type.code == "act"
                        ),
                        None,
                    )
                    counted = act_in_package.pages if act_in_package else None
                    print(
                        f"--- направление печатает число листов: "
                        f"{printed.group(0) if printed else 'НЕТ'} "
                        f"(посчитано у акта: {counted})"
                    )
                    if printed is None:
                        failures.append("число листов не попало в направление")
                    elif counted is None:
                        failures.append("у акта не посчитано число листов")
                    elif int(printed.group(1)) != counted:
                        failures.append(
                            "направление печатает не то число листов, "
                            "что посчитано у акта"
                        )

            status, form_html, _ = request(
                client, "GET", f"/ui/cases/{new_case_id}/edit"
            )
            print(f"--- форма редактирования: HTTP {status}")
            edit_parser = FormParser()
            edit_parser.feed(form_html)
            edit_fields = dict(edit_parser.fields)
            edit_fields["purpose"] = "Изменённая цель проверки"
            edit_fields["subject"] = "Изменённый предмет проверки"

            status, html, url = request(
                client, "POST", f"/ui/cases/{new_case_id}", edit_fields
            )
            print(f"--- сохранение изменений: HTTP {status}, {url}")
            if "Изменённая цель проверки" not in html:
                failures.append("изменения не сохранились")

            nested = (
                (ControlCaseBase, "оснований"),
                (ControlCaseInspector, "инспекторов"),
                (ControlAction, "действий"),
                (Violation, "нарушений"),
                (Prescription, "предписаний"),
                (Decision, "решений"),
            )
            for model, title in nested:
                count = db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.control_case_id == new_case_id)
                )
                print(f"    {title}: {count}")
                if count > 1:
                    failures.append(
                        f"после сохранения формы {title} стало {count} — дубли"
                    )

        # Наполнение справочника организаций: вместе с организацией сразу
        # должны завестись реквизиты и почта, а из карточки — подразделение,
        # представитель и роль.
        status, html, _ = request(client, "GET", "/ui/dictionaries")
        print(f"--- справочники: HTTP {status}")
        for needle in ("Организации", "Инспекторы", "Утверждающие лица", "Адреса", "Объекты контроля"):
            if needle not in html:
                failures.append(f"в справочниках нет раздела «{needle}»")

        address_id = db.scalar(select(Address.id).order_by(Address.id))
        organization_id = None
        status, html, url = request(
            client, "POST", "/ui/dictionaries/organizations",
            {
                "short_name": "ООО «Проверка справочника»",
                "full_name": "ООО «Проверка справочника»",
                "kind": "legal_entity",
                "inn": "7701234567",
                "kpp": "770101001",
                "legal_address_id": str(address_id) if address_id else "",
                "email": "check-org@example.ru",
            },
        )
        match = re.search(r"/ui/dictionaries/organizations/(\d+)", url)
        print(f"--- создание организации: HTTP {status}, {url}")
        if not match:
            failures.append("организация не создана")
        else:
            organization_id = int(match.group(1))
            if "Реквизитов нет" in html:
                failures.append("реквизиты не завелись вместе с организацией")
            if "Почты нет" in html:
                failures.append("почта не завелась вместе с организацией")
            else:
                print("    реквизиты и почта заведены")

            status, html, _ = request(
                client, "POST",
                f"/ui/dictionaries/organizations/{organization_id}/units",
                {"kind": "branch", "name": "филиал «Проверка»", "email": "branch@example.ru"},
            )
            print(f"--- подразделение: HTTP {status}, видно: {'филиал «Проверка»' in html}")
            if "филиал «Проверка»" not in html:
                failures.append("подразделение не добавилось")

            status, html, _ = request(
                client, "POST",
                f"/ui/dictionaries/organizations/{organization_id}/representatives",
                {"full_name": "Проверкин П.П.", "position": "Директор", "basis_kind": "charter"},
            )
            print(f"--- представитель: HTTP {status}, видно: {'Проверкин П.П.' in html}")
            if "Проверкин П.П." not in html:
                failures.append("представитель не добавился")

            status, html, _ = request(
                client, "POST",
                f"/ui/dictionaries/organizations/{organization_id}/roles",
                {"role": "managing_organization"},
            )
            print(f"--- роль: HTTP {status}, видно: {'managing_organization' in html}")
            if "managing_organization" not in html:
                failures.append("роль не добавилась")

        # Раздел пользователей: обычному сотруднику закрыт, администратору открыт.
        status, html, url = request(client, "GET", "/ui/users")
        print(f"--- /ui/users под инспектором: HTTP {status}, {url}")
        if status != 200 or "/ui?err=" not in url:
            failures.append(
                f"раздел пользователей не закрыт для не-администратора: {status} {url}"
            )

        status, html, url = request(client, "GET", "/ui/audit")
        print(f"--- /ui/audit под инспектором: HTTP {status}, {url}")
        if status != 200 or "/ui?err=" not in url:
            failures.append(f"журнал открыт для не-администратора: {status} {url}")

        admin_client, _ = make_client()
        _, _, admin_url = request(
            admin_client, "POST", "/ui/login",
            {"login": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if "/ui/login" in admin_url:
            failures.append("администратор не смог войти")
        status, html, _ = request(admin_client, "GET", "/ui/users")
        print(f"--- /ui/users под администратором: HTTP {status}")
        if status != 200 or "Новый пользователь" not in html:
            failures.append("администратору раздел пользователей недоступен")

        status, html, _ = request(
            admin_client, "POST", "/ui/users",
            {
                "full_name": "Проверка оператора",
                "email": OPERATOR_EMAIL,
                "position": "Специалист",
                "password": "operator-password-2026",
                "role_code": "manager",
            },
        )
        operator = db.scalar(select(User).where(User.email == OPERATOR_EMAIL))
        print(f"--- создание оператора: HTTP {status}, id={operator.id if operator else None}")
        if operator is None:
            failures.append("оператор не создан из интерфейса")
        else:
            if not auth_service.verify_password(
                "operator-password-2026", operator.password_hash
            ):
                failures.append("пароль оператора сохранён неверно")
            if not any(
                link.role and link.role.code == "manager" for link in operator.roles
            ):
                failures.append("оператору не выдана роль")

            status, html, _ = request(
                admin_client, "POST", f"/ui/users/{operator.id}/password",
                {"password": "operator-new-password-2026"},
            )
            db.refresh(operator)
            changed = auth_service.verify_password(
                "operator-new-password-2026", operator.password_hash
            )
            print(f"--- смена пароля: HTTP {status}, новый пароль работает: {changed}")
            if not changed:
                failures.append("пароль не сменился")

            status, html, _ = request(
                admin_client, "POST", f"/ui/users/{operator.id}/active",
                {"is_active": "0"},
            )
            db.refresh(operator)
            print(f"--- блокировка: HTTP {status}, активен: {operator.is_active}")
            if operator.is_active:
                failures.append("пользователь не заблокирован")

            blocked_client, _ = make_client()
            _, _, blocked_url = request(
                blocked_client, "POST", "/ui/login",
                {"login": OPERATOR_EMAIL, "password": "operator-new-password-2026"},
            )
            print(f"--- вход заблокированного: {blocked_url}")
            if "/ui/login" not in blocked_url:
                failures.append("заблокированный пользователь вошёл в систему")

            # Журнал: в нём должны быть следы всех действий этого прогона.
            status, html, _ = request(admin_client, "GET", "/ui/audit")
            print(f"--- /ui/audit под администратором: HTTP {status}")
            expected = {
                "создание заявки": "создана заявка",
                "изменение заявки": "изменено полей",
                "сборка пакета": "собран пакет «Первичное предписание»",
                "создание пользователя": "создан пользователь",
                "блокировка": "заблокирован",
                "правка справочника": "добавлена организация",
            }
            for title, needle in expected.items():
                found = needle in html
                print(f"    {title}: {'есть' if found else 'НЕТ'}")
                if not found:
                    failures.append(f"в журнале нет записи «{needle}»")

            session_id = db.scalar(
                select(UserSession.id)
                .where(UserSession.user_id == admin_user_id)
                .order_by(UserSession.id.desc())
            )
            status, html, url = request(
                admin_client, "POST", f"/ui/sessions/{session_id}/revoke", {}
            )
            print(f"--- закрытие своей сессии: HTTP {status}, {url}")
            status, html, url = request(admin_client, "GET", "/ui")
            if "/ui/login" not in url:
                failures.append("закрытая сессия продолжает работать")

        # Наблюдатель: смотреть можно, менять — нет.
        observer_client, _ = make_client()
        _, _, observer_url = request(
            observer_client, "POST", "/ui/login",
            {"login": OBSERVER_EMAIL, "password": OBSERVER_PASSWORD},
        )
        if "/ui/login" in observer_url:
            failures.append("наблюдатель не смог войти")

        status, html, _ = request(observer_client, "GET", "/ui")
        print(f"--- наблюдатель читает список заявок: HTTP {status}")
        if status != 200:
            failures.append("наблюдателю закрыт просмотр заявок")

        status, html, url = request(observer_client, "POST", "/ui/cases", {"erp_number": "1"})
        print(f"--- наблюдатель создаёт заявку: HTTP {status}, {url}")
        if "просмотра" not in urllib.parse.unquote(url):
            failures.append("наблюдатель смог создать заявку")

        status, html, _ = request(
            observer_client, "GET", f"/ui/cases/{source_id}/edit"
        )
        print(f"--- наблюдатель открывает форму правки: HTTP {status} (чтение разрешено)")

        status, html, url = request(
            observer_client, "POST", f"/ui/cases/{source_id}/packages", {}
        )
        print(f"--- наблюдатель собирает пакет: HTTP {status}, {url}")
        if "просмотра" not in urllib.parse.unquote(url):
            failures.append("наблюдатель смог собрать пакет")

        api_payload = json.dumps({"package_kind": "primary_prescription"}).encode()
        api_request = urllib.request.Request(
            BASE + f"/api/cases/{source_id}/packages",
            data=api_payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with observer_client.open(api_request, timeout=60) as response:
                api_status = response.status
        except urllib.error.HTTPError as error:
            api_status = error.code
        print(f"--- наблюдатель собирает пакет через API: HTTP {api_status} (ожидается 403)")
        if api_status != 403:
            failures.append(f"API разрешил сборку наблюдателю: HTTP {api_status}")

        status, html, _ = request(observer_client, "GET", "/api/cases")
        print(f"--- наблюдатель читает API: HTTP {status}")
        if status != 200:
            failures.append("наблюдателю закрыто чтение API")

        status, html, url = request(client, "POST", "/ui/logout", {})
        print(f"--- выход: HTTP {status}, адрес {url}")
        status, html, url = request(client, "GET", "/ui")
        print(f"--- после выхода /ui: HTTP {status}, адрес {url}")
        if "/ui/login" not in url:
            failures.append("после выхода страницы всё ещё доступны")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  все проверки входа и интерфейса пройдены")
        return 0
    finally:
        if new_case_id is not None:
            case = db.get(ControlCase, new_case_id)
            if case is not None:
                db.delete(case)
                db.commit()
                print(f"тестовая заявка {new_case_id} удалена")
        if check_user_id is not None:
            for email in (OPERATOR_EMAIL, CHECK_EMAIL, ADMIN_EMAIL, OBSERVER_EMAIL):
                person = db.scalar(select(User).where(User.email == email))
                if person is not None:
                    db.delete(person)
                    db.commit()
                    print(f"временный пользователь {email} удалён")
        if organization_id is not None:
            organization = db.get(Organization, organization_id)
            if organization is not None:
                db.delete(organization)
                db.commit()
                print(f"тестовая организация {organization_id} удалена")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
