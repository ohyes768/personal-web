"""股指数据服务模块 — 阿里云 alirmcom2 comkm K线接口（5 个全球股指）

参考 dividend-select calculator.py 的 comkm 翻页拉取：
- 接口: GET /query/comkm?period=D&pidx=1&psize=500&symbol=HKHSI&withlast=0
- 认证: Authorization: APPCODE {appcode}
- 响应: {"Code":0, "Msg":"", "Obj":[{"C":close, "O":open, "H":high, "L":low,
                                     "V":volume, "A":amount, "D":"YYYY-MM-DD 00:00:00",
                                     "Tick":unix_ts}, ...]}

策略：
- comkm 是历史 K 线接口（带翻页），5 个全球股指（恒生/上证/标普500/纳指/道指）
- 每个 symbol 单独翻页拉取（comkm 不支持批量 symbols=...，只能 pidx 翻页）
- 5 个 symbol 用 asyncio.gather 并发，错误隔离（一个失败不影响其他）
- 返回按 date 升序的 Series
- 后端 routes 在 fetch/indices/history 时全量写入 indices.csv，update/indices 时增量追加
- 翻页实现见 aliyun_comkm.fetch_comkm_klines：增量传 since=start_date，第 1 页覆盖即停
"""
import asyncio
from datetime import date
from typing import Dict, List, Optional

import httpx
import pandas as pd

from src.config import get_settings
from src.services.aliyun_comkm import fetch_comkm_klines
from src.utils.logger import setup_logger

logger = setup_logger("index_service")
settings = get_settings()


class AliyunIndexClient:
    """阿里云 alirmcom2 股指客户端（基于 comkm 历史 K线接口）

    comkm 不支持批量 symbols，所以每个 symbol 单独拉取+翻页
    """

    def __init__(self, appcode: str, base_url: str):
        self._headers = {"Authorization": f"APPCODE {appcode}"}
        self._base = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AliyunIndexClient":
        self._client = httpx.AsyncClient(headers=self._headers, timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_klines(self, symbol: str, since: Optional[date] = None) -> List[dict]:
        """拉取单个 symbol 日 K（翻页累加，返回升序）。since 用于增量提前停。"""
        if self._client is None:
            raise RuntimeError("AliyunIndexClient must be used via 'async with'")
        return await fetch_comkm_klines(
            self._client,
            base_url=self._base,
            symbol=symbol,
            logger=logger,
            since=since,
        )


class IndexService:
    """5 个全球股指并发拉取服务

    comkm 不支持批量，所以用 asyncio.gather 让 5 个 client 并发拉取（网络 I/O 等待重叠）
    """

    @staticmethod
    async def fetch_all(
        start_date: date, end_date: date
    ) -> Dict[str, pd.Series]:
        """并发拉 5 个指数日 K 线，按日期范围过滤

        Args:
            start_date: 起始日期（含）
            end_date: 结束日期（含）

        Returns:
            {HKHSI: Series, SH000001: Series, SPX: Series, IXIC: Series, DJI: Series}
            Series.index 是 date（Timestamp），values 是 close（float）
            失败的 symbol 对应空 Series（不抛异常）
        """
        if not settings.aliyun_api_appcode:
            logger.error("ALIYUN_API_APPCODE 未配置")
            return {}

        names = list(settings.index_symbols.keys())

        async def _fetch_one(name: str) -> tuple[str, pd.Series]:
            sym = settings.index_symbols[name]
            try:
                async with AliyunIndexClient(
                    settings.aliyun_api_appcode, settings.alirmcom_base_url
                ) as client:
                    records = await client.fetch_klines(sym, since=start_date)
            except Exception as e:
                logger.error(f"aliyun 拉取 {name}({sym}) 失败: {e}")
                return name, pd.Series(dtype="float64")

            if not records:
                return name, pd.Series(dtype="float64")

            df = pd.DataFrame(records).set_index("date").sort_index()
            # 去重（同一日期多次拉取保留最后一次）
            df = df[~df.index.duplicated(keep="last")]
            # 按日期范围过滤
            mask = (df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))
            return name, df.loc[mask, "close"]

        results = await asyncio.gather(*[_fetch_one(n) for n in names])
        logger.info(f"5 个指数并发拉取完成: {[(n, len(s)) for n, s in results]}")
        return {name: series for name, series in results}


# 全局单例
_index_service: Optional[IndexService] = None


def get_index_service() -> IndexService:
    """获取股指服务单例"""
    global _index_service
    if _index_service is None:
        _index_service = IndexService()
    return _index_service
