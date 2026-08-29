"""资金流向服务模块 — 东财沪深港通成交历史（RPT_MUTUAL_DEAL_HISTORY）

北向净买额自 2024-08-16 起交易所停发（BUY_AMT/SELL_AMT/NET_DEAL_AMT 全 null），
但北向成交总额 DEAL_AMT 与南向三列仍每日公布。akshare stock_hsgt_hist_em
与东财同源同 reportName，但其列映射漏掉 DEAL_AMT，故此处直调原始 API。

- MUTUAL_TYPE: 005=北向合计(沪+深), 006=南向合计
- 单位: 原始值百万元，÷100 转亿元（南向为亿港元）
- 增量窗口近 10 个自然日：节假日/断连缺口次日自愈（对齐 baostock 模式）
"""
import pandas as pd
from typing import Dict, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import get_settings
from src.utils.logger import setup_logger

# 东方财富偶发断连/超时：捕获 requests 传输层错误，重试 3 次指数退避
_eastmoney_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    retry=retry_if_exception_type((
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )),
    reraise=True,
)

logger = setup_logger("fund_flow_service")
settings = get_settings()

_EASTMONEY_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 东财列名 → 落库中文列名（单位亿元）
_NORTH_COLS = {"DEAL_AMT": "北向成交额"}
_SOUTH_COLS = {"NET_DEAL_AMT": "南向净流入", "BUY_AMT": "南向买入", "SELL_AMT": "南向卖出"}


def _request(params: dict) -> requests.Response:
    return requests.get(
        _EASTMONEY_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15
    )


class FundFlowService:
    """沪深港通资金服务 — 北向成交额 + 南向净流入/买入/卖出"""

    def __init__(self):
        self.start_date = settings.fund_flow_start_date

    def _fetch_page(self, mutual_type: str, page: int, page_size: int = 500) -> list:
        """拉取一页 RPT_MUTUAL_DEAL_HISTORY，返回行列表（空页 = 翻页终止）"""
        params = {
            "reportName": "RPT_MUTUAL_DEAL_HISTORY",
            "columns": "ALL",
            "filter": f'(MUTUAL_TYPE="{mutual_type}")',
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "1",
        }
        resp = _eastmoney_retry(_request)(params)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("success") is not True and "result" not in payload:
            raise Exception(f"东财接口返回异常: {payload.get('message', 'unknown')}")
        result = payload.get("result") or {}
        return result.get("data") or []

    def _fetch_all_pages(
        self, mutual_type: str, start_date: str, end_date: str, page_size: int = 500
    ) -> list:
        """按 TRADE_DATE 正序翻页拉取，日期过滤在本地做（API filter 不支持日期区间）"""
        rows: list = []
        page = 1
        while True:
            batch = self._fetch_page(mutual_type, page, page_size)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        # 正序拉全量后截区间：start/end 均含端点
        return [
            r for r in rows
            if start_date <= str(r.get("TRADE_DATE", ""))[:10] <= end_date
        ]

    @staticmethod
    def _to_frame(rows: list, col_map: Dict[str, str]) -> pd.DataFrame:
        """东财行 → DataFrame（index=日期，百万元 ÷100 转亿元）"""
        if not rows:
            return pd.DataFrame(columns=list(col_map.values()))
        data = {
            cn: [round(float(r[en]) / 100, 4) if r.get(en) is not None else None for r in rows]
            for en, cn in col_map.items()
        }
        df = pd.DataFrame(data, index=[str(r["TRADE_DATE"])[:10] for r in rows])
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        return df

    def fetch_history(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """全量拉取北向/南向历史（翻页到起始日期）

        Returns:
            {"north": df(北向成交额), "south": df(南向净流入, 南向买入, 南向卖出)}
        """
        start = start_date or self.start_date
        end = end_date or pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
        logger.info(f"获取沪深港通资金历史: {start} ~ {end}")

        north_rows = self._fetch_all_pages("005", start, end)
        south_rows = self._fetch_all_pages("006", start, end)

        result = {
            "north": self._to_frame(north_rows, _NORTH_COLS),
            "south": self._to_frame(south_rows, _SOUTH_COLS),
        }
        logger.info(
            f"成功获取沪深港通资金数据，北向 {len(result['north'])} 条，南向 {len(result['south'])} 条"
        )
        return result

    def fetch_recent(self, days: int = 10) -> Dict[str, pd.DataFrame]:
        """增量窗口：近 N 个自然日（缺口自愈），结构同 fetch_history"""
        end = pd.Timestamp.now().normalize()
        start = (end - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        return self.fetch_history(start, end.strftime("%Y-%m-%d"))


# 创建全局资金流向服务实例
_fund_flow_service: Optional[FundFlowService] = None


def get_fund_flow_service() -> FundFlowService:
    """获取资金流向服务单例"""
    global _fund_flow_service
    if _fund_flow_service is None:
        _fund_flow_service = FundFlowService()
    return _fund_flow_service
