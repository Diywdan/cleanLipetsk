"""Проблема на КП из домовых чатов (Домовой ГЖИ → DG → CRM): дело, ревизии, справочники, площадка."""

import json
from copy import deepcopy
from uuid import uuid4

from conftest import EXEC_EKOPROM, login, pair, signed
from test_kp import load, utko_row

GUID = "7208cea8-9215-4b75-acc9-c38cacbfa32d"
LAT, LON = 52.584176, 39.476076
MEDIA_1 = "31d5802d-e62f-5ba9-bdf4-3b637d5f614e"


def media_item(media_id: str, n: int) -> dict:
    return {
        "id": media_id, "type": "image",
        "storage": {"provider": "s3", "bucket": "datagateway-media", "key": f"raw/2026/10/06/e/photo_{n:03d}.webp"},
        "content_type": "image/webp", "size_bytes": 1234, "sha256": f"sha256:{n}",
        "metadata": {"sequence": n, "download_url": f"http://minio:9000/datagateway-media/raw/photo_{n:03d}.webp",
                     "download_url_expires_at": "2026-10-06T14:23:20Z", "message_id": f"mid.{n}"},
    }


def problem(revision: int = 1, **override) -> dict:
    """Каноническое событие DG по примеру 2 ГЖИ (Ангарская, 23 А)."""
    event_id = str(uuid4())
    event = {
        "schema": "datagateway.waste_site_problem",
        "schema_version": "1.0",
        "id": event_id,
        "event_type": "waste_site_problem",
        "source": {"type": "domovoy", "system": "domovoy", "channel": "max_house_chats",
                   "problem_id": "24a0fe0c-e9d2-5c47-9465-152da16e4180", "revision": revision,
                   "external_id": f"domovoy:24a0fe0c-e9d2-5c47-9465-152da16e4180:{revision}",
                   "event_type": "waste_site_problem.created"},
        "timestamps": {"first_reported_at": "2026-10-06T07:15:13Z", "last_reported_at": "2026-10-06T07:15:13Z",
                       "resolved_at": None, "updated_at": "2026-10-06T08:20:49Z",
                       "received_at": "2026-10-06T13:23:20Z"},
        "waste_site": {"utko_id": GUID, "registry_number": "0002526-48", "code": "LP-000260",
                       "address": "Ангарская ул, в районе д. 23 А", "municipality": "Городской округ г. Липецк",
                       "coordinates": {"latitude": LAT, "longitude": LON}, "containers_qty": 6,
                       "containers_volume_m3": 13.3, "match_score": 0.8, "match_presumed": False},
        "location": {"coordinates": {"latitude": LAT, "longitude": LON},
                     "address": "Ангарская ул, в районе д. 23 А", "municipality": "Городской округ г. Липецк"},
        "problem": {
            "theme": {"eds_code": "14:434134994", "name": "Сбор и вывоз твёрдых коммунальных отходов",
                      "short_name": "Вывоз ТКО", "group": "Вывоз мусора"},
            "status": "open", "summary": "Мусор реже вывозят.",
            "houses_count": 1, "messages_count": 1, "residents_count": 1, "media_count": 1,
            "responsible_hint": {"preliminary": True, "basis": "тема ЕДС",
                                 "organizations": [{"name": 'АО "ЭкоПром-Липецк"', "inn": "4825037859",
                                                    "kind": "Региональные операторы по обращению с отходами"}]},
        },
        "houses": [{
            "fias": "f288e5ff-615b-4bad-90f9-96993979cbcc",
            "address": "398902, Россия, Липецкая обл, г. Липецк, ул. Ангарская, д. 27",
            "coordinates": {"latitude": 52.584177, "longitude": 39.475567}, "distance_to_site_m": 34,
            "description": "Мусор реже вывозят.", "resolved": False, "resolved_at": None,
            "messages": [
                {"message_id": "mid.1", "sent_at": "2026-10-06T07:15:13Z", "author": "житель 1", "kind": "problem",
                 "text": "Редко вывозят мусор?", "media_ids": [MEDIA_1]},
                {"message_id": "mid.photo", "sent_at": "2026-10-06T07:15:14Z", "author": "житель 1",
                 "kind": "problem", "text": None, "media_ids": []},
            ],
        }],
        "media": [media_item(MEDIA_1, 1)],
        "processing": {"trace_id": "trace-1"},
    }
    for path, value in override.items():
        node = event
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return event


def post_problem(client, event: dict, event_type: str = "waste_site_problem"):
    body = {"event_id": event["id"], "event_type": event_type, "source": "domovoy",
            "source_event_id": event["source"]["external_id"], "canonical": event,
            "emitted_at": "2026-10-06T13:23:30Z"}
    raw = json.dumps(body, ensure_ascii=False).encode()
    return client.post("/api/v1/integrations/datagateway/events", content=raw, headers=signed(raw, event["id"]))


def only_case(client) -> tuple[dict, dict]:
    cases = client.get("/api/v1/cases").json()
    assert cases["total"] == 1
    case = cases["items"][0]
    return case, client.get(f"/api/v1/incidents/{case['id']}").json()


def test_problem_becomes_case_on_registry_site(client):
    pair(client)
    login(client)
    load([utko_row(GUID, 2526, lat=LAT, lon=LON)], complete=True)
    event = problem()
    assert post_problem(client, event).status_code == 202

    case, incident = only_case(client)
    assert case["status"] == "NEW" and case["review_reason"] is None
    assert case["engineer_id"] is None and case["assignment_id"] is None
    assert case["executor_id"] == EXEC_EKOPROM  # «АО "ЭкоПром-Липецк"» из подсказки = «АО «ЭКОПРОМ-ЛИПЕЦК»»
    assert incident["source"] == "HOUSE_CHATS" and incident["comment"] == "Мусор реже вывозят."
    assert incident["violationType"]["name"] == "Вывоз КГО, ТКО" and "engineerId" not in incident
    assert incident["responsibles"][0]["role"] == "waste_removal"
    assert incident["kp"]["method"] == "explicit" and incident["kp"]["score"] == 1.0  # по GUID УТКО, не по точке
    assert incident["kp"]["code"] == "LP-000001"  # код из реестра CRM (с kp-codes-gzhi он совпадёт с ГЖИ), не из события
    assert incident["media"]["photoBeforeUrl"].endswith(f"/incidents/{case['id']}/media/0")
    history = incident["timeline"]["history"]
    assert [h["title"] for h in history] == ["Проблема из домовых чатов", "Сообщение в чате дома"]
    assert history[0]["type"] == "AI" and history[0]["actor"] == "Домовой (ГЖИ)"
    assert history[0]["description"] == "Вывоз ТКО: Мусор реже вывозят. Домов: 1, сообщений: 1, жителей: 1."
    assert history[1]["description"] == "г. Липецк, ул. Ангарская, д. 27: «Редко вывозят мусор?»"
    assert history[1]["actor"] == "житель 1"
    row = client.get(f"/api/v1/events/{event['id']}").json()
    assert row["status"] == "PROCESSED" and row["schema"] == "datagateway.waste_site_problem/1.0"


def test_revisions_update_one_case(client):
    pair(client)
    login(client)
    assert post_problem(client, problem()).status_code == 202

    second = problem(2)
    second["problem"]["messages_count"] = 2
    second["houses"][0]["messages"].append(
        {"message_id": "mid.2", "sent_at": "2026-10-06T09:00:00Z", "author": "житель 2", "kind": "problem",
         "text": "До сих пор не вывезли", "media_ids": ["m-2"]})
    second["media"].append(media_item("m-2", 2))
    assert post_problem(client, second).status_code == 202

    case, incident = only_case(client)
    titles = [h["title"] for h in incident["timeline"]["history"]]
    assert titles == ["Проблема из домовых чатов", "Сообщение в чате дома", "Обновление из домовых чатов",
                      "Сообщение в чате дома"]  # старое сообщение второй раз не пишется
    assert [m["id"] for m in case["media"]] == [MEDIA_1, "m-2"]
    assert client.get(f"/api/v1/cases?event_id={second['id']}").json()["total"] == 1  # консоль находит дело

    stale = problem(1)  # та же ревизия новым событием DG пришла после второй — дело не трогаем
    assert post_problem(client, stale).status_code == 202
    assert len(only_case(client)[1]["timeline"]["history"]) == 4
    row = client.get(f"/api/v1/events/{stale['id']}").json()
    assert row["status"] == "PROCESSED" and "уже учтена" in row["error"]

    resolved = problem(3, timestamps__resolved_at="2026-10-06T12:00:00Z", problem__status="resolved")
    assert post_problem(client, resolved).status_code == 202
    case, incident = only_case(client)
    assert incident["timeline"]["history"][-1]["title"] == "Жители сообщают: проблема решена"
    assert case["status"] == "NEW"  # дело закрывает инспектор, а не источник


def test_unknown_operator_waits_for_inspector(client):
    """Елец: регоператора «ТЭКО-Сервис» нет в справочнике, площадки — в реестре."""
    pair(client)
    login(client)
    event = problem(**{"waste_site__utko_id": "aabdd8d9-992e-45ad-ac90-f6d0f255ec30",
                       "location__address": "мкр. Александровский, д. 31"})
    event["problem"]["responsible_hint"]["organizations"] = [
        {"name": 'ООО "ТЭКО-Сервис"', "inn": None, "kind": "Региональные операторы по обращению с отходами"}]
    assert post_problem(client, event).status_code == 202

    case, incident = only_case(client)
    assert case["executor_id"] is None and "ТЭКО-Сервис" in case["review_reason"]
    assert incident["responsibles"] == [] and incident["kp"] is None
    assert client.get(f"/api/v1/events/{event['id']}").json()["status"] == "NEEDS_REVIEW"

    url = f"/api/v1/incidents/{case['id']}/confirm"
    denied = client.post(url, json={"deadlineHours": 48})
    assert denied.status_code == 422 and "исполнителя" in denied.json()["detail"]
    confirmed = client.post(url, json={"deadlineHours": 48, "executorId": EXEC_EKOPROM})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "IN_PROGRESS"
    assert confirmed.json()["responsibles"][0]["organization"]["id"] == EXEC_EKOPROM
    note = confirmed.json()["timeline"]["history"][-1]["description"]
    assert "назначен исполнитель АО «ЭКОПРОМ-ЛИПЕЦК»" in note


def test_unknown_theme_and_mismatched_envelope(client):
    pair(client)
    login(client)
    event = problem(**{"problem__theme__eds_code": "99:1", "problem__theme__name": "Прочее"})
    event["problem"]["responsible_hint"] = None
    assert post_problem(client, event).status_code == 202
    case, _ = only_case(client)
    assert case["type_violation_id"] is None and case["executor_id"] is None
    assert "тема ЕДС «Прочее» не сопоставлена" in case["review_reason"]

    other = deepcopy(problem())
    assert post_problem(client, other, event_type="violation").status_code == 422
