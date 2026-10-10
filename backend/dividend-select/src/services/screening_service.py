"""Evaluate collected stocks without filtering away failed or incomplete rows."""
import math
import re

from src.api.models import DividendStock, ScreeningItem, ScreeningRequest

DIVIDEND_YEARS = (2023, 2024, 2025)


def adjacent_quarters(previous: str | None, latest: str | None) -> bool:
    labels = [re.fullmatch(r"(\d{4})Q([1-4])", label or "") for label in (previous, latest)]
    if not all(labels):
        return False
    indexes = [int(label[1]) * 4 + int(label[2]) for label in labels]
    return indexes[1] - indexes[0] == 1


def evaluate_stock(stock: DividendStock, conditions: ScreeningRequest) -> ScreeningItem:
    failures, missing, warnings = [], [], []

    def check(value: float | None, threshold: float, title: str):
        if value is None or not math.isfinite(value):
            missing.append(f"{title}缺失")
        elif value < threshold:
            failures.append(f"{title}低于 {threshold:g}%")

    check(stock.avg_yield_3y, conditions.min_yield, "近三年平均股息率")
    for year in DIVIDEND_YEARS:
        value = getattr(stock, f"dividend_{year}")
        if value is None or not math.isfinite(value):
            missing.append(f"{year} 年分红数据缺失")
        elif value <= 0:
            failures.append(f"{year} 年未分红")
    check(stock.roe, conditions.min_roe, "最近年度 ROE")
    check(stock.roe_avg_3y, conditions.min_roe_avg_3y, "近三年平均 ROE")
    history = {item.year: item.value for item in stock.roe_history}
    if stock.roe_year is None or any(
        history.get(year) is None or not math.isfinite(history[year])
        for year in range((stock.roe_year or 0) - 2, (stock.roe_year or 0) + 1)
    ):
        missing.append("连续三年年度 ROE 数据缺失")
    annual_title = f"{stock.annual_profit_year} 年扣非净利润" if stock.annual_profit_year else "最近年度扣非净利润"
    annual_profit = stock.annual_net_profit_ex_non_recurring
    if annual_profit is None or not math.isfinite(annual_profit):
        missing.append(f"{annual_title}缺失")
    elif annual_profit <= 0:
        failures.append(f"{annual_title}必须大于 0 元")
    if stock.annual_profit_year is None:
        missing.append("年度扣非净利润报告年度缺失")
    check(stock.net_profit_ex_non_recurring_yoy, 0, "最近年度扣非利润同比")
    latest, previous = stock.latest_quarter_yoy_pct, stock.previous_quarter_yoy_pct
    for value, label in ((previous, stock.previous_quarter_label), (latest, stock.latest_quarter_label)):
        if (adjacent_quarters(stock.previous_quarter_label, stock.latest_quarter_label)
                and value is not None and math.isfinite(value)
                and value <= -conditions.max_quarter_profit_decline_pct):
            failures.append(f"{label or '季度未知'} 单季扣非利润同比 {value:g}%，达到最大降幅 {conditions.max_quarter_profit_decline_pct:g}%（同比 ≤ -{conditions.max_quarter_profit_decline_pct:g}%）")
    if (latest is None or previous is None or not math.isfinite(latest)
            or not math.isfinite(previous)
            or not adjacent_quarters(stock.previous_quarter_label, stock.latest_quarter_label)):
        missing.append("连续两个相邻季度扣非同比数据缺失")
    elif latest < 0 and previous < 0:
        failures.append("连续两个季度扣非利润同比下降")
    elif (latest < 0 or previous < 0) and min(latest, previous) > -conditions.max_quarter_profit_decline_pct:
        warnings.append("一个季度扣非利润同比下降，建议持续关注")
    status = "excluded" if failures else "insufficient_data" if missing else "eligible"
    return ScreeningItem(stock=stock, status=status, reasons=failures + missing, warnings=warnings)
