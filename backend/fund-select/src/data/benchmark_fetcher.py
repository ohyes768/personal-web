"""
业绩比较基准 fetcher（phase2-A）

parse_formula: 「业绩比较基准」公式字符串 → [Component]
fetch_benchmark_tri: 公式 + 指数日线 → 基准 TRI 序列（参考日=1000 加权日收益复利）

数据源与停更陷阱见 config/benchmarks.yaml 头注释（2026-09-02 实测探测）。
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import akshare as ak
import pandas as pd
import yaml

from src.data.deposit_floor import PBOC_DEPOSIT_FLOOR_RATE
from src.data.fund_basic_fetcher import fetch_basic
from src.utils.config import CONFIG_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.benchmark_fetcher")

_BENCHMARKS_YAML = CONFIG_DIR / "benchmarks.yaml"
_STALE_DAYS = 10          # 末条数据早于 end-10 天 → 视为停更
_TRADING_DAYS = 252       # deposit_floor 日收益折算
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# NFKC 处理 ＋（）％ 等；乘号类字符（× ｘ ＊）统一 translate 成 *
_MUL_MAP = str.maketrans({"×": "*", "ｘ": "*", "＊": "*", "x": "*"})
# 「存款」类非指数成分关键词（业绩基准公式常见：活期/定期存款、基准利率）
_DEPOSIT_HINTS = ("存款", "基准利率", "活期", "定期", "贷款", "LPR", "同业存单")
# 名称清洗：去后缀（迭代）与前缀（汇率调整说明）
_SUFFIXES = ("指数", "收益率")
_PREFIXES = ("经汇率调整后的", "经估值汇率调整的", "经人民币汇率调整的", "使用估值汇率折算的")


class StaleIndexError(Exception):
    """指数日线停更（末条数据过旧）"""


@dataclass(frozen=True)
class Component:
    """公式成分：name 保真（剥括号注释后）、weight 原始小数（未归一）"""
    name: str
    weight: float
    kind: str                  # 'index' | 'deposit_floor' | 'unknown'
    ak_symbol: str | None = None


_cfg_cache: dict | None = None
_index_cache: dict[str, pd.DataFrame] = {}


def _load_benchmarks_yaml() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        _cfg_cache = yaml.safe_load(_BENCHMARKS_YAML.read_text(encoding="utf-8"))
    return _cfg_cache


def clear_index_cache() -> None:
    """清空指数日线进程内缓存（长驻进程中数据会老化，refresh 入口调用）"""
    _index_cache.clear()


def parse_formula(text: str) -> list[Component]:
    """解析公式为成分列表；空串/纯空白返回 []。"""
    s = unicodedata.normalize("NFKC", text or "").translate(_MUL_MAP).strip()
    s = re.sub(r"\(.*?\)", "", s)  # 括号内容视作注释（税后/汇率折算/指数英文名等）
    parts = [p.strip() for p in s.split("+") if p.strip()]
    if not parts:
        return []

    # 单指数无权重：整段无乘号即单指数（名字可含数字，如 纳斯达克100指数）
    only = parts[0]
    if len(parts) == 1 and "*" not in only:
        return [_classify(re.sub(r"\(.*?\)", "", only).strip(), 1.0)]

    components: list[Component] = []
    for part in parts:
        part = re.sub(r"\(.*?\)", "", part).strip()
        split = _split_weight(part)
        if split is None:
            components.append(Component(part, 0.0, "unknown", None))
            logger.warning("公式成分无法解析权重: %r", part)
            continue
        weight, name = split
        components.append(_classify(name, weight))
    return components


def _split_weight(part: str) -> tuple[float, str] | None:
    """「name×95%」或「95%×name」→ (0.95, name)；无法识别返回 None"""
    segs = [s.strip() for s in part.split("*") if s.strip()]
    if len(segs) != 2:
        return None
    for a, b in ((segs[0], segs[1]), (segs[1], segs[0])):
        t = a.replace("%", "").strip()
        if _NUM_RE.fullmatch(t):
            num = float(t)
            # 百分号显式或数值 >1.5 视为百分数（95 → 0.95）；否则已是小数（0.95）
            weight = num / 100.0 if ("%" in a or num > 1.5) else num
            return weight, b
    return None


def _lookup_keys(name: str) -> list[str]:
    """名称 → 前后缀剥离的全部中间形态（BFS 闭包）。

    「经人民币汇率调整的恒生指数收益率」需要 先剥前缀再剥后缀 / 先后缀再前缀
    两种路径都出现（「恒生指数」来自先剥后缀再剥前缀），故用 BFS 展开所有组合。
    """
    start = name.strip()
    keys = [start]
    queue = [start]
    while queue:
        cur = queue.pop(0)
        variants: list[str] = []
        for suf in _SUFFIXES:
            if cur.endswith(suf) and len(cur) > len(suf):
                variants.append(cur[: -len(suf)].strip())
        for pre in _PREFIXES:
            if cur.startswith(pre):
                variants.append(cur[len(pre):].strip())
        for v in variants:
            if v and v not in keys:
                keys.append(v)
                queue.append(v)
    return keys


def _classify(name: str, weight: float) -> Component:
    if any(h in name for h in _DEPOSIT_HINTS):
        return Component(name, weight, "deposit_floor", None)
    cfg = _load_benchmarks_yaml()
    keys = _lookup_keys(name)
    for key in keys:
        if key in cfg["indices"]:
            entry = cfg["indices"][key]
            return Component(name, weight, "index", entry["ak_symbol"])
    for key in keys:
        alias = cfg["aliases"].get(key)
        if alias and alias in cfg["indices"]:
            entry = cfg["indices"][alias]
            return Component(name, weight, "index", entry["ak_symbol"])
    return Component(name, weight, "unknown", None)


def _fetch_index_daily(symbol: str, source: str, start: date, end: date) -> pd.DataFrame:
    """按 yaml source 字段拉指数日线；返回 columns=[date, close, return]。

    进程内按 symbol 缓存全量数据（143 只基金重复引用同一指数时只拉一次）。
    末条数据 < end - 10 天视为停更 → StaleIndexError（上层走 fallback）。
    """
    if symbol in _index_cache:
        df = _index_cache[symbol]
    else:
        if source == "bond_composite_index_cbond":
            raw = ak.bond_composite_index_cbond(indicator="财富", period="总值")
            df = raw.rename(columns={"value": "close"})[["date", "close"]]
        elif source == "index_us_stock_sina":
            df = ak.index_us_stock_sina(symbol=symbol)[["date", "close"]]
        elif source == "stock_zh_index_daily_tx":  # 腾讯（港股指数唯一可用源）
            df = ak.stock_zh_index_daily_tx(symbol=symbol)[["date", "close"]]
        else:  # stock_zh_index_daily
            df = ak.stock_zh_index_daily(symbol=symbol)[["date", "close"]]
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        _index_cache[symbol] = df

    if df["date"].iloc[-1] < pd.Timestamp(end) - pd.Timedelta(days=_STALE_DAYS):
        raise StaleIndexError(f"{symbol} 停更于 {df['date'].iloc[-1].date()}")
    win = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].copy()
    win["return"] = win["close"].pct_change().fillna(0)
    return win.reset_index(drop=True)


def _resolve(symbol: str | None, start: date, end: date, cfg: dict, ctx: str = ""):
    """ctx：告警附带的基金定位信息（code/名称/基准公式/成分名），由调用方拼好透传。"""
    sources = {entry["ak_symbol"]: entry["source"] for entry in cfg["indices"].values()}
    chain = ([symbol] if symbol else []) + [s for s in cfg["fallback_chain"] if s != symbol]
    for sym in chain:
        try:
            df = _fetch_index_daily(sym, sources.get(sym, "stock_zh_index_daily"), start, end)
            return sym, df
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "指数 %s 拉取失败(%s: %s)，尝试 fallback | %s",
                sym, type(e).__name__, str(e)[:80], ctx,
            )
    return None


def fetch_benchmark_tri(code: str, start: date, end: date) -> tuple[pd.DataFrame, str]:
    """合成单只基金业绩比较基准 TRI。

    返回 (DataFrame[date, tri], source)。source 取值见 FundBenchmark.source 注释。
    """
    cfg = _load_benchmarks_yaml()
    try:
        info = fetch_basic(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_basic %s 失败: %s", code, str(e)[:120])
        return pd.DataFrame(columns=["date", "tri"]), "unavailable:basic_failed"

    raw = info.get("业绩比较基准")
    if not raw or not str(raw).strip():
        return pd.DataFrame(columns=["date", "tri"]), "unavailable:no_field"

    # 告警定位上下文：基金 code/名称 + 基准公式原文（雪球源叫「基金简称」，蛋卷 fallback 叫「基金名称」）
    fund_name = str(info.get("基金简称") or info.get("基金名称") or "").strip()
    ctx = f"基金 {code} {fund_name} | 基准公式: {str(raw)[:100]}"

    components = parse_formula(str(raw))
    if not components or all(c.kind == "unknown" for c in components):
        logger.warning("%s 公式整体不可解析: %r → fallback_chain", code, str(raw)[:80])
        return _fallback_chain_tri(start, end, cfg, ctx)

    # 逐成分取收盘价序列（价格对齐合成：ffill 价格后重算日收益，缺席日贡献 0）
    series: dict[str, pd.Series] = {}   # key -> 收盘价（index=date）；deposit 为 None 占位
    weights: dict[str, float] = {}      # key -> 原始权重
    fallback_syms: list[str] = []
    for c in components:
        key = f"deposit:{c.name}" if c.kind == "deposit_floor" else (c.ak_symbol or f"unknown:{c.name}")
        if key in series:
            weights[key] += c.weight
            continue
        if c.kind == "deposit_floor":
            series[key] = None  # 占位，合成阶段按常数日收益
            weights[key] = c.weight
        elif c.kind == "index":
            got = _resolve(c.ak_symbol, start, end, cfg, f"{ctx} | 成分「{c.name}」")
            if got is None:
                return _fallback_chain_tri(start, end, cfg, ctx)
            sym, df = got
            series[key] = df.set_index("date")["close"]
            weights[key] = c.weight
        else:  # unknown → fallback_index 替换
            got = _resolve(None, start, end, cfg, f"{ctx} | 成分「{c.name}」(未收录)")
            if got is None:
                return _fallback_chain_tri(start, end, cfg, ctx)
            sym, df = got
            series[key] = df.set_index("date")["close"]
            weights[key] = c.weight
            fallback_syms.append(sym)

    # 交易日骨架 = 各指数日期并集
    all_dates = sorted(set().union(*[s.index for s in series.values() if s is not None]))
    if not all_dates:
        return _fallback_chain_tri(start, end, cfg, ctx)
    # 价格对齐：并集日历上 ffill 价格（成分缺席日价格不变 → 收益 0，不再复制前日收益）；
    # dropna 裁掉前导缺失行（任一成分未上市前基准无定义）
    px = pd.DataFrame(index=pd.DatetimeIndex(all_dates))
    for key, s in series.items():
        if s is not None:
            px[key] = s
    px = px.sort_index().ffill().dropna()
    ret_df = px.pct_change().fillna(0)

    total_w = sum(weights.values())
    if total_w <= 0:
        return _fallback_chain_tri(start, end, cfg, ctx)
    weighted = pd.Series(0.0, index=ret_df.index)
    for key, s in series.items():
        w = weights[key] / total_w
        if s is None:  # deposit_floor 常数日收益
            weighted = weighted + w * (PBOC_DEPOSIT_FLOOR_RATE / _TRADING_DAYS)
        else:
            weighted = weighted + ret_df[key] * w

    tri = (1 + weighted).cumprod() * 1000
    out = pd.DataFrame({"date": tri.index, "tri": tri.values})
    if fallback_syms:
        return out, f"partial:fallback:{fallback_syms[0]}"
    return out, "fetched"


def _fallback_chain_tri(start: date, end: date, cfg: dict, ctx: str = "") -> tuple[pd.DataFrame, str]:
    empty = pd.DataFrame(columns=["date", "tri"])
    got = _resolve(None, start, end, cfg, ctx)
    if got is None:
        return empty, "unavailable:exhausted"
    sym, df = got
    tri = (1 + df["return"].fillna(0)).cumprod() * 1000
    return pd.DataFrame({"date": df["date"].values, "tri": tri.values}), f"fallback_chain:{sym}"
