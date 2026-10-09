"""
CSV 数据读取服务 - 股东户数和财务指标
"""
import json
import math

from pathlib import Path
from typing import Optional

import pandas as pd

from ..api.helpers.aux_data import find_latest_aux_file
from ..utils.helpers import DATA_DIR, setup_logger, CODE_DTYPE

logger = setup_logger(__name__)


class ShareholderReader:
    """
    股东户数数据读取服务
    """

    def __init__(self):
        self._cache: pd.DataFrame | None = None

    def _get_file_path(self) -> Optional[Path]:
        """获取文件路径（按 mtime 取最新季度后缀文件，无文件返回 None）"""
        return find_latest_aux_file("股东户数汇总")

    def check_exists(self) -> bool:
        """检查文件是否存在"""
        path = self._get_file_path()
        return path is not None and path.exists()

    def read_csv(self) -> pd.DataFrame:
        """读取股东户数数据"""
        filepath = self._get_file_path()
        if filepath is None or not filepath.exists():
            logger.warning(f"股东户数文件不存在")
            return pd.DataFrame()

        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=CODE_DTYPE)
            df["股票代码"] = df["股票代码"].astype(str).str.zfill(6)
            return df
        except Exception as e:
            logger.error(f"读取股东户数数据失败: {e}")
            return pd.DataFrame()

    def get_quarter(self) -> Optional[str]:
        """获取数据季度"""
        df = self.read_csv()
        if df.empty or "数据季度" not in df.columns:
            return None
        quarters = df["数据季度"].dropna().unique()
        if len(quarters) > 0:
            return str(sorted(quarters)[-1])
        return None

    def get_stock_data(self, code: str) -> Optional[dict]:
        """获取单只股票的股东户数数据"""
        df = self.read_csv()
        if df.empty:
            return None

        code = str(code).zfill(6)
        row = df[df["股票代码"] == code]
        if row.empty:
            return None

        row = row.iloc[0]
        return {
            "shareholder_count": int(row["股东户数"]) if pd.notna(row.get("股东户数")) else None,
            "shareholder_change_pct": float(row["股东人数增幅"]) if pd.notna(row.get("股东人数增幅")) else None,
            "per_share_holding": float(row["人均持股数量"]) if pd.notna(row.get("人均持股数量")) else None,
        }


class FinancialReader:
    """
    财务指标数据读取服务
    """

    def __init__(self):
        self._cache: pd.DataFrame | None = None

    def _get_file_path(self) -> Optional[Path]:
        """获取文件路径（按 mtime 取最新季度后缀文件，无文件返回 None）"""
        return find_latest_aux_file("财务指标汇总")

    def check_exists(self) -> bool:
        """检查文件是否存在"""
        path = self._get_file_path()
        return path is not None and path.exists()

    def read_csv(self) -> pd.DataFrame:
        """读取财务指标数据"""
        filepath = self._get_file_path()
        if filepath is None or not filepath.exists():
            logger.warning(f"财务指标文件不存在")
            return pd.DataFrame()

        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=CODE_DTYPE)
            df["股票代码"] = df["股票代码"].astype(str).str.zfill(6)
            return df
        except Exception as e:
            logger.error(f"读取财务指标数据失败: {e}")
            return pd.DataFrame()

    def get_quarter(self) -> Optional[str]:
        """获取数据季度"""
        df = self.read_csv()
        if df.empty or "数据季度" not in df.columns:
            return None
        quarters = df["数据季度"].dropna().unique()
        if len(quarters) > 0:
            return str(sorted(quarters)[-1])
        return None

    @staticmethod
    def parse_roe_history(value) -> list[dict]:
        """Old or malformed cache cells remain missing."""
        if not isinstance(value, str):
            return []
        try:
            items = json.loads(value)
            if not isinstance(items, list):
                return []
            result = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("year"), int):
                    return []
                number = item.get("value")
                if number is not None:
                    number = float(number)
                    if not math.isfinite(number):
                        return []
                result.append({"year": item["year"], "value": number})
            return result
        except (ValueError, TypeError):
            return []

    def get_stock_data(self, code: str) -> Optional[dict]:
        """获取单只股票的财务指标数据"""
        df = self.read_csv()
        if df.empty:
            return None

        code = str(code).zfill(6)
        row = df[df["股票代码"] == code]
        if row.empty:
            return None

        return self.row_to_data(row.iloc[0])

    @staticmethod
    def row_to_data(row) -> dict:
        """Convert a cache row, preserving missing and invalid numbers as null."""
        def number(column):
            try:
                value = float(row.get(column))
                return value if math.isfinite(value) else None
            except (ValueError, TypeError, OverflowError):
                return None

        def year(column):
            value = number(column)
            return int(value) if value is not None and value.is_integer() else None

        return {
            "gross_profit_margin": number("主营业务利润率"),
            "net_profit_margin": number("净利率"),
            "roe": number("ROE"),
            "roe_year": year("ROE年度"),
            "roe_avg_3y": number("近3年平均ROE"),
            "roe_history": FinancialReader.parse_roe_history(row.get("近3年ROE历史")),
            "previous_quarter_yoy_pct": number("前一季度扣非同比(%)"),
            "previous_quarter_label": str(row["前一季度"]) if pd.notna(row.get("前一季度")) else None,
            "debt_asset_ratio": number("资产负债率"),
            "net_profit_ex_non_recurring_yoy": number("扣非净利润同比"),
            "net_profit_cagr_3y": number("3年复合增长率"),
            "eps_year": year("最新EPS年度"),
            "eps": number("最新EPS(元)"),
            "latest_quarter_net_profit_ex_non_recurring": number("最新季度扣非(元)"),
            "latest_quarter_yoy_pct": number("最新季度扣非同比(%)"),
            "latest_quarter_label": str(row["数据季度"]) if pd.notna(row.get("数据季度")) and str(row["数据季度"]).strip() else None,
        }
