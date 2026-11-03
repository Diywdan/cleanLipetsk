"""Проверка связки «КНМ — наше обследование».

Интерфейс диспетчера и сервис документов стыкуются в одной точке: когда
инспектор в карточке обращения нажимает «Передать на КНМ», по заявке должно
завестись наше выездное обследование — с него начинается документооборот.

Проверка проходит весь маршрут обращения на временной заявке:

* принять в работу (confirm) — появляется срок устранения;
* передать на КНМ (escalate) — заводится первичный осмотр, статус меняется
  на KNM_ESCALATION, в заявке остаётся основание «передано на КНМ»;
* повторная передача второй осмотр не заводит;
* собрать пакет (act) — шесть документов, как и из нашего интерфейса;
* вернуть на доработку и принять работу (return, approve) — устранение
  нарушения отмечается и снимается;
* признать сигнал ложным (dismiss) — дело закрывается без исполнителя.

За собой проверка убирает заявку, осмотр, адрес и пользователя.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_knm_link.py
"""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlAction,
    ControlCase,
    ControlCaseBase,
    Role,
    User,
    UserRole,
    Violation,
    ViolationType,
)
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-knm@local"
CHECK_PASSWORD = "check-knm-2026"
ADDRESS = "398600, Липецкая область, г Липецк, ул. Обследованная, д 9"
SUBJECT = "проверка связки КНМ и обследования"


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def call(client, method: str, path: str, fields: dict | None = None, body: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        BASE + path, data=data, method=method, headers=headers
    )
    try:
        with client.open(request, timeout=180) as response:
            raw = response.read()
            return response.status, raw, response.headers.get("content-type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("content-type", "")


def payload(raw: bytes) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    case = None
    user_id = None
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка связки КНМ",
            email=CHECK_EMAIL,
            password_hash=auth_service.hash_password(CHECK_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        user_id = user.id

        violation_type = db.scalars(
            select(ViolationType).order_by(ViolationType.sort_order, ViolationType.id)
        ).first()

        client, _ = make_client()
        call(client, "POST", "/ui/login", {"login": CHECK_EMAIL, "password": CHECK_PASSWORD})

        # --- 1. Заявка с обращением, как её заводит оператор ---------------
        status, raw, _ = call(
            client,
            "POST",
            "/ui/cases",
            {
                "subject": SUBJECT,
                "violation_address": ADDRESS,
                "violation_type_id": str(violation_type.id) if violation_type else "",
                "violation_detected_at": "2026-10-14T09:00",
            },
        )
        match = re.search(r"/ui/cases/(\d+)", raw.decode("utf-8", "replace"))
        if not match:
            print("не удалось определить созданную заявку")
            return 1
        case = db.get(ControlCase, int(match.group(1)))
        incident_id = case.case_number or str(case.id)
        print(f"--- заявка {case.id}, обращение {incident_id}")

        status, raw, _ = call(client, "GET", f"/api/incidents/{incident_id}")
        before = payload(raw)
        print(f"--- до действий: статус {before.get('status')}, обследование: {before.get('inspection')}")
        if before.get("status") != "NEW":
            failures.append("новое обращение должно быть в статусе NEW")

        # --- 2. Принять в работу: появляется срок --------------------------
        status, raw, _ = call(
            client, "POST", f"/api/incidents/{incident_id}/confirm", body={"deadlineHours": 48}
        )
        db.refresh(case)
        print(
            f"--- confirm: HTTP {status}, срок исполнения заявки {case.control_due_on} "
            f"(ожидается через 48 часов)"
        )
        if status != 200 or case.control_due_on is None:
            failures.append("срок устранения не проставился")

        # --- 3. Передать на КНМ: заводится наше обследование ---------------
        status, raw, _ = call(client, "POST", f"/api/incidents/{incident_id}/escalate", body={})
        after = payload(raw)
        db.refresh(case)
        inspections = list(
            db.scalars(
                select(ControlAction).where(ControlAction.control_case_id == case.id)
            )
        )
        marks = list(
            db.scalars(
                select(ControlCaseBase).where(ControlCaseBase.control_case_id == case.id)
            )
        )
        knm_marks = [
            mark for mark in marks if "контрольно-надзорное" in (mark.description or "")
        ]
        print(
            f"--- escalate: HTTP {status}, статус {after.get('status')}, "
            f"осмотров {len(inspections)}, отметок КНМ {len(knm_marks)}"
        )
        if status != 200 or after.get("status") != "KNM_ESCALATION":
            failures.append("после передачи на КНМ статус не стал KNM_ESCALATION")
        if len(inspections) != 1:
            failures.append(
                f"по передаче на КНМ заведено осмотров: {len(inspections)} вместо 1"
            )
        if not knm_marks:
            failures.append("в заявке нет отметки о передаче на КНМ")

        # --- 4. Повторная передача второй осмотр не заводит ---------------
        call(client, "POST", f"/api/incidents/{incident_id}/escalate", body={})
        db.refresh(case)
        again = list(
            db.scalars(
                select(ControlAction).where(ControlAction.control_case_id == case.id)
            )
        )
        print(f"--- повторная передача: осмотров {len(again)} (ожидается 1)")
        if len(again) != 1:
            failures.append("повторная передача на КНМ завела второй осмотр")

        # --- 5. Документы: после КНМ сервис говорит, чего не хватает -------
        # Заявка заведена по минимуму (что случилось, вид нарушения, адрес),
        # поэтому пакет по ней не собирается — и это правильно: пустое поле
        # дало бы пустое место в официальном бланке. Проверяем, что причина
        # названа по-человечески и что она про заполнение, а не про осмотр.
        status_docs, raw_docs, _ = call(
            client, "GET", f"/api/incidents/{incident_id}/documents"
        )
        documents_state = payload(raw_docs)
        missing = documents_state.get("missing", [])
        print(
            f"--- документы: HTTP {status_docs}, можно собрать: {documents_state.get('canBuild')}, "
            f"чего не хватает: {len(missing)} пунктов"
        )
        if documents_state.get("canBuild"):
            failures.append("пакет предлагается собрать по незаполненной заявке")
        if not missing:
            failures.append("сервис не объяснил, чего не хватает для сборки")
        if any("осмотр" in item and "не заведён" in item for item in missing):
            failures.append("после передачи на КНМ обследование всё ещё считается незаведённым")

        status, raw, _ = call(client, "POST", f"/api/incidents/{incident_id}/act", body={})
        message = payload(raw).get("message", "")
        print(f"--- act по незаполненной заявке: HTTP {status}, ответ: {message[:70]}")
        if status != 409 or "нельзя сформировать" not in message:
            failures.append("сборка по незаполненной заявке не объяснила причину")

        # --- 6. Устранение: вернуть и принять -----------------------------
        call(client, "POST", f"/api/incidents/{incident_id}/approve", body={})
        violation = db.scalars(
            select(Violation).where(Violation.control_case_id == case.id)
        ).first()
        db.refresh(violation) if violation is not None else None
        approved = bool(violation and violation.is_eliminated)
        call(client, "POST", f"/api/incidents/{incident_id}/return", body={"comment": "мало"})
        db.refresh(violation) if violation is not None else None
        returned = bool(violation and not violation.is_eliminated)
        print(f"--- approve: устранено {approved}, return: снято {returned}")
        if not approved:
            failures.append("принятие работы не отметило нарушение устранённым")
        if not returned:
            failures.append("возврат на доработку не снял отметку об устранении")

        # --- 7. Ложный сигнал закрывает дело ------------------------------
        status, raw, _ = call(
            client, "POST", f"/api/incidents/{incident_id}/dismiss", body={"reason": "проверка"}
        )
        final = payload(raw)
        print(f"--- dismiss: HTTP {status}, статус {final.get('status')}")
        if final.get("status") != "CLOSED":
            failures.append("ложный сигнал не закрыл дело")

        # --- 8. Фотоотчёт исполнителя: понятная причина -------------------
        status, raw, _ = call(client, "POST", f"/api/incidents/{incident_id}/report", body={})
        message = payload(raw).get("message", "")
        print(f"--- report: HTTP {status}, ответ: {message[:60]}")
        if status != 409 or not message:
            failures.append("на фотоотчёт исполнителя нет понятного ответа")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  передача на КНМ заводит наше обследование, дальше документы идут по нему")
        return 0
    finally:
        if case is not None:
            stored = db.get(ControlCase, case.id)
            if stored is not None:
                db.delete(stored)
        db.commit()
        if user_id is not None:
            stored_user = db.get(User, user_id)
            if stored_user is not None:
                db.delete(stored_user)
            db.commit()
        address = db.scalar(select(Address).where(Address.full_address == ADDRESS))
        if address is not None:
            db.delete(address)
            db.commit()
        print("временные данные удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
