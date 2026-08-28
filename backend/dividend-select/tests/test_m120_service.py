"""
M120 Service 单元测试
"""
import os

import pandas as pd
import pytest
from unittest.mock import patch

from src.services.m120_service import M120Service

# 打真实阿里云行情 API 的集成测试：需要 ALIYUN_API_APPCODE 且能访问外网
requires_aliyun_appcode = pytest.mark.skipif(
    not os.getenv("ALIYUN_API_APPCODE"),
    reason="集成测试需要环境变量 ALIYUN_API_APPCODE（真实阿里云行情 API）",
)


def _write_realtime_csv(svc, rows):
    """把 rows（list of dict）写成实时价格 CSV（新格式列名）。"""
    df = pd.DataFrame(rows)
    df.to_csv(svc.REALTIME_PRICE_CSV_FILE, index=False, encoding="utf-8-sig")


class TestM120Service:
    """M120 服务测试"""

    @requires_aliyun_appcode
    def test_get_realtime_prices_batch_single(self):
        """测试批量获取单个股票的实时价格"""
        service = M120Service()
        result = service._get_realtime_prices_batch(["600519"])

        assert len(result) > 0, "应该返回至少一只股票的价格"
        assert "600519" in result or any("600519" in k for k in result.keys()), f"应该包含 600519，当前结果: {result}"
        sample = next(iter(result.values()))
        assert isinstance(sample, dict), "每条应为 dict"
        assert "realtime" in sample and "close" in sample
        assert "pe" in sample and "pb" in sample

    @requires_aliyun_appcode
    def test_get_realtime_prices_batch_multiple(self):
        """测试批量获取多个股票的实时价格"""
        service = M120Service()
        codes = ["600519", "000001", "600036"]
        result = service._get_realtime_prices_batch(codes)

        assert len(result) > 0, "应该返回至少一只股票的价格"
        # 检查是否返回了多个股票
        assert len(result) >= 1, f"应该返回股票数据，当前结果: {result}"

    def test_get_realtime_prices_batch_empty(self):
        """测试空列表输入"""
        service = M120Service()
        result = service._get_realtime_prices_batch([])

        assert result == {}, "空列表应该返回空字典"

    @requires_aliyun_appcode
    def test_get_m120_from_aliyun(self):
        """测试从阿里云获取单只股票M120"""
        service = M120Service()
        result = service._get_m120_from_aliyun("600519")

        assert result is not None, "应该返回M120数据"
        assert "m120" in result, "结果应该包含m120字段"
        assert result["m120"] > 0, "M120应该是正数"

    def test_stock_code_conversion(self):
        """测试股票代码转换格式"""
        service = M120Service()

        # 沪市股票
        assert service._get_stock_code_with_prefix("600519") == "sh600519"
        # 深市股票
        assert service._get_stock_code_with_prefix("000001") == "sz000001"


class TestReadPricesOnly:
    """read_prices_only：独立现价读取，不依赖 M120（行情价与 M120 解耦）。"""

    def test_reads_new_format(self, tmp_path):
        """新格式列名（昨日收盘/实时价格/静态PE/市净率）正确解析。"""
        rows = [
            {"日期": "2099-12", "股票代码": "000922", "昨日收盘": 5.23, "实时价格": 5.31, "静态PE": 8.2, "市净率": 0.95},
            {"日期": "2099-12", "股票代码": "600000", "昨日收盘": 10.0, "实时价格": None, "静态PE": None, "市净率": None},
        ]
        with patch("src.services.m120_service.DATA_DIR", tmp_path):
            svc = M120Service(date_str="2099-12")
            _write_realtime_csv(svc, rows)
            result = svc.read_prices_only()

        assert set(result.keys()) == {"000922", "600000"}
        assert result["000922"] == {"close": 5.23, "realtime": 5.31, "pe": 8.2, "pb": 0.95}
        # None 值透传
        assert result["600000"]["realtime"] is None
        assert result["600000"]["pe"] is None

    def test_code_zfill_preserved(self, tmp_path):
        """前导零股票代码（如 000922）保持 6 位，不被读成 int。"""
        rows = [{"日期": "2099-12", "股票代码": "000922", "昨日收盘": 5.0, "实时价格": 5.0, "静态PE": 8.0, "市净率": 1.0}]
        with patch("src.services.m120_service.DATA_DIR", tmp_path):
            svc = M120Service(date_str="2099-12")
            _write_realtime_csv(svc, rows)
            result = svc.read_prices_only()
        assert "000922" in result, f"前导零代码应保留，实际 keys={list(result.keys())}"

    def test_returns_empty_when_realtime_csv_missing(self, tmp_path):
        """实时价格 CSV 不存在 → 返回 {}。"""
        with patch("src.services.m120_service.DATA_DIR", tmp_path):
            svc = M120Service(date_str="2099-12")
            result = svc.read_prices_only()
        assert result == {}

    def test_works_without_m120_csv(self, tmp_path):
        """
        核心验收：M120 CSV 不存在时，read_prices_only 仍返回实时价格。
        对照 read_m120_with_deviation 此时返回 {}（被 M120 绑架，即本次要修的根因）。
        """
        rows = [{"日期": "2099-12", "股票代码": "000922", "昨日收盘": 5.23, "实时价格": 5.31, "静态PE": 8.2, "市净率": 0.95}]
        with patch("src.services.m120_service.DATA_DIR", tmp_path):
            svc = M120Service(date_str="2099-12")
            _write_realtime_csv(svc, rows)
            assert not svc.M120_CSV_FILE.exists()  # 不写 M120 CSV
            prices = svc.read_prices_only()
            with_dev = svc.read_m120_with_deviation()

        # read_prices_only 不受 M120 缺失影响
        assert "000922" in prices
        assert prices["000922"]["realtime"] == 5.31
        # read_m120_with_deviation 以 M120 为主表，缺失时返回 {}（根因，本次不动其语义）
        assert with_dev == {}


class TestReadM120WithDeviationUnchanged:
    """read_m120_with_deviation 行为不变（重构后仍走 _read_price_csv）。"""

    def test_still_merges_price_into_m120(self, tmp_path):
        """两 CSV 都在 → price 字段正确 merge 进 M120 主表。"""
        with patch("src.services.m120_service.DATA_DIR", tmp_path):
            svc = M120Service(date_str="2099-12")
            pd.DataFrame([
                {"日期": "2099-12", "股票代码": "000922", "M120": 5.0},
            ]).to_csv(svc.M120_CSV_FILE, index=False, encoding="utf-8-sig")
            _write_realtime_csv(svc, [
                {"日期": "2099-12", "股票代码": "000922", "昨日收盘": 5.2, "实时价格": 5.3, "静态PE": 8.0, "市净率": 1.0},
            ])
            result = svc.read_m120_with_deviation()

        assert "000922" in result
        info = result["000922"]
        assert info["m120"] == 5.0
        assert info["close"] == 5.2
        assert info["realtime"] == 5.3
        assert info["pe"] == 8.0
        assert info["pb"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
