"""
akshare `fund_name_em()` 「基金类型」子类 → tab 分类映射

akshare 返回的「基金类型」是「粗分类-子类」拼接（27 个枚举值），不是单纯粗分类。
本表按"投资标的 + 投资地域"把每个子类精确归到 4 个 tab 分类之一：

- 'bond'   → 债基·市场 universe
- 'stock'  → 股基·市场 universe
- 'other'  → 不在股基/债基 universe（FOF、货币型、未明确标的）

精确枚举而非 LIKE 前缀匹配，避免：
- 「指数型-固收」错归股基（实际是债指数）
- 「混合型-平衡」错归债基（实际混合偏股）
- 「QDII-纯债」错归 QDII 大类（实际是债）
"""
from __future__ import annotations


# akshare 27 个已知子类 → tab 分类（精确映射；新增子类需显式声明）
SUBCLASS_TO_CATEGORY: dict[str, str] = {
    # ── 股基·市场（投资标的为股，含海外股基） ──
    "股票型": "stock",
    "指数型-海外股票": "stock",
    "指数型-其他": "stock",
    "混合型-平衡": "stock",
    "混合型-绝对收益": "stock",
    "混合型-灵活": "stock",
    "QDII-普通股票": "stock",
    "QDII-混合偏股": "stock",
    "QDII-混合灵活": "stock",
    "QDII-混合平衡": "stock",
    "QDII-FOF": "stock",
    "QDII-REITs": "stock",
    "Reits": "stock",
    "REITs": "stock",

    # ── 债基·市场（投资标的为债，含海外债基、债指数） ──
    "债券型-中短债": "bond",
    "债券型-混合一级": "bond",
    "债券型-混合二级": "bond",
    "债券型-混合债": "bond",
    "债券型-利率债": "bond",
    "债券型-信用债": "bond",
    "债券型-长期纯债": "bond",
    "指数型-固收": "bond",     # 债指数 → 债基
    "QDII-纯债": "bond",       # 海外债 → 债基
    "QDII-混合债": "bond",

    # ── 不在股基/债基 universe（FOF / 货币型 / 商品） ──
    "FOF-稳健型": "other",
    "FOF-均衡型": "other",
    "FOF-进取型": "other",
    "货币型-普通货币": "other",
    "货币型-浮动净值": "other",
    "QDII-商品": "other",
    "商品": "other",
    "其他": "other",
}


def categorize(subtype: str) -> str:
    """子类 → tab 分类。未知子类降级 'other'，让运维显式补映射。"""
    if not subtype:
        return "other"
    return SUBCLASS_TO_CATEGORY.get(subtype.strip(), "other")


# 各 tab universe：精确枚举子类（与 SUBCLASS_TO_CATEGORY 保持一致）
DISCOVERY_BOND_SUBTYPES: list[str] = [
    s for s, cat in SUBCLASS_TO_CATEGORY.items() if cat == "bond"
]
DISCOVERY_STOCK_SUBTYPES: list[str] = [
    s for s, cat in SUBCLASS_TO_CATEGORY.items() if cat == "stock"
]
