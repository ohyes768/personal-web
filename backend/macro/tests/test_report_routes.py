"""报告看板 API 路由测试

隔离策略:
- 路由层 token 走全局 settings 单例属性(monkeypatch 自动还原)
- service 的 get_settings patch 后数据目录指向 tmp_path
  (basetemp 已重定向项目盘,见 .trellis/spec/backend/testing-environment.md)
"""
import os

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router
from src.services import report_board_service as rbs
from src.services.report_board_service import ReportBoardService

TOKEN = "test-token"
SOURCE_A = "a-share-macro-impact-skill"
SOURCE_B = "bond-market-macro-impact-skill"

UPLOAD_BODY = {
    "title": "2026-09-23 A股宏观展望｜偏支撑",
    "content": "# 核心判断\n测试正文。",
    "source": SOURCE_A,
    "url": "https://example.com/r",
}


class _FakeSettings:
    def __init__(self, data_dir: str):
        self.macro_report_data_dir = data_dir


def make_client(tmp_path, monkeypatch, token=TOKEN):
    """挂 router 的 TestClient;token 写入路由层 settings,数据目录指向 tmp_path"""
    monkeypatch.setattr(routes.settings, "macro_signal_upload_token", token)
    monkeypatch.setattr(
        rbs, "get_settings", lambda: _FakeSettings(str(tmp_path / "reports"))
    )
    # 重置单例:路由走 get_report_board_service(),上一测试残留的单例
    # settings 仍指旧 tmp_path,会导致重推误判 duplicate
    monkeypatch.setattr(rbs, "_singleton", None)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def auth_header(token=TOKEN):
    return {"X-Upload-Token": token}


def test_upload_401_without_token(tmp_path, monkeypatch):
    """无 X-Upload-Token header → 401"""
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/reports/upload", json=UPLOAD_BODY)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_upload_401_with_wrong_token(tmp_path, monkeypatch):
    """token 错误 → 401"""
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/reports/upload", json=UPLOAD_BODY, headers=auth_header("wrong")
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_upload_401_when_token_unconfigured(tmp_path, monkeypatch):
    """服务端未配置 token → 401 fail closed"""
    client = make_client(tmp_path, monkeypatch, token="")
    resp = client.post("/api/reports/upload", json=UPLOAD_BODY, headers=auth_header())
    assert resp.status_code == 401
    assert "未配置" in resp.json()["detail"]
    assert "MACRO_SIGNAL_UPLOAD_TOKEN" in resp.json()["detail"]


def test_upload_400_invalid_source(tmp_path, monkeypatch):
    """白名单外 source → 400"""
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/reports/upload",
        json={**UPLOAD_BODY, "source": "not-allowed-skill"},
        headers=auth_header(),
    )
    assert resp.status_code == 400
    assert "非法 source" in resp.json()["detail"]


def test_upload_list_detail_flow(tmp_path, monkeypatch):
    """上传 → 列表 → 详情 全链路"""
    client = make_client(tmp_path, monkeypatch)

    up = client.post("/api/reports/upload", json=UPLOAD_BODY, headers=auth_header())
    assert up.status_code == 200
    body = up.json()
    assert body["success"] is True
    report_id = body["data"]["report_id"]
    assert body["data"]["duplicate"] is False

    # 追加第二篇(另一来源,验证列表多来源)
    up2 = client.post(
        "/api/reports/upload",
        json={
            "title": "2026-09-22 利率债展望｜中性",
            "content": "债市正文",
            "source": SOURCE_B,
        },
        headers=auth_header(),
    )
    assert up2.status_code == 200

    # 列表:倒序
    lst = client.get("/api/reports")
    assert lst.status_code == 200
    data = lst.json()["data"]
    assert data["total"] == 2
    assert [r["analyzed_at"] for r in data["reports"]] == ["2026-09-23", "2026-09-22"]

    # 列表:source 筛选
    lst_a = client.get("/api/reports", params={"source": SOURCE_A})
    data_a = lst_a.json()["data"]
    assert data_a["total"] == 1
    assert data_a["reports"][0]["source"] == SOURCE_A

    # 详情:含 markdown 正文
    detail = client.get(f"/api/reports/{report_id}")
    assert detail.status_code == 200
    d = detail.json()["data"]
    assert d["report_id"] == report_id
    assert d["title"] == UPLOAD_BODY["title"]
    assert d["content"] == UPLOAD_BODY["content"]
    assert d["url"] == UPLOAD_BODY["url"]


def test_upload_duplicate_idempotent(tmp_path, monkeypatch):
    """同 (source, title) 重推:duplicate=true、不新增文件、total 不变"""
    client = make_client(tmp_path, monkeypatch)
    first = client.post("/api/reports/upload", json=UPLOAD_BODY, headers=auth_header())
    second = client.post(
        "/api/reports/upload",
        json={**UPLOAD_BODY, "content": "重推内容"},
        headers=auth_header(),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["data"]["duplicate"] is True
    assert second.json()["data"]["report_id"] == first.json()["data"]["report_id"]

    assert client.get("/api/reports").json()["data"]["total"] == 1


def test_get_report_404_unknown(tmp_path, monkeypatch):
    """未知 id → 404;路径穿越形态 id → 404"""
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/reports/no-such-id-0000").status_code == 404
    assert client.get("/api/reports/..%2F..%2Fsecret").status_code == 404
