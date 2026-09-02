# phase2-A 设计：业绩基准 fetcher + 风险利率

## 模块边界

```
src/data/
├── benchmark_fetcher.py        # 本 task 新建
│   ├── parse_formula(text) -> list[Component]
│   ├── _fetch_index_daily(symbol, source, start, end) -> pd.DataFrame
│   └── fetch_benchmark_tri(code, start, end) -> pd.DataFrame
├── risk_free_fetcher.py        # 本 task 新建
│   └── fetch_risk_free_rate(start, end) -> pd.DataFrame
├── deposit_floor.py            # 本 task 新建（常量 + 历史调整注释）
│   └── PBOC_DEPOSIT_FLOOR_RATE = 0.0035
├── nav_fetcher.py              # 已有，不动
└── fund_basic_fetcher.py       # 已有，本 task 复用 fetch_basic()
```

依赖：
- `parse_formula` 纯字符串处理，无外部依赖
- `_fetch_index_daily` → akshare（按 `source` 字段分发）
- `fetch_benchmark_tri` → `fetch_basic` + `parse_formula` + `_fetch_index_daily` + `deposit_floor.PBOC_DEPOSIT_FLOOR_RATE`
- `fetch_risk_free_rate` → akshare `bond_zh_us_rate`

## 数据模型

```python
# src/db/models.py 追加
from sqlalchemy import Column, String, Date, Float, DateTime
from datetime import UTC, datetime

class FundBenchmark(Base):
    """业绩比较基准 TRI（参考日=1000 复利累加）"""
    __tablename__ = "fund_benchmark"
    code = Column(String(6), primary_key=True)
    date = Column(Date, primary_key=True)
    tri = Column(Float, nullable=True)           # tri=NULL 表示无可用基准
    source = Column(String(64), nullable=False, default="fetched")
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class RiskFreeRate(Base):
    """无风险利率日频（中国国债 2Y 为主源）"""
    __tablename__ = "risk_free_rate"
    date = Column(Date, primary_key=True)
    rate = Column(Float, nullable=False)         # 年化小数
    source = Column(String(32), nullable=False, default="bond_zh_us_rate_2y")
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))
```

Alembic 迁移：`alembic revision --autogenerate -m "add fund_benchmark & risk_free_rate"`。

## Component 数据类

```python
# src/data/benchmark_fetcher.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Component:
    name: str            # 原始名（如 "沪深300" / "活期存款基准利率"）
    weight: float        # 归一化前的小数（可能和 ≠ 1，phase2-B 计算时归一）
    kind: str            # 'index' | 'deposit_floor' | 'unknown'
    ak_symbol: str | None = None   # 仅 kind == 'index' 时有值
```

## 算法 1: `parse_formula` 状态机

**输入**：`"沪深300指数收益率×45%+中证港股通综合×35%+中债总×20%"`
**输出**：`[Component("沪深300", 0.45, "index", "sh000300"), Component("中证港股通综合", 0.35, "index", ...), Component("中债总", 0.20, "index", ...)]`

### 步骤

```python
import re
import unicodedata

_FULLWIDTH = str.maketrans("＋ｘ（）", "+*()")   # 全角归一

def parse_formula(text: str) -> list[Component]:
    s = unicodedata.normalize("NFKC", text).translate(_FULLWIDTH).strip()
    # 剥离括号内容（视为注释）
    s = re.sub(r"[\(（].*?[\)）]", "", s)
    # 按 + 切分
    raw_parts = [p.strip() for p in s.split("+") if p.strip()]
    if not raw_parts:
        return []
    # 单指数无权重：整段只有一个 token 且无乘号分隔符。
    # 注意不能用「无数字」判断——「纳斯达克100指数」名字本身含 100。
    only = raw_parts[0]
    if len(raw_parts) == 1 and "×" not in only and "*" not in only:
        return [_classify(only, 1.0)]
    # 多项 / 含权重：逐项解析
    components = []
    for part in raw_parts:
        m = re.match(r"^(?P<num>\d+(?:\.\d+)?)\s*%?\s*[×*]\s*(?P<name>.+)$", part)
        if not m:
            m = re.match(r"^(?P<name>.+?)\s*[×*]\s*(?P<num>\d+(?:\.\d+)?)\s*%$", part)
        if m:
            num = float(m.group("num"))
            name = m.group("name").strip()
            weight = num / 100.0 if num > 1.5 else num   # 百分号语义判别
            components.append(_classify(name, weight))
        else:
            components.append(_classify(part.strip(), 1.0))
    return components


def _classify(name: str, weight: float) -> Component:
    # 1. 含「存款」/「基准利率」字眼 → deposit_floor
    if any(k in name for k in ("存款", "基准利率")):
        return Component(name, weight, "deposit_floor", None)
    # 2. 查 yaml 索引
    name_clean = name.replace("指数", "").replace("收益率", "").strip()
    cfg = _load_benchmarks_yaml()  # 缓存
    sym = cfg["indices"].get(name_clean) or cfg["indices"].get(name) \
        or cfg["indices"].get(cfg["aliases"].get(name_clean, ""))
    if sym:
        return Component(name, weight, "index", sym["ak_symbol"])
    # 3. 找不到
    return Component(name, weight, "unknown", None)
```

**关键边界**：
- 百分号语义判别：`num > 1.5` 当百分比（如 95 → 0.95）；否则当小数（如 0.95 → 0.95）
- 单指数无权重（`纳斯达克100指数`）→ 整段无乘号即单指数；不能用「无数字」判断（名字本身含 100）
- 不可解析项 → `kind="unknown", weight=0`（不参与合成，TRI 计算时跳过）
- `_classify` 的名称清洗链：剥括号注释 → 去后缀（迭代去 `指数` `收益率`）→ 去前缀（`经汇率调整后的` `经估值汇率调整的`）→ 查 indices → 查 aliases

## 算法 2: `fetch_benchmark_tri` TRI 复利合成

```python
import akshare as ak
import pandas as pd
from src.data.deposit_floor import PBOC_DEPOSIT_FLOOR_RATE

def fetch_benchmark_tri(code: str, start: date, end: date) -> pd.DataFrame:
    info = fetch_basic(code)
    raw = info.get("业绩比较基准")
    if not raw:
        return _empty_with_source(code, "unavailable:no_field")

    components = parse_formula(raw)
    if not components or all(c.kind == "unknown" for c in components):
        # 整体 fallback_chain
        return _fallback_chain_tri(code, start, end)

    # 1. 拉每个 index 的日线
    daily_returns = {}     # date -> series of (component_name, return)
    valid_components = []
    for c in components:
        if c.kind == "deposit_floor":
            valid_components.append(c)
            continue
        if c.kind == "unknown" or not c.ak_symbol:
            # 单个指数 fallback
            idx_df = _fetch_index_daily(cfg["fallback_index"], start, end)
            tag = Component(f"fallback:{cfg['fallback_index']}", c.weight, "index",
                            cfg["fallback_index"])
            valid_components.append(tag)
            daily_returns[tag.ak_symbol] = idx_df["return"]
        else:
            idx_df = _fetch_index_daily(c.ak_symbol, start, end)
            daily_returns[c.ak_symbol] = idx_df["return"]
            valid_components.append(c)

    # 2. 对齐所有日期（基准交易日为骨架）
    all_dates = sorted(set().union(*[set(s.index) for s in daily_returns.values()]))
    ret_df = pd.DataFrame(index=all_dates)
    for sym, s in daily_returns.items():
        ret_df[sym] = s
    ret_df = ret_df.sort_index().ffill()   # 缺失日前向 fill

    # 3. 加权日收益
    total_w = sum(c.weight for c in valid_components)
    if total_w <= 0:
        return _fallback_chain_tri(code, start, end)
    w_norm = {c.ak_symbol or c.name: c.weight / total_w for c in valid_components}

    weighted_ret = pd.Series(0.0, index=ret_df.index)
    for sym, w in w_norm.items():
        weighted_ret = weighted_ret + ret_df[sym].fillna(0) * w

    # 4. 复利累加 → TRI（参考日 = 1000）
    tri = (1 + weighted_ret).cumprod() * 1000

    return pd.DataFrame({"date": tri.index, "tri": tri.values})


def _fallback_chain_tri(code, start, end) -> pd.DataFrame:
    """公式完全失败：按 fallback_chain 顺序尝试第一个可用指数"""
    cfg = _load_benchmarks_yaml()
    for sym in cfg["fallback_chain"]:
        try:
            idx_df = _fetch_index_daily(sym, start, end)
            tri = (1 + idx_df["return"].fillna(0)).cumprod() * 1000
            return pd.DataFrame({
                "date": tri.index,
                "tri": tri.values,
                "source": f"fallback_chain:{sym}",
            })
        except Exception:
            continue
    return _empty_with_source(code, "fallback_chain:exhausted")
```

## 算法 3: `_fetch_index_daily` akshare 分发（实测后修订）

探测结论（tmp/probe_index_sources*.py，2026-09-02）：

| 源 | 接口 | 状态 |
|---|---|---|
| A 股指数 | `ak.stock_zh_index_daily(symbol)` | ✅ 32 个可用 |
| 债券指数 | `ak.bond_composite_index_cbond(indicator="财富", period="总值")` | ✅ 中债-综合指数 2002-至今 6170 行 |
| 美股指数 | `ak.index_us_stock_sina(symbol=".INX"/".NDX")` | ✅ |
| 港股指数 | `stock_hk_index_daily_em` / `_sina` | ❌ 全源失败（em ConnectionError / sina 无数据）→ 恒生类名字不收录，公式命中即 fallback_chain |

**停更陷阱**：新浪源部分指数断流（sh000922 中证红利断于 2019、sh000907 800成长断于 2016、sh000908 800价值断于 2019、sz399981 断于 2015、sh000824/sh000815 断于 2016）。收录无妨，但 fetcher 必须做**新鲜度检查**：

```python
def _fetch_index_daily(symbol: str, source: str, start: date, end: date) -> pd.DataFrame:
    """按 yaml source 字段分发；返回 columns=[date, close, return]。
    末条数据 < end - 10 天视为停更 → 抛 StaleIndexError（上层走 fallback）"""
    if source == "bond_composite_index_cbond":
        df = ak.bond_composite_index_cbond(indicator="财富", period="总值")
        df = df.rename(columns={"value": "close"})
    elif source == "index_us_stock_sina":
        df = ak.index_us_stock_sina(symbol=symbol)
    else:  # stock_zh_index_daily
        df = ak.stock_zh_index_daily(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    if df["date"].iloc[-1] < pd.Timestamp(end) - pd.Timedelta(days=10):
        raise StaleIndexError(f"{symbol} stale since {df['date'].iloc[-1]}")
    df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
    df["return"] = df["close"].pct_change().fillna(0)
    return df.reset_index(drop=True)
```

## 算法 4: `fetch_risk_free_rate`

```python
def fetch_risk_free_rate(start: date, end: date) -> pd.DataFrame:
    # 主源：bond_zh_us_rate 中国国债 2 年
    try:
        df = ak.bond_zh_us_rate()
        s = df.set_index(pd.to_datetime(df["日期"]))["中国国债收益率2年"].dropna()
        s = s / 100.0   # 百分比 → 小数
        s = s.sort_index()
        s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
        if len(s) >= 365:
            return pd.DataFrame({"date": s.index, "rate": s.values,
                                 "source": "bond_zh_us_rate_2y"})
    except Exception as e:
        logger.warning("bond_zh_us_rate 失败，降级 LPR: %s", e)

    # Fallback：macro_china_lpr LPR1Y（月度 → 日频 ffill）
    try:
        df = ak.macro_china_lpr()
        df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])
        s = df.set_index("TRADE_DATE")["LPR1Y"].dropna() / 100.0
        s = s.sort_index().reindex(
            pd.date_range(s.index.min(), pd.Timestamp(end))
        ).ffill()
        return pd.DataFrame({"date": s.index, "rate": s.values, "source": "lpr_1y"})
    except Exception as e:
        logger.warning("LPR 失败，降级常量 0.025: %s", e)

    # 兜底常量
    dates = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"date": dates, "rate": [0.025] * len(dates),
                         "source": "constant_0.025"})
```

## Refresh pipeline 接入

```python
# src/services/refresh_service.py 追加
def refresh_stock_funds_sync(task_id: str) -> None:
    # ... 现有逻辑：拉基础信息、achievement、performance 等
    # 新增步骤：
    _refresh_fund_benchmarks(task_id)


def _refresh_fund_benchmarks(task_id: str) -> None:
    """仅跑 funds_stock.yaml 名单；写入 fund_benchmark 表"""
    codes = _load_stock_codes()   # 143 只
    start = date.today() - timedelta(days=365 * 3)   # 3 年窗口
    end = date.today()
    with get_session() as s:
        for code in codes:
            try:
                df = fetch_benchmark_tri(code, start, end)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    s.merge(FundBenchmark(
                        code=code,
                        date=row["date"].date(),
                        tri=row.get("tri"),
                        source=row.get("source", "fetched"),
                    ))
            except Exception as e:
                logger.warning("fund_benchmark %s failed: %s", code, e)


def refresh_risk_free_rate_sync(task_id: str) -> None:
    """独立刷新 risk_free_rate；一次拉 35 年全历史"""
    start = date(1990, 1, 1)
    end = date.today()
    df = fetch_risk_free_rate(start, end)
    with get_session() as s:
        for _, row in df.iterrows():
            s.merge(RiskFreeRate(
                date=row["date"].date(),
                rate=row["rate"],
                source=row["source"],
            ))
```

## 错误处理 / 回滚

| 失败点 | 处理 | 影响范围 |
|---|---|---|
| `fetch_basic` 抛异常（schema 残缺） | 已 fallback danjuanfunds；不消费「业绩比较基准」 → DB tri=NULL | 单只基金无基准 |
| `parse_formula` 整体失败 | fallback_chain → sh000906 | 单只基金用替代基准 |
| `_fetch_index_daily` 抛异常 | 该 component fallback → fallback_index 单替换 | 单只基金部分基准替换 |
| `fetch_benchmark_tri` 全失败 | DB tri=NULL, source=`exhausted` | 单只基金无基准 |
| `fetch_risk_free_rate` 全失败 | DB rate=0.025 | 全局 Sharpe 偏低；可监控 |

**回滚策略**：每张新表独立 alembic 迁移；`downgrade()` 删除表即可回到现状，不影响债基。

## 性能

- 全量 143 只 × 0.89 秒/只 ≈ **127 秒**（实测）
- risk_free_rate 35 年 ≈ **1 次 5 秒**（`bond_zh_us_rate` 一次性返回）
- 整体 refresh 增加 ~130 秒，在可接受范围

## 兼容性

- 旧 `fund_benchmark` / `risk_free_rate` 表**不存在**，纯新增
- 旧 refresh 函数签名不变
- 前端 / API 不动（phase2-B 才消费）
- Python 3.13 兼容

## 验收脚本

```bash
cd backend/fund-select
.venv/Scripts/python -m pytest tests/test_benchmark_fetcher.py tests/test_risk_free_fetcher.py -v
.venv/Scripts/python -m pytest tests/ -v                       # 全量回归
.venv/Scripts/python -c "from src.data.benchmark_fetcher import fetch_benchmark_tri; print(fetch_benchmark_tri('005827', __import__('datetime').date(2023,1,1), __import__('datetime').date.today()).head())"
.venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m alembic downgrade base && .venv/Scripts/python -m alembic upgrade head   # 迁移双向验证
```
