"""Сохранение осмотра: работы меняются и возвращаются как было.

Форма читается со страницы целиком — так же, как её отправляет браузер.
"""
from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request

from lxml import html as lxml_html
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, Role, User, UserRole, Violation
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-insp-save@local"
PASSWORD = "check-insp-save-2026"
INSPECTION_ID = 7


def open_client():
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    data = urllib.parse.urlencode({"login": EMAIL, "password": PASSWORD}).encode()
    client.open(urllib.request.Request(BASE + "/ui/login", data=data, method="POST"))
    return client


def read_form(client, inspection_id: int):
    with client.open(BASE + f"/ui/inspections/{inspection_id}") as response:
        page = response.read().decode("utf-8", "replace")
    tree = lxml_html.fromstring(page)
    form = next(
        form
        for form in tree.iter("form")
        if (form.get("action") or "").endswith(f"/inspections/{inspection_id}")
    )
    pairs: list[tuple[str, str]] = []
    for element in form.iter():
        tag = element.tag
        name = element.get("name")
        if not name or tag not in ("input", "select", "textarea"):
            continue
        kind = (element.get("type") or "").lower()
        if tag == "input":
            if kind in ("checkbox", "radio"):
                if element.get("checked") is not None:
                    pairs.append((name, element.get("value") or "on"))
            elif kind not in ("submit", "button", "file", "reset"):
                pairs.append((name, element.get("value") or ""))
        elif tag == "select":
            options = [o for o in element.iter("option") if o.get("value") is not None]
            if element.get("multiple") is not None:
                chosen = [o for o in options if o.get("selected") is not None]
            else:
                chosen = [o for o in options if o.get("selected") is not None][:1]
                if not chosen and options:
                    chosen = options[:1]
            for option in chosen:
                pairs.append((name, option.get("value")))
        else:
            pairs.append((name, element.text or ""))
    return pairs


def post(client, inspection_id: int, pairs) -> int:
    data = urllib.parse.urlencode(pairs, doseq=True).encode()
    request = urllib.request.Request(
        BASE + f"/ui/inspections/{inspection_id}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with client.open(request) as response:
        return response.status


def works(db) -> list[str]:
    db.expire_all()
    violation = db.scalar(select(Violation).where(Violation.control_case_id == 7))
    return [f"{i.work.name}={i.quantity}" for i in violation.works]


def with_works(pairs, rows):
    cleaned = [
        (name, value)
        for name, value in pairs
        if name not in ("violation_work_ids", "violation_work_quantities")
    ]
    for work_id, quantity in rows:
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
            full_name="Проверка сохранения осмотра",
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

        violation = db.scalar(select(Violation).where(Violation.control_case_id == 7))
        original = [
            (item.work_id, str(item.quantity).removesuffix(".000").replace(".", ","))
            for item in violation.works
        ]
        print(f"до: {works(db)}")

        client = open_client()
        pairs = read_form(client, INSPECTION_ID)
        print(f"полей формы: {len(pairs)}")
        names = sorted({name for name, _ in pairs})
        print(f"  поля: {names}")

        status = post(client, INSPECTION_ID, with_works(pairs, [(1, "5")]))
        print(f"после правки (HTTP {status}): {works(db)}")

        status = post(client, INSPECTION_ID, with_works(pairs, original))
        print(f"возврат (HTTP {status}): {works(db)}")
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
