"""lookup API 测试（11-14-fund-code-quick-search）

重点：
- 路由顺序：/lookup/{code} 不能被通用 /{code} 吞掉（contracts §13 陷阱）
- found=false 走 200 不是 404（业务结果 vs 错误）
- 格式非法走 422（调用方 bug）
- DTO 七个字段全部透出（§3a 静默砍字段）
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, Fund


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add_all([
        Fund(code="000003", name="市场股基", fund_type="股票型", age_years=5.0,
             size_yi=10.0, mgr_name="张", mgr_company="某", mgr_days=1000,
             mgr_experience_years=5.0, is_active=True,
             market_type="stock", market_subtype="股票型"),
        Fund(code="000004", name="市场债基", fund_type="债券型", age_years=5.0,
             size_yi=10.0, mgr_name="张", mgr_company="某", mgr_days=1000,
             mgr_experience_years=5.0, is_active=True,
             market_type="bond", market_subtype="债券型-信用债"),
    ])
    db.commit()

    monkeypatch.setattr("src.services.lookup_service._yaml_membership",
                        lambda: (set(), set()))

    from src.db.session import get_db
    from src.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


class TestLookupApi:
    def test_found_stock(self, client):
        r = client.get("/api/funds/lookup/000003")
        assert r.status_code == 200
        b = r.json()
        assert b["found"] is True
        assert b["tab"] == "discovery-stock"
        assert b["path"] == "/discovery-stock?code=000003"
        assert b["name"] == "市场股基"

    def test_found_bond(self, client):
        b = client.get("/api/funds/lookup/000004").json()
        assert b["tab"] == "discovery-bond"

    def test_not_found_returns_200(self, client):
        """查不到 = 业务结果，返回 200 + found=false（不是 404）。"""
        r = client.get("/api/funds/lookup/999999")
        assert r.status_code == 200
        b = r.json()
        assert b["found"] is False
        assert b["tab"] is None and b["path"] is None

    @pytest.mark.parametrize("code", ["abc", "12345", "1234567", "00000a"])
    def test_invalid_format_422(self, client, code):
        assert client.get(f"/api/funds/lookup/{code}").status_code == 422

    def test_route_not_swallowed_by_detail(self, client):
        """路由顺序：若被 /{code} 吞掉会返回基金详情结构（含 nav_latest 等），
        而不是 lookup 的 7 字段。"""
        b = client.get("/api/funds/lookup/000003").json()
        assert set(b) == {"code", "found", "name", "tab", "market_type",
                          "in_yaml", "path"}
        assert "nav_latest" not in b, "被 /{code} 详情路由吞掉了"

    def test_all_fields_present(self, client):
        b = client.get("/api/funds/lookup/000003").json()
        for k in ("code", "found", "name", "tab", "market_type", "in_yaml", "path"):
            assert k in b, f"DTO 缺字段 {k}（Pydantic 静默砍字段）"
