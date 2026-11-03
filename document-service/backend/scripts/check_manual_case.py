"""Проверка пути «с нуля»: справочники -> заявка -> первичный пакет.

Все прежние проверки создавали заявку копированием уже готовой. Здесь
повторяется путь оператора, который заводит данные в пустую систему:
адрес, организация с реквизитами и почтой, филиал, представитель,
инспектор, объект контроля — и затем заявка, набранная руками.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_manual_case.py
"""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import io

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlBody,
    ControlBodySignatory,
    ControlCase,
    ControlForm,
    ControlKind,
    ControlObject,
    ControlObjectType,
    Inspector,
    NpaArticle,
    Organization,
    OrganizationRequisite,
    OrganizationUnit,
    PrescriptionStatus,
    Role,
    User,
    UserRole,
    ViolationType,
)
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-manual@local"
CHECK_PASSWORD = "check-manual-password-2026"

ADDRESS = "398600, Липецкая область, г Липецк, ул. Проверочная, д 1"
ORG_SHORT = "ООО «Проверка с нуля»"
UNIT_NAME = "филиал «Проверочный»"
INSPECTOR = "Проверяев Иван Иванович"
OBJECT_NAME = "земельный участок, расположенный по адресу: ул. Проверочная, д 1"
OBJECT_GENITIVE = "земельного участка, расположенного по адресу: ул. Проверочная, д 1"
ERP_NUMBER = "11112222333344445555"


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def request(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with client.open(req, timeout=240) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.url
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.url


def issues_from(html: str) -> list[str]:
    block = html.split("Что нужно заполнить")[-1]
    return [
        re.sub(r"<[^>]+>", "", item).strip()
        for item in re.findall(r"<li>(.*?)</li>", block, re.S)
    ][:12]


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    made: dict[str, object] = {}
    try:
        # Данные, которых не хватает у временного пользователя: всё остальное
        # берём из уже заполненных справочников.
        kind = db.scalar(select(ControlKind).order_by(ControlKind.id))
        form = db.scalar(select(ControlForm).order_by(ControlForm.sort_order))
        body = db.scalar(select(ControlBody).order_by(ControlBody.id))
        approver = db.scalar(
            select(ControlBodySignatory).order_by(ControlBodySignatory.id)
        )
        violation_type = db.scalar(select(ViolationType).order_by(ViolationType.sort_order))
        article = db.scalar(select(NpaArticle).order_by(NpaArticle.id))
        prescription_status = db.scalar(
            select(PrescriptionStatus).order_by(PrescriptionStatus.id)
        )
        object_type = db.scalar(select(ControlObjectType).order_by(ControlObjectType.sort_order))
        for name, value in (
            ("вид контроля", kind),
            ("форма мероприятия", form),
            ("орган контроля", body),
            ("утверждающее лицо", approver),
            ("тип нарушения", violation_type),
            ("статья НПА", article),
            ("вид объекта", object_type),
        ):
            if value is None:
                print(f"в справочниках нет данных: {name}")
                return 1

        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка ручного ввода",
            email=CHECK_EMAIL,
            password_hash=auth_service.hash_password(CHECK_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        if role is not None:
            db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        made["user"] = user.id

        client, jar = make_client()
        _, _, url = request(
            client, "POST", "/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD},
        )
        if "/ui/login" in url:
            print("не удалось войти")
            return 1
        print("--- вход выполнен")

        # 1. Адрес
        status, html, url = request(
            client, "POST", "/ui/dictionaries/addresses",
            {
                "full_address": ADDRESS,
                "postal_code": "398600",
                "locality": "г Липецк",
                "street": "ул. Проверочная",
                "house": "1",
            },
        )
        address = db.scalar(select(Address).where(Address.full_address == ADDRESS))
        print(f"--- адрес: HTTP {status}, id={address.id if address else None}")
        if address is None:
            failures.append("адрес не создан")
            return 1
        made["address"] = address.id

        # 2. Организация (реквизиты и почта заводятся вместе с ней)
        status, html, url = request(
            client, "POST", "/ui/dictionaries/organizations",
            {
                "short_name": ORG_SHORT,
                "full_name": ORG_SHORT,
                "kind": "legal_entity",
                "inn": "4800000001",
                "kpp": "480001001",
                "legal_address_id": str(address.id),
                "email": "manual-check@example.ru",
            },
        )
        organization = db.scalar(
            select(Organization).where(Organization.short_name == ORG_SHORT)
        )
        print(f"--- организация: HTTP {status}, id={organization.id if organization else None}")
        if organization is None:
            failures.append("организация не создана")
            return 1
        made["organization"] = organization.id

        # 3. Филиал
        status, html, _ = request(
            client, "POST",
            f"/ui/dictionaries/organizations/{organization.id}/units",
            {
                "kind": "branch",
                "name": UNIT_NAME,
                "address_id": str(address.id),
                "email": "branch-check@example.ru",
            },
        )
        unit = db.scalar(
            select(OrganizationUnit).where(OrganizationUnit.name == UNIT_NAME)
        )
        print(f"--- филиал: HTTP {status}, id={unit.id if unit else None}")
        if unit is None:
            failures.append("филиал не создан")
        else:
            made["unit"] = unit.id
            # Реквизиты филиала: в акт попадают его ИНН и КПП, поэтому они
            # хранятся отдельно от реквизитов головной организации.
            status, html, _ = request(
                client, "POST",
                f"/ui/dictionaries/organizations/{organization.id}/requisites",
                {
                    "unit_id": str(unit.id),
                    "inn": "4800000002",
                    "kpp": "480002001",
                    "legal_address_id": str(address.id),
                },
            )
            requisites = db.scalar(
                select(OrganizationRequisite).where(
                    OrganizationRequisite.unit_id == unit.id
                )
            )
            print(
                f"--- реквизиты филиала: HTTP {status}, "
                f"id={requisites.id if requisites else None}"
            )
            if requisites is None:
                failures.append("реквизиты филиала не сохранились")
            else:
                made["requisites"] = requisites.id

        # 4. Представитель
        status, html, _ = request(
            client, "POST",
            f"/ui/dictionaries/organizations/{organization.id}/representatives",
            {
                "full_name": "Проверяев Пётр Петрович",
                "position": "Директор",
                "basis_kind": "charter",
            },
        )
        print(f"--- представитель: HTTP {status}")

        # 5. Инспектор
        status, html, _ = request(
            client, "POST", "/ui/dictionaries/inspectors",
            {
                "full_name": INSPECTOR,
                "position": "главный консультант",
                "position_instrumental": "главным консультантом",
                "full_name_instrumental": "Проверяевым Иваном Ивановичем",
                "phone": "+7 4742 00-00-00",
                "email": "inspector-check@example.ru",
            },
        )
        inspector = db.scalar(select(Inspector).where(Inspector.full_name == INSPECTOR))
        print(f"--- инспектор: HTTP {status}, id={inspector.id if inspector else None}")
        if inspector is None:
            failures.append("инспектор не создан")
            return 1
        made["inspector"] = inspector.id

        # 6. Объект контроля
        status, html, _ = request(
            client, "POST", "/ui/dictionaries/objects",
            {
                "object_type_id": str(object_type.id),
                "name": OBJECT_NAME,
                "name_genitive": OBJECT_GENITIVE,
                "address_id": str(address.id),
                "operating_organization_id": str(organization.id),
            },
        )
        control_object = db.scalar(
            select(ControlObject).where(ControlObject.name == OBJECT_NAME)
        )
        print(f"--- объект контроля: HTTP {status}, id={control_object.id if control_object else None}")
        if control_object is None:
            failures.append("объект контроля не создан")
            return 1
        made["object"] = control_object.id

        # 7. Заявка, набранная руками
        fields = {
            # Внутренний номер заявке присваивает система.
            "erp_number": ERP_NUMBER,
            "control_kind_id": str(kind.id),
            "control_form_id": str(form.id),
            "control_body_id": str(body.id),
            "controlled_organization_id": str(organization.id),
            "controlled_unit_id": str(unit.id) if unit else "",
            "responsible_organization_id": str(organization.id),
            "control_object_id": str(control_object.id),
            "assignment_approved_by_signatory_id": str(approver.id),
            "inspector_id": str(inspector.id),
            "purpose": "проверка соблюдения требований к содержанию территории",
            "subject": "земельный участок по адресу: ул. Проверочная, д 1",
            "assignment_number": "123-П",
            "assignment_date": "2026-09-20T09:00",
            "planned_start_at": "2026-09-21T10:00",
            "planned_end_at": "2026-09-21T12:00",
            "actual_start_at": "2026-09-21T10:00",
            "actual_end_at": "2026-09-21T11:30",
            "act_composed_at": "2026-09-21T12:00",
            "basis_kind": "mu_material",
            "basis_document_number": "45/2026",
            "basis_document_date": "2026-09-15T08:00",
            "basis_description": "обращение жителя, зарегистрированное в системе",
            "action_type": "inspection",
            "action_started_at": "2026-09-21T10:00",
            "action_ended_at": "2026-09-21T11:30",
            "action_place_address_id": str(address.id),
            "action_result_text": "выявлено нарушение требований к содержанию территории",
            "violation_type_id": str(violation_type.id),
            "violation_detected_at": "2026-09-21T10:30",
            "violation_address_id": str(address.id),
            "violation_description": (
                "не обеспечена уборка территории, допущено складирование "
                "строительных материалов"
            ),
            "violation_article_ids": [str(article.id)],
            "prescription_number": "77/2026",
            "prescription_issued_on": "2026-09-21",
            "prescription_due_on": "2026-10-21",
            "prescription_requirement": (
                "обеспечить уборку территории и вывоз строительных материалов"
            ),
            "decision_number": "77/2026",
            "decision_date": "2026-09-21",
            "decision_kind": "решение по результатам контрольного мероприятия",
            "decision_content": "выдать предписание об устранении нарушения",
            "decision_item_description": "выдать предписание об устранении нарушений",
        }
        if prescription_status is not None:
            fields["prescription_status_id"] = str(prescription_status.id)

        status, html, url = request(client, "POST", "/ui/cases", fields)
        match = re.search(r"/ui/cases/(\d+)", url)
        print(f"--- заявка с нуля: HTTP {status}, {url}")
        if not match:
            failures.append("заявка не создана")
            print("   ", html[:300])
            return 1
        case_id = int(match.group(1))
        made["case"] = case_id

        # 8. Документы формируются по требованию: только что набранная заявка
        #    не требует пакет — в карточке спокойная строка и кнопка, а списка
        #    «чего не хватает» по умолчанию нет.
        calm = "Документы по заявке не формируются" in html
        button = "Создать пакет документов" in html
        print(
            f"--- карточка без документов: строка «не формируются»: {calm}, "
            f"кнопка сборки: {button}"
        )
        if not calm or not button:
            failures.append("в карточке нет спокойной строки и кнопки сборки")
        if "Пакет пока нельзя сформировать" in html:
            failures.append("карточка требует документы до того, как их собирают")

        # 9. Пакет: заявка набрана целиком, поэтому сборка проходит сразу —
        #    готовность проверяется в момент сборки, а не заранее.
        status, html, _ = request(client, "POST", f"/ui/cases/{case_id}/packages", {})
        documents = re.findall(r"/api/documents/(\d+)/file", html)
        print(f"--- первичный пакет: HTTP {status}, документов {len(documents)}")
        if len(documents) != 6:
            for issue in issues_from(html):
                print("      замечание:", issue)
            failures.append(f"документов {len(documents)} вместо 6")

        archive_match = re.search(r"/api/packages/(\d+)/archive", html)
        if archive_match:
            req = urllib.request.Request(
                BASE + f"/api/packages/{archive_match.group(1)}/archive"
            )
            with client.open(req, timeout=120) as response:
                data = response.read()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            print(f"--- архив: {len(names)} файлов, папка {names[0].split('/')[0]}")
            if names[0].split("/")[0] != ERP_NUMBER:
                failures.append("папка архива названа не номером мероприятия")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  заявка с нуля собрана в пакет без ручных правок в базе")
        return 0
    finally:
        # Убираем за собой: заявка, объект, филиал, представители, организация,
        # инспектор, адрес и временный пользователь.
        if "case" in made:
            case = db.get(ControlCase, made["case"])
            if case is not None:
                db.delete(case)
        if "object" in made:
            control_object = db.get(ControlObject, made["object"])
            if control_object is not None:
                db.delete(control_object)
        db.commit()
        if "organization" in made:
            organization = db.get(Organization, made["organization"])
            if organization is not None:
                db.delete(organization)
        db.commit()
        if "inspector" in made:
            inspector = db.get(Inspector, made["inspector"])
            if inspector is not None:
                db.delete(inspector)
        if "address" in made:
            address = db.get(Address, made["address"])
            if address is not None:
                db.delete(address)
        if "user" in made:
            user = db.get(User, made["user"])
            if user is not None:
                db.delete(user)
        db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
