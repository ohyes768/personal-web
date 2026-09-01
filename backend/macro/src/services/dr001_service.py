"""DR001 服务模块 - 从中国货币网获取隔夜质押式回购加权利率

数据源：中国货币网质押式回购当日快照
URL: https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-md.json

注意：此接口为 POST 请求，必须带 Referer + X-Requested-With 头，否则可能返回 403。

响应 JSON 结构:
  data.records[]: 每个期限一条记录，字段包含 productCode/weightedRate/latestRate/date 等
  DR001 加权利率取自 records[productCode='DR001'].weightedRate

参考：monetary-policy-skill 的 prr-md.json 同源数据；本项目内独立维护以避免跨项目耦合。
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

logger = setup_logger("dr001_service")

DR001_JSON_URL = (
    "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-md.json"
)
DR001_REFERER = "https://www.chinamoney.com.cn/chinese/mkdatapm/?tab=2"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/javascript,*/*;q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": DR001_REFERER,
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.chinamoney.com.cn",
}

_TARGET_PRODUCT = "DR001"
_WEIGHTED_RATE_KEY = "weightedRate"
_DATE_KEY = "date"


class DR001Service:
    """DR001 隔夜质押式回购加权利率服务

    字段：dr001（年化百分比）
    频率：每个银行间交易日（工作日）
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(DEFAULT_HEADERS)

    @staticmethod
    def extract_dr001(payload: Any) -> dict[str, Any] | None:
        """从 prr-md.json 响应里抽 DR001 加权利率。

        返回 {"value": float, "data_date": "YYYY-MM-DD"} 或 None（缺失/字段不对）。
        """
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        records = data.get("records")
        if not isinstance(records, list):
            return None

        for rec in records:
            if not isinstance(rec, dict):
                continue
            if rec.get("productCode") != _TARGET_PRODUCT:
                continue
            raw_value = rec.get(_WEIGHTED_RATE_KEY)
            if raw_value is None:
                return None
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                return None
            raw_date = rec.get(_DATE_KEY)
            # date 字段形如 "26-09-01"（YY-MM-DD），补齐 20YY 年份；缺失回退 None
            data_date: Optional[str] = None
            if isinstance(raw_date, str) and raw_date:
                data_date = _normalize_date(raw_date)
            return {"value": value, "data_date": data_date}
        return None

    def fetch_json(self, timeout: int = 20) -> dict[str, Any]:
        """POST 拉取最新 JSON。失败抛 requests.HTTPError。"""
        response = self.session.post(
            DR001_JSON_URL,
            data="",  # prr-md.json 接受空 body,POST 是浏览器真实行为
            timeout=timeout,
        )
        response.raise_for_status()
        if not response.encoding:
            response.encoding = "utf-8"
        return json.loads(response.text)

    async def fetch_today(self) -> pd.DataFrame:
        """拉取当日 DR001 加权利率。

        失败/字段缺失返回空 DataFrame（保留列结构）。返回的 DataFrame
        是单行（index=date, columns=['dr001']），可与 DR007 历史 DataFrame
        无缝衔接（同样的 asof 语义）。
        """
        df = pd.DataFrame(columns=["dr001"])
        try:
            payload = self.fetch_json()
        except Exception as e:
            logger.warning(f"DR001 接口请求失败: {e}")
            return df

        extracted = self.extract_dr001(payload)
        if extracted is None:
            logger.warning("DR001 接口响应中未找到有效记录")
            return df

        data_date_str = extracted["data_date"]
        if not data_date_str:
            logger.warning("DR001 接口响应缺少有效日期字段")
            return df

        date_ts = pd.Timestamp(data_date_str)
        df = pd.DataFrame({"dr001": [extracted["value"]]}, index=pd.DatetimeIndex([date_ts]))
        df.index.name = "date"
        return df


def _normalize_date(raw: str) -> Optional[str]:
    """prr-md.json 的 date 字段形如 "26-09-01"（YY-MM-DD）→ "YYYY-MM-DD"。

    解析失败返回 None。年份用当前世纪（20YY）补齐——与 demo 验证时一致，
    不做向后跨世纪推断（接口实际就是 2000 年后）。
    """
    raw = raw.strip()
    for fmt in ("%y-%m-%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# 全局单例
_dr001_service: Optional[DR001Service] = None


def get_dr001_service() -> DR001Service:
    global _dr001_service
    if _dr001_service is None:
        _dr001_service = DR001Service()
    return _dr001_service
