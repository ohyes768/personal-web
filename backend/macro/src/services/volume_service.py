"""两市成交额服务模块 — 沪深交易所官方 API 当日点抓取

数据源：
  - 沪市: https://query.sse.com.cn/commonQuery.do
          (sqlId=COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C, JSONP 格式)
  - 深市: https://www.szse.cn/api/report/ShowReport/data
          (CATALOGID=1803_sczm, JSON 格式)

参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:fetch_sse_volume / fetch_szse_volume / fetch_both_exchanges。
本项目内独立维护，不 import skill。

调用频率：每个交易日 16:30 盘后调度一次（n8n POST /api/macro/update/volume）。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.logger import setup_logger
from src.utils.retry import async_retry
from src.utils.trade_date import get_trade_date

logger = setup_logger("volume_service")

SSE_VOLUME_URL = "https://query.sse.com.cn/commonQuery.do"
SZSE_VOLUME_URL = "https://www.szse.cn/api/report/ShowReport/data"

SSE_PRODUCT_CODES = "01,02,03,11,17"
SSE_SQL_ID = "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _clean_number(s: str | float | int | None) -> float | None:
    """清洗数字：字符串去逗号/空格后转 float；float/int 直转。空值/占位符返回 None。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        if s != s:  # NaN
            return None
        return float(s)
    s = s.strip().replace(",", "").replace(" ", "")
    if not s or s == "-" or s == "NaN":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _normalize_lbmc(s: str) -> str:
    """规范化深交所板块名称，移除 &nbsp; 等 HTML 实体。"""
    return s.replace("&nbsp;", "").strip()


def _parse_sse_volume(date_str: str, json_str: str) -> dict[str, Any]:
    """解析 SSE JSONP 响应，按 PRODUCT_CODE 01/02/03/11/17 汇总 TRADE_AMT。

    返回:
        {
            "date": "2026-08-21",
            "total_amount_yi": float | None,  # 亿元
            "main_board_yi": float | None,    # 主板 A (01)
            "main_board_b_yi": float | None,  # 主板 B (02)
            "star_board_yi": float | None,    # 科创板 (17)
            "status": "ok" | "failed",
        }
    """
    result: dict[str, Any] = {
        "date": date_str,
        "total_amount_yi": None,
        "main_board_yi": None,
        "main_board_b_yi": None,
        "star_board_yi": None,
        "source": "sse",
        "status": "failed",
    }
    try:
        data = json.loads(json_str)
        items = data.get("result") or []
        if not items:
            logger.warning("SSE 成交额 API 返回空数据: %s", date_str)
            return result

        total = 0.0
        main_board = 0.0
        main_board_b = 0.0
        star_board = 0.0

        for item in items:
            code = item.get("PRODUCT_CODE", "")
            amt = _clean_number(item.get("TRADE_AMT")) or 0.0
            if code == "01":
                main_board = amt
                total += amt
            elif code == "02":
                main_board_b = amt
                total += amt
            elif code == "03":
                total += amt
            elif code == "11":
                total += amt
            elif code == "17":
                star_board = amt
                total += amt

        result.update({
            "date": date_str,
            "total_amount_yi": round(total, 2),
            "main_board_yi": round(main_board, 2),
            "main_board_b_yi": round(main_board_b, 2),
            "star_board_yi": round(star_board, 2),
            "status": "ok",
        })
    except Exception as exc:
        logger.warning("解析 SSE 成交额失败: %s", exc)

    return result


def _parse_szse_volume(date_str: str, data: list[Any]) -> dict[str, Any]:
    """解析 SZSE 响应：data[0].data 是 [{lbmc, cjje, ...}, ...]。

    按"主板 A 股 + 主板 B 股 + 创业板"汇总 cjje（单位：元 → 亿元）。

    返回:
        {
            "date": "2026-08-21",
            "total_amount_yi": float | None,  # 亿元
            "main_board_a_yi": float | None,
            "chinext_yi": float | None,
            "status": "ok" | "failed",
        }
    """
    result: dict[str, Any] = {
        "date": date_str,
        "total_amount_yi": None,
        "main_board_a_yi": None,
        "chinext_yi": None,
        "source": "szse",
        "status": "failed",
    }
    try:
        if not data or not data[0].get("data"):
            logger.warning("SZSE 成交额 API 返回空数据: %s", date_str)
            return result

        total = 0.0
        main_board_a = 0.0
        chinext = 0.0

        for item in data[0]["data"]:
            raw_lbmc = item.get("lbmc", "")
            lbmc = _normalize_lbmc(raw_lbmc) if isinstance(raw_lbmc, str) else str(raw_lbmc)
            cjje = _clean_number(item.get("cjje")) or 0.0

            if "主板A股" in lbmc:
                main_board_a = cjje
                total += cjje
            elif "主板B股" in lbmc:
                total += cjje
            elif "创业板" in lbmc:
                chinext = cjje
                total += cjje

        result.update({
            "date": date_str,
            "total_amount_yi": round(total / 1e8, 2),
            "main_board_a_yi": round(main_board_a / 1e8, 2),
            "chinext_yi": round(chinext / 1e8, 2),
            "status": "ok",
        })
    except Exception as exc:
        logger.warning("解析 SZSE 成交额失败: %s", exc)

    return result


class VolumeService:
    """两市成交额服务（沪深交易所官方 API 当日点）"""

    def __init__(self) -> None:
        self.session = requests.Session()
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_sse_volume(self, date_str: str) -> dict[str, Any]:
        """获取沪市成交额（JSONP 响应，需去包装）"""
        result: dict[str, Any] = {
            "date": date_str,
            "total_amount_yi": None,
            "main_board_yi": None,
            "main_board_b_yi": None,
            "star_board_yi": None,
            "source": "sse",
            "status": "failed",
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
            # JSONP: cb({...})
            start = text.index("(") + 1
            end = text.rindex(")")
            return _parse_sse_volume(date_str, text[start:end])
        except Exception as exc:
            logger.warning("SSE 成交额抓取失败: %s", exc)
            result["error"] = str(exc)
            return result

    def fetch_szse_volume(self, date_str: str) -> dict[str, Any]:
        """获取深市成交额（JSON 响应）"""
        result: dict[str, Any] = {
            "date": date_str,
            "total_amount_yi": None,
            "main_board_a_yi": None,
            "chinext_yi": None,
            "source": "szse",
            "status": "failed",
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
            return _parse_szse_volume(date_str, resp.json())
        except Exception as exc:
            logger.warning("SZSE 成交额抓取失败: %s", exc)
            result["error"] = str(exc)
            return result

    def _combine(self, sse: dict, szse: dict) -> dict[str, Any]:
        """合并 SSE + SZSE 结果为当日两市合计"""
        sse_yi = sse.get("total_amount_yi") or 0.0
        szse_yi = szse.get("total_amount_yi") or 0.0
        if (sse.get("status") != "ok" or sse.get("total_amount_yi") is None) and \
           (szse.get("status") != "ok" or szse.get("total_amount_yi") is None):
            status = "failed"
        elif sse.get("status") != "ok" or szse.get("status") != "ok":
            status = "partial"
        else:
            status = "ok"
        return {
            "date": sse.get("date") or szse.get("date"),
            "total_amount_yi": round(sse_yi + szse_yi, 2) if (sse_yi + szse_yi) > 0 else None,
            "sse_amount_yi": sse_yi or None,
            "szse_amount_yi": szse_yi or None,
            "source": "exchange_official",
            "status": status,
        }

    @async_retry(max_retries=3, delay=1.0)
    async def fetch_today(self) -> dict[str, Any]:
        """拉取当日两市成交额合计（自动判断盘中/盘后，回退最近交易日）"""
        date_str = get_trade_date()
        logger.info("两市成交额 fetch_today: trade_date=%s", date_str)

        sse = self.fetch_sse_volume(date_str)
        szse = self.fetch_szse_volume(date_str)

        combined = self._combine(sse, szse)

        if combined["status"] == "failed":
            logger.warning(
                "两市成交额获取失败: SSE=%s SZSE=%s",
                sse.get("status"), szse.get("status"),
            )

        return combined


# 全局单例
_volume_service: Optional[VolumeService] = None


def get_volume_service() -> VolumeService:
    global _volume_service
    if _volume_service is None:
        _volume_service = VolumeService()
    return _volume_service