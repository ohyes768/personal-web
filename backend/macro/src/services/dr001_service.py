"""DR001 服务模块 - 从中国货币网获取隔夜质押式回购加权利率

数据源：中国货币网公开历史 CSV（与 DR007 同一文件）
URL: https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv

CSV 列含义（实测 2026-09-15，共 9 列，已与 prr-md.json 当日值交叉验证）：
  0    日期（YYYY-MM-DD）
  1-5  其他盘口字段（本服务不使用）
  6    DR001 加权利率(%)  ← 本服务取这一列
  7    DR007 加权利率(%)  ← dr007_service 取这一列
  8    DR014 加权利率(%)

注意：同文件多产品同源；若货币网调整列位，DR001/DR007 两服务需在同一处修复。
参考：monetary-policy-skill/scripts/fetch_dr007.py（同源 URL），本项目内独立维护以避免跨项目耦合。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.logger import setup_logger

logger = setup_logger("dr001_service")

DR001_CSV_URL = (
    "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(DEFAULT_HEADERS)

    @staticmethod
    def parse_csv(csv_text: str) -> pd.DataFrame:
        """解析中国货币网 prr-chrt.csv，取 DR001 列（index 6）。

        返回 DataFrame：`columns = ["date", "dr001"]`，按日期升序排列。
        列数不足 9 列（含老格式行——不猜测列位）、或第 7 列（index 6）
        非 float 的行直接跳过。空输入返回空 DataFrame（保留列结构）。
        """
        df = pd.DataFrame(columns=["date", "dr001"])
        if not csv_text or not csv_text.strip():
            return df

        rows: list[tuple[pd.Timestamp, float]] = []
        seen: set[str] = set()
        for raw_line in csv_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            cols = line.split(",")
            if len(cols) < 9:
                continue
            date_str = cols[0].strip()[:10]
            if not date_str or date_str in seen:
                continue
            try:
                value = float(cols[6])
                ts = pd.Timestamp(date_str)
            except (ValueError, TypeError):
                continue
            rows.append((ts, value))
            seen.add(date_str)

        if not rows:
            return df
        out = pd.DataFrame(rows, columns=["date", "dr001"])
        return out.sort_values("date").reset_index(drop=True)

    def fetch_csv_text(self, timeout: int = 20) -> str:
        """拉取最新 CSV 文本。失败抛 requests.HTTPError。"""
        response = self.session.get(DR001_CSV_URL, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = "utf-8"
        return response.text

    async def fetch_history(
        self, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """拉取 [start_date, end_date] 区间的历史 DR001。

        中国货币网 CSV 是一个滚动序列（每月追加新交易日，旧日期持续存在），
        一次拉取覆盖全量历史，直接筛区间即可。
        """
        logger.info(f"获取 DR001 数据: 从 {start_date} 到 {end_date}")
        csv_text = self.fetch_csv_text()
        df = self.parse_csv(csv_text)
        if df.empty:
            logger.warning("DR001 返回数据为空")
            return df
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        filtered = df.loc[mask].reset_index(drop=True)
        logger.info(f"DR001 区间内共 {len(filtered)} 条记录")
        return filtered

    async def fetch_latest(
        self, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """拉取最新一段 DR001（增量更新场景：start_date = CSV 最后一行的下一天）。"""
        return await self.fetch_history(start_date, end_date)


# 全局单例
_dr001_service: Optional[DR001Service] = None


def get_dr001_service() -> DR001Service:
    global _dr001_service
    if _dr001_service is None:
        _dr001_service = DR001Service()
    return _dr001_service
