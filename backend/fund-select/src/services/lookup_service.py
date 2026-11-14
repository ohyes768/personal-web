"""基金代码 → 所属 tab 的路由判定（11-14-fund-code-quick-search）

纯只读逻辑：只查 funds 表 + 两份 yaml 名单，不写库、不触发采集。

优先级（yaml 名单优先于 market_type —— design §2）：
  1. 在 funds.yaml（债基精选 31 只）       → bond
  2. 在 funds_stock.yaml（股基名单 142 只）→ stock
  3. market_type 以「债券」开头（含脏值）  → discovery-bond
  4. market_type == 'stock'                → discovery-stock
  5. market_type == 'other' 且 subtype 属债券子类 → discovery-bond
  6. 其余（other + 混合/FOF/货币，或未知） → discovery-stock（兜底）
  7. 库内无该 code                          → found=False

为什么 yaml 优先：yaml 是「精选名单」，名单内的基金用户多半是从对应雪球 tab
认识的；market_type 是全市场粗分类。两份名单无交集（实测 31/142/交集 0）。

为什么 other 要再看 subtype：实测 other 有 5115 只，其中 2653 只 market_subtype
是「债券型-*」——若笼统兜底到股基市场，这两千多只债基会跳到错误 tab。
"""
from typing import Optional

from sqlalchemy import select

from src.data.fund_universe import load_fund_codes
from src.data.market_subtype_map import (
    DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES,
)
from src.db.models import Fund
from src.utils.config import get_funds_config_path, get_stock_funds_config_path

# tab 常量（与前端路由段一致）
TAB_BOND = "bond"
TAB_STOCK = "stock"
TAB_DISCOVERY_BOND = "discovery-bond"
TAB_DISCOVERY_STOCK = "discovery-stock"

_BOND_SUBTYPES = set(DISCOVERY_BOND_SUBTYPES)
_STOCK_SUBTYPES = set(DISCOVERY_STOCK_SUBTYPES)


def _yaml_membership() -> tuple[set[str], set[str]]:
    """(债基名单, 股基名单)。每次调用重读文件——名单很小（31/142），
    且改名单后重启即生效（与既有 refresh 链路一致），无需缓存失效逻辑。"""
    return (
        set(load_fund_codes(get_funds_config_path())),
        set(load_fund_codes(get_stock_funds_config_path())),
    )


def _resolve_by_market(fund: Fund) -> str:
    """market_type / market_subtype → tab（yaml 未命中时的判定）。"""
    mtype = (fund.market_type or "").strip()
    msub = (fund.market_subtype or "").strip()

    # 脏值防御：market_type 里被误写成 '债券型-长债'（实测 1 行 code=519622）
    if mtype.startswith("债券"):
        return TAB_DISCOVERY_BOND
    if mtype == "stock":
        return TAB_DISCOVERY_STOCK
    if mtype == "bond":
        return TAB_DISCOVERY_BOND

    # other / 空 / 未知：按 subtype 细分
    # 先精确匹配两个 discovery universe，再按「债券」前缀兜底
    if msub in _BOND_SUBTYPES or msub.startswith("债券"):
        return TAB_DISCOVERY_BOND
    if msub in _STOCK_SUBTYPES:
        return TAB_DISCOVERY_STOCK
    # 混合型之外的兜底：混合/FOF/货币/空 → 股基·市场（与 discovery-stock
    # 的 universe 口径一致，混合型本就在其中）
    return TAB_DISCOVERY_STOCK


def resolve_tab(db, code: str) -> dict:
    """6 位基金代码 → {code, found, name, tab, market_type, in_yaml, path}。

    找不到时 found=False、tab/path 为 None；调用方（API）仍返回 200。
    path 是**相对路径**（不带 /funds 前缀，Next basePath 会自动补，
    写成 /funds/... 会变成 /funds/funds/... 404 —— contracts §4）。
    """
    bond_codes, stock_codes = _yaml_membership()

    fund = db.execute(select(Fund).where(Fund.code == code)).scalars().first()
    if fund is None:
        return {
            "code": code, "found": False, "name": None, "tab": None,
            "market_type": None, "in_yaml": None, "path": None,
        }

    if code in bond_codes:
        tab, in_yaml = TAB_BOND, "bond"
    elif code in stock_codes:
        tab, in_yaml = TAB_STOCK, "stock"
    else:
        tab, in_yaml = _resolve_by_market(fund), None

    return {
        "code": code,
        "found": True,
        "name": fund.name,
        "tab": tab,
        "market_type": fund.market_type,
        "in_yaml": in_yaml,
        "path": f"/{tab}?code={code}",
    }
