"""
基金经理数据源（经理维度评价，任务 11-10-fund-manager-evaluation）

与既有 manager_fetcher（基金维度的 mgr_* 附带字段）分离：
- manager_table_fetcher：全市场经理表，**保留东财经理 ID**（akshare 封装丢弃了它）
- manager_profile_fetcher：经理档案页 → 历任基金明细（含已离任）
- manager_nav_fetcher：pingzhongdata → 复权净值序列（算收益/回撤专用）

口径陷阱（实测，见任务 design.md §8）：
- 档案页 UTF-8 带 BOM，requests.text 默认 ISO-8859-1 解码会把「年/天」变乱码
- 「累计净值」不复权，算收益必须用 equityReturn 连乘
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from akshare.utils import demjson

DATA_URL = "https://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx"
PROFILE_URL = "https://fund.eastmoney.com/manager/{manager_id}.html"
PINGZHONG_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://fund.eastmoney.com/manager/default.html",
}
PAGE_SIZE = 500
REQUEST_DELAY_S = 0.3
MAX_RETRIES = 3


def _get_with_retry(url: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    """带指数退避重试的 GET。全部失败抛最后一个异常。"""
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(REQUEST_DELAY_S * (2 ** attempt))
    raise last  # type: ignore[misc]


def fetch_manager_table_with_id() -> list[dict[str, Any]]:
    """全市场经理表（含东财经理 ID）。

    dt=14 返回 12 列（实测）：
      [0]经理ID [1]姓名 [2]_ [3]所属公司 [4]现任基金代码 [5]现任基金
      [6]累计从业时间(天) [7]现任基金最佳回报 [8]_ [9]_ [10]现任规模 [11]_

    Returns:
        [{"manager_id", "name", "company", "fund_codes": list[str],
          "career_days": int, "best_return_pct": float|None,
          "current_scale_yi": float|None}, ...]
    """
    first = _get_with_retry(DATA_URL, params={
        "dt": "14", "mc": "returnjson", "ft": "all",
        "pn": str(PAGE_SIZE), "pi": "1", "sc": "abbname", "st": "asc",
    })
    payload = demjson.decode(first.text.strip().strip("var returnjson= "))
    total_pages = int(payload.get("pages", 1))
    rows: list[list] = list(payload["data"])

    for page in range(2, total_pages + 1):
        time.sleep(REQUEST_DELAY_S)
        resp = _get_with_retry(DATA_URL, params={
            "dt": "14", "mc": "returnjson", "ft": "all",
            "pn": str(PAGE_SIZE), "pi": str(page), "sc": "abbname", "st": "asc",
        })
        payload = demjson.decode(resp.text.strip().strip("var returnjson= "))
        rows.extend(payload["data"])

    out: list[dict[str, Any]] = []
    for r in rows:
        if len(r) < 11 or not r[0]:
            continue
        out.append({
            "manager_id": str(r[0]),
            "name": str(r[1]).strip(),
            "company": str(r[3]).strip(),
            "fund_codes": [c.strip().zfill(6) for c in str(r[4]).split(",") if c.strip()],
            "career_days": int(r[6]) if r[6] not in (None, "") else None,
            "best_return_pct": _to_float(str(r[7]).replace("%", "")) if r[7] else None,
            "current_scale_yi": _to_float(str(r[10]).replace("亿元", "")) if r[10] else None,
        })
    return out


def fetch_manager_tenures(manager_id: str) -> list[dict[str, Any]]:
    """经理档案页 → 历任基金明细（含已离任）。

    历任表是 <body> 后第 2 个 <table>，列序（实测）：
      代码 | 名称 | 链接 | 类型 | 规模(亿) | 任职时间 | 任职天数 | 任职回报

    Returns:
        [{"fund_code", "fund_name", "fund_type", "size_yi",
          "start_date": "YYYY-MM-DD"|None, "end_date": "YYYY-MM-DD"|None,
          "tenure_days": int, "tenure_return_pct": float|None, "is_current": bool}, ...]
    """
    resp = _get_with_retry(PROFILE_URL.format(manager_id=manager_id))
    # 关键：显式 utf-8 解码。响应带 BOM，requests.text 会按 ISO-8859-1 把中文变乱码，
    # 导致「7年又56天」解析失败、tenure_days 全 0。
    html = resp.content.decode("utf-8", errors="replace")
    body = html[html.find("<body"):]
    tables = re.findall(r"<table.*?</table>", body, flags=re.S)
    if len(tables) < 2:
        return []

    rows = re.findall(r"<tr.*?</tr>", tables[1], flags=re.S)
    out: list[dict[str, Any]] = []
    for tr in rows[1:]:  # 首行是表头
        cells = [
            re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
            for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", tr, flags=re.S)
        ]
        if len(cells) < 8 or not re.match(r"^\d{6}$", cells[0]):
            continue
        period = cells[5]
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*~\s*(至今|\d{4}-\d{2}-\d{2})$", period)
        start = m.group(1) if m else None
        end_raw = m.group(2) if m else None
        end = None if (end_raw is None or end_raw == "至今") else end_raw
        ret = _to_float(cells[7].replace("%", "").replace(",", ""))
        out.append({
            "fund_code": cells[0],
            "fund_name": cells[1],
            "fund_type": cells[3],
            "size_yi": _to_float(cells[4].replace(",", "")),
            "start_date": start,
            "end_date": end,
            "tenure_days": parse_tenure_days(cells[6]),
            "tenure_return_pct": ret,
            "is_current": end is None,
        })
    return out


def fetch_adjusted_series(code: str) -> list[tuple[str, float]]:
    """pingzhongdata → 复权净值序列（equityReturn 连乘）。

    「累计净值」不复权（分红不再投），直接拿它算收益会把
    富国天惠 161005 的 1500% 算成 462%。equityReturn 是当日复权
    增长率（%），连乘即真实净值曲线（实测 1498.6%，与官方吻合）。

    Returns:
        [("YYYY-MM-DD", adjusted_nav), ...] 首点 nav=1.0
    """
    resp = _get_with_retry(PINGZHONG_URL.format(code=code), timeout=40)
    text = resp.content.decode("utf-8", errors="replace")
    m = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", text, flags=re.S)
    if not m:
        raise ValueError(f"pingzhongdata 无 Data_netWorthTrend: {code}")
    points = json.loads(m.group(1))
    if not points:
        return []

    out: list[tuple[str, float]] = []
    nav = 1.0
    for p in points:
        er = p.get("equityReturn")
        if er is None:
            er = 0.0
        nav *= 1 + float(er) / 100
        out.append((_ms_to_date(p["x"]), round(nav, 6)))
    return out


def parse_tenure_days(text: str) -> int | None:
    """「7年又56天」/「82天」/「1年又48天」 → 天数。空/异常返回 None。"""
    if not text:
        return None
    y = re.search(r"(\d+)\s*年", text)
    d = re.search(r"(\d+)\s*天", text)
    if not y and not d:
        return None
    return (int(y.group(1)) * 365 if y else 0) + (int(d.group(1)) if d else 0)


def _to_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _ms_to_date(ms: int) -> str:
    from datetime import datetime, timezone, timedelta
    # 东财净值时间戳是北京时间零点，用 UTC+8 转日期
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d")
