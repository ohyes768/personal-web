"""
债券分类：利率债 / 信用债 / 可转债 / 其他（移植 fund_screen_31.py 关键词法）
"""

# 利率债关键词（债券名称含其一 → 利率债）
RATE_BOND_KEYWORDS = ["国开", "农发", "进出口", "国债", "铁道", "汇金", "地方", "央行"]


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def classify_bond(name: str) -> str:
    """rate=利率债 / credit=信用债 / convertible=可转债 / other"""
    n = _clean(name)
    if not n:
        return "other"
    if "转" in n:
        return "convertible"
    for kw in RATE_BOND_KEYWORDS:
        if kw in n:
            return "rate"
    return "credit"
