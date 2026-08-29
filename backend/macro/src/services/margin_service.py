"""融资余额服务模块 — akshare 当日点 + 全量历史

数据源：
  - 沪市: akshare.macro_china_market_margin_sh()
  - 深市: akshare.macro_china_market_margin_sz()
合并沪+深按日期对齐（outer join，缺侧 0），融资余额合计（元 → 亿元）。

参考 risk-appetite-skill/scripts/fetch_margin.py:fetch_margin_ohlc。
本项目独立实现，不 import skill（akshare 依赖保留）。
历史禁止按行号/iloc 对齐（沪深交易日不完全重合）。

调用频率：每个交易日 09:45+（融资余额 T-1 数据已发布），建议与 volume/turnover
串行调用。全量回补走 POST /api/macro/fetch/margin/history。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd

from src.config import get_settings
from src.utils.logger import setup_logger
from src.utils.retry import async_retry

logger = setup_logger("margin_service")


def _detect_margin_columns(columns: list[str]) -> dict[str, str] | None:
    """检测融资融券数据的列名映射。

    优先精确匹配，再做子串匹配；子串匹配排除"融资融券余额"汇总列，
    避免"融资余额"被误匹配到汇总列。
    """
    patterns = {
        "date": ["日期", "date", "日期列"],
        "rzye": ["融资余额", "融资余额(元)", "融资余额(万元)"],
        "rzje": ["融资买入额", "买入额", "融资买入"],
        "rqye": ["融券余额", "融券余额(元)", "融券余额(万元)"],
        "rqje": ["融券卖出额", "融券卖出"],
        "rzjmre": ["融资净买入", "净买入"],
        "rqjmre": ["融券净卖出", "净卖出"],
    }

    col_map: dict[str, str] = {}

    # 第一轮：精确匹配
    for target, keywords in patterns.items():
        for col in columns:
            if col.strip() in keywords:
                col_map[target] = col

    # 第二轮：子串匹配（跳过已匹配目标，排除"融资融券余额"汇总列）
    for target, keywords in patterns.items():
        if target in col_map:
            continue
        for col in columns:
            if "融资融券余额" in col:
                continue
            for kw in keywords:
                if kw in col:
                    col_map[target] = col
                    break
            if target in col_map:
                break

    # 至少需要日期和融资余额
    if "date" not in col_map or "rzye" not in col_map:
        return None

    return col_map


def _to_float(v: Any) -> float | None:
    """安全转 float，失败返回 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _extract_latest_margin(
    sh_df: pd.DataFrame, sz_df: pd.DataFrame,
    sh_cols: list[str], sz_cols: list[str],
) -> dict[str, Any] | None:
    """从沪市 + 深市 DataFrame 提取最新一行，合并融资融券余额。

    单位：akshare 返回元 → 转换为亿元（÷ 1e8）。
    """
    sh_map = _detect_margin_columns(sh_cols)
    sz_map = _detect_margin_columns(sz_cols)
    if not sh_map or not sz_map:
        return None

    if sh_df.empty or sz_df.empty:
        return None

    sh_latest = sh_df.iloc[-1]
    sz_latest = sz_df.iloc[-1]

    # 单位：akshare 返回元 → 转换为亿元（÷ 1e8）。
    rzye_wan_sh = _to_float(sh_latest[sh_map["rzye"]])
    rzye_wan_sz = _to_float(sz_latest[sz_map["rzye"]])
    # 沪市 + 深市 融券余额（万元）
    rqye_wan_sh = _to_float(sh_latest[sh_map["rqye"]]) if "rqye" in sh_map else None
    rqye_wan_sz = _to_float(sz_latest[sz_map["rqye"]]) if "rqye" in sz_map else None

    if rzye_wan_sh is None or rzye_wan_sz is None:
        return None

    rzye_yi = round((rzye_wan_sh + rzye_wan_sz) / 100000000, 2)
    rqye_yi = None
    if rqye_wan_sh is not None and rqye_wan_sz is not None:
        rqye_yi = round((rqye_wan_sh + rqye_wan_sz) / 100000000, 2)

    # 日期取沪市最新行的日期列
    date_col_sh = sh_map.get("date", sh_cols[0])
    date_str = str(sh_latest[date_col_sh])[:10]

    return {
        "date": date_str,
        "rzye": rzye_yi,
        "rqye": rqye_yi,
        "source": "akshare",
        "status": "ok",
    }


def _margin_series_by_date(df: pd.DataFrame, col_map: dict[str, str]) -> pd.Series:
    """单市融资余额：按日期去重 keep=last，元 → 亿元。"""
    part = pd.DataFrame({
        "date": pd.to_datetime(df[col_map["date"]], errors="coerce"),
        "rzye": pd.to_numeric(df[col_map["rzye"]], errors="coerce"),
    }).dropna(subset=["date"])
    part = part.drop_duplicates(subset=["date"], keep="last")
    return part.set_index("date")["rzye"] / 1e8


def _merge_margin_history(
    sh_df: pd.DataFrame, sz_df: pd.DataFrame,
) -> pd.DataFrame | None:
    """沪+深按日期 outer join 合计融资余额。

    缺一侧记 0。列名无法识别时返回 None。返回 columns: date, margin_balance_yi。
    """
    sh = sh_df.copy()
    sz = sz_df.copy()
    sh.columns = [str(c).strip() for c in sh.columns]
    sz.columns = [str(c).strip() for c in sz.columns]

    sh_map = _detect_margin_columns(sh.columns.tolist())
    sz_map = _detect_margin_columns(sz.columns.tolist())
    if not sh_map or not sz_map:
        return None

    sh_s = _margin_series_by_date(sh, sh_map)
    sz_s = _margin_series_by_date(sz, sz_map)
    aligned = pd.concat([sh_s.rename("sh"), sz_s.rename("sz")], axis=1).fillna(0)
    aligned = aligned.reset_index()
    date_col = aligned.columns[0]
    out = pd.DataFrame({
        "date": pd.to_datetime(aligned[date_col]),
        "margin_balance_yi": (aligned["sh"] + aligned["sz"]).round(2),
    }).sort_values("date").reset_index(drop=True)
    return out


class MarginService:
    """融资余额服务（akshare 当日点 + 全量历史）"""

    def __init__(self) -> None:
        # akshare 模块按需导入；模块级 import 会拖慢启动，且 akshare 在某些环境不可用
        self._akshare = None

    def _get_akshare(self):
        if self._akshare is None:
            import akshare as ak
            self._akshare = ak
        return self._akshare

    def fetch_today(self) -> dict[str, Any]:
        """拉取当日融资余额（T 日 09:45+ 时数据为 T-1）

        返回:
            {
                "date": "2026-08-21",
                "rzye": float,       # 融资余额 (亿元)
                "rqye": float | None,
                "source": "akshare",
                "status": "ok" | "failed",
            }
        """
        result: dict[str, Any] = {
            "date": None,
            "rzye": None,
            "rqye": None,
            "source": "akshare",
            "status": "failed",
        }

        try:
            ak = self._get_akshare()
            sh_df = ak.macro_china_market_margin_sh()
            sz_df = ak.macro_china_market_margin_sz()

            # akshare 返回的列名可能含空格，strip 一下
            sh_df.columns = [c.strip() for c in sh_df.columns]
            sz_df.columns = [c.strip() for c in sz_df.columns]

            latest = _extract_latest_margin(
                sh_df, sz_df, sh_df.columns.tolist(), sz_df.columns.tolist()
            )
            if not latest:
                logger.warning("akshare 融资余额解析失败（列名识别失败或数据空）")
                return result

            result.update(latest)
            logger.info(
                "akshare 融资余额获取成功: 融资余额=%.2f亿, date=%s",
                latest["rzye"], latest["date"],
            )
            return result
        except Exception as exc:
            logger.warning("akshare 融资余额抓取失败: %s", exc)
            result["error"] = str(exc)
            return result

    def fetch_history(self) -> dict[str, Any]:
        """拉取沪深全表，按日期对齐合计后返回 DataFrame。

        返回:
            {
                "status": "ok" | "failed",
                "error": str | None,
                "data": DataFrame[date, margin_balance_yi],
            }
        """
        empty = pd.DataFrame(columns=["date", "margin_balance_yi"])
        result: dict[str, Any] = {"status": "failed", "error": None, "data": empty}

        try:
            ak = self._get_akshare()
            sh_df = ak.macro_china_market_margin_sh()
            sz_df = ak.macro_china_market_margin_sz()
            sh_df.columns = [c.strip() for c in sh_df.columns]
            sz_df.columns = [c.strip() for c in sz_df.columns]

            merged = _merge_margin_history(sh_df, sz_df)
            if merged is None or merged.empty:
                logger.warning("akshare 融资余额历史解析失败（列名识别失败或数据空）")
                return result

            start = pd.Timestamp(get_settings().historical_start_date)
            merged = merged[merged["date"] >= start].reset_index(drop=True)
            if merged.empty:
                logger.warning("akshare 融资余额历史过滤后为空")
                return result

            result["status"] = "ok"
            result["data"] = merged
            logger.info(
                "akshare 融资余额历史获取成功: %d行, %s ~ %s",
                len(merged),
                merged["date"].iloc[0].strftime("%Y-%m-%d"),
                merged["date"].iloc[-1].strftime("%Y-%m-%d"),
            )
            return result
        except Exception as exc:
            logger.warning("akshare 融资余额历史抓取失败: %s", exc)
            result["error"] = str(exc)
            return result


# 全局单例
_margin_service: Optional[MarginService] = None


def get_margin_service() -> MarginService:
    global _margin_service
    if _margin_service is None:
        _margin_service = MarginService()
    return _margin_service