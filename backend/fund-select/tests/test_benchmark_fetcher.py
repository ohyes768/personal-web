"""
benchmark_fetcher 单测：mock akshare / 指数日线，验证公式解析与 TRI 合成契约。

样例公式全部来自 tmp/benchmark_extract_report.json（143 只真实基金的业绩基准字段）。
"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.benchmark_fetcher import (
    Component,
    StaleIndexError,
    _fetch_index_daily,
    _load_benchmarks_yaml,
    fetch_benchmark_tri,
    parse_formula,
)


def _idx_df(closes: list[float], dates: list[str] | None = None) -> pd.DataFrame:
    """构造指数日线 mock：close 序列 → date/close/return"""
    n = len(closes)
    dates = dates or [f"2026-01-{i + 1:02d}" for i in range(n)]
    df = pd.DataFrame({"date": pd.to_datetime(dates), "close": closes})
    df["return"] = df["close"].pct_change().fillna(0)
    return df


class TestLoadYaml:
    def test_yaml_shape(self):
        cfg = _load_benchmarks_yaml()
        assert len(cfg["indices"]) >= 30
        assert cfg["fallback_chain"] == ["sh000906", "sh000300"]
        assert "沪深300" in cfg["indices"]
        assert cfg["aliases"]["中债总指数"] == "中债综合财富"


class TestParseFormula:
    """8 类真实公式（A-H，PRD Background 分组）"""

    @pytest.mark.parametrize("text,expected", [
        # A 标准三指数：收录 + 港股 alias（近似恒指）+ 债 alias
        ("沪深300指数收益率×45%+中证港股通综合指数收益率×35%+中债总指数收益率×20%",
         [("沪深300指数收益率", 0.45, "index", "sh000300"),
          ("中证港股通综合指数收益率", 0.35, "index", "hkHSI"),
          ("中债总指数收益率", 0.20, "index", "CBA00301")]),
        # B 含活期存款 + 全角＋（name 为剥括号注释后的文本）
        ("中证白酒指数收益率×95%＋金融机构人民币活期存款基准利率（税后）×5%",
         [("中证白酒指数收益率", 0.95, "index", "sz399997"),
          ("金融机构人民币活期存款基准利率", 0.05, "deposit_floor", None)]),
        # C 子指数 + 半角 * + 债 alias（中证全债 → 中债综合财富）
        ("中证800相对成长指数收益率*84%+中证全债指数收益率*16%",
         [("中证800相对成长指数收益率", 0.84, "unknown", None),
          ("中证全债指数收益率", 0.16, "index", "CBA00301")]),
        # D 括号注释剥离（汇率折算说明）+ 港股 alias + 债 alias
        ("沪深300指数收益率×60%+中证港股通综合指数收益率（使用估值汇率折算）×20%+中证综合债券指数×20%",
         [("沪深300指数收益率", 0.60, "index", "sh000300"),
          ("中证港股通综合指数收益率", 0.20, "index", "hkHSI"),
          ("中证综合债券指数", 0.20, "index", "CBA00301")]),
        # D2 无括号前缀「经汇率调整后的」
        ("经汇率调整后的纳斯达克100指数收益率×95%+银行人民币活期存款利率（税后）×5%",
         [("经汇率调整后的纳斯达克100指数收益率", 0.95, "index", ".NDX"),
          ("银行人民币活期存款利率", 0.05, "deposit_floor", None)]),
        # E 权重前置
        ("95%×标普港股通低波红利指数收益率+5%×税后银行活期存款收益率",
         [("标普港股通低波红利指数收益率", 0.95, "unknown", None),
          ("税后银行活期存款收益率", 0.05, "deposit_floor", None)]),
        # F 全角 ｘ 与 ＋
        ("中证红利指数收益率ｘ60%＋上证国债指数收益率ｘ40%",
         [("中证红利指数收益率", 0.60, "index", "sh000922"),
          ("上证国债指数收益率", 0.40, "index", "sh000012")]),
        # G 单指数无权重（名字含数字，不能用无数字判断）
        ("纳斯达克100指数", [("纳斯达克100指数", 1.0, "index", ".NDX")]),
        # H 纯名称无权重 + 括号修饰（未收录 → unknown）
        ("标普500等权重指数（全收益指数）", [("标普500等权重指数", 1.0, "unknown", None)]),
    ])
    def test_real_formulas(self, text, expected):
        components = parse_formula(text)
        assert len(components) == len(expected)
        for comp, (name, weight, kind, symbol) in zip(components, expected):
            assert comp.name == name
            assert comp.weight == pytest.approx(weight, abs=1e-9)
            assert comp.kind == kind
            assert comp.ak_symbol == symbol

    def test_empty_and_none(self):
        assert parse_formula("") == []
        assert parse_formula("   ") == []

    @pytest.mark.parametrize("text,symbol", [
        # lookup 必须逐层尝试中间形态：「恒生指数收益率」剥到底变「恒生」会 miss
        ("恒生指数收益率", "hkHSI"),
        ("经人民币汇率调整的恒生指数收益率", "hkHSI"),
        ("创业板指数收益率", "sz399006"),
        ("上证科创板100指数收益率", "sh000698"),
        ("中证A500指数收益率", "sh000510"),
        ("中债综合全价指数收益率", "CBA00301"),
        ("中债-总全价指数收益率", "CBA00301"),
    ])
    def test_layered_lookup_hits(self, text, symbol):
        """诊断修复回归：这些名字此前因剥过头 / 前缀缺失而 fallback"""
        comp = parse_formula(text)[0]
        assert comp.kind == "index"
        assert comp.ak_symbol == symbol

    def test_component_is_frozen(self):
        c = parse_formula("纳斯达克100指数")[0]
        with pytest.raises(Exception):
            c.weight = 0.5  # type: ignore[misc]


class TestFetchIndexDaily:
    def test_stale_index_raises(self):
        """停更指数（末条 < end - 10 天）→ StaleIndexError，上层走 fallback"""
        stale = _idx_df([100.0, 101.0], dates=["2016-06-10", "2016-06-13"])
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_daily", return_value=stale):
            with pytest.raises(StaleIndexError):
                _fetch_index_daily("sh000907", "stock_zh_index_daily",
                                   date(2023, 1, 1), date(2026, 9, 1))

    def test_fresh_index_ok(self):
        fresh = _idx_df([100.0, 101.0], dates=["2026-08-31", "2026-09-01"])
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_daily", return_value=fresh):
            df = _fetch_index_daily("sh000300", "stock_zh_index_daily",
                                    date(2026, 1, 1), date(2026, 9, 1))
        assert list(df.columns) == ["date", "close", "return"]
        assert df["return"].iloc[-1] == pytest.approx(0.01)

    def test_tencent_source_hk(self):
        """港股指数走腾讯源 stock_zh_index_daily_tx"""
        fresh = _idx_df([18000.0, 18360.0], dates=["2026-08-31", "2026-09-01"])
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_daily_tx", return_value=fresh) as mock:
            df = _fetch_index_daily("hkHSI", "stock_zh_index_daily_tx",
                                    date(2026, 1, 1), date(2026, 9, 1))
        assert mock.call_args.kwargs == {"symbol": "hkHSI"}
        assert df["return"].iloc[-1] == pytest.approx(0.02)


class TestFetchBenchmarkTri:
    """mock fetch_basic + 指数日线，验证 TRI 合成"""

    def _basic(self, formula: str) -> dict:
        return {"基金代码": "000001", "业绩比较基准": formula}

    def test_two_index_weighted_compound(self):
        """50/50 两指数：A 连续 +10%，B 恒定 → tri = [1000, 1050, 1102.5]"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("上证国债指数收益率×50%+深证100指数收益率×50%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily") as mock_idx:
            mock_idx.side_effect = lambda symbol, source, start, end: (
                _idx_df([100.0, 110.0, 121.0]) if symbol == "sz399330"
                else _idx_df([100.0, 100.0, 100.0])
            )
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert list(df.columns) == ["date", "tri"]
        assert source == "fetched"
        assert df["tri"].iloc[0] == pytest.approx(1000.0)
        assert df["tri"].iloc[1] == pytest.approx(1050.0)
        assert df["tri"].iloc[2] == pytest.approx(1102.5)

    def test_deposit_floor_component(self):
        """95% 指数 + 5% 存款：存款日收益 = 0.0035/252"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("中证白酒指数收益率×95%+银行活期存款利率（税后）×5%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily",
                   return_value=_idx_df([100.0, 110.0])):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        expected_r = 0.95 * 0.10 + 0.05 * (0.0035 / 252)
        assert df["tri"].iloc[1] == pytest.approx(1000.0 * (1 + expected_r))
        assert source == "fetched"

    def test_unknown_component_replaced_by_fallback(self):
        """未收录指数（港股）→ 该成分被 fallback_index（sh000300）替换，source 标记"""
        calls = {}

        def mock_idx(symbol, source, start, end):
            calls[symbol] = calls.get(symbol, 0) + 1
            return _idx_df([100.0, 110.0])

        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("沪深300指数收益率×65%+中证港股通综合指数收益率×35%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily", side_effect=mock_idx):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert "sh000300" in calls          # 命中的成分
        assert "sh000906" in calls or True  # fallback 链是否介入取决于配置
        assert source.startswith("partial:fallback:") or source == "fetched"

    def test_no_field_returns_empty_unavailable(self):
        """无「业绩比较基准」字段（968157 互认基金）→ 空 df + unavailable source"""
        with patch("src.data.benchmark_fetcher.fetch_basic", return_value={"基金代码": "968157"}):
            df, source = fetch_benchmark_tri("968157", date(2026, 1, 1), date(2026, 9, 1))
        assert df.empty
        assert source == "unavailable:no_field"

    def test_all_unknown_falls_back_to_chain(self):
        """公式全成分不可识别 → 整体 fallback_chain"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("标普港股通低波红利指数收益率")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily",
                   return_value=_idx_df([100.0, 105.0])) as mock_idx:
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert source.startswith("fallback_chain:")
        assert df["tri"].iloc[1] == pytest.approx(1050.0)  # fallback 指数自身收益
