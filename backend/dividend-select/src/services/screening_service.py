"""Evaluate collected stocks without filtering away failed or incomplete rows.

判定只有一份实现：`build_checks` 逐条产出条件判定，`evaluate_stock` 由这些判定派生
状态与原因文案。这样列表页的「未符合原因」与阅读页的「筛选条件复核」永远同源，
不会出现两套规则算出不同结论的情况。
"""
import math
import re

from src.api.models import DividendStock, ScreeningCheck, ScreeningItem, ScreeningRequest

DIVIDEND_YEARS = (2023, 2024, 2025)


def adjacent_quarters(previous: str | None, latest: str | None) -> bool:
    labels = [re.fullmatch(r"(\d{4})Q([1-4])", label or "") for label in (previous, latest)]
    if not all(labels):
        return False
    indexes = [int(label[1]) * 4 + int(label[2]) for label in labels]
    return indexes[1] - indexes[0] == 1


def _finite(value) -> bool:
    return value is not None and math.isfinite(value)


def _pct(value: float) -> str:
    return f"{value:.2f}%"


def _threshold_check(value, threshold: float, title: str, key: str, label: str) -> ScreeningCheck:
    """数值门槛判定：缺失 → missing，低于门槛 → fail，其余 pass"""
    threshold_text = f"≥ {threshold:g}%"
    if not _finite(value):
        return ScreeningCheck(
            key=key, label=label, result="missing", value_text="待补", threshold_text=threshold_text,
            detail="缺数据，刷新财务指标后复核", reason=f"{title}缺失",
        )
    if value < threshold:
        return ScreeningCheck(
            key=key, label=label, result="fail", value_text=_pct(value), threshold_text=threshold_text,
            detail=f"低于门槛 {threshold:g}%，需复核", reason=f"{title}低于 {threshold:g}%",
        )
    return ScreeningCheck(
        key=key, label=label, result="pass", value_text=_pct(value), threshold_text=threshold_text,
    )


def build_checks(stock: DividendStock, conditions: ScreeningRequest) -> list[ScreeningCheck]:
    """逐条产出筛选条件判定（阅读页「筛选条件复核」展示用）"""
    checks: list[ScreeningCheck] = []

    # 可调门槛：近三年平均股息率
    checks.append(_threshold_check(
        stock.avg_yield_3y, conditions.min_yield, "近三年平均股息率", "yield_3y", "近三年平均股息率"))

    # 固定条件：近三年每年分红（分红窗口固定 2023–2025）
    for year in DIVIDEND_YEARS:
        value = getattr(stock, f"dividend_{year}")
        if not _finite(value):
            checks.append(ScreeningCheck(
                key=f"dividend_{year}", label=f"{year} 年分红", result="missing", value_text="待补",
                threshold_text="有分红（> 0）", detail="分红数据缺失，刷新后复核",
                reason=f"{year} 年分红数据缺失",
            ))
        elif value <= 0:
            checks.append(ScreeningCheck(
                key=f"dividend_{year}", label=f"{year} 年分红", result="fail", value_text="0 元",
                threshold_text="有分红（> 0）", detail="当年未分红，需复核",
                reason=f"{year} 年未分红",
            ))
        else:
            checks.append(ScreeningCheck(
                key=f"dividend_{year}", label=f"{year} 年分红", result="pass", value_text=f"{value:.3f} 元",
                threshold_text="有分红（> 0）",
            ))

    # 可调门槛：ROE
    checks.append(_threshold_check(
        stock.roe, conditions.min_roe, "最近年度 ROE", "roe", "最近年度 ROE"))
    checks.append(_threshold_check(
        stock.roe_avg_3y, conditions.min_roe_avg_3y, "近三年平均 ROE", "roe_avg_3y", "近三年平均 ROE"))

    # 固定条件：连续三年年度 ROE 完整
    history = {item.year: item.value for item in stock.roe_history}
    if stock.roe_year is None:
        checks.append(ScreeningCheck(
            key="roe_history", label="连续三年年度 ROE", result="missing", value_text="待补",
            threshold_text="最近年报及前两年均有值", detail="缺年度 ROE，刷新后复核",
            reason="连续三年年度 ROE 数据缺失",
        ))
    else:
        years = range(stock.roe_year - 2, stock.roe_year + 1)
        missing_years = [year for year in years if not _finite(history.get(year))]
        if missing_years:
            checks.append(ScreeningCheck(
                key="roe_history", label="连续三年年度 ROE", result="missing",
                value_text="缺 " + "、".join(str(year) for year in missing_years),
                threshold_text="最近年报及前两年均有值", detail="年度 ROE 缺失，刷新后复核",
                reason="连续三年年度 ROE 数据缺失",
            ))
        else:
            checks.append(ScreeningCheck(
                key="roe_history", label="连续三年年度 ROE", result="pass",
                value_text="、".join(str(year) for year in years), threshold_text="最近年报及前两年均有值",
            ))

    # 固定条件：最近年度扣非净利润 > 0
    annual_title = f"{stock.annual_profit_year} 年扣非净利润" if stock.annual_profit_year else "最近年度扣非净利润"
    annual_profit = stock.annual_net_profit_ex_non_recurring
    if not _finite(annual_profit):
        checks.append(ScreeningCheck(
            key="annual_profit", label="最近年度扣非净利润", result="missing", value_text="待补",
            threshold_text="> 0 元", detail="年度扣非净利润缺失，刷新后复核",
            reason=f"{annual_title}缺失",
        ))
    elif annual_profit <= 0:
        checks.append(ScreeningCheck(
            key="annual_profit", label="最近年度扣非净利润", result="fail", value_text=f"{annual_profit / 1e8:.2f} 亿元",
            threshold_text="> 0 元", detail="年度扣非净利润不为正，需复核",
            reason=f"{annual_title}必须大于 0 元",
        ))
    else:
        checks.append(ScreeningCheck(
            key="annual_profit", label="最近年度扣非净利润", result="pass",
            value_text=f"{annual_profit / 1e8:.2f} 亿元", threshold_text="> 0 元",
            detail=f"{stock.annual_profit_year} 年报" if stock.annual_profit_year else "",
        ))

    # 固定条件：扣非净利润报告年度存在
    if stock.annual_profit_year is None:
        checks.append(ScreeningCheck(
            key="annual_profit_year", label="扣非净利润报告年度", result="missing", value_text="待补",
            threshold_text="有年度口径", detail="缺报告年度，刷新后复核",
            reason="年度扣非净利润报告年度缺失",
        ))
    else:
        checks.append(ScreeningCheck(
            key="annual_profit_year", label="扣非净利润报告年度", result="pass",
            value_text=f"{stock.annual_profit_year} 年报", threshold_text="有年度口径",
        ))

    # 固定条件：最近年度扣非同比 >= 0
    checks.append(_threshold_check(
        stock.net_profit_ex_non_recurring_yoy, 0, "最近年度扣非利润同比",
        "annual_yoy", "最近年度扣非同比"))

    # 可调门槛：扣非净利润 3 年复合增长率（算不出来只提示，不排除）
    cagr_3y = stock.net_profit_cagr_3y
    cagr_threshold_text = f"≥ {conditions.min_cagr_3y:g}%"
    if not _finite(cagr_3y):
        checks.append(ScreeningCheck(
            key="cagr_3y", label="扣非净利润 3 年复合增长率", result="warn", value_text="不可计算",
            threshold_text=cagr_threshold_text, detail="近三年存在亏损或数据不足，未参与该条件判定",
            warning="扣非净利润3年复合增长率不可计算（近三年存在亏损或数据不足），未参与该条件判定",
        ))
    elif cagr_3y < conditions.min_cagr_3y:
        checks.append(ScreeningCheck(
            key="cagr_3y", label="扣非净利润 3 年复合增长率", result="fail", value_text=_pct(cagr_3y),
            threshold_text=cagr_threshold_text, detail=f"低于门槛 {conditions.min_cagr_3y:g}%，需复核",
            reason=f"扣非净利润3年复合增长率 {cagr_3y:g}% 低于 {conditions.min_cagr_3y:g}%",
        ))
    else:
        checks.append(ScreeningCheck(
            key="cagr_3y", label="扣非净利润 3 年复合增长率", result="pass", value_text=_pct(cagr_3y),
            threshold_text=cagr_threshold_text,
        ))

    # 单季扣非同比：最大降幅规则 + 不得连续两季为负
    latest, previous = stock.latest_quarter_yoy_pct, stock.previous_quarter_yoy_pct
    adjacent = adjacent_quarters(stock.previous_quarter_label, stock.latest_quarter_label)
    pair_ready = adjacent and _finite(latest) and _finite(previous)
    quarter_text = "；".join(
        f"{label or '季度未知'} {value:g}%"
        for label, value in ((stock.previous_quarter_label, previous), (stock.latest_quarter_label, latest))
        if _finite(value)
    ) or "待补"
    decline_threshold_text = f"单季同比不低于 −{conditions.max_quarter_profit_decline_pct:g}%"
    # 降幅规则逐季判定：只要季度报告期相邻且该季数值有限即可判定，不依赖另一季是否有值
    breaches = [
        f"{label or '季度未知'} 单季扣非利润同比 {value:g}%，达到最大降幅 {conditions.max_quarter_profit_decline_pct:g}%（同比 ≤ -{conditions.max_quarter_profit_decline_pct:g}%）"
        for label, value in ((stock.previous_quarter_label, previous), (stock.latest_quarter_label, latest))
        if adjacent and _finite(value) and value <= -conditions.max_quarter_profit_decline_pct
    ]
    if breaches:
        checks.append(ScreeningCheck(
            key="quarter_decline", label="单季扣非利润最大降幅", result="fail", value_text=quarter_text,
            threshold_text=decline_threshold_text, detail="单季降幅超过阈值，需复核",
            reason="；".join(breaches),
        ))
    elif not adjacent:
        checks.append(ScreeningCheck(
            key="quarter_decline", label="单季扣非利润最大降幅", result="missing", value_text=quarter_text,
            threshold_text=decline_threshold_text, detail="相邻报告期不连续，未判定",
        ))
    elif not (_finite(previous) and _finite(latest)):
        checks.append(ScreeningCheck(
            key="quarter_decline", label="单季扣非利润最大降幅", result="missing", value_text=quarter_text,
            threshold_text=decline_threshold_text, detail="单季同比数据缺失，未判定",
        ))
    else:
        checks.append(ScreeningCheck(
            key="quarter_decline", label="单季扣非利润最大降幅", result="pass", value_text=quarter_text,
            threshold_text=decline_threshold_text,
        ))

    if not pair_ready:
        checks.append(ScreeningCheck(
            key="quarter_pair", label="连续两季扣非同比", result="missing", value_text=quarter_text,
            threshold_text="不得连续两季为负", detail="相邻季度数据不完整，未判定",
            reason="连续两个相邻季度扣非同比数据缺失",
        ))
    elif latest < 0 and previous < 0:
        checks.append(ScreeningCheck(
            key="quarter_pair", label="连续两季扣非同比", result="fail", value_text=quarter_text,
            threshold_text="不得连续两季为负", detail="连续两季扣非同比为负，需复核",
            reason="连续两个季度扣非利润同比下降",
        ))
    elif (latest < 0 or previous < 0) and min(latest, previous) > -conditions.max_quarter_profit_decline_pct:
        checks.append(ScreeningCheck(
            key="quarter_pair", label="连续两季扣非同比", result="warn", value_text=quarter_text,
            threshold_text="不得连续两季为负", detail="一个季度扣非同比下降，建议持续关注",
            warning="一个季度扣非利润同比下降，建议持续关注",
        ))
    else:
        checks.append(ScreeningCheck(
            key="quarter_pair", label="连续两季扣非同比", result="pass", value_text=quarter_text,
            threshold_text="不得连续两季为负",
        ))

    return checks


def evaluate_stock(stock: DividendStock, conditions: ScreeningRequest) -> ScreeningItem:
    checks = build_checks(stock, conditions)
    failures = [check.reason for check in checks if check.result == "fail" and check.reason]
    missing = [check.reason for check in checks if check.result == "missing" and check.reason]
    warnings = [check.warning for check in checks if check.warning]
    status = "excluded" if failures else "insufficient_data" if missing else "eligible"
    return ScreeningItem(stock=stock, status=status, reasons=failures + missing, warnings=warnings)
