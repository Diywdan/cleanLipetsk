"""Проверка заявок без пакета документов.

Новые вводные: по части заявок пакет документов не формируется вообще.
Такая заявка живёт в системе, по ней проводится осмотр, назначается
ответственный за исполнение, может быть повторный осмотр — и на этом всё.
Документы формируются по требованию.

Проверка идёт тем же путём, что и оператор, — через интерфейс:

* только что созданная заявка не требует документов: в карточке спокойная
  строка и кнопка «Создать пакет документов», а списка «чего не хватает»
  по умолчанию нет;
* список «чего не хватает» появляется тогда, когда пакет действительно
  собирают, — после нажатия кнопки, и ведёт к незаполненным полям;
* заявка с осмотром и без пакета не выглядит незавершённой ни в карточке,
  ни в списке заявок: «Первичный осмотр» — законное состояние;
* срок исполнения нарушения стоит в видимой части формы заявки, вне
  свёрнутых блоков, и виден в карточке;
* ответственного за исполнение делопроизводитель назначает в карточке, а
  роль без права сборки пакетов его назначить не может.

За собой проверка убирает: заявку, осмотр, адрес и временных пользователей.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_no_documents.py
"""

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlAction,
    ControlCase,
    Organization,
    Role,
    User,
    UserRole,
    ViolationType,
)
from app.models.enums import InspectionKind
from app.services import auth as auth_service
from app.services import inspections


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-no-documents@local"
CHECK_PASSWORD = "check-no-documents-2026"
INSPECTOR_EMAIL = "check-no-documents-inspector@local"
INSPECTOR_PASSWORD = "check-no-documents-inspector-2026"

SUBJECT = "навалы мусора у контейнерной площадки (заявка без документов)"
ADDRESS = "398600, Липецкая область, г Липецк, ул. Бездокументная, д 3"
DUE_ON = date(2026, 10, 20)


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


def issues_from(html: str) -> list[str]:
    """Пункты готовности из карточки — то, чего не хватает для пакета."""

    block = html.split("Что нужно заполнить")[-1]
    return [
        re.sub(r"<[^>]+>", "", item).strip()
        for item in re.findall(r"<li>(.*?)</li>", block, re.S)
    ][:12]


def make_user(db, email: str, password: str, role_code: str, full_name: str) -> User:
    """Временный пользователь с нужной ролью."""

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        db.delete(existing)
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
    return user


def login(email: str, password: str):
    client, jar = make_client()
    status, html, url = request(
        client, "POST", "/ui/login", {"login": email, "password": password}
    )
    if "/ui/login" in url:
        raise RuntimeError(f"не удалось войти: {email}")
    return client


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    case: ControlCase | None = None
    action: ControlAction | None = None
    clerk: User | None = None
    inspector: User | None = None
    try:
        clerk = make_user(
            db, CHECK_EMAIL, CHECK_PASSWORD, "manager", "Проверка без документов"
        )
        inspector = make_user(
            db,
            INSPECTOR_EMAIL,
            INSPECTOR_PASSWORD,
            "inspector",
            "Проверка инспектора",
        )
        violation_type = db.scalars(
            select(ViolationType).order_by(ViolationType.sort_order, ViolationType.id)
        ).first()
        if violation_type is None:
            print("в справочнике нет ни одного вида нарушения")
            return 1

        client = login(CHECK_EMAIL, CHECK_PASSWORD)

        # --- 1. Заявка без документов: короткая форма ---------------------
        status, html, url = request(
            client,
            "POST",
            "/ui/cases",
            {
                "subject": SUBJECT,
                "violation_address": ADDRESS,
                "violation_type_id": str(violation_type.id),
                "violation_detected_at": "2026-10-06T09:15",
            },
        )
        match = re.search(r"/ui/cases/(\d+)", url)
        if not match:
            print(f"заявка не создана: HTTP {status}, {url}")
            print(html[:300])
            return 1
        case = db.get(ControlCase, int(match.group(1)))
        print(f"--- заявка без документов: №{case.id}, состояние в карточке: "
              f"{'На исполнении' if 'состояние: На исполнении' in html else 'НЕЯСНО'}")

        if "Документы по заявке не формируются" not in html:
            failures.append("в карточке нет строки «Документы по заявке не формируются»")
        if "Пакет пока нельзя сформировать" in html:
            failures.append("карточка требует документы по умолчанию")
        if "Что нужно заполнить и где" in html:
            failures.append("в карточке сразу показан список недостающего")
        if "состояние: На исполнении" not in html:
            failures.append("состояние заявки без осмотра не «На исполнении»")

        # --- 2. Осмотр: пакета по-прежнему нет ----------------------------
        action = inspections.start(db, case, kind=InspectionKind.PRIMARY)
        db.commit()

        status, html, _ = request(client, "GET", f"/ui/cases/{case.id}")
        print(f"--- после осмотра: HTTP {status}, состояние "
              f"{'Первичный осмотр' if 'состояние: Первичный осмотр' in html else 'НЕЯСНО'}, "
              f"кнопка сборки: {'есть' if 'Создать пакет документов' in html else 'нет'}")
        if "состояние: Первичный осмотр" not in html:
            failures.append("после первичного осмотра состояние не «Первичный осмотр»")
        if "Документы по заявке не формируются" not in html:
            failures.append("после осмотра карточка не показывает спокойную строку")
        if "Создать пакет документов" not in html:
            failures.append("после осмотра нет кнопки «Создать пакет документов»")
        if "Пакет пока нельзя сформировать" in html:
            failures.append("после осмотра карточка требует документы")
        if "Следующий шаг: собрать пакет документов" in html:
            failures.append("заявка без пакета выглядит незавершённой в карточке")
        if "Сделать повторный осмотр" not in html:
            failures.append("после первичного осмотра нет кнопки повторного осмотра")

        # Список заявок: та же спокойная картина, состояние — законное.
        status, list_html, _ = request(client, "GET", "/ui")
        row = list_html.split(f"/ui/cases/{case.id}")[0].split("<tr>")[-1]
        print(f"--- список заявок: состояние «Первичный осмотр»: "
              f"{'Первичный осмотр' in list_html}")
        if "Первичный осмотр" not in list_html:
            failures.append("в списке заявок нет состояния «Первичный осмотр»")
        if "не сформирован" in row or "не хватает" in row:
            failures.append("в списке заявка без документов помечена как незавершённая")

        # --- 3. Пакет собирают — и только теперь видно, чего не хватает ---
        status, html, _ = request(client, "POST", f"/ui/cases/{case.id}/packages", {})
        print(f"--- сборка пакета по неполной заявке: HTTP {status} (ожидается 409), "
              f"пунктов готовности: {len(issues_from(html))}")
        if status != 409:
            failures.append(f"сборка неполной заявки вернула HTTP {status} вместо 409")
        if "Пакет пока не собрался: заполнены не все поля" not in html:
            failures.append("при сборке не показано, чего не хватает")
        if "Что нужно заполнить и где" not in html:
            failures.append("при сборке нет списка «что нужно заполнить и где»")
        if not issues_from(html):
            failures.append("список недостающих полей пуст — вести к полям некуда")

        # --- 4. Срок исполнения нарушения: видимая часть формы ------------
        status, form_html, _ = request(client, "GET", f"/ui/cases/{case.id}/edit")
        field_at = form_html.find('name="control_due_on"')
        # Поле не должно оказаться внутри свёрнутого блока: считаем
        # открытые <details> перед ним.
        before = form_html[:field_at] if field_at != -1 else ""
        open_details = before.count("<details")
        closed_details = before.count("</details>")
        visible = field_at != -1 and open_details == closed_details
        print(f"--- срок исполнения нарушения в форме: HTTP {status}, "
              f"вне свёрнутых блоков: {visible}")
        if field_at == -1:
            failures.append("в форме заявки нет поля срока исполнения нарушения")
        elif not visible:
            failures.append("срок исполнения нарушения спрятан в свёрнутом блоке")
        if "Срок исполнения нарушения" not in form_html:
            failures.append("поле срока исполнения нарушения подписано иначе")

        case.control_due_on = DUE_ON
        db.commit()
        status, html, _ = request(client, "GET", f"/ui/cases/{case.id}")
        shown = DUE_ON.strftime("%d.%m.%Y") in html
        print(f"--- срок в карточке: {'виден' if shown else 'НЕ виден'} "
              f"({DUE_ON.strftime('%d.%m.%Y')}), дата контроля берётся из него: "
              f"{'да' if 'срок исполнения заявки' in html else 'нет'}")
        if not shown:
            failures.append("срок исполнения нарушения не виден в карточке")
        if "срок исполнения заявки" not in html:
            failures.append("дата контроля не связана со сроком исполнения нарушения")

        # --- 5. Ответственный за исполнение: назначается в карточке -------
        organization = db.scalars(
            select(Organization)
            .where(Organization.is_active.is_(True))
            .order_by(Organization.short_name)
        ).first()
        if organization is None:
            failures.append("в справочнике нет ни одной действующей организации")
        else:
            status, html, url = request(
                client,
                "POST",
                f"/ui/cases/{case.id}/responsible",
                {"responsible_organization_id": str(organization.id)},
            )
            db.refresh(case)
            assigned = case.responsible_organization_id == organization.id
            print(f"--- ответственный в карточке: HTTP {status}, "
                  f"назначен: {assigned}, виден: {organization.short_name in html}")
            if not assigned:
                failures.append("ответственный за исполнение не сохранился")
            if organization.short_name not in html:
                failures.append("ответственный не виден в карточке")
            if "Ответственный за исполнение" not in html:
                failures.append("в карточке нет поля ответственного за исполнение")

            # Роль без права сборки пакетов ответственного не назначает.
            other = login(INSPECTOR_EMAIL, INSPECTOR_PASSWORD)
            status, html, url = request(
                other,
                "POST",
                f"/ui/cases/{case.id}/responsible",
                {"responsible_organization_id": ""},
            )
            db.refresh(case)
            still = case.responsible_organization_id == organization.id
            print(f"--- инспектор снимает ответственного: HTTP {status}, "
                  f"назначение сохранилось: {still}")
            if not still:
                failures.append("ответственного снял пользователь без права сборки")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  заявка без документов работает: осмотр, срок, ответственный, "
              "пакет — по требованию")
        return 0
    finally:
        # Убираем за собой: осмотр, заявку, заведённый ею адрес и пользователей.
        if action is not None:
            stored = db.get(ControlAction, action.id)
            if stored is not None:
                db.delete(stored)
        if case is not None:
            stored = db.get(ControlCase, case.id)
            if stored is not None:
                db.delete(stored)
        db.commit()
        for email in (CHECK_EMAIL, INSPECTOR_EMAIL):
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                db.delete(user)
        db.commit()
        address = db.scalar(select(Address).where(Address.full_address == ADDRESS))
        if address is not None:
            db.delete(address)
            db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
