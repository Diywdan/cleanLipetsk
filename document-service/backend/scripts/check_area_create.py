"""Создание управы со своим адресом и кабинетом — проверка ввода.

Управа создаётся через ту же форму, что заполняет оператор, и удаляется в
конце: данные не остаются.
"""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import Address, Area, AreaAddress, Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-area-create@local"
PASSWORD = "check-area-create-2026"
NAME = "Проверка управы (временная)"
ADDRESS = "г. Липецк, ул. Механизаторов, д. 15"
OFFICE = "207"


def main() -> int:
    db = SessionLocal()
    user_id = None
    created_area_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка управы",
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

        payload = urllib.parse.urlencode(
            {"name": NAME, "control_body_id": "1", "area_address": ADDRESS,
             "office": OFFICE}
        ).encode()
        request = urllib.request.Request(
            BASE + "/ui/areas",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with client.open(request) as response:
            print(f"создание управы: HTTP {response.status}")

        db.expire_all()
        area = db.scalar(select(Area).where(Area.name == NAME))
        if area is None:
            print("управа не создана")
            return 1
        created_area_id = area.id
        print(f"управа: {area.name}")
        print(f"  адрес: {area.address.full_address if area.address else None}")
        print(f"  кабинет: {area.office}")

        with client.open(BASE + "/ui/areas") as response:
            page = response.read().decode("utf-8", "replace")
        print()
        print(f"поле ввода адреса: "
              f"{'есть' if 'name=\"area_address\"' in page else 'НЕТ'}")
        found = ADDRESS in page
        print(f"адрес виден на странице: {found}")
        return 0
    finally:
        if created_area_id is not None:
            for link in db.scalars(
                select(AreaAddress).where(AreaAddress.area_id == created_area_id)
            ):
                db.delete(link)
            area = db.get(Area, created_area_id)
            if area is not None:
                db.delete(area)
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()
        # Адрес, заведённый проверкой, мог остаться без связей.
        stray = db.scalar(
            select(Address).where(Address.full_address == ADDRESS)
        )
        still_used = db.scalar(
            select(AreaAddress).where(AreaAddress.address_id == stray.id)
        ) if stray is not None else None
        if stray is not None and still_used is None:
            db.delete(stray)
            db.commit()
        print()
        print("проверочные данные удалены")
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
