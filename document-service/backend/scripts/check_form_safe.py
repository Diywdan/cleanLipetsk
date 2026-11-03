"""Безопасная проверка формы: отправка всех полей страницы целиком.

Прошлая проверка отправляла частичную форму, а обработчик сохраняет наборы
целиком — незаполненные поля очищались. Здесь форма читается со страницы,
меняются только работы, и после проверки всё возвращается как было.
"""
from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request

from lxml import html as lxml_html
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Role, User, UserRole, Violation
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-form@local"
PASSWORD = "check-form-2026"
CASE_NUMBER = "122313"


def open_client():
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    data = urllib.parse.urlencode({"login": EMAIL, "password": PASSWORD}).encode()
    client.open(urllib.request.Request(BASE + "/ui/login", data=data, method="POST"))
    return client


def read_form(client, case_id: int) -> list[tuple[str, str]]:
    """Все поля формы заявки так, как их отправил бы браузер."""

    with client.open(BASE + f"/ui/cases/{case_id}/edit") as response:
        page = response.read().decode("utf-8", "replace")
    tree = lxml_html.fromstring(page)
    forms = [
        form
        for form in tree.iter("form")
        if (form.get("action") or "").endswith(f"/cases/{case_id}")
    ]
    if not forms:
        # Запасной вариант: форма без action отправляется на текущий адрес.
        forms = [
            form
            for form in tree.iter("form")
            if "violation_work_ids" in lxml_html.tostring(form, encoding="unicode")
        ]
    if not forms:
        raise SystemExit("форма заявки не найдена")
    pairs: list[tuple[str, str]] = []

    def add(name: str, value: str) -> None:
        if name not in seen or name in ("violation_work_ids", "violation_work_quantities"):
            pairs.append((name, value))

    seen: set[str] = set()
    for element in forms[0].iter():
        tag = element.tag
        name = element.get("name")
        if not name or tag not in ("input", "select", "textarea"):
            continue
        kind = (element.get("type") or "").lower()
        if tag == "input":
            if kind in ("checkbox", "radio"):
                if element.get("checked") is not None:
                    add(name, element.get("value") or "on")
                    seen.add(name)
            elif kind not in ("submit", "button", "file", "reset"):
                add(name, element.get("value") or "")
                seen.add(name)
        elif tag == "select":
            options = [o for o in element.iter("option") if o.get("value") is not None]
            if element.get("multiple") is not None:
                chosen = [o for o in options if o.get("selected") is not None]
                for option in chosen:
                    add(name, option.get("value"))
            else:
                chosen = [o for o in options if o.get("selected") is not None]
                if chosen:
                    add(name, chosen[0].get("value"))
                elif options:
                    add(name, options[0].get("value"))
            seen.add(name)
        else:
            add(name, element.text or "")
            seen.add(name)
    return pairs


def post(client, case_id: int, pairs) -> int:
    data = urllib.parse.urlencode(pairs, doseq=True).encode()
    request = urllib.request.Request(
        BASE + f"/ui/cases/{case_id}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with client.open(request) as response:
        return response.status


def works_text(db, case_id: int) -> list[str]:
    db.expire_all()
    violation = db.scalar(
        select(Violation).where(Violation.control_case_id == case_id)
    )
    return [f"{i.work.name}={i.quantity}" for i in violation.works]


def with_works(pairs, works: list[tuple[int, str]]):
    cleaned = [
        (name, value)
        for name, value in pairs
        if name not in ("violation_work_ids", "violation_work_quantities")
    ]
    for work_id, quantity in works:
        cleaned.append(("violation_work_ids", str(work_id)))
        cleaned.append(("violation_work_quantities", quantity))
    return cleaned


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка формы",
            email=EMAIL,
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        user_id = user.id

        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        live = db.scalar(
            select(Violation).where(Violation.control_case_id == case.id)
        )
        original = [(i.work_id, str(i.quantity).rstrip("0").rstrip(".") if "." in str(i.quantity) else str(i.quantity)) for i in live.works]
        original = [
            (i.work_id, (str(i.quantity).removesuffix(".000")).replace(".", ","))
            for i in live.works
        ]
        before = works_text(db, case.id)
        print(f"до: {before}")

        client = open_client()
        pairs = read_form(client, case.id)
        print(f"полей в форме прочитано: {len(pairs)}")
        print("  ключевые:", sorted({name for name, _ in pairs}))

        status = post(client, case.id, with_works(pairs, [(1, "7"), (3, "9")]))
        after = works_text(db, case.id)
        print(f"после правки (HTTP {status}): {after}")

        status = post(client, case.id, with_works(pairs, original))
        back = works_text(db, case.id)
        print(f"возврат (HTTP {status}): {back}")
        return 0
    finally:
        if user_id is not None:
            try:
                db.rollback()
                user = db.get(User, user_id)
                if user is not None:
                    db.delete(user)
                    db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
