"""
费率 fetcher（预研源码缺失，按 cache/fees_{code}.json 契约补回）

数据源：东财基金 F10 费率页 https://fundf10.eastmoney.com/jjfl_{code}.html
契约字段（全部 %、字符串数字，写库时转 float）：
  fee_buy_small       申购小额档
  fee_redeem_lt7d     持有 <7 天赎回费
  fee_redeem_7d_1y    7 天 ~ 1 年赎回费
  fee_redeem_ge1y     ≥1 年赎回费
  fee_redeem_ge7d     ≥7 天赎回费（部分基金仅有此档）
  fee_mgmt            管理费（年）
  fee_custody         托管费（年）
  fee_service         销售服务费（年，C 类；无则缺省）
"""
import json
import re
from pathlib import Path

import requests

from src.utils.config import CACHE_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.fee_fetcher")

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}

FEE_KEYS = [
    "fee_buy_small",
    "fee_redeem_lt7d",
    "fee_redeem_7d_1y",
    "fee_redeem_ge1y",
    "fee_redeem_ge7d",
    "fee_mgmt",
    "fee_custody",
    "fee_service",
]


def _cache_file(code: str) -> Path:
    return CACHE_DIR / f"fees_{code}.json"


def fetch_fees(code: str, use_cache: bool = True) -> dict:
    """拉单只基金费率。返回契约字段 dict（值 float 或缺失）。

    与预研 cache/fees_{code}.json 契约一致；已有缓存的 31 只直接命中。
    拉取失败返回空 dict（不抛异常，费率列显示 "-"）。
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf = _cache_file(code)
    if use_cache and cf.exists():
        try:
            raw = json.loads(cf.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in raw.items() if v not in (None, "")}
        except Exception:
            logger.warning("费率缓存损坏 %s，重新拉取", cf.name)

    raw = _fetch_from_eastmoney(code)
    if not raw:
        return {}

    try:
        cf.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.warning("费率缓存写入失败 %s（不影响流程）", code)
    return {k: float(v) for k, v in raw.items() if v not in (None, "")}


def _parse_pct(text: str) -> str | None:
    """'0.80%' -> '0.8'；'---' / '无' -> None"""
    t = (text or "").strip()
    if not t or t in ("---", "-", "无", "暂无数据"):
        return None
    m = re.search(r"([\d.]+)\s*%?", t)
    return m.group(1) if m else None


def _fetch_from_eastmoney(code: str) -> dict:
    """解析东财 F10 费率页 HTML。返回原始字符串 dict（契约字段）。"""
    try:
        r = requests.get(
            f"https://fundf10.eastmoney.com/jjfl_{code}.html",
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.warning("费率页拉取失败 %s: %s", code, str(e)[:120])
        return {}

    raw: dict[str, str] = {}

    # 管理费 / 托管费 / 销售服务费：费率概况表（金额栏形如 "0.30%（每年）"）
    for key, label in [
        ("fee_mgmt", "管理费"),
        ("fee_custody", "托管费"),
        ("fee_service", "销售服务费"),
    ]:
        m = re.search(
            rf"{label}</th>\s*<td[^>]*>([^<]*)</td>", html
        )
        if not m:
            # 兜底：宽松匹配 label 后最近的百分比
            m = re.search(rf"{label}[^%]*?([\d.]+)%", html)
        v = _parse_pct(m.group(1)) if m else None
        if v is not None:
            raw[key] = v

    # 申购费：取小额档（<100 万），形如 "0.80%" 或 "0.15%"（打折前原费率）
    m = re.search(r"申购金额[^%]{0,200}?([\d.]+)%", html)
    if m:
        raw["fee_buy_small"] = _parse_pct(m.group(1) + "%") or None
    if raw.get("fee_buy_small") is None:
        raw.pop("fee_buy_small", None)

    # 赎回费：按持有期限档位
    # 页面结构形如：<7天 1.50% / 7天-1年 0.10% / 1年以上 0.00%
    def _redeem(pattern: str, key: str) -> None:
        m = re.search(pattern, html)
        if m:
            v = _parse_pct(m.group(1))
            if v is not None:
                raw[key] = v

    _redeem(r"小于7天[^%]*?([\d.]+)%", "fee_redeem_lt7d")
    _redeem(r"7天-1年[^%]*?([\d.]+)%", "fee_redeem_7d_1y")
    _redeem(r"大于等于(?:7天|1年)[^%]*?([\d.]+)%", "fee_redeem_ge7d")
    _redeem(r"1年以上[^%]*?([\d.]+)%", "fee_redeem_ge1y")

    return {k: v for k, v in raw.items() if v is not None}
