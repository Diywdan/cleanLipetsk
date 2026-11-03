"""Фронт и подложка карты с того же адреса, что и API, и пустой справочник КП до реестра НСИ."""

import importlib

from fastapi.testclient import TestClient

from conftest import login


def test_kp_is_empty_until_registry(client):
    assert client.get("/api/v1/kp").status_code == 401
    login(client)
    assert client.get("/api/v1/kp").json() == []


def test_web_served_next_to_api(client, tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Диспетчерская</title>", encoding="utf-8")
    (web / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("CRM_WEB_DIR", str(web))
    from app import config, main

    config.get_settings.cache_clear()
    reloaded = importlib.reload(main)
    try:
        with TestClient(reloaded.app) as browser:
            page = browser.get("/")
            assert "Диспетчерская" in page.text
            assert page.headers["cache-control"] == "no-cache"  # после выкладки браузер берёт новую сборку
            asset = browser.get("/assets/app.js")
            assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
            assert browser.get("/admin/admin.js").headers["cache-control"] == "no-cache"
            assert "cache-control" not in browser.get("/api/v1/auth/me").headers
            assert browser.get("/health").json()["status"] == "ok"  # API не перекрыт
            assert browser.get("/api/v1/auth/me").status_code == 401
    finally:
        monkeypatch.delenv("CRM_WEB_DIR")
        config.get_settings.cache_clear()
        importlib.reload(main)


def test_map_tiles_served_by_range(tmp_path, monkeypatch):
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "lipetsk.pmtiles").write_bytes(bytes(range(256)) * 4)
    monkeypatch.setenv("CRM_MAPS_DIR", str(maps))
    from app import config, main

    config.get_settings.cache_clear()
    reloaded = importlib.reload(main)
    try:
        with TestClient(reloaded.app) as browser:
            # Карта читает файл кусками; без Range подложка молча пустая
            part = browser.get("/maps/lipetsk.pmtiles", headers={"Range": "bytes=16-31"})
            assert part.status_code == 206
            assert part.content == bytes(range(16, 32))
            assert part.headers["content-range"] == "bytes 16-31/1024"
            assert browser.head("/maps/lipetsk.pmtiles").status_code == 200  # фронт так проверяет, что файл на месте
            assert browser.get("/maps/missing.pmtiles").status_code == 404
    finally:
        monkeypatch.delenv("CRM_MAPS_DIR")
        config.get_settings.cache_clear()
        importlib.reload(main)
