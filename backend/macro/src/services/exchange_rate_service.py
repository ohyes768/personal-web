"""汇率数据服务 — 阿里云 alirmcom2 comkm（DXY / USDCNY / USDJPY / EURUSD）

与 index_service / commodity_service 同一套 comkm 翻页。
API 字段名保持 dollar_index / usd_cny / usd_jpy / usd_eur，前端不用改。

口径：
- dollar_index = ICE DXY，不是 FRED DTWEXBGS（贸易加权广义指数，量级约 118）
- usd_cny / usd_jpy = 外币/1 美元（与 FRED DEXCHUS / DEXJPUS 同向，报价不同）
- usd_eur = 1 / EURUSD，与旧 FRED 倒数列一致（外币/1 美元）

禁止把 Aliyun 行 append 进仍是 FRED 广义美元指数的 CSV。
"""
import asyncio
from datetime import date
from typing import Dict, List, Optional, Tuple

import httpx
import pandas as pd

from src.config import get_settings
from src.services.aliyun_comkm import fetch_comkm_klines
from src.utils.logger import setup_logger

logger = setup_logger("exchange_rate_service")
settings = get_settings()


class AliyunFxClient:
    """阿里云 comkm 汇率客户端（每个 symbol 单独翻页）。"""

    def __init__(self, appcode: str, base_url: str):
        self._headers = {"Authorization": f"APPCODE {appcode}"}
        self._base = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AliyunFxClient":
        self._client = httpx.AsyncClient(headers=self._headers, timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_klines(self, symbol: str, since: Optional[date] = None) -> List[dict]:
        if self._client is None:
            raise RuntimeError("AliyunFxClient must be used via 'async with'")
        return await fetch_comkm_klines(
            self._client,
            base_url=self._base,
            symbol=symbol,
            logger=logger,
            since=since,
        )


class ExchangeRateService:
    """4 个汇率/美元指数并发拉取。失败的 series 为空，不抛异常。"""

    @staticmethod
    async def fetch_all(
        start_date: date, end_date: date
    ) -> Dict[str, pd.Series]:
        if not settings.aliyun_api_appcode:
            logger.error("ALIYUN_API_APPCODE 未配置")
            return {}

        names = list(settings.exchange_rate_symbols.keys())

        async def _fetch_one(name: str) -> Tuple[str, pd.Series]:
            sym = settings.exchange_rate_symbols[name]
            try:
                async with AliyunFxClient(
                    settings.aliyun_api_appcode, settings.alirmcom_base_url
                ) as client:
                    records = await client.fetch_klines(sym, since=start_date)
            except Exception as e:
                logger.error(f"aliyun 拉取汇率 {name}({sym}) 失败: {e}")
                return name, pd.Series(dtype="float64")

            if not records:
                return name, pd.Series(dtype="float64")

            df = pd.DataFrame(records).set_index("date").sort_index()
            df = df[~df.index.duplicated(keep="last")]
            mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
            series = df.loc[mask, "close"]
            if series.empty:
                return name, pd.Series(dtype="float64")

            # 与旧 FRED 落盘一致：usd_eur 存「欧元/1 美元」，阿里云 EURUSD 是美元/1 欧元
            if name == "usd_eur":
                series = 1.0 / series
            return name, series

        results = await asyncio.gather(*[_fetch_one(n) for n in names])
        logger.info(f"汇率 comkm 拉取完成: {[(n, len(s)) for n, s in results]}")
        return {name: series for name, series in results}


_exchange_rate_service: Optional[ExchangeRateService] = None


def get_exchange_rate_service() -> ExchangeRateService:
    global _exchange_rate_service
    if _exchange_rate_service is None:
        _exchange_rate_service = ExchangeRateService()
    return _exchange_rate_service
