import time

import pytest
from fastapi.testclient import TestClient

from src.collector import collect_latest
from src.main import create_app
from src.ximalaya import (CredentialsMissing, XimalayaApiError,
                          XimalayaClient, collect_ximalaya_official, pick_age, sign)

ALBUMS = [{
    "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
    "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
    "age_confidence": "高",
}]


def test_sign_matches_official_algorithm_snapshot():
    params = {"app_key": "test-key", "calc_dimension": "1", "category_id": "6",
              "client_os_type": "4", "nonce": "abc123", "device_id": "0123456789abcdef",
              "device_id_type": "UUID", "server_api_version": "1.0.0",
              "timestamp": "1700000000000"}
    # 快照值来自官方文档算法（Base64 → HMAC-SHA1 原始字节 → MD5 小写）手工核对。
    assert sign(params, "test-secret") == "bdb6208095d06a4203a1fdd83967aa29"


def test_from_env_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("XM_APP_KEY", raising=False)
    monkeypatch.delenv("XM_APP_SECRET", raising=False)
    with pytest.raises(CredentialsMissing):
        XimalayaClient.from_env()


def make_metadata(age_values: list[str]) -> list[dict]:
    """模拟 /v2/metadata/list：儿童内容分类(儿歌/哄睡音乐) + 可选年龄层。"""
    tree = [{
        "id": 11173, "display_name": "儿童内容分类", "kind": "metadata",
        "attributes": [{
            "attr_key": 31914, "attr_value": "儿童音乐", "display_name": "儿童音乐",
            "child_metadatas": [{
                "id": 11176, "display_name": "儿童音乐", "kind": "metadata",
                "attributes": [
                    {"attr_key": 351279, "attr_value": "哄睡音乐", "display_name": "哄睡音乐"},
                    {"attr_key": 10, "attr_value": "儿歌", "display_name": "儿歌"},
                ]}]}]}]
    if age_values:
        tree.append({
            "id": 10384, "display_name": "年龄层", "kind": "metadata",
            "attributes": [{"attr_key": 900 + i, "attr_value": v, "display_name": v}
                           for i, v in enumerate(age_values)]})
    return tree


class FakeClient:
    def __init__(self, age_values: list[str], albums: list[dict]):
        self.categories = [{"id": 6, "category_name": "儿童"}]
        self.metadata = make_metadata(age_values)
        self.albums = albums
        self.album_queries: list[dict] = []

    def get(self, path: str, **params: str):
        if path == "/categories/list":
            return self.categories
        if path == "/v2/metadata/list":
            return self.metadata
        if path == "/v2/metadata/albums":
            self.album_queries.append(params)
            return {"total_count": len(self.albums), "albums": self.albums}
        raise AssertionError(f"unexpected path {path}")


def album(album_id: int, title: str, **extra: object) -> dict:
    return {"id": album_id, "album_title": title, "play_count": 100, **extra}


def test_pick_age_prefers_0_1_over_0_3():
    attrs = [{"owner_id": "10384", "value": "0-3岁", "display_name": "0-3岁"},
             {"owner_id": "10384", "value": "0-1岁", "display_name": "0-1岁"}]
    assert pick_age(attrs)["value"] == "0-1岁"


def test_pick_age_accepts_variant_writing():
    attrs = [{"owner_id": "10384", "value": "0~1岁", "display_name": "0~1岁"}]
    assert pick_age(attrs)["value"] == "0~1岁"


def test_collect_marks_exact_age_and_filters_request_by_it():
    client = FakeClient(["0-1岁", "3-6岁"], [album(100, "宝宝儿歌", is_paid=True)])
    rows = collect_ximalaya_official(client)
    assert rows[0]["platform"] == "喜马拉雅开放平台"
    assert rows[0]["age_confidence"] == "高"
    assert rows[0]["sale_type"] == 1
    # is_paid 缺失时不得猜测付费状态。
    client_unknown = FakeClient(["0-1岁", "3-6岁"], [album(101, "免费缺失标记")])
    assert collect_ximalaya_official(client_unknown)[0]["sale_type"] is None
    assert "平台元数据精确年龄段 0-1岁" in rows[0]["age_evidence"]
    # 年龄属性必须拼进过滤条件，而不是仅当标签用。
    assert any("10384:0-1岁" in q["metadata_attributes"] for q in client.album_queries)


def test_collect_falls_back_to_0_3_age():
    client = FakeClient(["0-3岁", "3-6岁"], [album(101, "哄睡轻音乐")])
    rows = collect_ximalaya_official(client)
    assert "平台元数据精确年龄段 0-3岁" in rows[0]["age_evidence"]


def test_collect_marks_inference_when_platform_has_no_age_metadata():
    # 现状：开放平台儿童分类无年龄段元数据，须如实标记推断来源。
    client = FakeClient([], [album(102, "白噪音哄睡")])
    rows = collect_ximalaya_official(client)
    assert rows[0]["age_confidence"] == "中"
    assert "由内容属性" in rows[0]["age_evidence"]
    assert "0-1岁/0-3岁" in rows[0]["age_evidence"]
    assert all("10384" not in q["metadata_attributes"] for q in client.album_queries)


def test_collect_returns_empty_when_openapi_has_no_kids_albums():
    client = FakeClient([], albums=[])
    assert collect_ximalaya_official(client) == []


def test_collect_requires_child_category():
    client = FakeClient([], [])
    client.categories = [{"id": 3, "category_name": "有声书"}]
    with pytest.raises(XimalayaApiError):
        collect_ximalaya_official(client)


def test_collect_latest_falls_back_to_web_when_official_empty(monkeypatch):
    monkeypatch.delenv("XM_APP_KEY", raising=False)
    monkeypatch.delenv("XM_APP_SECRET", raising=False)
    monkeypatch.setattr("src.collector.collect_qingting", lambda: ALBUMS)
    monkeypatch.setattr("src.collector.collect_ximalaya_web", lambda: [])
    rows = collect_latest()
    assert rows == ALBUMS


def web_api_response(channel_name: str, albums: list[dict]) -> dict:
    return {"data": {"channels": [{"channelName": channel_name,
                                   "relationMetadataValueId": 10}]}}


def test_collect_ximalaya_web_ranks_age_evidence(monkeypatch):
    from src import collector
    responses = {
        collector.XM_GROUP_ALL: {"data": {"groups": [{"id": 11, "name": "儿童"}]}},
        collector.XM_GROUP_CHANNELS: web_api_response("儿歌", []),
        collector.XM_CHANNEL_ALBUMS: {"data": {"albums": [
            {"albumId": 1, "albumTitle": "宝宝儿歌 0-1岁", "intro": "", "isPaid": False},
            {"albumId": 2, "albumTitle": "三字儿歌学说话 0-3岁早教", "intro": "", "isPaid": False},
            {"albumId": 3, "albumTitle": "贝乐虎儿歌", "intro": "唱跳儿歌", "isPaid": False},
        ]}},
    }

    def fake_get(url, **params):
        return responses[url]

    monkeypatch.setattr(collector, "_get_json", fake_get)
    rows = collector.collect_ximalaya_web()
    # 儿歌频道无年龄标注的不收，避免混入 3 岁以上内容。
    assert [r["album_id"] for r in rows] == ["1", "2"]
    assert rows[0]["age_confidence"] == "高" and "标注 0-1 岁" in rows[0]["age_evidence"]
    assert rows[1]["age_confidence"] == "中" and "低龄推断" in rows[1]["age_evidence"]


def test_collect_ximalaya_web_lullaby_channel_infers_from_scene(monkeypatch):
    from src import collector
    responses = {
        collector.XM_GROUP_ALL: {"data": {"groups": [{"id": 11, "name": "儿童"}]}},
        collector.XM_GROUP_CHANNELS: web_api_response("哄睡", []),
        collector.XM_CHANNEL_ALBUMS: {"data": {"albums": [
            {"albumId": 9, "albumTitle": "晚安妈妈睡前故事", "intro": "", "isPaid": True},
        ]}},
    }
    monkeypatch.setattr(collector, "_get_json", lambda url, **p: responses[url])
    rows = collector.collect_ximalaya_web()
    assert rows[0]["age_confidence"] == "中"
    assert "婴幼儿向哄睡内容" in rows[0]["age_evidence"]
    assert rows[0]["sale_type"] == 1


def test_collect_ximalaya_web_rejects_school_age_and_adult_lullabies(monkeypatch):
    from src import collector
    responses = {
        collector.XM_GROUP_ALL: {"data": {"groups": [{"id": 11, "name": "儿童"}]}},
        collector.XM_GROUP_CHANNELS: web_api_response("哄睡", []),
        collector.XM_CHANNEL_ALBUMS: {"data": {"albums": [
            {"albumId": 1, "albumTitle": "孙悟空上学记 | 睡前故事", "intro": "", "isPaid": False},
            {"albumId": 2, "albumTitle": "失眠小姐，不要在深夜流浪", "intro": "", "isPaid": False},
            {"albumId": 3, "albumTitle": "晚安妈妈睡前故事", "intro": "", "isPaid": False},
        ]}},
    }
    monkeypatch.setattr(collector, "_get_json", lambda url, **p: responses[url])
    rows = collector.collect_ximalaya_web()
    # 学龄向与成人助眠节目都不收，只留婴幼儿向哄睡内容。
    assert [r["album_id"] for r in rows] == ["3"]


def test_collect_ximalaya_web_requires_kids_group(monkeypatch):
    from src import collector
    monkeypatch.setattr(collector, "_get_json",
                        lambda url, **p: {"data": {"groups": [{"id": 1, "name": "小说"}]}})
    with pytest.raises(RuntimeError):
        collector.collect_ximalaya_web()


def test_monthly_auto_refresh_persists_albums(tmp_path):
    def collector():
        return ALBUMS

    app = create_app(data_dir=tmp_path / "data", collector=collector,
                     auto_refresh_seconds=3600)
    # collector 线程先采集后落库，轮询等待数据库出现结果而非依赖采集回调时序。
    deadline = time.monotonic() + 10
    with TestClient(app) as client:
        listing = client.get("/api/albums").json()
        while not listing["albums"] and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
    assert listing["albums"][0]["title"] == "摇篮曲"
