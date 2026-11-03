"""Проверка страниц: управы и карточка заявки."""
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
EMAIL = "check-areas@local"
PASSWORD = "check-areas-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка управ",
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

        with client.open(BASE + "/ui/areas") as response:
            page = response.read().decode("utf-8", "replace")
        print(f"=== /ui/areas: HTTP {response.status} ===")
        print(f"  выбор адреса управы: "
              f"{'есть' if 'name=\"area_address_id\"' in page else 'нет'}")
        for match in re.finditer(
            r'<option value="(\d+)"[^>]*>([^<]*Советская[^<]*)</option>', page
        ):
            print(f"    адрес из справочника: {match.group(2)[:70]}")

        with client.open(BASE + "/ui/cases/7") as response:
            card = response.read().decode("utf-8", "replace")
        print()
        print(f"=== карточка заявки: HTTP {response.status} ===")
        print(f"  место протокола списком: "
              f"{'есть' if 'name=\"protocol_place\"' in card else 'нет'}")
        block = re.search(
            r'<select name="protocol_place">(.*?)</select>', card, re.S
        )
        if block:
            options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>',
                                 block.group(1))
            print(f"  вариантов: {len(options)}")
            for value, title in options[:4]:
                print(f"    {title.strip()[:70] or '— по умолчанию —'}")
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
