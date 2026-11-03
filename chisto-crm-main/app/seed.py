"""Начальные данные. Всё идемпотентно: повторный запуск ничего не дублирует и не перезаписывает."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Assignment, Engineer, Executor, Permission, Role, Territory, User, ViolationType
from app.security import PERMISSIONS, hash_password

log = logging.getLogger("crm.seed")

# Справочник ведомств и проблем — из бота ДРТ (zvnic/agent_city_48_bot, data/categories.json, 78e3b62).
CATEGORIES = Path(__file__).parent / "data" / "categories.json"

SYSTEM_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Системный администратор", sorted(PERMISSIONS)),
    "dispatcher": (
        "Диспетчер ДРТ",
        ["references.read", "engineers.write", "registrations.review", "events.read",
         "cases.read", "cases.inspect", "audit.read"],
    ),
    "inspector": ("Инспектор ДРТ", ["references.read", "cases.read", "cases.inspect"]),
    # Аккаунты организаций: видят только свои дела (users.executor_id) и сдают по ним фотоотчёт.
    "executor": ("Исполнитель (ведомство)", ["cases.read", "cases.report"]),
    "uk_master": ("Мастер УК", ["cases.read", "cases.report"]),
    "manager": ("Руководитель", ["references.read", "events.read", "cases.read", "audit.read"]),
}

# Вид организации для фронта по ключу ведомства в боте; остальные — OMSU.
EXECUTOR_KINDS = {"ekoprom": "REG_OPERATOR", "housing_inspection": "GZHI", "nature_ministry": "MPR"}


def seed_permissions_and_roles(db: Session) -> None:
    created = set()
    for code, name in PERMISSIONS.items():
        if db.get(Permission, code) is None:
            db.add(Permission(code=code, name=name))
            created.add(code)
    db.flush()
    for code, (name, perms) in SYSTEM_ROLES.items():
        role = db.get(Role, code)
        if role is None:
            role = Role(code=code, name=name, is_system=True)
            role.permissions = [db.get(Permission, p) for p in perms]
            db.add(role)
        else:  # новое право достаётся системным ролям один раз, ручные правки ролей не затираются
            role.permissions += [db.get(Permission, p) for p in perms if p in created]
    admin = db.get(Role, "admin")
    if admin is not None:  # новые права достаются администратору автоматически
        have = {p.code for p in admin.permissions}
        admin.permissions += [db.get(Permission, p) for p in PERMISSIONS if p not in have]


def seed_admin(db: Session) -> None:
    settings = get_settings()
    password = settings.admin_password.get_secret_value()
    if not password or db.scalar(select(User).where(User.username == settings.admin_username)):
        return
    user = User(username=settings.admin_username, full_name="Системный администратор", password_hash=hash_password(password))
    user.roles = [db.get(Role, "admin")]
    db.add(user)
    log.info("seed: создан администратор %s", settings.admin_username)


def seed_references(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Executor)):
        return
    data = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    type_no = 0
    for exec_no, (key, dept) in enumerate(data.items(), start=1):
        executor = Executor(
            executor_id=f"EXEC-{exec_no:04d}", code=key, name=dept["name"], full_name=dept.get("full_name", ""),
            kind=EXECUTOR_KINDS.get(key, "OMSU"),
        )
        for problem_key, problem in dept["problems"].items():
            type_no += 1
            vtype = ViolationType(
                type_violation_id=f"VIOLATION-{type_no:04d}",
                code=f"{key}.{problem_key}",
                name=problem["name"],
                requires_description=bool(problem.get("requires_description")),
            )
            db.add(vtype)
            executor.violation_types.append(vtype)
        db.add(executor)
    log.info("seed: справочник из бота — %d исполнителей, %d типов", len(data), type_no)


# Прямоугольник города из снимка DG (local_references.json) — только для демо-участков.
_CITY = {"south": 52.5, "west": 39.4, "north": 52.75, "east": 39.8}


def seed_demo(db: Session) -> None:
    """Условные участки и инженеры для стенда. На проде не включать (CRM_SEED_DEMO=false)."""
    if db.scalar(select(func.count()).select_from(Engineer)):
        return
    names = ["Центральный округ", "Правобережный округ", "Левобережный округ", "Октябрьский округ"]
    territories = [Territory(territory_id=f"TERR-{i:03d}", name=n, bounds=_CITY) for i, n in enumerate(names, 1)]
    db.add_all(territories)
    people = [
        ("Иванов Иван Иванович", "+79990000482"),
        ("Петров Пётр Сергеевич", "+79990000517"),
        ("Кузнецова Анна Викторовна", "+79990000701"),
        ("Сидоров Алексей Петрович", "+79990000733"),
    ]
    for i, (name, phone) in enumerate(people, 1):
        engineer = Engineer(engineer_id=f"ENG-{i:05d}", full_name=name, phone=phone)
        db.add(engineer)
        db.add(
            Assignment(
                assignment_id=f"ASG-{i:06d}",
                engineer=engineer,
                territory=territories[(i - 1) % len(territories)],
                starts_on=date(2026, 10, 1),
            )
        )
    log.info("seed: демо — %d участка, %d инженера", len(territories), len(people))


def seed_all(db: Session) -> None:
    seed_permissions_and_roles(db)
    db.flush()
    seed_admin(db)
    seed_references(db)
    if get_settings().seed_demo:
        seed_demo(db)
