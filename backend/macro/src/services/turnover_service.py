"""换手率服务模块 — 沪深交易所官方 API 当日点抓取

沪市取上交所加权换手率（SSE API TOTAL_TO_RATE × TRADE_AMT 加权）；
深市用 cjje/ltsz 自计算（深交所 ShowReport 不直接返回换手率）；
两市按成交额加权合成全市场换手率。

参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:fetch_sse_turnover / fetch_szse_turnover。
本项目独立实现，不 import skill。

调用频率：每个交易日 16:30 盘后调度一次（n8n POST /api/macro/update/turnover）。
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.logger import setup_logger
from src.utils.retry import async_retry
from src.utils.trade_date import get_trade_date
from src.services.volume_service import (
    DEFAULT_HEADERS,
    SSE_PRODUCT_CODES,
    SSE_SQL_ID,
    SSE_VOLUME_URL,
    SZSE_VOLUME_URL,
    _clean_number,
    _normalize_lbmc,
)

logger = setup_logger("turnover_service")


def _parse_sse_turnover(date_str: str, json_str: str) -> dict[str, Any]:
    """解析 SSE JSONP 响应：按 TRADE_AMT 加权 TOTAL_TO_RATE。

    返回:
        {
            "date": "2026-08-21",
            "turnover_rate": float | None,  # %
            "amount_yi": float | None,      # 亿元
            "status": "ok" | "failed",
        }
    """
    import json

    result: dict[str, Any] = {
        "date": date_str,
        "turnover_rate": None,
        "amount_yi": None,
        "source": "sse",
        "status": "failed",
    }
    try:
        data = json.loads(json_str)
        items = data.get("result") or []
        if not items:
            logger.warning("SSE 换手率 API 返回空数据: %s", date_str)
            return result

        total_amount = 0.0
        weighted_rate = 0.0
        for item in items:
            amt = _clean_number(item.get("TRADE_AMT")) or 0.0
            rate = _clean_number(item.get("TOTAL_TO_RATE")) or 0.0
            total_amount += amt
            weighted_rate += amt * rate

        if total_amount > 0:
            rate = round(weighted_rate / total_amount, 4)
            result.update({
                "turnover_rate": rate,
                "amount_yi": round(total_amount, 2),
                "status": "ok",
            })
    except Exception as exc:
        logger.warning("解析 SSE 换手率失败: %s", exc)

    return result


def _parse_szse_turnover(date_str: str, data: list[Any]) -> dict[str, Any]:
    """解析 SZSE 响应：从"股票"分类的 cjje / ltsz 自计算换手率（%）。

    返回:
        {
            "date": "2026-08-21",
            "turnover_rate": float | None,  # %
            "amount_yi": float | None,      # 亿元
            "ltsz_yi": float | None,        # 流通市值 亿元
            "status": "ok" | "failed",
        }
    """
    result: dict[str, Any] = {
        "date": date_str,
        "turnover_rate": None,
        "amount_yi": None,
        "ltsz_yi": None,
        "source": "szse",
        "status": "failed",
    }
    try:
        if not data or not data[0].get("data"):
            logger.warning("SZSE 换手率 API 返回空数据: %s", date_str)
            return result

        stock_row = None
        for item in data[0]["data"]:
            raw_lbmc = item.get("lbmc", "")
            lbmc = _normalize_lbmc(raw_lbmc) if isinstance(raw_lbmc, str) else str(raw_lbmc)
            if lbmc == "股票":
                stock_row = item
                break

        if not stock_row:
            logger.warning("SZSE 换手率：未找到'股票'分类")
            return result

        cjje = _clean_number(stock_row.get("cjje"))
        ltsz = _clean_number(stock_row.get("ltsz"))
        if not cjje or not ltsz:
            return result

        result.update({
            "turnover_rate": round(cjje / ltsz * 100, 4),
            "amount_yi": round(cjje / 1e8, 2),
            "ltsz_yi": round(ltsz / 1e8, 2),
            "status": "ok",
        })
    except Exception as exc:
        logger.warning("解析 SZSE 换手率失败: %s", exc)

    return result


def _combine_turnover(date_str: str, sse: dict, szse: dict) -> dict[str, Any]:
    """两市按成交额加权合成换手率。

    公式: (sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)
    单边失败时退化为单值（partial），双边失败返回 failed。
    """
    sh_rate = sse.get("turnover_rate")
    sh_amt = sse.get("amount_yi") or 0.0
    sz_rate = szse.get("turnover_rate")
    sz_amt = szse.get("amount_yi") or 0.0

    if sh_rate is not None and sz_rate is not None and (sh_amt + sz_amt) > 0:
        combined = (sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)
        return {
            "date": date_str,
            "turnover_rate": round(combined, 4),
            "sh_turnover_rate": sh_rate,
            "sz_turnover_rate": sz_rate,
            "sh_amount_yi": sh_amt,
            "sz_amount_yi": sz_amt,
            "source": "exchange_official",
            "status": "ok",
        }

    # 单边可用退化
    single = sh_rate if sh_rate is not None else sz_rate
    if single is not None:
        return {
            "date": date_str,
            "turnover_rate": round(single, 4),
            "sh_turnover_rate": sh_rate,
            "sz_turnover_rate": sz_rate,
            "status": "partial",
        }

    return {
        "date": date_str,
        "turnover_rate": None,
        "status": "failed",
    }


class TurnoverService:
    """两市换手率服务"""

    def __init__(self) -> None:
        self.session = requests.Session()
        retries = Retry(
            total=3, connect=3, read=3, backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_sse_turnover(self, date_str: str) -> dict[str, Any]:
        """获取沪市换手率（SSE 加权平均 + 成交额）"""
        result: dict[str, Any] = {
            "date": date_str, "turnover_rate": None, "amount_yi": None,
            "source": "sse", "status": "failed",
        }
        try:
            resp = self.session.get(
                SSE_VOLUME_URL,
                params={
                    "jsonCallBack": "cb",
                    "sqlId": SSE_SQL_ID,
                    "PRODUCT_CODE": SSE_PRODUCT_CODES,
                    "type": "inParams",
                    "SEARCH_DATE": date_str,
                },
                headers={"Referer": "https://www.sse.com.cn/"},
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text
            start = text.index("(") + 1
            end = text.rindex(")")
            return _parse_sse_turnover(date_str, text[start:end])
        except Exception as exc:
            logger.warning("SSE 换手率抓取失败: %s", exc)
            result["error"] = str(exc)
            return result

    def fetch_szse_turnover(self, date_str: str) -> dict[str, Any]:
        """获取深市换手率（cjje/ltsz 自计算）"""
        result: dict[str, Any] = {
            "date": date_str, "turnover_rate": None, "amount_yi": None, "ltsz_yi": None,
            "source": "szse", "status": "failed",
        }
        try:
            resp = self.session.get(
                SZSE_VOLUME_URL,
                params={
                    "SHOWTYPE": "JSON",
                    "CATALOGID": "1803_sczm",
                    "TABKEY": "tab1",
                    "txtQueryDate": date_str,
                },
                headers={"Referer": "https://www.szse.cn/market/overview/index.html"},
                timeout=15,
            )
            resp.raise_for_status()
            return _parse_szse_turnover(date_str, resp.json())
        except Exception as exc:
            logger.warning("SZSE 换手率抓取失败: %s", exc)
            result["error"] = str(exc)
            return result

    @async_retry(max_retries=3, delay=1.0)
    async def fetch_today(self) -> dict[str, Any]:
        """拉取当日两市换手率合计（自动判断盘中/盘后）"""
        date_str = get_trade_date()
        logger.info("换手率 fetch_today: trade_date=%s", date_str)

        sse = self.fetch_sse_turnover(date_str)
        szse = self.fetch_szse_turnover(date_str)

        combined = _combine_turnover(date_str, sse, szse)
        return combined


# 全局单例
_turnover_service: Optional[TurnoverService] = None


def get_turnover_service() -> TurnoverService:
    global _turnover_service
    if _turnover_service is None:
        _turnover_service = TurnoverService()
    return _turnover_service