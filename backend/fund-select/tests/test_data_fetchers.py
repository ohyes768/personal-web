"""
数据层单测：债券分类 / 费率契约 / 宇宙配置 / 基础信息 fetcher 容错（不联网，用 mock）
"""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.data import fund_basic_fetcher
from src.data.bond_classifier import classify_bond
from src.data.fee_fetcher import _parse_pct, fetch_fees
from src.data.fund_basic_fetcher import fetch_basic, parse_size
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


class TestParseSize:
    """规模文本 '94.51亿' / '12.34万' -> 亿元"""

    def test_yi(self):
        assert parse_size("94.51亿") == 94.51

    def test_wan(self):
        assert parse_size("10000万") == 1.0

    def test_empty(self):
        assert parse_size("") is None
        assert parse_size(None) is None
        assert parse_size("暂无数据") is None

    def test_unparseable(self):
        assert parse_size("foo") is None


class TestFetchBasic:
    def test_normal_path(self):
        """akshare 正常返回：字典化 items"""
        fake_df = pd.DataFrame({
            "item": ["基金代码", "基金名称", "基金类型"],
            "value": ["005827", "易方达蓝筹精选混合", "混合型-偏股"],
        })
        with patch("src.data.fund_basic_fetcher.ak.fund_individual_basic_info_xq", return_value=fake_df):
            out = fetch_basic("005827")
        assert out["基金代码"] == "005827"
        assert out["基金类型"] == "混合型-偏股"

    def test_keyerror_triggers_fallback(self):
        """akshare 列子集 KeyError → fallback 走 danjuanfunds 已有字段"""
        with patch(
            "src.data.fund_basic_fetcher.ak.fund_individual_basic_info_xq",
            side_effect=KeyError("['最新规模', ...] not in index"),
        ):
            with patch.object(fund_basic_fetcher.requests, "get") as mock_get:
                mock_get.return_value.json.return_value = {
                    "data": {
                        "fd_code": "968157",
                        "fd_name": "东亚联丰环球股票人民币",
                        "fd_full_name": "东亚联丰环球股票基金R(3)类别人民币",
                        "found_date": "2024-12-09",
                        "keeper_name": "东亚联丰投资管理有限公司",
                        "manager_name": "张文健",
                        "type_desc": "互认基金",
                        "rating_desc": "暂无评级",
                    }
                }
                out = fetch_basic("968157")

        assert out["基金代码"] == "968157"
        assert out["基金名称"] == "东亚联丰环球股票人民币"
        # 互认基金标准化映射为 QDII-互认，对接 screen_stock 谓词
        assert out["基金类型"] == "QDII-互认"
        assert out["基金公司"] == "东亚联丰投资管理有限公司"
        # 缺字段不在 dict 里
        assert "最新规模" not in out
        assert "托管银行" not in out

    def test_fallback_empty_data(self):
        """danjuanfunds 返回 data=None 时 fallback 返回空 dict（refresh 上层捕捉）"""
        with patch(
            "src.data.fund_basic_fetcher.ak.fund_individual_basic_info_xq",
            side_effect=KeyError("missing"),
        ):
            with patch.object(fund_basic_fetcher.requests, "get") as mock_get:
                mock_get.return_value.json.return_value = {"data": None}
                out = fetch_basic("000000")
        assert out == {}

    def test_session_reused_across_calls(self):
        """thread-local Session 复用：连续 fallback 调 _http() 拿到同一个 Session 实例"""
        # mock fund_individual 失败 + http get 任意返回
        with patch(
            "src.data.fund_basic_fetcher.ak.fund_individual_basic_info_xq",
            side_effect=KeyError("missing"),
        ), patch.object(fund_basic_fetcher.requests, "get"):
            s1 = fund_basic_fetcher._http()
            s2 = fund_basic_fetcher._http()
        assert s1 is s2
        assert s1.headers["User-Agent"] == fund_basic_fetcher.USER_AGENT


class TestReplaceAchievementGenericMapping:
    """_replace_achievement 走 ACHIEVEMENT_COLUMNS 通用映射"""

    def test_numeric_and_text_columns(self, db_session):
        """ret/max_dd 列数值化，period_kind/period/peer_rank 字符串化"""
        from src.services.refresh_service import _replace_achievement
        from src.db.models import FundAchievementRank
        import pandas as pd
        df = pd.DataFrame({
            "业绩类型": ["年度业绩", "年度业绩"],
            "周期": ["2025", "2024"],
            "本产品区间收益": ["6.86", 1.7],
            "本产品最大回撒": ["13.96", 21.02],
            "周期收益同类排名": ["4406/5118", ""],
        })
        _replace_achievement(db_session, "000001", df, _ref_date())
        db_session.commit()

        rows = db_session.query(FundAchievementRank).filter_by(code="000001").all()
        assert len(rows) == 2
        sorted_rows = sorted(rows, key=lambda r: r.period)
        r2024 = sorted_rows[0]  # period '2024': ret=1.7, peer_rank=''
        r2025 = sorted_rows[1]  # period '2025': ret=6.86, peer_rank='4406/5118'
        # numeric 列转 float
        assert r2024.ret == 1.7
        assert r2024.max_dd == 21.02
        assert r2025.ret == 6.86
        # period_kind / period 强制 str
        assert r2024.period_kind == "年度业绩"
        assert r2025.period == "2025"
        # peer_rank 空字符串落 None（可空）；非空保留
        assert r2024.peer_rank is None
        assert r2025.peer_rank == "4406/5118"

    def test_idempotent_replace(self, db_session):
        """重复调用覆盖旧行，不累积"""
        from src.services.refresh_service import _replace_achievement
        from src.db.models import FundAchievementRank
        import pandas as pd
        df = pd.DataFrame({"业绩类型": ["a"], "周期": ["1y"], "本产品区间收益": [10.0]})
        _replace_achievement(db_session, "000002", df, _ref_date())
        db_session.commit()  # 模拟生产：每只基金 commit 一次
        _replace_achievement(db_session, "000002", df, _ref_date())
        db_session.commit()

        rows = db_session.query(FundAchievementRank).filter_by(code="000002").all()
        assert len(rows) == 1


def _ref_date():
    from datetime import date
    return date(2026, 9, 1)


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
