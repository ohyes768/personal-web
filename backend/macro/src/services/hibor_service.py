"""HIBOR 服务模块 - 调用 akshare 东方财富公开数据获取隔夜拆息数据"""
import asyncio
import pandas as pd
from typing import Optional

from src.utils.logger import setup_logger
from src.utils.retry import async_retry

logger = setup_logger("hibor_service")

# akshare rate_interbank 参数固定值
_AKSHARE_MARKET = "香港银行同业拆借市场"
_AKSHARE_SYMBOL = "Hibor港币"  # 注意:akshare 中为「港币」非「港元」
_AKSHARE_INDICATOR = "隔夜"


class HIBORService:
    """HIBOR 隔夜拆息服务类

    数据源:akshare.rate_interbank(东方财富源)
    字段:hibor_overnight(隔夜拆息,年化百分比)
    频率:每个香港交易日
    """

    def __init__(self) -> None:
        """初始化 HIBOR 服务"""
        pass

    @async_retry(max_retries=3, delay=1.0)
    async def fetch_series(
        self,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.Series:
        """获取 HIBOR 隔夜数据

        Args:
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            日期索引的 Series(值为 hibor_overnight 百分比,name 字段为 'hibor_overnight')
        """
        logger.info(
            f"获取 HIBOR 数据:从 {start_date} 到 {end_date}(akshare {_AKSHARE_SYMBOL})"
        )

        # akshare 同步函数,放线程池中执行以保留 fetch_series 的 async 签名
        df = await asyncio.to_thread(
            self._fetch_raw_df,
        )

        if df.empty:
            logger.warning("HIBOR 返回数据为空")
            return pd.Series(dtype="float64")

        # _fetch_raw_df 已 set_index('end_of_date'),以索引做日期过滤
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        if df.empty:
            logger.warning(
                f"HIBOR 在区间 [{start_date}, {end_date}] 内无数据"
            )
            return pd.Series(dtype="float64")

        series = df["hibor_overnight"]
        series.name = "hibor_overnight"

        logger.info(f"成功获取 HIBOR 数据,共 {len(series)} 条记录")
        return series

    @staticmethod
    def _fetch_raw_df() -> pd.DataFrame:
        """同步调用 akshare.rate_interbank 并规范化为 (index=end_of_date, col=hibor_overnight)。

        akshare 返回中文列名:[报告日, 利率, 涨跌],只保留前两列。
        """
        import akshare as ak  # 局部导入,允许测试时无 akshare 环境

        raw = ak.rate_interbank(
            market=_AKSHARE_MARKET,
            symbol=_AKSHARE_SYMBOL,
            indicator=_AKSHARE_INDICATOR,
        )
        if raw is None or raw.empty:
            return pd.DataFrame()

        df = raw.iloc[:, :2].copy()
        df.columns = ["end_of_date", "hibor_overnight"]
        df["end_of_date"] = pd.to_datetime(df["end_of_date"], errors="coerce")
        df["hibor_overnight"] = pd.to_numeric(
            df["hibor_overnight"], errors="coerce"
        )
        df = df.dropna(subset=["end_of_date", "hibor_overnight"])
        df = df.set_index("end_of_date").sort_index()
        return df


# 创建全局 HIBOR 服务实例
_hibor_service: Optional[HIBORService] = None


def get_hibor_service() -> HIBORService:
    """获取 HIBOR 服务单例

    Returns:
        HIBOR 服务实例
    """
    global _hibor_service
    if _hibor_service is None:
        _hibor_service = HIBORService()
    return _hibor_service
