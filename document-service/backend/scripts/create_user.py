"""Создание пользователя системы и смена пароля.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/create_user.py <почта> <пароль> "<ФИО>" [роль]

Роли: administrator, manager, inspector, observer.
Повторный запуск с той же почтой меняет пароль и ФИО.
"""

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    email = sys.argv[1].strip().lower()
    password = sys.argv[2]
    full_name = sys.argv[3]
    role_code = sys.argv[4] if len(sys.argv) > 4 else "administrator"

    if len(password) < 8:
        print("пароль должен быть не короче 8 символов")
        return 1

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        created = user is None
        if user is None:
            user = User(full_name=full_name, email=email)
            db.add(user)
            db.flush()
        else:
            user.full_name = full_name
        user.password_hash = auth.hash_password(password)
        user.is_active = True

        role = db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            print(f"роль {role_code!r} не найдена — пользователь создан без роли")
        else:
            link = db.scalar(
                select(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role_id == role.id
                )
            )
            if link is None:
                db.add(UserRole(user_id=user.id, role_id=role.id))

        db.commit()
        print(
            f"{'создан' if created else 'обновлён'} пользователь id={user.id} "
            f"{email} ({full_name}), роль {role_code}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
