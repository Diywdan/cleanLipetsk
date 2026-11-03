"""Страница заявки: событие правонарушения собирается из дат, поля нет."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-admin@local"
PASSWORD = "check-admin-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка производства",
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
            page = response.read().decode("utf-8", "replace")

        print(f"HTTP {response.status}")
        print(f"  поля offense_description: "
              f"{'ЕСТЬ' if 'name=\"offense_description\"' in page else 'нет'}")
        match = re.search(
            r"Событие правонарушения[^<]*</label>\s*<div[^>]*>([^<]{0,700})", page
        )
        print(f"  собранный текст: {' '.join(match.group(1).split())[:500] if match else '—'}")

        row = db.execute(
            text(
                "select offense_description from administrative_cases "
                "where control_case_id = 7"
            )
        ).first()
        print(f"  прежний текст в базе сохранён: {bool(row and row[0])}")
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
