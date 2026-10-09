from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import endpoints
from src.channels import ChannelRegistry
from src.store import EAST8, parse_post, write_post


@pytest.fixture
def client(tmp_path):
    registry = ChannelRegistry(tmp_path / "channels.json", {"xinwen": {"title": "新闻联播服务", "description": "新闻"}})
    endpoints.set_channel_registry(registry)
    endpoints.set_storage_config(tmp_path / "posts", 15)
    endpoints.set_rss_token("secret")
    endpoints.set_rss_config({"title": "全部", "link": "https://example.com/rss", "self_url": "https://example.com/rss/api/rss-relay/rss.xml"}, 200, 50)
    app = FastAPI()
    app.include_router(endpoints.router)
    return TestClient(app)


def test_registry_persistence_failure_and_concurrency(tmp_path, monkeypatch):
    path = tmp_path / "channels.json"
    registry = ChannelRegistry(path, {})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: registry.create({"id": f"channel-{i}", "title": str(i), "description": "", "enabled": True}), range(12)))
    restored = ChannelRegistry(path, {"ignored": {"title": "ignored"}})
    assert len(restored.list(True)) == 13
    original = restored.get("channel-0")
    monkeypatch.setattr("src.channels.os.replace", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        restored.update("channel-0", {"title": "changed"})
    assert restored.get("channel-0") == original
    assert ChannelRegistry(path, {}).get("channel-0") == original


def test_channel_lifecycle(client):
    assert client.post("/api/channels", json={"id": "bilibili", "title": "B站"}).status_code == 201
    assert client.post("/api/channels", json={"id": "bilibili", "title": "重复"}).status_code == 409
    assert client.post("/api/channels", json={"id": "Bad/id", "title": "错误"}).status_code == 422
    assert client.patch("/api/channels/bilibili", json={"id": "changed"}).status_code == 422
    assert client.patch("/api/channels/bilibili", json={"title": "   "}).status_code == 422
    assert client.patch("/api/channels/bilibili", json={"title": None}).status_code == 422
    assert client.patch("/api/channels/unclassified", json={"enabled": False}).status_code == 422
    assert client.patch("/api/channels/missing", json={"title": "x"}).status_code == 404
    assert client.patch("/api/channels/bilibili", json={"title": "B站字幕", "enabled": False}).status_code == 200
    assert "bilibili" not in [c["id"] for c in client.get("/api/channels").json()["channels"]]
    assert any(c["id"] == "bilibili" and not c["enabled"] for c in client.get("/api/channels?include_disabled=true").json()["channels"])
    payload = {"title": "文章", "content": "正文", "source": "openclaw", "channel": "bilibili"}
    assert client.post("/api/post", json=payload).status_code == 409
    feed = client.get("/api/rss.xml?token=secret&channel=bilibili")
    assert feed.status_code == 200
    assert ET.fromstring(feed.text).findtext("channel/title") == "B站字幕"
    assert client.patch("/api/channels/bilibili", json={"enabled": True}).status_code == 200
    assert client.post("/api/post", json=payload).status_code == 201
    payload["channel"] = "unknown"
    assert client.post("/api/post", json=payload).status_code == 422


def test_save_failure_does_not_report_success(client, monkeypatch):
    monkeypatch.setattr("src.channels.os.replace", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    assert client.post("/api/channels", json={"id": "new", "title": "new"}).status_code == 503
    assert client.patch("/api/channels/xinwen", json={"title": "changed"}).status_code == 503
    channels = client.get("/api/channels").json()["channels"]
    assert not any(c["id"] == "new" for c in channels)
    assert next(c for c in channels if c["id"] == "xinwen")["title"] == "新闻联播服务"


def test_feed_filter_compatibility_auth_and_self_url(client, tmp_path):
    now = datetime.now(EAST8)
    for i in range(5):
        write_post(tmp_path / "posts", str(i), f"other-{i}", "body", created_at=now + timedelta(seconds=i))
    write_post(tmp_path / "posts", "news", "news", "body", channel="xinwen", source="openclaw", created_at=now - timedelta(seconds=1))
    legacy = tmp_path / "posts" / "0.md"
    legacy.write_text(legacy.read_text(encoding="utf-8").replace("channel: unclassified\n", ""), encoding="utf-8")
    assert parse_post(legacy)["channel"] == "unclassified"
    feed = client.get("/api/rss.xml?token=secret&channel=xinwen&limit=1")
    xml = ET.fromstring(feed.text)
    assert xml.findtext("channel/title") == "新闻联播服务"
    assert [i.findtext("guid") for i in xml.findall("channel/item")] == ["news"]
    self_url = xml.find("channel/{http://www.w3.org/2005/Atom}link").attrib["href"]
    assert self_url == "https://example.com/rss/api/rss-relay/rss.xml?token=secret&channel=xinwen&limit=1"
    assert len(ET.fromstring(client.get("/api/rss.xml?token=secret").text).findall("channel/item")) == 6
    assert client.get("/api/rss.xml?token=bad&channel=missing").status_code == 401
    assert client.get("/api/rss.xml?token=secret&channel=missing").status_code == 404
    assert client.get("/api/rss.xml?channel=xinwen").status_code == 422
    endpoints.set_rss_token("")
    assert client.get("/api/rss.xml?token=secret&channel=xinwen").status_code == 401
    endpoints.set_rss_token("secret")
    assert client.post("/api/post", json={"title": "legacy", "content": "body"}).status_code == 201
    assert client.get("/api/posts").json()["posts"][0]["channel"] == "unclassified"


def test_posts_filter_before_limit_and_disabled_history(client, tmp_path):
    now = datetime.now(EAST8)
    for i in range(5):
        write_post(tmp_path / "posts", f"other-{i}", "other", "body", created_at=now)
    write_post(tmp_path / "posts", "news-history", "news", "body", channel="xinwen",
               created_at=now - timedelta(minutes=1))
    response = client.get("/api/posts?channel=xinwen&limit=1")
    assert response.status_code == 200
    assert [post["id"] for post in response.json()["posts"]] == ["news-history"]
    assert response.json()["total"] == 1
    assert client.get("/api/posts?channel=missing").status_code == 404
    assert client.patch("/api/channels/xinwen", json={"enabled": False}).status_code == 200
    assert client.get("/api/posts?channel=xinwen").json()["posts"][0]["id"] == "news-history"
    assert len(client.get("/api/posts").json()["posts"]) == 6
    assert len(client.get("/api/posts?channel=unclassified").json()["posts"]) == 5
