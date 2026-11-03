"""Проверка: все ли нормы есть в списке и как работает фильтр.

Смотрит готовую разметку формы: сколько норм внутри select, сгруппированы ли
они, и есть ли у каждой привязка к виду нарушения (по ней работает фильтр).
"""
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
EMAIL = "check-norms3@local"
PASSWORD = "check-norms3-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка норм",
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
            html = response.read().decode("utf-8", "replace")

        match = re.search(
            r'<select name="violation_article_ids".*?</select>', html, re.S
        )
        block = match.group(0) if match else ""
        print(f"блок выбора норм найден: {bool(block)}, длина {len(block)}")

        options = re.findall(
            r'<option value="(\d+)"[^>]*data-kinds="([^"]*)"[^>]*>\s*([^<]*?)\s*</option>',
            block,
            re.S,
        )
        print(f"норм в списке: {len(options)}")
        for option_id, kinds, text in options:
            print(f"  id={option_id:<4} kinds={kinds!r:24} {text}")

        groups = re.findall(r'<optgroup label="([^"]+)"', block)
        print(f"групп: {len(groups)}")
        for group in groups:
            print(f"  {group}")

        without_kinds = [o for o in options if not o[1].strip()]
        print(f"норм без привязки к виду нарушения: {len(without_kinds)}")
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
