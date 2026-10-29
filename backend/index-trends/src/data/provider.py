"""行情数据供应商适配（腾讯财经公开接口）。

主数据：月K（拟合与图形）；日线（最近已完成交易日收盘，用于当前位置与周报）。

腾讯 fqkline 返回行结构为 [日期, 开盘, 收盘, 最高, 最低, 成交量, ...]，
收盘在最高/最低之前，不能按常见 OHLC 顺序解包。
该接口无稳定性承诺：调用方必须处理超时、重试与数据校验。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) index-trends/0.1"
REQUEST_TIMEOUT = 15.0


class ProviderError(RuntimeError):
    """供应商请求或响应异常。"""


@dataclass(frozen=True)
class KlineBar:
    date: str   # YYYY-MM-DD（月K为该月最后交易日）
    open: float
    close: float
    high: float
    low: float


def _parse_rows(rows: object, symbol: str) -> list[KlineBar]:
    if not isinstance(rows, list):
        raise ProviderError(f"{symbol} 行情数据缺失")
    bars: list[KlineBar] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            raise ProviderError(f"{symbol} 行情行结构异常: {row!r}")
        try:
            bars.append(
                KlineBar(
                    date=str(row[0]),
                    open=float(row[1]),
                    close=float(row[2]),   # 注意顺序：收盘在第 3 位
                    high=float(row[3]),
                    low=float(row[4]),
                )
            )
        except (TypeError, ValueError) as e:
            raise ProviderError(f"{symbol} 行情数值解析失败: {row!r}") from e
    return bars


def _extract(data: dict, symbol: str, period: str) -> list[KlineBar]:
    node = data.get(symbol)
    if not isinstance(node, dict):
        raise ProviderError(f"响应缺少 {symbol} 数据节点")
    # qfq 参数下日线键可能为 qfqday，月K为 month/qfqmonth，兼容两种。
    for key in (period, f"qfq{period}"):
        if isinstance(node.get(key), list):
            return _parse_rows(node[key], symbol)
    raise ProviderError(f"响应缺少 {period} 行情键")


def fetch_kline(
    symbol: str,
    period: str,
    count: int,
    client: httpx.Client,
) -> list[KlineBar]:
    """拉取指定周期的K线。period: "month" | "day"。"""
    params = {"param": f"{symbol},{period},,,{count},qfq"}
    try:
        resp = client.get(TENCENT_KLINE_URL, params=params)
    except httpx.HTTPError as e:
        raise ProviderError(f"腾讯行情请求失败: {e}") from e
    if resp.status_code != 200:
        raise ProviderError(f"腾讯行情 HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as e:
        raise ProviderError(f"腾讯行情响应非 JSON: {e}") from e
    if body.get("code") != 0:
        raise ProviderError(f"腾讯行情返回异常: code={body.get('code')} msg={body.get('msg')}")
    return _extract(body.get("data", {}), symbol, period)


def new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    )
