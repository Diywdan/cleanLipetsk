"""Проверка: цель и предмет выбираются из списка, в новой заявке — первое значение."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from lxml import html as lxml_html
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-purpose@local"
PASSWORD = "check-purpose-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка цели",
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

        for path, title in (
            ("/ui/cases/new", "новая заявка"),
            ("/ui/cases/7/edit", "правка заявки 122313"),
        ):
            with client.open(BASE + path) as response:
                page = response.read().decode("utf-8", "replace")
            tree = lxml_html.fromstring(page)
            print(f"=== {title}: HTTP {response.status} ===")
            for name in ("purpose", "subject"):
                selects = [
                    element
                    for element in tree.iter("select")
                    if element.get("name") == name
                ]
                if not selects:
                    print(f"  {name}: списка нет")
                    continue
                options = [
                    option
                    for option in selects[0].iter("option")
                    if option.get("value") is not None
                ]
                chosen = [
                    option for option in options if option.get("selected") is not None
                ]
                print(f"  {name}: вариантов {len(options)}")
                for option in options[:4]:
                    mark = " ← выбрано" if option in chosen else ""
                    print(f"    · {option.get('value')[:90]}{mark}")
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
