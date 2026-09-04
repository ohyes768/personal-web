"""
benchmark_fetcher 单测：mock akshare / 指数日线，验证公式解析与 TRI 合成契约。

样例公式全部来自 tmp/benchmark_extract_report.json（143 只真实基金的业绩基准字段）。
"""
from dataclasses import FrozenInstanceError
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.benchmark_fetcher import (
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

    def test_sina_stale_indices_use_tx(self):
        """新浪断更的 3 个中证指数（红利/800成长/800价值）必须走腾讯源（2026-09-03 修复）"""
        cfg = _load_benchmarks_yaml()
        for name in ("中证红利", "中证800成长", "中证800价值"):
            assert cfg["indices"][name]["source"] == "stock_zh_index_daily_tx"

    def test_cbond_uses_general_source(self):
        """B1 修复：中债综合财富必须走日期正确的 bond_index_general_cbond
        （旧源 bond_composite_index_cbond 同指数但日期整体 -1 天，丢中债周五收益）"""
        cfg = _load_benchmarks_yaml()
        assert cfg["indices"]["中债综合财富"] == {
            "ak_symbol": "CBA00301", "source": "bond_index_general_cbond",
        }

    @pytest.mark.parametrize("name,symbol,source", [
        # 2026-09-04 收录（探测脚本留档于任务 research/probe_index_sources_0904.py，实测末条 T-1）
        ("中证A50", "930050", "stock_zh_index_hist_csindex"),
        ("中证800相对成长", "H30357", "stock_zh_index_hist_csindex"),
        ("中证港股通央企红利", "931233", "stock_zh_index_hist_csindex"),
        ("中证海外中国互联网", "H11136", "stock_zh_index_hist_csindex"),
        ("国证自由现金流", "980092", "index_hist_cni"),
        ("申万医药生物行业", "801150", "index_hist_sw"),
        ("申银万国制造业", "801110", "index_hist_sw"),
    ])
    def test_newly_listed_indices(self, name, symbol, source):
        cfg = _load_benchmarks_yaml()
        assert cfg["indices"][name]["ak_symbol"] == symbol
        assert cfg["indices"][name]["source"] == source

    @pytest.mark.parametrize("alias,target", [
        # curated 替代（无源指数 → 最近似已收录指数）与名称归一
        ("恒生综合", "恒生指数"),
        ("中证国债指数", "上证国债"),
        ("中债全债", "中债综合财富"),
        ("中债-1-3年国债及政策性金融债财富", "上证国债"),
        ("标普500等权重指数", "标普500"),
        ("上证科创板50成份指数", "科创50"),
        ("中证环保产业", "中证环保"),
        ("中证全指证券公司", "中证全指证券"),
    ])
    def test_curated_aliases(self, alias, target):
        cfg = _load_benchmarks_yaml()
        assert cfg["aliases"][alias] == target
        assert target in cfg["indices"]   # Constraint: alias 只能指向已收录指数


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
        # C 子指数 + 半角 * + 债 alias（中证全债 → 中债综合财富；800相对成长 2026-09-04 收录）
        ("中证800相对成长指数收益率*84%+中证全债指数收益率*16%",
         [("中证800相对成长指数收益率", 0.84, "index", "H30357"),
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
        # H 纯名称无权重 + 括号修饰（curated alias → 标普500）
        ("标普500等权重指数（全收益指数）", [("标普500等权重指数", 1.0, "index", ".INX")]),
    ])
    def test_real_formulas(self, text, expected):
        components = parse_formula(text)
        assert len(components) == len(expected)
        for comp, (name, weight, kind, symbol) in zip(components, expected):
            assert comp.name == name
            assert comp.weight == pytest.approx(weight, abs=1e-9)
            assert comp.kind == kind
            assert comp.ak_symbol == symbol

    def test_real_formula_bare_percent_addon(self):
        """000051 实证：「沪深300×95%＋1%」的裸 N% 加成 → 常数日收益成分（不打 warning）"""
        comps = parse_formula("沪深300指数收益率×95%＋1%（指年收益率，评价时应按期间折算）")
        assert [(c.name, c.weight, c.kind) for c in comps] == [
            ("沪深300指数收益率", 0.95, "index"),
            ("存款加成", 0.01, "deposit_floor"),
        ]

    def test_real_formula_trailing_period_and_orphan_paren(self):
        """161130 尾部句号 / 050025 嵌套括号残留的孤立括号，均不应产生 unknown"""
        comps = parse_formula("纳斯达克100指数收益率（使用估值汇率折算）×95%+活期存款利率（税后）×5%。")
        assert [(c.name, c.kind) for c in comps] == [
            ("纳斯达克100指数收益率", "index"), ("活期存款利率", "deposit_floor")]
        comps = parse_formula("经人民币汇率调整的标普500净总收益指数（S&P 500 Index（Net TR））收益率×95%＋人民币活期存款税后利率×5%")
        assert comps[0].kind == "index" and comps[0].ak_symbol == ".INX"

    def test_half_width_x_is_mul_only_before_digit(self):
        """「收益率x60%」半角 x 是乘号（210002 实证）；「Index」内的 x 不是（486002 实证）"""
        comps = parse_formula("中证红利指数收益率x60%+上证国债指数收益率x40%")
        assert [c.kind for c in comps] == ["index", "index"]
        assert comps[0].ak_symbol == "sh000922"
        # 英文名内 x 不被破坏 → 单成分整体可解析（不再打「无法解析权重」warning）
        comps = parse_formula("MSCI All Country World Index（MSCI ACWI指数）总收益")
        assert len(comps) == 1 and comps[0].weight == 1.0

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
        # 2026-09-04 新增前缀（全量扫描实证：012804/270042/016055/016532/021142/270023）
        ("人民币计价的恒生指数", "hkHSI"),
        ("人民币计价的恒生科技指数收益率", "hkHSTECH"),
        ("经汇率调整的纳斯达克100指数收益率", ".NDX"),
        ("经估值汇率调整后的纳斯达克100指数收益率", ".NDX"),
        ("经估值汇率调整后的中证港股通央企红利指数收益率", "931233"),
        ("人民币计价的纳斯达克100总收益指数收益率", ".NDX"),
    ])
    def test_layered_lookup_hits(self, text, symbol):
        """诊断修复回归：这些名字此前因剥过头 / 前缀缺失而 fallback"""
        comp = parse_formula(text)[0]
        assert comp.kind == "index"
        assert comp.ak_symbol == symbol

    def test_component_is_frozen(self):
        c = parse_formula("纳斯达克100指数")[0]
        with pytest.raises(FrozenInstanceError):   # frozen dataclass 专有异常，非裸 Exception
            c.weight = 0.5  # type: ignore[misc]


class TestFetchIndexDaily:
    def test_stale_index_raises(self):
        """停更指数（末条 < end - 10 天）→ StaleIndexError，上层走 fallback"""
        stale = _idx_df([100.0, 101.0], dates=["2016-06-10", "2016-06-13"])
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_daily", return_value=stale), \
                pytest.raises(StaleIndexError):
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

    def test_tencent_source_a_share(self):
        """A 股指数同样可走腾讯源（中证红利 sh000922 新浪断于 2019，2026-09-03 修复）"""
        fresh = _idx_df([4000.0, 4040.0], dates=["2026-08-31", "2026-09-01"])
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_daily_tx", return_value=fresh):
            df = _fetch_index_daily("sh000922", "stock_zh_index_daily_tx",
                                    date(2026, 1, 1), date(2026, 9, 1))
        assert df["return"].iloc[-1] == pytest.approx(0.01)

    def test_csindex_and_cni_sources(self):
        """2026-09-04 新增源：中证官网（日期/收盘）与国证（日期/收盘价）列名映射"""
        cs = pd.DataFrame({"日期": pd.to_datetime(["2026-08-31", "2026-09-01"]), "收盘": [100.0, 110.0]})
        with patch("src.data.benchmark_fetcher.ak.stock_zh_index_hist_csindex", return_value=cs) as mock:
            df = _fetch_index_daily("930050", "stock_zh_index_hist_csindex",
                                    date(2026, 1, 1), date(2026, 9, 1))
        assert mock.call_args.kwargs["symbol"] == "930050"
        assert mock.call_args.kwargs["start_date"] == "20260101"
        assert df["return"].iloc[-1] == pytest.approx(0.10)

        cni = pd.DataFrame({"日期": pd.to_datetime(["2026-08-31", "2026-09-01"]), "收盘价": [1000.0, 1020.0]})
        with patch("src.data.benchmark_fetcher.ak.index_hist_cni", return_value=cni):
            df = _fetch_index_daily("980092", "index_hist_cni", date(2026, 1, 1), date(2026, 9, 1))
        assert df["return"].iloc[-1] == pytest.approx(0.02)

    def test_cbond_source_dates_kept_as_is(self):
        """B1 回归：中债源日期必须原样透传（旧源整体 -1 天 → 周五标成周四、周日混入）。

        mock 真实债市日历：10-11 周五 / 10-12 周六（债市调休交易日，股市休市）/ 10-14 周一。
        断言：调用参数锁定综合指数/财富/总值；周五行保留（B1 核心损失）；无周日错位行。
        """
        raw = pd.DataFrame({
            "date": pd.to_datetime(["2024-10-11", "2024-10-12", "2024-10-14"]),
            "value": [100.0, 101.0, 102.0],
        })
        with patch("src.data.benchmark_fetcher.ak.bond_index_general_cbond",
                   return_value=raw) as mock:
            df = _fetch_index_daily("CBA00301", "bond_index_general_cbond",
                                    date(2024, 1, 1), date(2024, 10, 14))
        assert mock.call_args.kwargs == {
            "index_category": "综合指数", "indicator": "财富", "period": "总值",
        }
        assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2024-10-11", "2024-10-12", "2024-10-14"]
        assert df["date"].dt.weekday.tolist() == [4, 5, 0]   # 周五(保留!) / 周六调休 / 周一
        assert not (df["date"].dt.weekday == 6).any()        # 旧源错位特征是大量周日行
        assert df["return"].iloc[-1] == pytest.approx(102.0 / 101.0 - 1.0)


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
        """低权重未收录指数（5%）→ 该成分被 fallback 指数替换，source 标记 partial:fallback"""
        calls = {}

        def mock_idx(symbol, source, start, end):
            calls[symbol] = calls.get(symbol, 0) + 1
            return _idx_df([100.0, 110.0])

        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("沪深300指数收益率×65%+中证某定制小指数×5%+上证国债指数收益率×30%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily", side_effect=mock_idx):
            _, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert {"sh000300", "sh000012", "sh000906"} <= set(calls)   # 两成分 + fallback 顶替
        assert source.startswith("partial:fallback:")

    def test_major_unknown_component_returns_null(self):
        """高权重（≥50%）未收录成分 → 不再用 fallback 顶替（宁缺毋错，spec B3）

        006373 实证：85% unknown 被 sh000906 顶替 → excess_3y=+146% 失真。
        """
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("MSCI欧洲净收益指数收益率×90%+税后银行活期存款收益率×10%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily") as mock_idx:
            df, source = fetch_benchmark_tri("006282", date(2026, 1, 1), date(2026, 9, 1))
        assert df.empty
        assert source == "unavailable:unknown_majority"
        mock_idx.assert_not_called()   # 完全不发起指数拉取

    def test_unknown_at_exact_half_weight_returns_null(self):
        """R4 边界：weight 恰 0.5 即置 NULL（>= 语义，防改写成 > 后 50% 成分被顶替）"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("MSCI欧洲净收益指数收益率×50%+沪深300指数收益率×50%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily") as mock_idx:
            df, source = fetch_benchmark_tri("006282", date(2026, 1, 1), date(2026, 9, 1))
        assert df.empty
        assert source == "unavailable:unknown_majority"
        mock_idx.assert_not_called()

    def test_bare_percent_addon_compounds_as_deposit(self):
        """AC2：000051「沪深300×95%＋1%」→ 加成走常数日收益，source=fetched 不再 partial"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("沪深300指数收益率×95%＋1%（指年收益率，评价时应按期间折算）")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily",
                   return_value=_idx_df([100.0, 110.0])):
            df, source = fetch_benchmark_tri("000051", date(2026, 1, 1), date(2026, 9, 1))
        expected_r = (0.95 / 0.96) * 0.10 + (0.01 / 0.96) * (0.0035 / 252)
        assert df["tri"].iloc[1] == pytest.approx(1000.0 * (1 + expected_r))
        assert source == "fetched"

    def test_mixed_calendar_no_return_duplication(self):
        """混合日历价格对齐：成分缺席日收益贡献 0，不复制前一交易日收益（09-04 B2 修复）。

        A 交易日 = d1/d3/d5（周一三五），B = d2/d4（周二四），50/50。
        旧算法对收益 ffill：d3/d5 复制 B 的 d2/d4 收益、d4 复制 A 的 d3 收益（双计）。
        新算法：B 缺席日 d3/d5 贡献 0（价格 held），TRI 只含 A 当日收益。
        """
        dates_a = ["2026-01-05", "2026-01-07", "2026-01-09"]
        dates_b = ["2026-01-06", "2026-01-08"]

        def mock_idx(symbol, source, start, end):
            if symbol == "sz399330":  # A
                return _idx_df([100.0, 110.0, 121.0], dates=dates_a)   # r=[0,.10,.10]
            return _idx_df([200.0, 204.0], dates=dates_b)              # B r=[0,.02]

        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("深证100指数收益率×50%+上证国债指数收益率×50%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily", side_effect=mock_idx):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert source == "fetched"
        # 前导裁剪：d1 只有 A 有价，并集起点裁到 d2（此后并集完整 d2..d5）
        assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
        # weighted = [0, .05(A r .10), .01(B r .02), .05(A r .10)]
        assert list(df["tri"]) == pytest.approx([1000.0, 1050.0, 1060.5, 1113.525], abs=1e-9)

    def test_leading_dates_trimmed_to_latest_component(self):
        """成分 B 首个交易日晚于 A：输出首行 = B 首日（前导 NaN 无法 ffill，裁掉）"""
        def mock_idx(symbol, source, start, end):
            if symbol == "sz399330":  # A 从 d1 有价
                return _idx_df([100.0, 105.0, 110.25], dates=["2026-01-05", "2026-01-06", "2026-01-07"])
            return _idx_df([50.0, 52.5], dates=["2026-01-06", "2026-01-07"])  # B 从 d2

        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("深证100指数收益率×50%+上证国债指数收益率×50%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily", side_effect=mock_idx):
            df, _ = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert df["date"].iloc[0] == pd.Timestamp("2026-01-06")
        # TRI 参考日 = 裁剪后首行（d2, =1000）；d3 起 A、B 各 +5% → 加权 +5%
        assert df["tri"].iloc[0] == pytest.approx(1000.0)
        assert df["tri"].iloc[1] == pytest.approx(1050.0, abs=1e-9)

    def test_same_calendar_matches_return_compound(self):
        """回归：全成分同一日历 → 新算法与「收益序列直接 cumprod」完全一致（09-04 B2）"""
        def mock_idx(symbol, source, start, end):
            if symbol == "sz399330":
                return _idx_df([100.0, 110.0, 121.0])   # r=[0, .10, .10]
            return _idx_df([200.0, 202.0, 204.0])       # r=[0, .01, .00990099...]

        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("深证100指数收益率×50%+上证国债指数收益率×50%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily", side_effect=mock_idx):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        r_a = pd.Series([100.0, 110.0, 121.0]).pct_change().fillna(0)
        r_b = pd.Series([200.0, 202.0, 204.0]).pct_change().fillna(0)
        expected = ((1 + 0.5 * (r_a + r_b)).cumprod() * 1000).tolist()
        assert source == "fetched"
        assert list(df["tri"]) == pytest.approx(expected, rel=1e-9)

    def test_deposit_weight_normalization(self):
        """权重和 <1 时归一：90% 指数 + 5% 存款 → 实际 90/95 与 5/95"""
        with patch("src.data.benchmark_fetcher.fetch_basic",
                   return_value=self._basic("中证白酒指数收益率×90%+银行活期存款利率（税后）×5%")), \
             patch("src.data.benchmark_fetcher._fetch_index_daily",
                   return_value=_idx_df([100.0, 110.0])):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        expected_r = (0.90 / 0.95) * 0.10 + (0.05 / 0.95) * (0.0035 / 252)
        assert df["tri"].iloc[1] == pytest.approx(1000.0 * (1 + expected_r))
        assert source == "fetched"

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
                   return_value=_idx_df([100.0, 105.0])):
            df, source = fetch_benchmark_tri("000001", date(2026, 1, 1), date(2026, 9, 1))
        assert source.startswith("fallback_chain:")
        assert df["tri"].iloc[1] == pytest.approx(1050.0)  # fallback 指数自身收益
