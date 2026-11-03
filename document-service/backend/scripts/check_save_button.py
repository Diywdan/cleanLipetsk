"""Проверка: кнопка сохранения видна вне свёрнутых блоков."""
from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request

from lxml import html as lxml_html
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-button@local"
PASSWORD = "check-button-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка кнопки",
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
        with client.open(BASE + "/ui/cases/7/edit") as response:
            page = response.read().decode("utf-8", "replace")
        tree = lxml_html.fromstring(page)
        form = next(
            f for f in tree.iter("form") if (f.get("action") or "").endswith("/cases/7")
        )
        buttons = [
            element
            for element in form.iter("button")
            if (element.get("type") or "").lower() == "submit"
        ]
        print(f"кнопок отправки в форме: {len(buttons)}")
        for button in buttons:
            # Ищем, не лежит ли кнопка внутри details.
            parent = button.getparent()
            inside_details = False
            while parent is not None:
                if parent.tag == "details":
                    inside_details = True
                    break
                parent = parent.getparent()
            print(f"  «{' '.join(button.text_content().split())}» "
                  f"внутри свёрнутого блока: {'ДА' if inside_details else 'нет'}")
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
