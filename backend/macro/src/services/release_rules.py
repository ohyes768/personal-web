"""指标级发布规则(下个周期预期时间的后端兜底)

规则来源:各 skill SKILL.md「数据发布时间」表(与前端 release-rules.ts 同源,以后端为准)。
skill JSON 可通过自报字段覆盖(见 macro_signal_service):
- macro_signal.json: indicator_meta[key].next_release = { "date": "...", "note": "..." }
- risk_data.json:    data.{volume,turnover,margin}.next_release = { "date": "...", "note": "..." }

三类规则:
- WORKDAILY:   每个工作日更新 → 下一个工作日
- MONTHLY:     每月固定日发布 → 下一个该日,落周末时校正(统计局系前移 / 央行系顺延)
- MONTH_END:   每月最后一日发布(PMI 当月数据当月末发布) → 下一个月末

注意:工作日 = 周一~周五,不含法定节假日;note 中用「约」表达该误差。
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Tuple, Dict, Literal

ShiftDir = Literal["before", "after"]


@dataclass(frozen=True)
class ReleaseRule:
    kind: str          # 'workdaily' | 'monthly' | 'month_end'
    day: int = 0       # monthly 用的每月几日
    shift: ShiftDir = "before"  # monthly 落周末时的校正方向
    note: str = ""


# indicator key → 发布规则(与前端 INDICATOR_LABELS 的 key 对齐,开放兜底:查不到返回 None)
INDICATOR_RELEASE_RULES: Dict[str, ReleaseRule] = {
    # === 货币政策 ===
    "dr007":  ReleaseRule("workdaily", note="DR007 每个工作日随银行间市场更新"),
    "lpr_1y": ReleaseRule("monthly", day=20, shift="after", note="LPR 每月20日发布(节假日顺延)"),
    "mlf_1y": ReleaseRule("monthly", day=15, shift="after", note="MLF 每月中旬操作日公布"),
    # === 信用扩张(央行调统司,每月13日左右) ===
    "m2_yoy":     ReleaseRule("monthly", day=13, note="金融统计数据(M2/社融)约每月13日发布"),
    "m1_yoy":     ReleaseRule("monthly", day=13, note="金融统计数据(M2/社融)约每月13日发布"),
    "social_yoy": ReleaseRule("monthly", day=13, note="金融统计数据(M2/社融)约每月13日发布"),
    # === 经济运行 ===
    "pmi_manufacturing": ReleaseRule("month_end", note="制造业 PMI 每月最后一日发布当月数据"),
    "industrial_yoy":    ReleaseRule("monthly", day=13, note="工业增加值等统计局数据约每月13日发布"),
    "fai_yoy":           ReleaseRule("monthly", day=13, note="固投/社零约每月13日发布"),
    "retail_yoy":        ReleaseRule("monthly", day=13, note="固投/社零约每月13日发布"),
    "electricity_yoy":   ReleaseRule("monthly", day=20, note="工业用电量约每月20日发布"),
    "railway_yoy":       ReleaseRule("monthly", day=7,  note="铁路货运量约每月7日发布"),
    # === 通胀环境(统计局每月9日发布上月数据) ===
    "cpi_yoy":      ReleaseRule("monthly", day=9, note="CPI/PPI 约每月9日发布上月数据"),
    "ppi_yoy":      ReleaseRule("monthly", day=9, note="CPI/PPI 约每月9日发布上月数据"),
    "core_cpi_yoy": ReleaseRule("monthly", day=9, note="核心 CPI 随 CPI 同步发布"),
    # === 外部压力(每工作日,FRED 延迟 1-2 天) ===
    "dollar_index": ReleaseRule("workdaily", note="美元指数每工作日更新(FRED 延迟约1天)"),
    "usd_cny":      ReleaseRule("workdaily", note="汇率每工作日更新"),
    "ted_spread":   ReleaseRule("workdaily", note="TED 利差每工作日更新(FRED 延迟约1周)"),
    # 中文 key(skill 端直接以中文指标名作 key 输出时兜底,与英文 key 同规则)
    "美元指数":        ReleaseRule("workdaily", note="美元指数每工作日更新(FRED 延迟约1天)"),
    "美元兑人民币":    ReleaseRule("workdaily", note="汇率每工作日更新"),
    "TED利差":         ReleaseRule("workdaily", note="TED 利差每工作日更新(FRED 延迟约1周)"),
    "北向7日日均成交额": ReleaseRule("workdaily", note="北向成交额每交易日盘后更新"),
    "北向当日成交额":    ReleaseRule("workdaily", note="北向成交额每交易日盘后更新"),
    "北向7日环比":      ReleaseRule("workdaily", note="北向成交额每交易日盘后更新"),
    # === 市场情绪(盘后/次日 09:45) ===
    "total_amount_yi":   ReleaseRule("workdaily", note="两市成交额每交易日盘后更新"),
    "turnover_rate":     ReleaseRule("workdaily", note="换手率每交易日盘后更新"),
    "margin_balance_yi": ReleaseRule("workdaily", note="融资余额次日 09:45 更新前一交易日"),
    "两市成交额":   ReleaseRule("workdaily", note="两市成交额每交易日盘后更新"),
    "换手率":       ReleaseRule("workdaily", note="换手率每交易日盘后更新"),
    "融资融券余额": ReleaseRule("workdaily", note="融资余额次日 09:45 更新前一交易日"),
}


def _is_workday(d: date) -> bool:
    return d.weekday() < 5  # 周一~周五


def _next_workday(d: date) -> date:
    """d 之后(不含 d)的第一个工作日"""
    nxt = d + timedelta(days=1)
    while not _is_workday(nxt):
        nxt += timedelta(days=1)
    return nxt


def _shift_workday(d: date, shift: ShiftDir) -> date:
    """monthly 落周末时校正:before=前移到最近工作日(统计局系),after=顺延到下一工作日(央行系)"""
    if _is_workday(d):
        return d
    if shift == "after":
        while not _is_workday(d):
            d += timedelta(days=1)
    else:
        while not _is_workday(d):
            d -= timedelta(days=1)
    return d


def _next_monthly_day(day: int, after: date, shift: ShiftDir) -> date:
    """从 after 起找下一个「每月 day 日」(校正周末后须仍 > after,否则取下月)"""
    y, m = after.year, after.month
    while True:
        last_day = calendar.monthrange(y, m)[1]
        candidate = _shift_workday(date(y, m, min(day, last_day)), shift)
        if candidate > after:
            return candidate
        # 校正后已过期(如 after=12日周五,13日周六前移到12日)→ 取下月
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _next_month_end(after: date) -> date:
    """从 after 起找下一个「月末最后一日」(PMI 口径,不做周末校正——月末发布常含周末)"""
    y, m = after.year, after.month
    candidate = date(y, m, calendar.monthrange(y, m)[1])
    if candidate > after:
        return candidate
    m += 1
    if m > 12:
        y, m = y + 1, 1
    return date(y, m, calendar.monthrange(y, m)[1])


def get_next_release(key: str, ref_date: date) -> Optional[Tuple[str, str]]:
    """按规则计算指标 key 的下个周期预期发布日。

    ref_date: 基准日(取 max(数据时间, 今天),保证「下次」一定在未来)。
    返回 (next_release_at 'YYYY-MM-DD', note);key 无规则(未来新指标)返回 None,
    由调用方落 null,前端不渲染「下次」段。
    """
    rule = INDICATOR_RELEASE_RULES.get(key)
    if rule is None:
        return None

    if rule.kind == "workdaily":
        nxt = _next_workday(ref_date)
    elif rule.kind == "monthly":
        nxt = _next_monthly_day(rule.day, ref_date, rule.shift)
    elif rule.kind == "month_end":
        nxt = _next_month_end(ref_date)
    else:  # pragma: no cover - 规则表笔误防御
        return None

    return nxt.isoformat(), rule.note
