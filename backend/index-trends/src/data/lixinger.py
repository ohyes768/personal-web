"""理杏仁（lixinger）指数基本面适配层。

只取沪深300 的 PE-TTM（总市值加权）与近 10 年分位，直接使用供应商统计值，
不在本地重新计算分位。

供应商契约（官方文档 2026-11-02 核实）：
- POST https://open.lixinger.com/api/cn/index/fundamental
- 请求体：stockCodes / metricsList / startDate / endDate / token
- 成功响应：{"code":1,"data":[{"stockCode":"000300","date":"...+08:00","pe_ttm.mcw":12.3,"pe_ttm.y10.mcw.cvpos":0.56}]}
- 指标字段是**平铺的带点号键**，不是嵌套对象；cvpos 原值为 0–1 的比例。

本模块只做请求与严格解析，不含缓存、状态判定与日期语义（见 src/services/valuation_service.py）。
错误一律用固定 reason 码 + 脱敏说明，禁止回显供应商正文、请求体与 Token。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import httpx

LIXINGER_FUNDAMENTAL_URL = "https://open.lixinger.com/api/cn/index/fundamental"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) index-trends/0.1"
REQUEST_TIMEOUT = 10.0

# PE-TTM（总市值加权）
METRIC_PE_TTM = "pe_ttm.mcw"
# PE-TTM 近 10 年分位（0–1 的比例）
METRIC_CVPOS = "pe_ttm.y10.mcw.cvpos"
METRICS: tuple[str, ...] = (METRIC_PE_TTM, METRIC_CVPOS)

# 分位窗口口径（展示用，供应商固定为近 10 年）
VALUATION_WINDOW = "y10"
VALUATION_SOURCE = "lixinger"
VALUATION_METRIC = "pe_ttm_mcw"

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# 回看窗口：覆盖目标日前 30 个日历日，用于识别供应商更新滞后
LOOKBACK_DAYS = 30


class LixingerError(RuntimeError):
    """供应商请求或响应异常。

    reason 是稳定的机器可读码（对外只暴露这个与脱敏 message）；
    message 不得包含 Token、请求体或供应商正文。
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ValuationPoint:
    """一条合格估值记录。

    date 为北京时间自然日；percentile_ratio 为供应商原始比例（0–1）。
    """

    date: str
    pe_ttm: float
    percentile_ratio: float


def new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        follow_redirects=True,
    )


def _beijing_date(raw: Any) -> str | None:
    """把供应商时间戳规范化成北京时间自然日。

    官方返回带 +08:00 的 ISO 时间；无时区的时间按北京时间解释。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(SHANGHAI_TZ).date().isoformat()


def _positive_number(raw: Any) -> float | None:
    """接受有限正数；拒绝 bool、NaN、Infinity 与非数值。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _ratio(raw: Any) -> float | None:
    """接受 [0,1] 的有限比例；拒绝 bool、NaN、越界值。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0 or value > 1:
        return None
    return value


def parse_fundamental(
    body: Any,
    stock_code: str,
    end_date: str,
) -> list[ValuationPoint]:
    """解析并校验供应商响应，返回合格记录（不保证顺序）。

    - 业务 code 必须为 1；data 必须是数组。
    - 逐条校验：指数代码一致、日期可解析且不晚于 end_date、字段存在、数值合法。
    - 不合格的记录被跳过；一条合格记录都没有时视为响应异常。
    """
    if not isinstance(body, dict):
        raise LixingerError("invalid_response", "理杏仁响应结构异常")
    code = body.get("code")
    if code != 1:
        # 只暴露业务码，不回显 msg（可能包含供应商内部信息）
        raise LixingerError("upstream_error", f"理杏仁返回业务码 {code}")
    data = body.get("data")
    if data is None:
        raise LixingerError("invalid_response", "理杏仁响应缺少 data")
    if not isinstance(data, list):
        raise LixingerError("invalid_response", "理杏仁响应 data 结构异常")
    if not data:
        return []

    points: list[ValuationPoint] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("stockCode")) != stock_code:
            continue
        day = _beijing_date(row.get("date"))
        if day is None or day > end_date:
            continue  # 未来或不可解析的记录直接丢弃
        pe = _positive_number(row.get(METRIC_PE_TTM))
        ratio = _ratio(row.get(METRIC_CVPOS))
        if pe is None or ratio is None:
            continue
        points.append(ValuationPoint(date=day, pe_ttm=pe, percentile_ratio=ratio))

    if not points:
        raise LixingerError("invalid_data", "理杏仁响应没有合格记录")
    return points


def fetch_fundamental(
    client: httpx.Client,
    token: str,
    stock_code: str,
    end_date: str,
    start_date: str | None = None,
    metrics: Sequence[str] = METRICS,
) -> list[ValuationPoint]:
    """请求指数基本面并返回合格记录。

    显式给出 startDate/endDate（不依赖供应商默认 endDate——官方默认是上周一），
    回看 30 个日历日用于识别更新滞后。
    """
    if not token:
        raise LixingerError("token_not_configured", "未配置理杏仁访问令牌")
    end = date.fromisoformat(end_date)
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=LOOKBACK_DAYS)
    if start > end:
        raise LixingerError("invalid_request", "理杏仁请求区间非法")
    payload = {
        "stockCodes": [stock_code],
        "metricsList": list(metrics),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "token": token,
    }
    try:
        resp = client.post(LIXINGER_FUNDAMENTAL_URL, json=payload)
    except httpx.HTTPError as exc:
        raise LixingerError("network_error", f"理杏仁请求失败: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise LixingerError("http_error", f"理杏仁 HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise LixingerError("invalid_response", "理杏仁响应非 JSON") from exc
    return parse_fundamental(body, stock_code, end.isoformat())


def latest_qualified(points: Sequence[ValuationPoint], end_date: str) -> ValuationPoint | None:
    """挑选日期最新且不晚于 end_date 的合格记录（不假设供应商已排序）。"""
    candidates = [p for p in points if p.date <= end_date]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.date)
