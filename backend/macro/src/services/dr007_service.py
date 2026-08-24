"""DR007 服务模块 - 从中国货币网获取 7 天质押式回购加权利率

数据源：中国货币网公开历史 CSV
URL: https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv

CSV 列含义（共 8 列）：
  0 日期（YYYY-MM-DD）
  1 加权利率(%)
  2 加权平均(%)
  3 成交笔数
  4 成交量(亿)
  5 卖开利率
  6 买开利率
  7 加权平均(%)  ← 本服务取这一列作为 DR007 收盘利率

参考：monetary-policy-skill/scripts/fetch_dr007.py（同源 URL、同列含义），本项目内独立维护以避免跨项目耦合。
"""
from __future__ import annotations

from io import StringIO
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.logger import setup_logger

logger = setup_logger("dr007_service")

DR007_CSV_URL = (
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


class DR007Service:
    """DR007 7 天质押式回购加权利率服务

    字段：dr007（年化百分比）
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
        """解析中国货币网 prr-chrt.csv。

        返回 DataFrame：`columns = ["date", "dr007"]`，按日期升序排列。
        列数不足 8 列、或第 8 列（index 7）非 float 的行直接跳过。
        空输入返回空 DataFrame（保留列结构）。
        """
        df = pd.DataFrame(columns=["date", "dr007"])
        if not csv_text or not csv_text.strip():
            return df

        rows: list[tuple[pd.Timestamp, float]] = []
        seen: set[str] = set()
        for raw_line in csv_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            cols = line.split(",")
            if len(cols) < 8:
                continue
            date_str = cols[0].strip()[:10]
            if not date_str or date_str in seen:
                continue
            try:
                value = float(cols[7])
                ts = pd.Timestamp(date_str)
            except (ValueError, TypeError):
                continue
            rows.append((ts, value))
            seen.add(date_str)

        if not rows:
            return df
        out = pd.DataFrame(rows, columns=["date", "dr007"])
        return out.sort_values("date").reset_index(drop=True)

    def fetch_csv_text(self, timeout: int = 20) -> str:
        """拉取最新 CSV 文本。失败抛 requests.HTTPError。"""
        response = self.session.get(DR007_CSV_URL, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = "utf-8"
        return response.text

    async def fetch_history(
        self, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """拉取 [start_date, end_date] 区间的历史 DR007。

        中国货币网 CSV 是一个滚动序列（每月追加新交易日，旧日期持续存在），
        一次拉取覆盖全量历史，直接筛区间即可。
        """
        logger.info(f"获取 DR007 数据: 从 {start_date} 到 {end_date}")
        csv_text = self.fetch_csv_text()
        df = self.parse_csv(csv_text)
        if df.empty:
            logger.warning("DR007 返回数据为空")
            return df
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        filtered = df.loc[mask].reset_index(drop=True)
        logger.info(f"DR007 区间内共 {len(filtered)} 条记录")
        return filtered

    async def fetch_latest(
        self, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """拉取最新一段 DR007（增量更新场景：start_date = CSV 最后一行的下一天）。"""
        return await self.fetch_history(start_date, end_date)


# 全局单例
_dr007_service: Optional[DR007Service] = None


def get_dr007_service() -> DR007Service:
    global _dr007_service
    if _dr007_service is None:
        _dr007_service = DR007Service()
    return _dr007_service