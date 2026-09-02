"""
API 接口单测：用 in-memory DB 覆盖依赖
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from src.db.models import Base


@pytest.fixture
def client(seeded_db, monkeypatch):
    """TestClient + 数据库依赖注入到 in-memory 库"""
    from src.db.session import get_db
    from src.main import app

    def _override():
        yield seeded_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealth:
    def test_health(self, client):
        assert client.get("/api/funds/health").json() == {"status": "ok"}


class TestScreen:
    def test_no_filter(self, client):
        r = client.get("/api/funds/screen")
        assert r.status_code == 200
        assert r.json()["total"] == 3  # is_active=False 被排除

    def test_filter_combo(self, client):
        r = client.get("/api/funds/screen?min_age=3&min_size_yi=1&max_dd_3y=5&min_mgr_exp=5")
        assert r.status_code == 200
        assert [it["code"] for it in r.json()["items"]] == ["000001"]

    def test_invalid_sort_422(self, client):
        r = client.get("/api/funds/screen?sort=name; DROP TABLE funds")
        assert r.status_code == 422

    def test_invalid_param_range_422(self, client):
        assert client.get("/api/funds/screen?min_age=-1").status_code == 422
        assert client.get("/api/funds/screen?order=up").status_code == 422

    def test_stock_screen_does_not_include_bond_seed(self, client):
        """股票 yaml 在夹具里为空；债基种子不得出现在 /stock/screen。"""
        r = client.get("/api/funds/stock/screen")
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []


class TestStats:
    def test_bond_stats_total_is_universe(self, client):
        r = client.get("/api/funds/stats")
        assert r.status_code == 200
        assert r.json()["total"] == 3  # 000001/000002/000004

    def test_stock_stats_empty_when_stock_universe_unpatched(self, client):
        """seeded_db 把股票 yaml 打成空名单，股票 stats 不得把债基算进去。"""
        r = client.get("/api/funds/stock/stats")
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestDetail:
    def test_detail_found(self, client):
        r = client.get("/api/funds/000001")
        assert r.status_code == 200
        d = r.json()
        assert d["fees"]["fee_mgmt"] == 0.3
        assert d["holdings"]["rate_bond_pct"] == 30.0

    def test_detail_404(self, client):
        assert client.get("/api/funds/999999").status_code == 404


class TestExportCsv:
    def test_csv_bom_and_header(self, client):
        r = client.get("/api/funds/export/csv")
        assert r.status_code == 200
        assert r.content.startswith("﻿".encode("utf-8"))  # BOM
        assert "基金代码" in r.text
        assert "attachment" in r.headers["content-disposition"]
        assert "funds_" in r.headers["content-disposition"]

    def test_csv_respects_filter(self, client):
        r = client.get("/api/funds/export/csv?min_age=3&min_mgr_exp=5")
        lines = r.text.strip().splitlines()
        # header + 000001 + 000004（D 无业绩但 age/mgr 满足，LEFT JOIN 保留）
        assert len(lines) == 3
        assert "000002" not in r.text


class TestRefreshStatus:
    def test_status_404_when_empty(self, seeded_db, monkeypatch):
        """无刷新记录 → 404（seeded_db 无 RefreshRun）"""
        from src.db.session import get_db
        from src.main import app

        def _override():
            yield seeded_db

        app.dependency_overrides[get_db] = _override
        with TestClient(app) as c:
            assert c.get("/api/funds/refresh/status").status_code == 404
        app.dependency_overrides.clear()
