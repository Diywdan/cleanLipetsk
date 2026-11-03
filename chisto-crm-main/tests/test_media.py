"""Фото из событий DG по постоянной ссылке CRM: копия при приёме, свежая ссылка DG, видео потоком."""

import email.message
import io
import json

import pytest

from conftest import EXEC_DDHIB, canonical_event, login, pair, post_event
from test_workflow import as_user

JPEG = b"\xff\xd8\xff\xe0" + b"\x01" * 300
LIVE = "http://minio:9000/datagateway/media/a.jpg?X-Amz-Signature=live"
FRESH = "http://minio:9000/datagateway/media/a.jpg?X-Amz-Signature=fresh"


def item(kind="image", expires="2099-01-01T00:00:00Z", key="media/a.jpg"):
    return {"id": f"m-{kind}", "type": kind, "storage": {"provider": "s3", "bucket": "datagateway", "key": key},
            "content_type": "image/jpeg" if kind == "image" else "video/mp4", "size_bytes": 304, "sha256": "x",
            "metadata": {"download_url": LIVE, "download_url_expires_at": expires}}


class Fake:
    def __init__(self, body: bytes, content_type: str):
        self.body = io.BytesIO(body)
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body))

    def read(self, n=-1):
        return self.body.read(n)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def dg(monkeypatch):
    """Хранилище DG: живая ссылка, выдача свежей по ключу; calls — какие адреса открывались."""
    state = {"calls": [], "down": False, "live_expired": False}

    def urlopen(url, timeout=None):
        state["calls"].append(url)
        if state["down"]:
            raise OSError("connection refused")
        if url.startswith("http://datagateway:8000/api/v1/storage/object?key="):
            return Fake(json.dumps({"url": FRESH, "expires_seconds": 300}).encode(), "application/json")
        if url == LIVE and state["live_expired"]:
            raise OSError("403 expired")
        if url in (LIVE, FRESH):
            return Fake(b"\x00\x00\x00\x18ftypmp42" if "video" in state.get("kind", "") else JPEG,
                        state.get("kind", "image/jpeg"))
        raise AssertionError(url)

    monkeypatch.setattr("app.media.urlopen", urlopen)
    return state


def new_case(client, media):
    pair(client)
    assert post_event(client, canonical_event(media=media)).status_code == 202
    login(client)
    return client.get("/api/v1/incidents").json()[0]


def test_photo_copied_on_receipt_and_served_by_crm(client, dg):
    incident = new_case(client, [item()])
    url = f"/api/v1/incidents/{incident['id']}/media/0"
    assert incident["media"]["photoBeforeUrl"] == url
    assert dg["calls"] == [LIVE]  # забрали при приёме, по ссылке из события
    response = client.get(url)
    assert response.status_code == 200 and response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert dg["calls"] == [LIVE]  # дальше отдаём свою копию, DG не нужен
    stored = client.get(f"/api/v1/cases/{incident['id']}").json()["media"][0]
    assert stored["crm_file"].endswith(".jpg")


def test_expired_link_gets_fresh_one_from_dg(client, dg):
    dg["down"] = True  # при приёме DG недоступен — дело всё равно заводится
    incident = new_case(client, [item(expires="2020-01-01T00:00:00Z")])
    dg.update(down=False, calls=[])
    response = client.get(f"/api/v1/incidents/{incident['id']}/media/0")
    assert response.status_code == 200 and response.content == JPEG
    assert dg["calls"] == ["http://datagateway:8000/api/v1/storage/object?key=media%2Fa.jpg", FRESH]


def test_dg_down_without_copy_is_502(client, dg):
    dg["down"] = True
    incident = new_case(client, [item()])
    assert client.get(f"/api/v1/incidents/{incident['id']}/media/0").status_code == 502
    assert client.get(f"/api/v1/incidents/{incident['id']}/media/5").status_code == 404


def test_video_streams_without_copy(client, dg):
    dg["kind"] = "video/mp4"
    incident = new_case(client, [item("video")])
    assert incident["media"]["photoBeforeUrl"] == ""
    response = client.get(f"/api/v1/incidents/{incident['id']}/media/0")
    assert response.status_code == 200 and response.headers["content-type"] == "video/mp4"
    assert "crm_file" not in client.get(f"/api/v1/cases/{incident['id']}").json()["media"][0]


def test_other_organization_cannot_see_photo(client, dg):
    incident = new_case(client, [item()])
    stranger = as_user(client, "other", "other-master-pass-1", ["uk_master"], "EXEC-0003")
    assert stranger.get(f"/api/v1/incidents/{incident['id']}/media/0").status_code == 404
    own = as_user(client, "own", "own-master-pass-12", ["uk_master"], EXEC_DDHIB)
    assert own.get(f"/api/v1/incidents/{incident['id']}/media/0").status_code == 200


def test_console_event_media(client, dg):
    incident = new_case(client, [item()])
    event_id = incident["eventId"]
    response = client.get(f"/api/v1/events/{event_id}/media/0")
    assert response.status_code == 200 and response.content == JPEG


def test_cli_media_cache_takes_missing_copies(client, dg):
    dg["down"] = True
    new_case(client, [item()])
    dg.update(down=False, calls=[])
    from app.cli import media_cache

    assert media_cache() == (1, 1)
    assert media_cache() == (0, 0)
