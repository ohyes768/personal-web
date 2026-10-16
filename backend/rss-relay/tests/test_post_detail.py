from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import endpoints
from src.channels import ChannelRegistry
from src.store import EAST8, find_post, write_post


@pytest.fixture
def client(tmp_path):
    registry = ChannelRegistry(tmp_path / "channels.json", {})
    endpoints.set_channel_registry(registry)
    endpoints.set_storage_config(tmp_path / "posts", 15)
    endpoints.set_rss_token("secret")
    endpoints.set_rss_config({"title": "全部", "link": "https://example.com/rss", "self_url": "https://example.com/rss/api/rss-relay/rss.xml"}, 200, 50)
    app = FastAPI()
    app.include_router(endpoints.router)
    return TestClient(app)


def test_create_post_returns_detail_url(client, tmp_path):
    response = client.post("/api/post", json={"title": "标题", "content": "正文", "source": "openclaw"})
    assert response.status_code == 201
    body = response.json()
    post_id = body["id"]
    assert body["detail_url"] == f"https://example.com/rss/view/{post_id}"
    # 已存在的文件可通过单篇接口读回
    assert client.get(f"/api/post/{post_id}").status_code == 200


def test_get_post_detail_matches_list_item(client, tmp_path):
    write_post(tmp_path / "posts", "detail-1", "标题", "正文 markdown", url="https://example.com/a", source="openclaw", channel="unclassified")
    single = client.get("/api/post/detail-1")
    assert single.status_code == 200
    listed = client.get("/api/posts?limit=1").json()["posts"][0]
    assert single.json() == listed


def test_get_post_not_found_and_expired(client, tmp_path):
    assert client.get("/api/post/missing-id").status_code == 404
    expired = datetime.now(EAST8) - timedelta(days=16)
    write_post(tmp_path / "posts", "expired", "旧文", "正文", created_at=expired)
    assert client.get("/api/post/expired").status_code == 404


def test_get_post_rejects_invalid_id(client, tmp_path):
    # 路径穿越 / 超长 id：store 层直接拒绝，API 层转 404
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()
    assert find_post(posts_dir, "../escape") is None
    assert find_post(posts_dir, "a\\b") is None
    assert find_post(posts_dir, "x" * 201) is None
    assert client.get(f"/api/post/{'x' * 201}").status_code == 404


def test_find_post_parses_existing_file(tmp_path):
    write_post(tmp_path / "posts", "found", "标题", "正文", source="openclaw")
    post = find_post(tmp_path / "posts", "found")
    assert post is not None
    assert post["title"] == "标题"
    assert post["content"] == "正文"
