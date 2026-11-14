"""基金代码 → tab 路由判定测试（11-14-fund-code-quick-search）

覆盖 design §2 的六级优先级，重点是实测发现的「other 里 2653 只债券型」陷阱。
"""
import pytest

from src.db.models import Fund
from src.services.lookup_service import (
    TAB_BOND, TAB_DISCOVERY_BOND, TAB_DISCOVERY_STOCK, TAB_STOCK, resolve_tab,
)


def _mk(code, *, market_type=None, market_subtype=None, name="基金"):
    return Fund(
        code=code, name=f"{name}{code}", fund_type="股票型",
        age_years=5.0, size_yi=10.0, mgr_name="张", mgr_company="某司",
        mgr_days=1000, mgr_experience_years=5.0, is_active=True,
        market_type=market_type, market_subtype=market_subtype,
    )


@pytest.fixture
def seeded(db_session, monkeypatch):
    """yaml 名单用假的：000001 债基名单，000002 股基名单；其余靠 market_type。"""
    monkeypatch.setattr(
        "src.services.lookup_service._yaml_membership",
        lambda: ({"000001"}, {"000002"}),
    )
    db_session.add_all([
        _mk("000001", market_type="stock", market_subtype="混合型-灵活"),  # 在债基名单（测优先级）
        _mk("000002", market_type="bond", market_subtype="债券型-长债"),   # 在股基名单
        _mk("000003", market_type="stock", market_subtype="股票型"),
        _mk("000004", market_type="bond", market_subtype="债券型-信用债"),
        _mk("000005", market_type="other", market_subtype="债券型-长债"),   # ← 关键陷阱
        _mk("000006", market_type="other", market_subtype="混合型-偏股"),
        _mk("000007", market_type="other", market_subtype="FOF-稳健型"),
        _mk("000008", market_type="other", market_subtype="货币型-普通货币"),
        _mk("000009", market_type="债券型-长债", market_subtype=None),     # ← 脏值
        _mk("000010", market_type=None, market_subtype=None),
    ])
    db_session.commit()
    return db_session


class TestYamlPriority:
    def test_bond_yaml_wins_over_market_type(self, seeded):
        """000001 在债基名单，即使 market_type=stock 也判 bond。"""
        r = resolve_tab(seeded, "000001")
        assert r["tab"] == TAB_BOND
        assert r["in_yaml"] == "bond"
        assert r["path"] == "/bond?code=000001"

    def test_stock_yaml_wins_over_market_type(self, seeded):
        """000002 在股基名单，即使 market_type=bond 也判 stock。"""
        r = resolve_tab(seeded, "000002")
        assert r["tab"] == TAB_STOCK
        assert r["in_yaml"] == "stock"
        assert r["path"] == "/stock?code=000002"


class TestMarketTypeFallback:
    def test_stock_market_goes_discovery_stock(self, seeded):
        r = resolve_tab(seeded, "000003")
        assert r["tab"] == TAB_DISCOVERY_STOCK
        assert r["in_yaml"] is None

    def test_bond_market_goes_discovery_bond(self, seeded):
        assert resolve_tab(seeded, "000004")["tab"] == TAB_DISCOVERY_BOND

    def test_other_with_bond_subtype_goes_discovery_bond(self, seeded):
        """关键陷阱：other + 债券型子类必须判债基（实测这类有 2653 只）。"""
        r = resolve_tab(seeded, "000005")
        assert r["tab"] == TAB_DISCOVERY_BOND, "other+债券型不能兜底到股基市场"

    def test_other_with_equity_subtype_goes_discovery_stock(self, seeded):
        assert resolve_tab(seeded, "000006")["tab"] == TAB_DISCOVERY_STOCK

    def test_other_with_fof_goes_discovery_stock(self, seeded):
        """FOF 不在两个 discovery universe，兜底股基市场。"""
        assert resolve_tab(seeded, "000007")["tab"] == TAB_DISCOVERY_STOCK

    def test_other_with_money_fund_goes_discovery_stock(self, seeded):
        assert resolve_tab(seeded, "000008")["tab"] == TAB_DISCOVERY_STOCK

    def test_dirty_market_type_bond_prefix(self, seeded):
        """market_type 被误写成 '债券型-长债'（实测 code=519622）。"""
        assert resolve_tab(seeded, "000009")["tab"] == TAB_DISCOVERY_BOND

    def test_null_market_type_falls_back_to_stock(self, seeded):
        assert resolve_tab(seeded, "000010")["tab"] == TAB_DISCOVERY_STOCK


class TestNotFound:
    def test_missing_code(self, seeded):
        r = resolve_tab(seeded, "999999")
        assert r["found"] is False
        assert r["tab"] is None
        assert r["path"] is None
        assert r["name"] is None

    def test_path_has_no_funds_prefix(self, seeded):
        """basePath 契约：path 必须是相对路径（加 /funds 会变 /funds/funds/... 404）。"""
        for code in ("000003", "000004", "000005"):
            path = resolve_tab(seeded, code)["path"]
            assert not path.startswith("/funds"), path
            assert path.startswith("/")

    def test_found_shape_complete(self, seeded):
        r = resolve_tab(seeded, "000003")
        assert set(r) == {"code", "found", "name", "tab", "market_type",
                          "in_yaml", "path"}
