"""Проверка дат, которые подставляются по дню осмотра.

При заведении осмотра даты не должны набираться руками:

* начало — текущее время (его проставляет система при заведении осмотра);
* окончание — начало плюс 15 минут;
* дата задания — предыдущий рабочий день от дня осмотра, выходные пропускаются;
* дата решения — день протокола осмотра.

Проверка идёт по интерфейсу: заводит осмотр у временной заявки, меняет дату
осмотра и смотрит, что зависимые даты едут за ней, а дата, введённая руками,
не перезаписывается.

За собой проверка убирает заявку, осмотр, решение, адрес и пользователя.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_inspection_dates.py
"""

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.forms import DISPLAY_TZ
from app.models import (
    Address,
    ControlAction,
    ControlCase,
    Decision,
    Role,
    User,
    UserRole,
    Violation,
    ViolationType,
)
from app.services import auth as auth_service
from app.services import auto_dates


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-dates@local"
CHECK_PASSWORD = "check-dates-2026"
ADDRESS = "398600, Липецкая область, г Липецк, ул. Датная, д 7"
SUBJECT = "проверка дат при осмотре"


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


def field_value(html: str, name: str) -> str:
    """Значение поля ввода со страницы."""

    match = re.search(
        rf'name="{name}"[^>]*value="([^"]*)"', html
    ) or re.search(rf'value="([^"]*)"[^>]*name="{name}"', html)
    return match.group(1) if match else ""


def local(value) -> str:
    """Дата и время в местном времени документов — так их видит оператор."""

    if value is None:
        return "—"
    return value.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y %H:%M")


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    case = None
    user = None
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка дат",
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

        # --- 1. Заявка и осмотр ------------------------------------------
        status, html, url = request(
            client,
            "POST",
            "/ui/cases",
            {
                "subject": SUBJECT,
                "violation_address": ADDRESS,
                "violation_type_id": str(violation_type.id) if violation_type else "",
                "violation_detected_at": "2026-10-06T09:00",
            },
        )
        match = re.search(r"/ui/cases/(\d+)", url)
        if not match:
            print(f"заявка не создана: HTTP {status}, {url}")
            return 1
        case = db.get(ControlCase, int(match.group(1)))

        status, html, url = request(client, "POST", f"/ui/cases/{case.id}/inspections", {"kind": "primary"})
        match = re.search(r"/ui/inspections/(\d+)", url)
        if not match:
            print(f"осмотр не заведён: HTTP {status}, {url}")
            return 1
        inspection = db.get(ControlAction, int(match.group(1)))
        db.refresh(case)
        print(
            f"--- осмотр {inspection.id} заведён: начало {local(inspection.started_at)}, "
            f"окончание {local(inspection.ended_at)}"
        )
        if inspection.started_at is None:
            failures.append("при заведении осмотра не проставлено начало")
        if inspection.ended_at is None or (
            inspection.ended_at - inspection.started_at != auto_dates.DEFAULT_DURATION
        ):
            failures.append("окончание осмотра не проставлено как начало плюс 15 минут")
        if case.assignment_date is None:
            failures.append("дата задания не подставилась при заведении осмотра")

        # --- 2. Форма показывает окончание +15 минут ----------------------
        status, page, _ = request(client, "GET", f"/ui/inspections/{inspection.id}")
        started_value = field_value(page, "started_at")
        ended_value = field_value(page, "ended_at")
        if started_value and ended_value:
            started = datetime.fromisoformat(started_value)
            ended = datetime.fromisoformat(ended_value)
            printed_ok = ended - started == auto_dates.DEFAULT_DURATION
        else:
            printed_ok = False
            started = ended = None
        print(
            f"--- поля формы: начало {started_value}, окончание {ended_value}, "
            f"разница 15 минут: {printed_ok}"
        )
        if not printed_ok:
            failures.append("в форме осмотра окончание не подставлено как начало плюс 15 минут")

        # --- 3. Меняем дату осмотра: вторник 06.10.2026 ------------------
        status, html, url = request(
            client,
            "POST",
            f"/ui/inspections/{inspection.id}",
            {
                "started_at": "2026-10-06T09:00",
                "ended_at": "2026-10-06T09:15",
                "action_type": "inspection",
            },
        )
        db.refresh(case)
        db.refresh(inspection)
        decision = db.scalars(
            select(Decision).where(Decision.control_case_id == case.id)
        ).first()
        assignment = auto_dates.local_date(case.assignment_date)
        decision_date = decision.decision_date if decision is not None else None
        print(
            f"--- осмотр во вторник 06.10.2026: задание {assignment}, решение {decision_date}"
        )
        if assignment != auto_dates.previous_working_day(
            auto_dates.local_date(inspection.started_at)
        ):
            failures.append("дата задания не равна предыдущему рабочему дню")
        if decision_date != auto_dates.local_date(inspection.started_at):
            failures.append("дата решения не равна дню осмотра")

        # --- 4. Осмотр в понедельник: задание уходит на пятницу ----------
        request(
            client,
            "POST",
            f"/ui/inspections/{inspection.id}",
            {
                "started_at": "2026-10-12T09:00",
                "ended_at": "2026-10-12T09:15",
                "action_type": "inspection",
            },
        )
        db.refresh(case)
        # Осмотр правился через интерфейс в другой сессии: обновляем и его.
        db.refresh(inspection)
        db.refresh(decision)
        assignment = auto_dates.local_date(case.assignment_date)
        friday = auto_dates.previous_working_day(auto_dates.local_date(inspection.started_at))
        print(
            f"--- осмотр в понедельник 12.10.2026: задание {assignment} "
            f"(ожидается пятница {friday})"
        )
        if assignment != friday:
            failures.append("для осмотра в понедельник задание не ушло на пятницу")
        if decision.decision_date != auto_dates.local_date(inspection.started_at):
            failures.append("дата решения не поехала за датой осмотра")

        # --- 5. Правка руками не перезаписывается ------------------------
        case.assignment_date = auto_dates.parse_datetime("2026-10-01T09:00")
        db.commit()
        request(
            client,
            "POST",
            f"/ui/inspections/{inspection.id}",
            {
                "started_at": "2026-10-13T10:00",
                "ended_at": "2026-10-13T10:15",
                "action_type": "inspection",
            },
        )
        db.refresh(case)
        # Осмотр правился через интерфейс в другой сессии: обновляем и его.
        db.refresh(inspection)
        db.refresh(decision)
        kept = auto_dates.local_date(case.assignment_date)
        print(f"--- после правки руками: задание {kept} (ожидается 01.10.2026)")
        if kept != auto_dates.local_date(
            auto_dates.parse_datetime("2026-10-01T09:00")
        ):
            failures.append("дата задания, введённая руками, перезаписана системой")
        if decision.decision_date != auto_dates.local_date(inspection.started_at):
            failures.append("дата решения не следует за датой осмотра после правки")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  даты осмотра, задания и решения подставляются и остаются редактируемыми")
        return 0
    finally:
        if case is not None:
            stored = db.get(ControlCase, case.id)
            if stored is not None:
                db.delete(stored)
        db.commit()
        for mail in (CHECK_EMAIL,):
            stored_user = db.scalar(select(User).where(User.email == mail))
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
