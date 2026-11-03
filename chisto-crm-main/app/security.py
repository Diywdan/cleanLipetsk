from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

# --- Пароли: scrypt из стандартной библиотеки, без лишних зависимостей ---

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# --- Сессия: подписанная HttpOnly-кука {uid, ver, exp} ---

SESSION_COOKIE = "crm_session"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_session(user_id: int, version: int, secret: str, ttl_seconds: int) -> str:
    body = _b64(json.dumps({"uid": user_id, "ver": version, "exp": int(time.time()) + ttl_seconds}).encode())
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def read_session(token: str | None, secret: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, mac = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, mac):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


def bearer_matches(header: str | None, expected: str) -> bool:
    if not header or not expected:
        return False
    scheme, _, value = header.partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(value.strip(), expected)


# --- Телефон: E.164, российские номера принимаем и в местной записи ---

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    digits = _DIGITS.sub("", raw or "")
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not 11 <= len(digits) <= 15:
        raise ValueError("Некорректный номер телефона")
    return "+" + digits


def mask_phone(phone: str) -> str:
    return phone[:2] + "*" * max(len(phone) - 6, 0) + phone[-4:]


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


# --- Права. Коды прав фиксированы в коде, роли из них собираются данными ---

PERMISSIONS: dict[str, str] = {
    "references.read": "Просмотр справочников",
    "references.write": "Изменение справочников: участки, исполнители, типы нарушений",
    "engineers.write": "Изменение инженеров и назначений",
    "registrations.review": "Разбор регистраций из бота",
    "events.read": "Просмотр входящих событий DG",
    "cases.read": "Просмотр дел",
    "cases.inspect": "Ведение дел: подтверждение, приёмка, возврат, эскалация, акт",
    "cases.report": "Фотоотчёт исполнителя по делам своей организации",
    "users.manage": "Управление пользователями и ролями",
    "integration.manage": "Настройка интеграции с DG",
    "audit.read": "Журнал действий",
}
