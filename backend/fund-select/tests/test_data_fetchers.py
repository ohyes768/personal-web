"""
数据层单测：债券分类 / 费率契约 / 宇宙配置（不联网，用缓存夹具）
"""
import json
from pathlib import Path

from src.data.bond_classifier import classify_bond
from src.data.fee_fetcher import _parse_pct, fetch_fees
from src.data.fund_universe import load_fund_codes

LEGACY_CACHE = Path(__file__).parent.parent.parent / "cache"


class TestClassifyBond:
    def test_rate_bond_keywords(self):
        assert classify_bond("24国开03") == "rate"
        assert classify_bond("25农发31") == "rate"
        assert classify_bond("25附息国债03") == "rate"
        assert classify_bond("22进出10") == "rate" or classify_bond("22进出口行10") == "rate"

    def test_credit_bond(self):
        assert classify_bond("24中行二级资本债02A") == "credit"
        assert classify_bond("23建行永续债01") == "credit"

    def test_convertible_first(self):
        """含「转」优先于利率债关键词"""
        assert classify_bond("某转债") == "convertible"

    def test_empty(self):
        assert classify_bond("") == "other"
        assert classify_bond(None) == "other"


class TestFeeContract:
    def test_parse_pct(self):
        assert _parse_pct("0.80%") == "0.80"
        assert _parse_pct("1.5%") == "1.5"
        assert _parse_pct("---") is None
        assert _parse_pct("") is None
        assert _parse_pct("无") is None

    def test_fetch_fees_from_fixture(self):
        """预研缓存夹具：契约字段解析为 float"""
        fees = fetch_fees("003547")
        assert fees["fee_buy_small"] == 0.8
        assert fees["fee_redeem_lt7d"] == 1.5
        assert fees["fee_mgmt"] == 0.3
        assert fees["fee_custody"] == 0.1
        assert "fee_service" not in fees  # 该基金无销售服务费

    def test_fetch_fees_all_31_fixtures(self):
        """31 份夹具全部可解析（契约稳定性）"""
        files = list(LEGACY_CACHE.glob("fees_*.json"))
        assert len(files) == 31
        for f in files:
            code = f.stem.split("_")[1]
            fees = fetch_fees(code)
            assert isinstance(fees, dict), f"{code} 解析失败"
            assert fees.get("fee_mgmt") is not None, f"{code} 缺管理费"


class TestFundUniverse:
    def test_load_configured_codes(self):
        codes = load_fund_codes()
        assert len(codes) == 31
        assert "003547" in codes and "004010" in codes
        assert all(len(c) == 6 for c in codes)

    def test_missing_config_returns_empty(self, tmp_path):
        assert load_fund_codes(tmp_path / "nonexistent.yaml") == []

    def test_empty_config_returns_empty(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("funds: []\n", encoding="utf-8")
        assert load_fund_codes(p) == []
