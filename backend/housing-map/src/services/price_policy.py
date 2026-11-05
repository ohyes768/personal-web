"""价格时效政策（11-04-housing-price-freshness）

统一三件事, 供 data_loader / 后续采集刷新批次共用:
1. "今天"一律指上海时区当前日期, 测试可注入固定日期。
2. 成交月份有效性: 价格所属月份距当前上海月份不超过 6 个月为有效
   （恰好 6 个月有效, 7 个月过期）, 按当前日期实时判断, 允许记录自然过期。
3. 采集陈旧提示: 距成功采集日超过 30 天提示"超过30天未更新",
   与月度有效期分别计算, 互不替代。

双价投影（project_price_record）把一条 JSONL 价格记录归一化为
deal / listing / 过期历史条目。纯函数, 无 IO、无全局状态。
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MAX_DEAL_AGE_MONTHS = 6  # 恰好 6 个月仍有效, 7 个月过期
STALE_AFTER_DAYS = 30    # 超过 30 天未成功更新提示陈旧（恰好 30 天不算）

PRICE_KIND_DEAL = "monthly_deal_avg_latest"
PRICE_KIND_LISTING = "listing_avg"
# 只带套数、不带价格的快照（抓到首页但无任何价格）: 不冒充价格更新（R3）
PRICE_KIND_COUNTS = "counts_only"


def shanghai_today(today: dt.date | None = None) -> dt.date:
    """注入日期优先; 否则返回上海时区今天。"""
    if today is not None:
        return today
    return dt.datetime.now(SHANGHAI_TZ).date()


def month_gap_from_today(month: str | None, *, today: dt.date | None = None) -> int | None:
    """成交月份 "YYYY-MM" 到当前上海月份的月差; 解析失败或不是月份字符串返回 None。"""
    if not isinstance(month, str) or "-" not in month:
        return None
    parts = month.split("-")
    try:
        year, month_number = int(parts[0]), int(parts[1])
        dt.date(year, month_number, 1)
    except (TypeError, ValueError):
        return None
    current = shanghai_today(today)
    return (current.year - year) * 12 + current.month - month_number


def deal_month_is_current(month: str | None, *, today: dt.date | None = None) -> bool:
    """成交月份是否仍属有效当前价: 月差 0..6 有效; 未来月份/未知/超期一律无效。"""
    gap = month_gap_from_today(month, today=today)
    return gap is not None and 0 <= gap <= MAX_DEAL_AGE_MONTHS


def collection_stale(captured_on: str | None, *, today: dt.date | None = None,
                     max_age_days: int = STALE_AFTER_DAYS) -> bool:
    """采集日距今超过 max_age_days 天为陈旧（恰好当天边界不算）。

    接受 "YYYY-MM-DD" 或 ISO 时间戳（截前 10 位）; 无法判定时不算陈旧, 不编造。
    """
    if not isinstance(captured_on, str) or not captured_on:
        return False
    try:
        captured = dt.date.fromisoformat(captured_on[:10])
    except ValueError:
        return False
    return (shanghai_today(today) - captured).days > max_age_days


def project_price_record(record: dict, *, today: dt.date | None = None) -> dict | None:
    """单条价格记录 → 归一化价格条目; 无可展示价格时返回 None。

    返回形状: {"price", "month", "captured_at", "captured_date", "source_url",
    "stale", "current", "expired"}。data_loader 按 current/expired 分槽:
    - deal: 月份取 raw_payload.tendency.latest_month; 距当前上海月份 <=6 个月为
      current, >6 为 expired 历史; 月份缺失/非法返回 None, 不得用采集日期顶替。
    - listing: 挂牌价没有成交月份概念, month 恒为 None; listing_count 非正视为
      无挂牌, 不产出条目。
    - stale 只反映 30 天采集陈旧, 与月度有效性无关; 不改写价格与采集日期。
    """
    if not isinstance(record, dict):
        return None
    price = record.get("avg_price")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    price_type = record.get("price_type")
    captured_at = record.get("crawled_at") or record.get("snapshot_date") or None
    captured_date = record.get("snapshot_date") or captured_at
    stale = collection_stale(captured_date, today=today)
    entry: dict = {
        "price": price,
        "month": None,
        "captured_at": captured_at,
        "captured_date": captured_date,
        "source_url": record.get("source_url") or None,
        "stale": stale,
        "current": False,
        "expired": False,
    }
    if price_type == PRICE_KIND_DEAL:
        raw = record.get("raw_payload")
        tendency = raw.get("tendency") if isinstance(raw, dict) else None
        month = tendency.get("latest_month") if isinstance(tendency, dict) else None
        gap = month_gap_from_today(month, today=today)
        if gap is None or gap < 0:
            return None
        entry["month"] = month
        entry["current"] = gap <= MAX_DEAL_AGE_MONTHS
        entry["expired"] = gap > MAX_DEAL_AGE_MONTHS
        return entry
    if price_type == PRICE_KIND_LISTING:
        if not record.get("listing_count"):
            return None  # 明确无挂牌, 不产出挂牌价条目
        entry["current"] = True
        return entry
    return None
