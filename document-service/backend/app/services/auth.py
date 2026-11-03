"""Пароли и сессии: вход оператора в систему.

Пароли хранятся как scrypt-хэш со случайной солью (стандартная библиотека,
без внешних зависимостей). Сессия — случайный токен в базе, в браузер уходит
только он, в куке с флагами HttpOnly и SameSite.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Role, User, UserRole, UserSession


SESSION_COOKIE = "document_service_session"
SESSION_TTL = timedelta(hours=12)

# Параметры scrypt: память около 16 МБ на проверку — приемлемо для веб-входа.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=int(n),
        r=int(r),
        p=int(p),
        dklen=len(bytes.fromhex(digest_hex)),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def now() -> datetime:
    return datetime.now(timezone.utc)


def authenticate(db: Session, login: str, password: str) -> User | None:
    """Проверяет логин (электронную почту) и пароль."""

    user = db.scalar(
        select(User).where(User.email == login.strip().lower())
    )
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def has_role(user: User, code: str) -> bool:
    """Есть ли у пользователя роль с таким кодом."""

    return any(
        link.role is not None and link.role.code == code for link in user.roles
    )


def is_administrator(user: User) -> bool:
    """Полные права: управление пользователями и справочниками."""

    return has_role(user, "administrator")


# Роли, которым разрешено менять данные. Наблюдатель работает только на чтение.
EDIT_ROLES = {"administrator", "manager", "inspector"}


def can_edit(user: User) -> bool:
    """Можно ли пользователю менять данные.

    Наблюдатель — только просмотр. Пользователю без ролей не ограничиваем
    работу: иначе забытая роль незаметно превратилась бы в запрет.
    """

    codes = {link.role.code for link in user.roles if link.role is not None}
    if not codes:
        return True
    return bool(codes & EDIT_ROLES)


# Роли, которым разрешено собирать пакеты документов. Инспектор осмотр
# делает, но документы собирает делопроизводитель: это разные работы.
PACKAGE_ROLES = {"administrator", "manager"}


def can_build_packages(user: User) -> bool:
    """Можно ли пользователю собирать пакеты документов.

    Пользователю без ролей не ограничиваем: это то же правило, что и с
    правкой данных, — иначе забытая роль стала бы запретом.
    """

    codes = {link.role.code for link in user.roles if link.role is not None}
    if not codes:
        return True
    return bool(codes & PACKAGE_ROLES)


def grant_role(db: Session, user: User, code: str) -> Role | None:
    """Выдаёт роль, если её ещё нет. Возвращает роль или None."""

    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        return None
    exists = db.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id, UserRole.role_id == role.id
        )
    )
    if exists is None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    return role


def create_session(
    db: Session,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
    ttl: timedelta | None = None,
) -> UserSession:
    session = UserSession(
        user_id=user.id,
        token=secrets.token_hex(32),
        expires_at=now() + (ttl or SESSION_TTL),
        last_seen_at=now(),
        user_agent=(user_agent or "")[:500] or None,
        ip_address=ip_address,
    )
    db.add(session)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            entity_table="users",
            entity_id=user.id,
            action="login",
            comment=f"вход в систему, {ip_address or 'адрес неизвестен'}",
        )
    )
    db.commit()
    db.refresh(session)
    return session


def resolve_session(db: Session, token: str | None) -> User | None:
    """Возвращает пользователя по токену сессии, если она жива."""

    if not token:
        return None
    session = db.scalar(
        select(UserSession).where(UserSession.token == token)
    )
    if session is None or session.revoked_at is not None:
        return None
    if session.expires_at <= now():
        return None
    if not session.user.is_active:
        return None
    session.last_seen_at = now()
    db.commit()
    return session.user


def revoke_session(db: Session, token: str | None, user: User | None = None) -> None:
    if not token:
        return
    session = db.scalar(select(UserSession).where(UserSession.token == token))
    if session is None:
        return
    session.revoked_at = now()
    db.add(
        AuditLog(
            actor_user_id=session.user_id,
            entity_table="users",
            entity_id=session.user_id,
            action="logout",
            comment="выход из системы",
        )
    )
    db.commit()


def purge_expired(db: Session) -> int:
    """Удаляет истёкшие сессии: вызывается при входе, чтобы не копить мусор."""

    expired = list(
        db.scalars(
            select(UserSession).where(UserSession.expires_at <= now())
        )
    )
    for session in expired:
        db.delete(session)
    if expired:
        db.commit()
    return len(expired)
