"""Проверка сборки снимка данных по демонстрационному делу.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_context.py
"""

import json

from app.db.session import SessionLocal
from app.models.enums import SnapshotEntityKind
from app.services import snapshots


def main() -> None:
    db = SessionLocal()
    try:
        payload = snapshots.build_case_context(db, 1)

        print("=== контролируемое лицо ===")
        print(payload["controlled_person"]["representation"])
        print("ИНН:", payload["controlled_person"]["requisites"]["inn"])
        print("адрес:", payload["controlled_person"]["requisites"]["legal_address"])
        print("контакты:", payload["controlled_person"]["contacts"])

        print("=== объект контроля ===")
        print(payload["control_object"]["type"], "|", payload["control_object"]["address"])

        print("=== дело ===")
        case = payload["case"]
        print("вид контроля:", case["control_kind"])
        print("форма:", case["control_form"], "| без взаимодействия:", case["control_form_without_interaction"])
        print("ЕРКНМ:", case["erp_number"])
        print(
            "фактические сроки:",
            case["actual_start_date_words"],
            case["actual_start_time"],
            "—",
            case["actual_end_time"],
        )
        print("задание:", case["assignment_number"], "от", case["assignment_date_words"])

        print("=== инспекторы ===")
        for inspector in payload["inspectors"]:
            print(" ", inspector["position"], "|", inspector["short_name"], "|", inspector["role"])
        print("утверждает:", payload["approver"]["position"], "|", payload["approver"]["short_name"])

        print("=== основания ===")
        for base in payload["bases"]:
            print(" ", base["kind"], base["document_number"], "от", base["document_date_words"])

        print("=== действия ===")
        for action in payload["actions"]:
            print(" ", action["type"], action["started_time"], "-", action["ended_time"], "|", action["place"])

        print("=== нарушения ===")
        for violation in payload["violations"]:
            print(" ", violation["description"][:80], "...")
            for provision in violation["provisions"]:
                print("   норма:", provision["reference"], "|", provision["npa_title"])

        print("=== предписание ===")
        prescription = payload["prescription"]
        print(" №", prescription["number"], "от", prescription["issued_on_words"], "срок до", prescription["due_on_words"])
        for item in prescription["items"]:
            print("  пункт:", (item["requirement_text"] or "")[:70], "...")

        digest_1 = snapshots.payload_digest(payload, "prescription-v1")
        digest_2 = snapshots.payload_digest(payload, "prescription-v1")
        print("=== снимок ===")
        print("хэш стабилен:", digest_1 == digest_2, digest_1[:16])

        snapshot = snapshots.save_snapshot(
            db,
            payload,
            entity_kind=SnapshotEntityKind.CASE,
            entity_id=1,
            template_version="prescription-v1",
        )
        print("сохранён снимок id:", snapshot.id, "sha256:", snapshot.sha256[:16])
        print("размер payload, байт:", len(json.dumps(payload, ensure_ascii=False)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
