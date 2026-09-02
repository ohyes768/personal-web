"""
财务指标获取器单元测试 — 覆盖 EPS 提取逻辑

列名依据：akshare.stock_financial_analysis_indicator() 真实返回
（截至 akshare 1.16.x）。回归 guard 防止猜错列名。
"""
import sys
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.financial_fetcher import FinancialFetcher


class TestCalcLatestEps:
    """_calc_latest_eps 单元测试（取最近一期年报的 EPS）"""

    @pytest.fixture
    def fetcher(self):
        return FinancialFetcher()

    def test_calc_latest_eps_normal(self, fetcher):
        """正常情况：3 年 12-31 数据，返回最新一年 EPS"""
        df = pd.DataFrame({
            "日期": ["2022-12-31", "2023-12-31", "2024-12-31", "2025-03-31"],
            "加权每股收益(元)": [0.80, 1.00, 1.20, 0.30],
        })
        result = fetcher._calc_latest_eps(df)
        assert result == {"最新EPS年度": 2024, "最新EPS(元)": 1.20}

    def test_calc_latest_eps_no_year_end(self, fetcher):
        """没有 12-31 数据：返回 None dict"""
        df = pd.DataFrame({
            "日期": ["2024-03-31", "2024-06-30", "2024-09-30"],
            "摊薄每股收益(元)": [0.30, 0.60, 0.90],
        })
        result = fetcher._calc_latest_eps(df)
        assert result == {"最新EPS年度": None, "最新EPS(元)": None}

    def test_calc_latest_eps_negative(self, fetcher):
        """亏损股：EPS 负值保留（路由层识别"亏损"）"""
        df = pd.DataFrame({
            "日期": ["2022-12-31", "2023-12-31", "2024-12-31"],
            "加权每股收益(元)": [0.50, -0.20, -0.50],
        })
        result = fetcher._calc_latest_eps(df)
        assert result == {"最新EPS年度": 2024, "最新EPS(元)": -0.50}

    def test_calc_latest_eps_latest_year_first(self, fetcher):
        """取最新一年而非最早：数据乱序时仍取 2024 而非 2022"""
        df = pd.DataFrame({
            "日期": ["2024-12-31", "2022-12-31", "2023-12-31"],
            "加权每股收益(元)": [1.50, 0.80, 1.00],
        })
        result = fetcher._calc_latest_eps(df)
        assert result["最新EPS年度"] == 2024
        assert result["最新EPS(元)"] == 1.50

    def test_calc_latest_eps_missing_eps_column(self, fetcher):
        """摊薄每股收益列不存在：返回 None EPS 但年度有值"""
        df = pd.DataFrame({
            "日期": ["2024-12-31", "2023-12-31"],
            # 故意没有"摊薄每股收益(元)"列
        })
        result = fetcher._calc_latest_eps(df)
        assert result == {"最新EPS年度": 2024, "最新EPS(元)": None}

    def test_calc_latest_eps_real_akshare_columns(self, fetcher):
        """Regression guard：使用真实 akshare 返回的多列 DataFrame

        历史 bug：曾误用"基本每股收益(元)"，但 akshare 实际返回"摊薄每股收益(元)"。
        本测试用真实列名 + 真实日期格式（datetime.date）防止再犯。
        """
        import datetime
        df = pd.DataFrame({
            "日期": [
                datetime.date(2022, 12, 31),
                datetime.date(2023, 12, 31),
                datetime.date(2024, 12, 31),
                datetime.date(2025, 12, 31),  # 用户期望的 2025 年报
                datetime.date(2025, 3, 31),
            ],
            "摊薄每股收益(元)": [0.50, 0.80, 1.00, 1.20, 0.30],
            "基本每股收益(元)": [0.51, 0.81, 1.01, 1.21, 0.31],  # 真实也有，但用错列
            "加权每股收益(元)": [0.52, 0.82, 1.02, 1.22, 0.32],
            "扣除非经常性损益后的净利润(元)": [1e8, 1.5e8, 2e8, 2.5e8, 0.6e8],
        })
        result = fetcher._calc_latest_eps(df)
        # 必须取到 2025 年报数据
        assert result["最新EPS年度"] == 2025, f"应取 2025-12-31，实际 {result}"
        assert result["最新EPS(元)"] == 1.22, f"应用加权EPS=1.22（而非摊薄1.20/基本1.21），实际 {result}"


class TestFetchBatch:
    """fetch_batch 单元测试 — 成功计数与返回值不受分批保存影响"""

    @pytest.fixture
    def fetcher(self):
        return FinancialFetcher()

    @staticmethod
    def _mock_result(code):
        return {"股票代码": code, "ROE": 10.0}

    def test_returns_all_results_across_batches(self, fetcher, caplog):
        """回归 guard：batch 保存后 results 会被清空，但最终返回必须是累计成功结果。

        历史 bug：曾复用被清空的 results 做统计和返回值，导致
        202 只股票全部成功时打印"成功 0/202"、API count 返回 0。
        """
        codes = [str(600000 + i) for i in range(25)]  # 25 只，batch_size=10 → 3 批
        with patch.object(FinancialFetcher, "fetch_one", side_effect=lambda code, **_: self._mock_result(code)):
            with caplog.at_level("INFO", logger="src.data.financial_fetcher"):
                df = fetcher.fetch_batch(codes, delay=0, show_progress=True, batch_size=10)

        assert len(df) == 25, f"应返回全部 25 条成功结果，实际 {len(df)}"
        assert list(df["股票代码"]) == codes

        # 完成日志必须报告累计成功数，而不是被批次清空后的剩余数
        done_logs = [r.message for r in caplog.records if "财务指标获取完成" in r.message]
        assert done_logs and "成功 25/25" in done_logs[-1], f"完成日志应含 '成功 25/25'，实际 {done_logs}"

    def test_counts_failures_in_stats(self, fetcher, caplog):
        """失败计数累计：25 只中 5 只失败 → 成功 20/25, 失败 5"""
        codes = [str(600000 + i) for i in range(25)]
        fail_codes = set(codes[:5])

        def mock_fetch_one(code, **_):
            return None if code in fail_codes else self._mock_result(code)

        with patch.object(FinancialFetcher, "fetch_one", side_effect=mock_fetch_one):
            with caplog.at_level("INFO", logger="src.data.financial_fetcher"):
                df = fetcher.fetch_batch(codes, delay=0, show_progress=True, batch_size=10)

        assert len(df) == 20
        done_logs = [r.message for r in caplog.records if "财务指标获取完成" in r.message]
        assert done_logs and "成功 20/25, 失败 5" in done_logs[-1], f"实际 {done_logs}"


class TestCalcQuarterlyYoy:
    """_calc_quarterly_yoy 单元测试（各股最新报告期单季扣非同比，自动切换季度）"""

    @pytest.fixture
    def fetcher(self):
        return FinancialFetcher()

    def test_latest_is_q2_single_quarter(self, fetcher):
        """最新期 06-30：单季 = H1累计 − Q1累计，同比 vs 去年同期单季（H1'−Q1'）"""
        df = pd.DataFrame({
            "日期": [date(2026, 6, 30), date(2026, 3, 31),
                     date(2025, 6, 30), date(2025, 3, 31),
                     date(2025, 12, 31)],
            "扣除非经常性损益后的净利润(元)": [500e8, 200e8, 400e8, 180e8, 900e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        # 单季 = 500 − 200 = 300；去年同期单季 = 400 − 180 = 220
        assert result["最新季度扣非(元)"] == 300e8
        assert result["最新季度扣非同比(%)"] == round((300e8 - 220e8) / 220e8 * 100, 2)
        assert result["数据季度"] == "2026Q2"

    def test_latest_is_q1(self, fetcher):
        """最新期 03-31（Q1 累计=单季）：同比 vs 去年 Q1（回归旧口径行为）"""
        df = pd.DataFrame({
            "日期": [date(2026, 3, 31), date(2025, 3, 31), date(2025, 12, 31)],
            "扣除非经常性损益后的净利润(元)": [272e8, 268e8, 1000e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["最新季度扣非(元)"] == 272e8
        assert result["最新季度扣非同比(%)"] == 1.49  # (272-268)/268
        assert result["数据季度"] == "2026Q1"

    def test_latest_is_annual_report_q4(self, fetcher):
        """最新期 12-31（年报）：单季 = 全年 − 前三季累计"""
        df = pd.DataFrame({
            "日期": [date(2025, 12, 31), date(2025, 9, 30),
                     date(2024, 12, 31), date(2024, 9, 30)],
            "扣除非经常性损益后的净利润(元)": [1000e8, 750e8, 900e8, 700e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        # 单季 = 1000 − 750 = 250；去年同期单季 = 900 − 700 = 200
        assert result["最新季度扣非(元)"] == 250e8
        assert result["最新季度扣非同比(%)"] == 25.0
        assert result["数据季度"] == "2025Q4"

    def test_new_stock_no_last_year_data(self, fetcher):
        """新股只有 2026Q1、无 2025 数据：绝对值有、同比 None、数据季度 2026Q1"""
        df = pd.DataFrame({
            "日期": [date(2026, 3, 31)],
            "扣除非经常性损益后的净利润(元)": [100e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["最新季度扣非(元)"] == 100e8
        assert result["最新季度扣非同比(%)"] is None
        assert result["数据季度"] == "2026Q1"

    def test_missing_same_year_prev_cumulative(self, fetcher):
        """缺同年上一累计期（有 06-30 无 03-31）：单季无法还原，绝对值与同比 None"""
        df = pd.DataFrame({
            "日期": [date(2026, 6, 30), date(2025, 6, 30), date(2025, 3, 31)],
            "扣除非经常性损益后的净利润(元)": [500e8, 400e8, 180e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["最新季度扣非(元)"] is None
        assert result["最新季度扣非同比(%)"] is None
        assert result["数据季度"] == "2026Q2"

    def test_base_value_zero(self, fetcher):
        """去年同期单季=0（基数极小/亏损边缘）：同比 None 避免除零爆炸"""
        df = pd.DataFrame({
            "日期": [date(2026, 3, 31), date(2025, 3, 31)],
            "扣除非经常性损益后的净利润(元)": [100e8, 0],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["最新季度扣非(元)"] == 100e8
        assert result["最新季度扣非同比(%)"] is None
        assert result["数据季度"] == "2026Q1"

    def test_real_akshare_columns_and_dates(self, fetcher):
        """Regression guard：真实 akshare 列名 + datetime.date 格式
        防止再改 akshare 接口时猜错列名或日期解析。
        """
        import datetime
        df = pd.DataFrame({
            "日期": [
                datetime.date(2026, 6, 30),
                datetime.date(2026, 3, 31),
                datetime.date(2025, 6, 30),
                datetime.date(2025, 3, 31),
                datetime.date(2025, 12, 31),
            ],
            "摊薄每股收益(元)": [0.60, 0.32, 0.55, 0.30, 1.20],  # 干扰列
            "扣除非经常性损益后的净利润(元)": [500e8, 200e8, 400e8, 180e8, 900e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["最新季度扣非(元)"] == 300e8
        assert result["最新季度扣非同比(%)"] == round((300e8 - 220e8) / 220e8 * 100, 2)
        assert result["数据季度"] == "2026Q2"

    def test_data_quarter_label(self, fetcher):
        """数据季度标签：反映扣非数据实际所属报告期（Q2 场景 → 2026Q2）"""
        df = pd.DataFrame({
            "日期": [date(2026, 6, 30), date(2026, 3, 31),
                     date(2025, 6, 30), date(2025, 3, 31)],
            "扣除非经常性损益后的净利润(元)": [100e8, 40e8, 90e8, 50e8],
        })
        result = fetcher._calc_quarterly_yoy(df)
        assert result["数据季度"] == "2026Q2"

