"""Возврат адреса, который был вписан руками в производстве.

Адрес «г. Липецк, ул. Механизаторов, д. 15» ввели когда-то прямо в поле места
явления, поэтому в справочнике адресов его не было. При уборке демонстрационных
данных поле очистили, и адрес пропал. Возвращаем его в справочник, чтобы он
был доступен для выбора управе.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Address
from app.services import addresses as address_service

ADDRESS = "г. Липецк, ул. Механизаторов, д. 15"


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.scalar(
            select(Address).where(Address.full_address == ADDRESS)
        )
        if existing is not None:
            print(f"адрес уже есть: {existing.id} {existing.full_address}")
            return
        address = address_service.resolve(db, ADDRESS)
        db.commit()
        print(f"адрес возвращён в справочник: {address.id} {address.full_address}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
