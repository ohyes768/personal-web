"""商品数据服务模块 — 阿里云 alirmcom2 comkm K线接口（黄金/白银/原油/铜）

参考 dividend-select calculator.py 的 comkm 翻页拉取 + index_service.py 同模式：
- 接口: GET /query/comkm?period=D&pidx=N&psize=500&symbol={symbol}&withlast=0
- 认证: Authorization: APPCODE {appcode}
- 响应: {"Code":0, "Msg":"", "Obj":[{"C":close, "O":open, "H":high, "L":low,
                                     "V":volume, "A":amount, "D":"YYYY-MM-DD 00:00:00",
                                     "Tick":unix_ts}, ...]}

策略：
- comkm 是历史 K 线接口（带翻页），4 个商品（黄金/白银/原油/铜）
- 每个 symbol 单独翻页拉取（comkm 不支持批量 symbols=...，只能 pidx 翻页）
- 4 个 symbol 用 asyncio.gather 并发，错误隔离（一个失败不影响其他）
- 返回按 date 升序的 Series（应用 commodity_units factor 换算到展示单位）
- 后端 routes 在 fetch/commodities/history 时全量写入 commodities.csv，
  update/commodities 时增量追加
- 翻页实现见 aliyun_comkm.fetch_comkm_klines：增量传 since=start_date，第 1 页覆盖即停
"""
import asyncio
from datetime import date
from typing import Dict, List, Optional, Tuple

import httpx
import pandas as pd

from src.config import get_settings
from src.services.aliyun_comkm import fetch_comkm_klines
from src.utils.logger import setup_logger

logger = setup_logger("commodity_service")
settings = get_settings()


class AliyunCommodityKlineClient:
    """阿里云 alirmcom2 商品客户端（基于 comkm 历史 K线接口）

    comkm 不支持批量 symbols，所以每个 symbol 单独拉取+翻页
    （镜像 index_service.AliyunIndexClient 模式）
    """

    def __init__(self, appcode: str, base_url: str):
        self._headers = {"Authorization": f"APPCODE {appcode}"}
        self._base = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AliyunCommodityKlineClient":
        self._client = httpx.AsyncClient(headers=self._headers, timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_klines(self, symbol: str, since: Optional[date] = None) -> List[dict]:
        """拉取单个 symbol 日 K（翻页累加，返回升序）。since 用于增量提前停。"""
        if self._client is None:
            raise RuntimeError("AliyunCommodityKlineClient must be used via 'async with'")
        return await fetch_comkm_klines(
            self._client,
            base_url=self._base,
            symbol=symbol,
            logger=logger,
            since=since,
        )


class CommodityService:
    """4 个商品并发拉取服务 — 阿里云 comkm K 线 + 服务端单位换算

    对比 index_service 的差异：
    - 4 commodity code vs 5 index code（都用 asyncio.gather）
    - 增加单位换算（apply settings.commodity_units[name].factor）
    - 增加首行 sanity check，超出范围 log warn（不抛异常）
    """

    @staticmethod
    async def fetch_all(
        start_date: date, end_date: date
    ) -> Dict[str, pd.Series]:
        """并发拉 4 个商品日 K 线，应用单位换算 + sanity check 后返回

        Args:
            start_date: 起始日期（含）
            end_date: 结束日期（含）

        Returns:
            {gold: Series(date->close 元/克), silver: Series 元/克,
             oil: Series $/桶, copper: Series $/吨}
            Series.index 是 date（Timestamp），values 是 close（float，已换算到展示单位）
            失败的 symbol 对应空 Series（不抛异常）
        """
        if not settings.aliyun_api_appcode:
            logger.error("ALIYUN_API_APPCODE 未配置")
            return {}

        names = ["gold", "silver", "oil", "copper"]

        async def _fetch_one(name: str) -> Tuple[str, pd.Series]:
            sym = settings.commodity_symbols.get(name)
            if not sym:
                logger.error(f"未知商品: {name}")
                return name, pd.Series(dtype="float64")

            unit_cfg = settings.commodity_units.get(name, {"factor": 1.0, "display": ""})
            factor: float = unit_cfg.get("factor", 1.0)
            display_unit: str = unit_cfg.get("display", "")

            try:
                async with AliyunCommodityKlineClient(
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
            series = df.loc[mask, "close"]

            if series.empty:
                return name, pd.Series(dtype="float64")

            # 应用单位换算（gold/oil factor=1.0 恒等，silver/copper 实际换算）
            if factor != 1.0:
                series = series * factor
                logger.info(
                    f"商品 {name} 单位换算: factor={factor}, "
                    f"raw 首行={df.loc[mask, 'close'].iloc[0]:.4f} → "
                    f"换算后={series.iloc[0]:.4f} {display_unit}"
                )

            # sanity check：用首行 close 看是否在合理范围
            sanity = settings.commodity_sanity_range.get(name)
            if sanity:
                lo, hi = sanity
                first_val = float(series.iloc[0])
                if not (lo <= first_val <= hi):
                    logger.warning(
                        f"⚠️ 商品 {name} 首行 close={first_val:.4f} {display_unit} "
                        f"超出预期范围 [{lo}, {hi}]，请检查单位口径（factor={factor}）"
                    )

            return name, series

        results = await asyncio.gather(*[_fetch_one(n) for n in names])
        logger.info(f"4 个商品并发拉取完成: {[(n, len(s)) for n, s in results]}")
        return {name: series for name, series in results}


# 全局单例
_commodity_service: Optional[CommodityService] = None


def get_commodity_service() -> CommodityService:
    """获取商品服务单例"""
    global _commodity_service
    if _commodity_service is None:
        _commodity_service = CommodityService()
    return _commodity_service
