"""cron 表达式 → 中文可读描述转换"""

# 数字 dow 按 *标准 crontab* 习惯展示（0/7=周日）。注意：APScheduler 3.x
# 的 CronTrigger 数字 0=周一，与 crontab 相反；预设必须写 mon-fri，不要写 1-5。
_DOW_NAMES = {
    "0": "日",
    "7": "日",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
}

# APScheduler / 标准 cron 都认英文缩写，无数字歧义
_DOW_ABBREV = {
    "sun": "日",
    "mon": "一",
    "tue": "二",
    "wed": "三",
    "thu": "四",
    "fri": "五",
    "sat": "六",
}


def cron_to_human(cron: str) -> str:
    """将 5 字段 cron 表达式转中文可读描述。

    支持常见模式；无法识别时返回原字符串。

    >>> cron_to_human("30 16 * * mon-fri")
    '每周一至周五 16:30'
    >>> cron_to_human("30 15 * * 1-5")
    '每周一至周五 15:30'
    >>> cron_to_human("0 2 * * 6")
    '每周六 02:00'
    >>> cron_to_human("0 2 1 * *")
    '每月 1 日 02:00'
    >>> cron_to_human("0 0 * * *")
    '每天 00:00'
    >>> cron_to_human("*/5 * * * *")
    '每 5 分钟'
    """
    try:
        fields = cron.strip().split()
        if len(fields) != 5:
            return cron
        m, h, dom, mon, dow = fields

        # 模式 0: 步进表达式（*/N）优先处理
        if m.startswith("*/") and h == "*" and dom == "*" and mon == "*" and dow == "*":
            return f"每 {m[2:]} 分钟"
        if h.startswith("*/") and m == "0" and dom == "*" and mon == "*" and dow == "*":
            return f"每 {h[2:]} 小时"

        # 其他模式都需要 hhmm
        try:
            hhmm = _format_hhmm(h, m)
        except (ValueError, TypeError):
            return cron

        # 模式 1: 月内某日（dom != *）
        if dom != "*":
            # 同时指定 dow 是不常见的模式，兜底
            if dow == "*" and mon == "*":
                return f"每月 {int(dom)} 日 {hhmm}"
            return cron

        # 模式 2: 每周（dow != *）
        if dow != "*":
            dow_desc = _format_dow(dow)
            if dow_desc is None:
                return cron
            return f"每{dow_desc} {hhmm}"

        # 模式 3: 每天
        if dow == "*" and dom == "*" and mon == "*":
            return f"每天 {hhmm}"

        # 其他不认识的模式
        return cron
    except Exception:
        return cron


def _format_hhmm(h: str, m: str) -> str:
    """格式化 HH:MM，固定 2 位"""
    # 处理 */N 不在此分支出现（前面已分流），这里只兜底数字
    hh = int(h)
    mm = int(m)
    return f"{hh:02d}:{mm:02d}"


def _format_dow(dow: str) -> str | None:
    """dow 字段转中文描述"""
    key = dow.strip().lower()
    # 英文缩写：mon / mon-fri / sat,sun（APScheduler 预设用这个，避免 1-5 歧义）
    if key in _DOW_ABBREV:
        return f"周{_DOW_ABBREV[key]}"
    if "-" in key:
        left, right = key.split("-", 1)
        if left in _DOW_ABBREV and right in _DOW_ABBREV:
            return f"周{_DOW_ABBREV[left]}至周{_DOW_ABBREV[right]}"
    # 数字单值：1, 2, ...
    if key in _DOW_NAMES:
        return f"周{_DOW_NAMES[key]}"
    # 数字范围：1-5（仅文案；APScheduler 实际会当成周二到周六）
    if "-" in key:
        parts = key.split("-")
        if len(parts) == 2 and parts[0] in _DOW_NAMES and parts[1] in _DOW_NAMES:
            return f"周{_DOW_NAMES[parts[0]]}至周{_DOW_NAMES[parts[1]]}"
    # 列表：0,6 或 sat,sun
    if "," in key:
        parts = [p.strip() for p in key.split(",")]
        if all(p in _DOW_ABBREV for p in parts):
            return "周" + "".join(_DOW_ABBREV[p] for p in parts)
        if all(p in _DOW_NAMES for p in parts):
            return "周" + "".join(_DOW_NAMES[p] for p in parts)
    return None
