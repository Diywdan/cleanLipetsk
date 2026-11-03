"""Проверка интерфейса: работы в форме и карточке, требование из данных."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-works@local"
PASSWORD = "check-works-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка работ",
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

        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        data = urllib.parse.urlencode(
            {"login": EMAIL, "password": PASSWORD}
        ).encode()
        client.open(
            urllib.request.Request(BASE + "/ui/login", data=data, method="POST")
        )

        with client.open(BASE + "/ui/cases/7") as response:
            card = response.read().decode("utf-8", "replace")
        print("=== карточка заявки ===")
        for pattern, title in (
            (r"Работы:[^<]{0,200}", "работы"),
            (r"<label>Требование</label>\s*<div>([^<]{0,600})", "требование"),
        ):
            match = re.search(pattern, card, re.S)
            print(f"  {title}: {' '.join(match.group(0).split())[:400] if match else '—'}")

        with client.open(BASE + "/ui/cases/7/edit") as response:
            form = response.read().decode("utf-8", "replace")
        print()
        print("=== форма ===")
        print(f"  шаблон строки работ: {'work-row-template' in form}")
        print(f"  выбор действия: {'prescription_action_code' in form}")
        options = re.findall(r'data-unit="([^"]*)"[^>]*>([^<]+)</option>', form)
        print(f"  работ в справочнике: {len(options)}")
        for unit, name in options:
            print(f"    {name.strip()} ({unit})")
        selected = re.findall(r'"work_id":\s*(\d+)', form)
        print(f"  уже выбранные работы: {selected}")
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
