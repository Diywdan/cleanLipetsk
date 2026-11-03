"""Проверка сквозной нумерации заявок.

Внутренний номер заявки присваивает система: он сквозной для всех
пользователей и вручную не меняется. Проверка отвечает на четыре вопроса:

* номер появляется сам при создании заявки и выглядит как 000123;
* номера идут по возрастанию и не повторяются;
* номер, присланный формой, ничего не меняет — даже при правке заявки;
* номер виден в списке и в карточке заявки.

За собой проверка убирает созданные заявки, адрес и временного пользователя.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_case_numbers.py
"""

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Address, ControlCase, Role, User, UserRole, ViolationType
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-numbers@local"
CHECK_PASSWORD = "check-numbers-2026"
ADDRESS = "398600, Липецкая область, г Липецк, ул. Номерная, д 1"
SUBJECT = "проверка нумерации заявок"
FAKE_NUMBER = "ВЗЛОМ-000000"
NUMBER_PATTERN = re.compile(r"^\d{6}$")


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
        with client.open(req, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.url
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.url


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    created: list[int] = []
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка нумерации",
            email=CHECK_EMAIL,
            password_hash=auth_service.hash_password(CHECK_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()

        violation_type = db.scalars(
            select(ViolationType).order_by(ViolationType.sort_order, ViolationType.id)
        ).first()

        client, _ = make_client()
        request(client, "POST", "/ui/login", {"login": CHECK_EMAIL, "password": CHECK_PASSWORD})

        # --- 1. Три заявки подряд: номер присваивается сам ----------------
        numbers: list[str] = []
        for index in range(3):
            status, html, url = request(
                client,
                "POST",
                "/ui/cases",
                {
                    "subject": f"{SUBJECT} ({index + 1})",
                    "violation_address": ADDRESS,
                    "violation_type_id": str(violation_type.id) if violation_type else "",
                    "violation_detected_at": "2026-10-14T09:00",
                    # Номер в запросе — попытка задать его вручную: сервер
                    # должен её проигнорировать.
                    "case_number": FAKE_NUMBER,
                },
            )
            match = re.search(r"/ui/cases/(\d+)", url)
            if not match:
                print(f"заявка не создана: HTTP {status}, {url}")
                return 1
            case_id = int(match.group(1))
            created.append(case_id)
            case = db.get(ControlCase, case_id)
            db.refresh(case)
            numbers.append(case.case_number or "")
            print(f"--- заявка {case_id}: номер {case.case_number!r}")

        if any(not NUMBER_PATTERN.match(number) for number in numbers):
            failures.append("номер не вида 000123")
        if FAKE_NUMBER in numbers:
            failures.append("номер, присланный формой, попал в заявку")
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            failures.append("номера не идут по возрастанию или повторяются")
        steps = [
            int(numbers[i + 1]) - int(numbers[i])
            for i in range(len(numbers) - 1)
            if numbers[i].isdigit() and numbers[i + 1].isdigit()
        ]
        print(f"--- номера подряд: {numbers}, шаги между ними: {steps}")
        if any(step != 1 for step in steps):
            failures.append("номера идут не подряд: последовательность рвётся")

        # --- 2. Правка заявки номер не меняет ----------------------------
        case_id = created[0]
        case = db.get(ControlCase, case_id)
        was = case.case_number
        request(
            client,
            "POST",
            f"/ui/cases/{case_id}/edit",
            {
                "subject": f"{SUBJECT} (правка)",
                "erp_number": case.erp_number or "",
                "case_number": "999999",
            },
        )
        db.refresh(case)
        print(f"--- после правки с номером 999999: {case.case_number!r} (было {was!r})")
        if case.case_number != was:
            failures.append("номер изменился при правке заявки")

        # --- 3. Номер виден в списке и в карточке ------------------------
        status, html, _ = request(client, "GET", "/ui")
        in_list = was in html
        status, card, _ = request(client, "GET", f"/ui/cases/{case_id}")
        in_card = was in card
        print(f"--- номер {was} в списке: {in_list}, в карточке: {in_card}")
        if not in_list or not in_card:
            failures.append("номер заявки не виден в списке или в карточке")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  номера присваиваются сквозной последовательностью и не правятся вручную")
        return 0
    finally:
        for case_id in created:
            stored = db.get(ControlCase, case_id)
            if stored is not None:
                db.delete(stored)
        db.commit()
        stored_user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if stored_user is not None:
            db.delete(stored_user)
        db.commit()
        address = db.scalar(select(Address).where(Address.full_address == ADDRESS))
        if address is not None:
            db.delete(address)
            db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
