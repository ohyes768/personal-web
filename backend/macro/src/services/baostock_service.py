"""BaoStock 两市成交额/换手率服务 — 上证指数 + 深证综指日线（历史 + 当日增量）

数据源：
  - baostock.query_history_k_data_plus，frequency="d"，adjustflag="3"
  - 沪市: sh.000001 上证指数（全沪市样本）
  - 深市: sz.399106 深证综指（全深市样本）

合成口径（与旧 exchange_official 口径同趋势，量级一致，2026-08-29 调研定稿）：
  - 两市成交额 = (sh.amount + sz.amount) / 1e8   （amount 单位元 → 亿元）
  - 两市换手率 = (sh_amt*sh_turn + sz_amt*sz_turn) / (sh_amt + sz_amt)  （%）
  - 两指数按日期 inner-join 对齐交易日，NaN 行逐指标 dropna

baostock 免费服务需显式 login/logout，一次会话内完成两指标拉取（logout 放 finally）。

调用频率：每个交易日盘后（n8n POST /api/macro/update/volume|turnover）；
历史回补走 POST /api/macro/update/volume-turnover/history。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("baostock_service")

K_FIELDS = "date,close,volume,amount,turn"


class BaostockService:
    """两市成交额/换手率服务（BaoStock 指数日线）"""

    _SH_CODE = "sh.000001"   # 上证指数（全沪市样本）
    _SZ_CODE = "sz.399106"   # 深证综指（全深市样本）

    def __init__(self) -> None:
        # baostock 模块按需导入；模块级 import 会拖慢启动（与 margin_service 处理 akshare 一致）
        self._baostock = None

    def _get_baostock(self):
        if self._baostock is None:
            import baostock as bs
            self._baostock = bs
        return self._baostock

    def fetch_index_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        """拉取单指数日线（需已 login），返回 date/amount/turn 三列 DataFrame。

        amount 单位元、turn 单位 %，均为 float；空串/非法值转 NaN。
        """
        bs = self._get_baostock()
        rs = bs.query_history_k_data_plus(
            code, K_FIELDS,
            start_date=start, end_date=end,
            frequency="d", adjustflag="3",
        )
        if rs.error_code != "0":
            raise RuntimeError(f"{code} 查询失败: {rs.error_msg}")

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        df = pd.DataFrame(rows, columns=rs.fields)

        if df.empty:
            return pd.DataFrame(columns=["date", "amount", "turn"])

        out = df[["date", "amount", "turn"]].copy()
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
        out["turn"] = pd.to_numeric(out["turn"], errors="coerce")
        return out

    def fetch_history(self, start: str, end: str) -> dict[str, Any]:
        """一次 login 会话拉两指数并合成两市指标。

        返回:
            {
                "volume": DataFrame[date, total_amount_yi],   # 亿元
                "turnover": DataFrame[date, turnover_rate],   # %
                "source": "baostock",
                "status": "ok" | "failed",
                "error": str  # 仅失败时
            }
        """
        result: dict[str, Any] = {
            "volume": pd.DataFrame(columns=["date", "total_amount_yi"]),
            "turnover": pd.DataFrame(columns=["date", "turnover_rate"]),
            "source": "baostock",
            "status": "failed",
        }
        bs = self._get_baostock()
        try:
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"baostock login failed: {lg.error_msg}")

            sh = self.fetch_index_daily(self._SH_CODE, start, end)
            sz = self.fetch_index_daily(self._SZ_CODE, start, end)

            merged = pd.merge(
                sh.rename(columns={"amount": "sh_amount", "turn": "sh_turn"}),
                sz.rename(columns={"amount": "sz_amount", "turn": "sz_turn"}),
                on="date", how="inner",
            ).sort_values("date").reset_index(drop=True)

            if merged.empty:
                logger.warning("BaoStock 两指数日期无交集: %s ~ %s", start, end)
                result["status"] = "ok"
                return result

            total = merged["sh_amount"] + merged["sz_amount"]
            volume_df = pd.DataFrame({
                "date": merged["date"],
                "total_amount_yi": (total / 1e8).round(2),
            }).dropna(subset=["total_amount_yi"])

            turnover_df = pd.DataFrame({
                "date": merged["date"],
                "turnover_rate": (
                    (merged["sh_amount"] * merged["sh_turn"]
                     + merged["sz_amount"] * merged["sz_turn"]) / total
                ).round(4),
            }).dropna(subset=["turnover_rate"])

            result["volume"] = volume_df.reset_index(drop=True)
            result["turnover"] = turnover_df.reset_index(drop=True)
            result["status"] = "ok"
            logger.info(
                "BaoStock 两市指标拉取成功: %s ~ %s, volume=%d行, turnover=%d行",
                start, end, len(volume_df), len(turnover_df),
            )
            return result
        except Exception as exc:
            logger.warning("BaoStock 两市指标拉取失败: %s", exc)
            result["error"] = str(exc)
            return result
        finally:
            bs.logout()

    def fetch_today(self, now: datetime | None = None) -> dict[str, Any]:
        """当日增量入口：拉近 10 个自然日窗口（覆盖节假日缺口），返回最新单点 + 小批量。

        与旧 volume/turnover fetch_today 语义对齐（date/total_amount_yi/turnover_rate
        字段名不变）；批量 DataFrame 供落库补缺口。非交易日/盘前时最新行自然回退到
        最近交易日。
        """
        if now is None:
            now = datetime.now()
        start = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        history = self.fetch_history(start, end)

        result: dict[str, Any] = {
            "date": None,
            "total_amount_yi": None,
            "turnover_rate": None,
            "volume": history["volume"],
            "turnover": history["turnover"],
            "source": "baostock",
            "status": history["status"],
        }
        if "error" in history:
            result["error"] = history["error"]

        volume_df: pd.DataFrame = history["volume"]
        turnover_df: pd.DataFrame = history["turnover"]

        latest_date: Optional[str] = None
        if not volume_df.empty:
            latest_date = str(volume_df["date"].iloc[-1])
            result["date"] = latest_date
            result["total_amount_yi"] = float(volume_df["total_amount_yi"].iloc[-1])
        if not turnover_df.empty:
            if latest_date is None:
                latest_date = str(turnover_df["date"].iloc[-1])
                result["date"] = latest_date
            row = turnover_df[turnover_df["date"] == latest_date]
            if not row.empty:
                result["turnover_rate"] = float(row["turnover_rate"].iloc[0])

        return result


# 全局单例
_baostock_service: Optional[BaostockService] = None


def get_baostock_service() -> BaostockService:
    global _baostock_service
    if _baostock_service is None:
        _baostock_service = BaostockService()
    return _baostock_service
