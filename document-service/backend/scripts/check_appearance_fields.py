"""Проверка полей явки: место — списком, кабинет — с подсказками."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Role, User, UserRole
from app.services import auth as auth_service, snapshots

BASE = "http://127.0.0.1:8000"
EMAIL = "check-appearance@local"
PASSWORD = "check-appearance-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка явки",
            email=EMAIL,
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "worker"))
        if role is None:
            role = db.scalar(select(Role))
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

        print(f"HTTP {response.status}")
        print(f"  место явки списком: "
              f"{'есть' if '<select name=\"appearance_place\">' in card else 'НЕТ'}")
        print(f"  кабинет с подсказками: "
              f"{'есть' if 'list=\"office-options\"' in card else 'НЕТ'}")
        block = re.search(r'<select name="appearance_place">(.*?)</select>', card, re.S)
        if block:
            options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>',
                                 block.group(1))
            print(f"  вариантов места явки: {len(options)}")
            for value, title in options[:4]:
                print(f"    {title.strip()[:70] or '— по умолчанию —'}")

        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        payload = snapshots.build_case_context(db, case.id)
        administrative = payload["administrative"]
        print()
        print(f"  место явки в данных: {administrative.get('appearance_place')!r}")
        print(f"  кабинет в данных:    {administrative.get('appearance_office')!r}")
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
