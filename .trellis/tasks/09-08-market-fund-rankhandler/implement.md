# Implement: market tab 全量数据接入（rankhandler + fund_basic + 日频净值 + 风险指标）

> **本任务不实现定时任务**。用户明确要求：先做手动「全量刷新」按钮，定时 cron 后续再说。
> 全量刷新 = 4 阶段流水线，~1.5 小时跑完全市场 ~4452 只股基 / ~5353 只债基。

## 概览

按 4 个阶段交付，每阶段独立可验证：

1. **阶段 1：rankhandler 业绩**（最快）— 已有初步设计，需扩展字段
2. **阶段 2：fund_basic 经理/类型/年限**（基础字段补全）
3. **阶段 3：日频净值 + dd_3y / ret_5y**（回撤与长周期收益）
4. **阶段 4：业绩比较基准 + 风险指标**（sharpe / IR / α / γ）
5. **阶段 5：前端「全量刷新」按钮**（4 阶段串联 + 进度聚合）

每阶段末尾设 review gate。

---

## 阶段 1：rankhandler 业绩（新增 market_fund_rank 表）

### 1.1 `db/models.py` 新增 `MarketFundRank`

```python
class MarketFundRank(Base):
    """市场 tab 业绩（东方财富 rankhandler 批量接口；与 fund_performance 独立）

    老 yaml refresh 走 fund_performance（含 dd_3y + sharpe + ir + alpha + ...）
    市场 tab 走 market_fund_rank（仅 9 个时间段涨幅 + 净值）
    """
    __tablename__ = "market_fund_rank"

    code = Column(String(6), primary_key=True)
    nav_date = Column(Date, nullable=True)
    nav_latest = Column(Float, nullable=True)
    ret_1w = Column(Float, nullable=True)
    ret_1m = Column(Float, nullable=True)
    ret_3m = Column(Float, nullable=True)
    ret_6m = Column(Float, nullable=True)
    ret_1y = Column(Float, nullable=True)
    ret_2y = Column(Float, nullable=True)
    ret_3y = Column(Float, nullable=True)
    ret_ytd = Column(Float, nullable=True)
    ret_all = Column(Float, nullable=True)
    ft_code = Column(String(8), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))
```

启动时 `Base.metadata.create_all(engine)` 自动建表。

### 1.2 `data/market_rank_fetcher.py` 新增

```python
"""
东方财富 rankhandler 批量业绩 fetcher

URL: http://fund.eastmoney.com/data/rankhandler.aspx
参数: op=ph, dt=kf, ft={gp|hh|zq|zs|qdii|lof|fof|bb},
      sc={zzf|1yzf|3nzf|6yzf|...}, st=desc|asc, sd=YYYY-MM-DD, ed=YYYY-MM-DD,
      pi=页码, pn=每页条数(≤50), dx=1
响应: JSONP var rankData = {datas: [...], allRecords, allPages}
"""
import json
import re
import time
from datetime import date, timedelta

import pandas as pd
import requests

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_rank")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REFERER = "https://fund.eastmoney.com/data/fundranking.html"
RANKHANDLER_URL = "http://fund.eastmoney.com/data/rankhandler.aspx"
PAGE_DELAY_S = 0.5  # 防东财限流

# datas 字段位置（实测）
_FIELDS = [
    "code", "name", "pinyin", "nav_date", "nav_latest", "acc_nav",
    "ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m",
    "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all",
    "established_date", "ft_code", "size_yi", "fee_buy",
]


def fetch_market_rank_page(ft: str, sd: str, ed: str, pi: int = 1, pn: int = 50,
                            sc: str = "3nzf", st: str = "desc") -> list[dict]:
    """单页 rankhandler 调用。返回 [{code, name, ret_*, ...}]。"""
    params = {
        "op": "ph", "dt": "kf", "ft": ft,
        "sc": sc, "st": st, "sd": sd, "ed": ed,
        "pi": pi, "pn": pn, "dx": 1,
    }
    headers = {"User-Agent": USER_AGENT, "Referer": REFERER}
    r = requests.get(RANKHANDLER_URL, params=params, headers=headers, timeout=15)
    r.raise_for_status()

    m = re.search(r"var\s+rankData\s*=\s*(\{.*?\});", r.text, re.DOTALL)
    if not m:
        raise ValueError(f"rankhandler 响应格式异常（ft={ft} pi={pi}）")
    body = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', m.group(1))
    data = json.loads(body)

    rows = []
    for d in data.get("datas", []):
        parts = d.split(",")
        if len(parts) < len(_FIELDS):
            continue
        row = {f: parts[i] for i, f in enumerate(_FIELDS)}
        row["nav_latest"] = _to_float(row["nav_latest"])
        for k in ("ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m",
                  "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all"):
            row[k] = _to_float(row[k])
        row["size_yi"] = _to_float(row["size_yi"])
        row["nav_date"] = _to_date(row["nav_date"])
        rows.append(row)
    return rows


def _to_float(v: str) -> float | None:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _to_date(v: str) -> date | None:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def fetch_market_rank_bulk(fts: list[str], pages_per_ft: int = 20,
                            sd: str | None = None, ed: str | None = None) -> pd.DataFrame:
    """按 ft 列表分页拉业绩。返回 DataFrame[code, name, nav_date, nav_latest, ret_*, ft_code]."""
    if sd is None:
        ed = ed or date.today().isoformat()
        sd = (date.today() - timedelta(days=365 * 3)).isoformat()

    all_rows: list[dict] = []
    for ft in fts:
        for pi in range(1, pages_per_ft + 1):
            try:
                rows = fetch_market_rank_page(ft=ft, sd=sd, ed=ed, pi=pi, pn=50)
                if not rows:
                    break
                all_rows.extend(rows)
                time.sleep(PAGE_DELAY_S)
            except Exception as e:
                logger.warning("rankhandler 拉取失败 ft=%s pi=%d: %s", ft, pi, str(e)[:120])
                break

    if not all_rows:
        return pd.DataFrame(columns=["code", "name", "nav_date", "nav_latest",
                                      "ret_1w", "ret_1m", "ret_3m", "ret_6m",
                                      "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all",
                                      "ft_code"])
    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info("fetch_market_rank_bulk: %d 只 (fts=%s)", len(df), fts)
    return df
```

### 1.3 `services/market_rank_refresh.py` 新增

upsert `market_fund_rank`，每 500 行 commit。

```python
"""
market_fund_rank upsert refresh
"""
import json
from datetime import UTC, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import MarketFundRank, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_rank_refresh")
BATCH_SIZE = 500


def refresh(session: Session, df: pd.DataFrame, task_id: Optional[str] = None) -> dict:
    """upsert DataFrame 到 market_fund_rank 表。"""
    # ... (与 market_universe_refresh.refresh 同骨架，更新字段不同)
    # 字段映射：nav_date / nav_latest / ret_1w / ... / ret_all / ft_code
```

### 1.4 验证

```bash
python -m pytest tests/test_market_rank_fetcher.py tests/test_market_rank_refresh.py -v
```

**Review Gate 1**：fetcher 单测过 + 实测拉取正确

---

## 阶段 2：fund_basic 给全市场补经理/类型/年限

### 2.1 `data/market_basic_fetcher.py` 新增

```python
"""
全市场 fund_basic 并发 fetcher（雪球 ak.fund_individual_basic_info_xq）

每只 ~2s，5 worker 并发：4452 只 / 5 × 2s ≈ 30 分钟
复用现有 fetch_basic()，仅改 batch + 并发包装
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from src.data.fund_basic_fetcher import fetch_basic
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_basic")
MAX_WORKERS = 5
DELAY_S = 0.2  # 防雪球限流


def fetch_market_basic(codes: list[str], max_workers: int = MAX_WORKERS) -> pd.DataFrame:
    """并发拉全市场 fund_basic。返回 [code, fund_type, age_years, size_yi, mgr_name, ...]"""
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe_fetch, code): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            data = future.result()
            if data:
                rows.append({"code": code, **data})
    return pd.DataFrame(rows)


def _safe_fetch(code: str) -> dict | None:
    """单只 fetch_basic + 字段标准化。失败返回 None。"""
    time.sleep(DELAY_S)
    try:
        info = fetch_basic(code)
        # 提取字段（fund_basic_fetcher 返回 item -> value dict）
        out = {}
        out["fund_type"] = info.get("基金类型", "")
        out["established_date"] = info.get("成立时间", "")
        out["size_yi_raw"] = info.get("最新规模", "")
        out["mgr_name"] = info.get("基金经理", "")
        # mgr_days / mgr_experience_years 需要经理表 cross-reference → 复用现有 mgr_fetcher
        # 但单只 fund_basic 不返回 mgr_days；需要从 manager_em.json 查（缓存已有）
        return out
    except Exception as e:
        logger.warning("fetch_basic %s 失败: %s", code, str(e)[:120])
        return None
```

### 2.2 `data/market_basic_refresh.py` 新增

upsert funds 表的 `fund_type / established_date / age_years / size_yi / mgr_name / mgr_company / mgr_days / mgr_experience_years` 字段。

**不重置** `market_subtype / market_type / name`（这两列由 market_universe_refresh 写）。

**复用** `manager_fetcher.fetch_manager_table()` 的缓存（已有 2.7 万条经理表），cross-reference 经理名 → 从业天数。

```python
def refresh(session: Session, df: pd.DataFrame, task_id=None) -> dict:
    """upsert funds 表基础字段（fund_type / age_years / size_yi / mgr_*）"""
    # 加载经理表
    mgr_worktime, mgr_company = fetch_manager_table(use_cache=True)

    for batch in chunks(df, 500):
        codes = batch['code'].tolist()
        existing = get existing funds
        for row in batch:
            if row.code in existing:
                update funds set fund_type=..., age_years=..., mgr_name=...,
                                mgr_company=..., mgr_days=..., mgr_experience_years=...,
                                size_yi=..., updated_at=now
                            where code=...
            else:
                insert new fund row（fund_type / mgr_*）
```

### 2.3 验证

```bash
python -m pytest tests/test_market_basic_refresh.py -v
```

**Review Gate 2**：跑一次 fund_basic 全市场补全，mgr_* / fund_type / age_years 填满

---

## 阶段 3：日频净值 + dd_3y / ret_5y

### 3.1 `data/market_nav_fetcher.py` 新增

```python
"""
全市场日频净值并发 fetcher（ak.fund_open_fund_info_em）

每只 ~1.5s，5 worker：4452 × 1.5s / 5 ≈ 22 分钟
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import pandas as pd
from src.data.nav_fetcher import fetch_nav
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_nav")
MAX_WORKERS = 5
DELAY_S = 0.2


def fetch_market_nav(codes: list[str], max_workers: int = MAX_WORKERS) -> dict[str, pd.DataFrame]:
    """并发拉全市场日频净值。返回 {code: DataFrame[净值日期, 日增长率]}。"""
    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe_fetch, code): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            df = future.result()
            if df is not None and not df.empty:
                out[code] = df
    return out


def _safe_fetch(code: str) -> pd.DataFrame | None:
    time.sleep(DELAY_S)
    try:
        return fetch_nav(code)
    except Exception as e:
        logger.warning("fetch_nav %s 失败: %s", code, str(e)[:120])
        return None
```

### 3.2 `data/market_nav_refresh.py` 新增

upsert `fund_performance` 表（复用现有表！）：
- `as_of_date = today`
- `nav_latest / nav_date`
- `ret_1m / ret_6m / ret_1y / ret_3y / ret_5y`
- `dd_1y / dd_3y / dd_5y`

**复用** `performance_service.compute_performance()` 计算 ret/dd。

```python
def refresh(session, nav_data: dict[str, pd.DataFrame], task_id=None) -> dict:
    """upsert fund_performance（每个 code 一行 as_of_date=today）"""
    for batch in chunks(codes, 500):
        for code in batch:
            df = nav_data[code]
            perf = compute_performance(df, today=pd.Timestamp.now().normalize())
            # perf = {nav_latest, nav_date, ret_1m, ret_6m, ret_1y, ret_3y, ret_5y, dd_1y, dd_3y, dd_5y}
            upsert fund_performance(code=code, as_of_date=today, **perf)
```

### 3.3 验证

```bash
python -m pytest tests/test_market_nav_refresh.py -v
# 跑一次 fund_performance 补全，dd_3y / ret_5y 字段填满
```

**Review Gate 3**：fund_performance 表 dd_3y / ret_5y 列填满

---

## 阶段 4：业绩比较基准 + 风险指标

### 4.1 `data/market_benchmark_fetcher.py` 新增

```python
"""
全市场业绩比较基准并发 fetcher
复用现有 benchmark_fetcher.fetch_benchmark_tri（每只 3s）
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import date, timedelta
from src.data.benchmark_fetcher import fetch_benchmark_tri
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_benchmark")
MAX_WORKERS = 5
DELAY_S = 0.2


def fetch_market_benchmark(codes: list[str], max_workers=MAX_WORKERS) -> dict[str, tuple]:
    """并发拉全市场业绩比较基准 TRI。返回 {code: (DataFrame, source)}。"""
    end = date.today()
    start = end - timedelta(days=365 * 3)
    out: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe_fetch, code, start, end): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            result = future.result()
            if result is not None:
                out[code] = result
    return out


def _safe_fetch(code, start, end):
    time.sleep(DELAY_S)
    try:
        return fetch_benchmark_tri(code, start, end)
    except Exception as e:
        logger.warning("fetch_benchmark_tri %s 失败: %s", code, str(e)[:120])
        return None
```

### 4.2 `data/market_risk_refresh.py` 新增

```python
"""
全市场风险指标计算（基于 fund_performance + fund_benchmark）

复用现有 risk_service.refresh_fund_risks 单只逻辑，并发包装
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from src.services.risk_service import refresh_fund_risk_for_single_fund
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_risk")
MAX_WORKERS = 5


def refresh(session, codes: list[str], task_id=None) -> dict:
    """并发计算风险指标"""
    # 加载日频净值缓存 / 业绩基准缓存
    # 对每只基金调 refresh_fund_risk_for_single_fund（新增的 helper）
    pass
```

**复用现有** `refresh_fund_risks()`，但需要拆分出 per-fund 函数（重构小）。

### 4.3 验证

```bash
python -m pytest tests/test_market_risk_refresh.py -v
# 跑一次风险指标全市场补全
```

**Review Gate 4**：fund_risk_metrics 表 sharpe / IR / α / γ 列填满

---

## 阶段 5：前端「全量刷新」按钮 + 4 阶段串联

### 5.1 `scheduler/tasks.py` 加 `refresh_market_full_sync`

```python
def refresh_market_full_sync(
    universe_filter: list[str] | None = None,  # market_subtype 子集；None = 全 universe
    min_age: float | None = None,              # 成立年限 ≥ X（先 SQL 过滤）
    min_size_yi: float | None = None,          # 规模 ≥ Y（先 SQL 过滤）
    preset_task_id: str | None = None,
) -> dict:
    """市场 tab 全量数据 refresh：4 阶段流水线（用户先筛年限/规模 → 减少 universe）。

    阶段：
      L1 rankhandler 业绩 (50 秒)
      L2 fund_basic 经理/类型 (30 分钟)
      L3 日频净值 + dd/ret (22 分钟)
      L4 业绩基准 + 风险指标 (44 分钟)

    返回：{task_id, universe_size, stage_results}
    """
    import json as _json
    import uuid as _uuid

    task_id = preset_task_id or str(_uuid.uuid4())
    db = SessionLocal()
    try:
        # 1. 加载 universe（funds 表 is_active + market_subtype + 年限/规模 过滤）
        codes = _load_market_universe(db, universe_filter, min_age, min_size_yi)
        logger.info(
            "[market_full] task=%s universe=%d 只 (filter: min_age=%s min_size_yi=%s)",
            task_id, len(codes), min_age, min_size_yi,
        )

        results = {}

        # L1 rankhandler 业绩
        results["L1"] = _run_stage(db, task_id, "L1_rank", len(codes),
                                     lambda: refresh_market_rank(db, fetch_market_rank_bulk(...)))

        # L2 fund_basic 经理/类型（仅 universe codes）
        results["L2"] = _run_stage(db, task_id, "L2_basic", len(codes),
                                     lambda: refresh_market_basic(db, codes))

        # L3 日频净值 + 性能指标
        results["L3"] = _run_stage(db, task_id, "L3_nav", len(codes),
                                     lambda: refresh_market_nav(db, codes))

        # L4 业绩基准 + 风险指标
        results["L4"] = _run_stage(db, task_id, "L4_risk", len(codes),
                                     lambda: refresh_market_risk(db, codes))

        return {"task_id": task_id, "universe_size": len(codes), "stage_results": results}
    finally:
        db.close()


def _load_market_universe(
    db,
    universe_filter: list[str] | None = None,
    min_age: float | None = None,
    min_size_yi: float | None = None,
) -> list[str]:
    """加载股基·市场 + 债基·市场 universe 的 code 列表。

    按 market_subtype + 可选年限/规模过滤；按 SQL 预过滤减少拉取量。
    """
    from src.data.market_subtype_map import (
        DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES
    )
    all_types = list(DISCOVERY_BOND_SUBTYPES) + list(DISCOVERY_STOCK_SUBTYPES)
    if universe_filter:
        all_types = [t for t in all_types if t in universe_filter]
    q = select(Fund.code).where(
        Fund.is_active == True, Fund.market_subtype.in_(all_types)
    )
    if min_age is not None:
        q = q.where(Fund.age_years >= min_age)
    if min_size_yi is not None:
        q = q.where(Fund.size_yi >= min_size_yi)
    return list(db.execute(q).scalars().all())


def _run_stage(db, task_id, stage_name, total_codes, fn) -> dict:
    """跑单阶段，写进度到 RefreshRun。"""
    run = RefreshRun(task_id=f"{task_id}_{stage_name}", status="running", total=total_codes)
    db.add(run); db.commit()
    try:
        result = fn()
        run.status = "done"
        run.completed = total_codes
        run.finished_at = datetime.now(UTC)
        db.commit()
        return result
    except Exception as e:
        run.status = "error"
        run.errors = _json.dumps([str(e)[:200]], ensure_ascii=False)
        run.finished_at = datetime.now(UTC)
        db.commit()
        return {"error": str(e)[:200]}
```

### 5.2 `api/routes.py` 加 `/discovery-{bond,stock}/full/refresh` 端点

```python
@router_discovery_bond.get("/full/refresh", response_model=RefreshResponse)
async def discovery_bond_full_refresh(
    background: BackgroundTasks,
    scope: str = Query("all", pattern="^(all|bond|stock)$"),
    min_age: float | None = Query(None, ge=0, le=100),
    min_size_yi: float | None = Query(None, ge=0, le=10000),
):
    """手动触发市场 tab 全量 refresh（4 阶段流水线）

    用户可在调用前先按年限/规模过滤，避免拉全 universe：
      GET /api/funds/discovery-bond/full/refresh?min_age=5&min_size_yi=10
    """
    task_id = str(uuid.uuid4())
    universe_filter = None if scope == "all" else (
        DISCOVERY_BOND_SUBTYPES if scope == "bond" else DISCOVERY_STOCK_SUBTYPES
    )
    background.add_task(
        refresh_market_full_sync,
        universe_filter=universe_filter,
        min_age=min_age, min_size_yi=min_size_yi,
        preset_task_id=task_id,
    )
    return RefreshResponse(task_id=task_id, status="started")
```

discovery-stock 同理。

### 5.3 前端「全量刷新」按钮 + 预筛选表单 + 筛选面板拆分

**核心 UX**：
- **「全量刷新」按钮旁的预筛选表单**：年限 / 规模 / 经理 / 净值天数（基础维度）
- **左侧筛选面板**（始终显示所有维度）：
  - **预筛选维度**（年限/规模/经理）：refresh 完成后从预筛选表单**同步过来**，**灰色 disabled 不可改**
  - **业绩维度**（基金类型/排除 QDII/夏普）：正常可调

**用户视角完整流程**：
1. 进入「股基·市场」tab
2. 顶部 FundsHeader 三个按钮：「刷新名单」「仅拉业绩」「**全量刷新**」
3. 「全量刷新」按钮旁边展开**预筛选表单**：年限 ≥ 5 / 规模 ≥ 10 / 经理 ≥ 3 / 净值天数 ≤ 30
4. 左筛选面板：基金类型（10+14 子类多选）、排除 QDII、夏普
5. 用户调好预筛选 → 点「开始全量刷新」→ 弹窗显示 4 阶段进度（~1.5h）
6. **refresh 期间**：预筛选表单锁定
7. refresh 完成 → 弹窗关闭 → 表格自动 reload → **预筛选值同步到左侧筛选面板**（年限/规模/经理输入框变灰色，但显示当前值）
8. 用户现在可以用**左侧业绩维度**（基金类型/排除 QDII/夏普）自由筛选；**预筛选维度不可改**（避免列表突变）

**为什么 disabled 预筛选维度**：
- 预筛选值已决定"拉了哪些基金"，改了会改变 universe → 用户感受不到变化（数据未拉）
- 灰色展示让用户看到当前生效的过滤范围
- 想改预筛选 → 点「全量刷新」按钮重新拉

```typescript
// RefreshStatusPopover 内含预筛选表单
function FullRefreshDialog({ open, onClose, currentFilters, onFiltersChange }) {
  const [minAge, setMinAge] = useState(3);
  const [minSizeYi, setMinSizeYi] = useState(5);
  const [minMgrYears, setMinMgrYears] = useState(null);
  const [maxNavStaleDays, setMaxNavStaleDays] = useState(30);
  const [refreshing, setRefreshing] = useState(false);

  return (
    <Dialog open={open}>
      <h3>全量刷新</h3>
      <p>以下预筛选条件用于缩小拉取范围（拉到约 600 只基金）</p>
      <div>
        <label>成立年限 ≥ <input type="number" value={minAge} onChange={...} disabled={refreshing} /></label>
        <label>规模 ≥ <input type="number" value={minSizeYi} onChange={...} disabled={refreshing} /></label>
        <label>经理从业 ≥ <input type="number" value={minMgrYears} onChange={...} disabled={refreshing} /></label>
        <label>净值新鲜度 ≤ <input type="number" value={maxNavStaleDays} onChange={...} disabled={refresh} /> 天</label>
      </div>
      <button onClick={startRefresh} disabled={refreshing}>
        {refreshing ? '刷新中...' : '开始全量刷新'}
      </button>
      {refreshing && <ProgressBar stages={...} />}
    </Dialog>
  );
}
```

```typescript
// FilterPanel：保留所有维度，预筛选维度 disabled
function FilterPanel({ filters, lockedFields = [], ... }) {
  return (
    <div>
      {dimensions.map(dim => (
        <DimensionControl
          key={dim.key}
          dim={dim}
          value={filters[dim.key]}
          disabled={lockedFields.includes(dim.key)}  // 预筛选维度 locked
          onChange={v => onChange(dim.key, v)}
        />
      ))}
      ...
    </div>
  );
}

// discovery-* tab 的 lockedFields：
const DISCOVERY_LOCKED = ['min_age', 'min_size_yi', 'min_mgr_exp'];
// 从 refresh 时的预筛选值同步过来（page 组件持有 refresh 时设的状态）
```

```typescript
// 页面层
function DiscoveryStockPageInner() {
  const [preFilters, setPreFilters] = useState({
    min_age: 3, min_size_yi: 5, min_mgr_exp: null,
  });
  const [showFullRefresh, setShowFullRefresh] = useState(false);

  return (
    <main>
      <FundsHeader onFullRefreshClick={() => setShowFullRefresh(true)} />

      <FullRefreshDialog
        open={showFullRefresh}
        onClose={() => setShowFullRefresh(false)}
        onComplete={(filters) => {
          // 同步到左侧筛选面板（预筛选维度）
          setPreFilters(filters);
          setShowFullRefresh(false);
          reload();  // 表格自动 reload
        }}
      />

      <FilterPanel
        filters={{ ...filters, ...preFilters }}  // 预筛选维度值覆盖（locked 后用户改不动）
        lockedFields={['min_age', 'min_size_yi', 'min_mgr_exp']}
        ...
      />
    </main>
  );
}
```

```typescript
// DimensionControl 加 disabled 支持
function DimensionControl({ dim, value, onChange, disabled = false }) {
  return (
    <div ...>
      <input
        type="number"
        ...
        disabled={disabled}
        className={disabled ? 'opacity-50 cursor-not-allowed bg-paper-tint' : ''}
      />
    </div>
  );
}
```

### 5.4 验证

```bash
# 端到端
curl -s 'http://localhost:8095/api/funds/discovery-stock/full/refresh'
# 触发 task 跑 1.5 小时

# 1.5 小时后检查
python -c "
from src.db.session import SessionLocal
from src.db.models import Fund, FundPerformance, FundRiskMetrics, MarketFundRank
from sqlalchemy import select, func
db = SessionLocal()
codes = set(db.execute(select(Fund.code).where(Fund.is_active == True, Fund.market_subtype.in_(...))).scalars().all())
print('fund_performance:', db.execute(select(func.count()).select_from(FundPerformance).where(FundPerformance.code.in_(codes))).scalar())
print('fund_risk_metrics:', db.execute(select(func.count()).select_from(FundRiskMetrics).where(FundRiskMetrics.code.in_(codes))).scalar())
print('market_fund_rank:', db.execute(select(func.count()).select_from(MarketFundRank).where(MarketFundRank.code.in_(codes))).scalar())
db.close()
"
```

**Review Gate 5**：全量刷新跑完后，funds 表字段齐全（fund_type / mgr_* / age_years / size_yi / dd_3y / sharpe / IR / α / ret_* 全填满）

---

## Review Gates 总览

| Gate | 检查项 | 命令 |
|---|---|---|
| 1 | rankhandler fetcher + refresh | `pytest tests/test_market_rank_*` + 实测拉取 |
| 2 | fund_basic 并发 + refresh | `pytest tests/test_market_basic_*` + mgr_* 填满 |
| 3 | 日频净值 + dd/ret 计算 | `pytest tests/test_market_nav_*` + dd_3y/ret_5y 填满 |
| 4 | 业绩基准 + 风险指标 | `pytest tests/test_market_risk_*` + sharpe/IR 填满 |
| 5 | 前端 + 端到端 | 综合测试 + 浏览器手工 |

## ⚠️ 不在范围内（明确排除）

- ❌ **定时任务**（用户明确指示：先不要管定时任务）
- ❌ 债基利率债占比 / 持仓分析（季报慢，MVP 不做）
- ❌ 增量更新（全量刷新每次跑全 universe）
- ❌ 历史业绩快照

## 数据齐全性保证

跑完全量刷新后，市场 tab 的每只基金字段：

| 字段 | 来源 | 阶段 |
|---|---|---|
| code / name | funds | universe refresh (已有) |
| market_subtype / market_type | funds | universe refresh (已有) |
| fund_type（雪球细分类） | funds | **L2** |
| age_years / established_date | funds | **L2** |
| size_yi | funds | **L2**（fund_basic 写，覆盖 universe 拉的） |
| mgr_name / mgr_company / mgr_days / mgr_experience_years | funds | **L2** |
| nav_latest / nav_date / ret_1y / ret_3y / ret_5y / dd_3y | fund_performance | **L3** |
| sharpe / IR / α / γ / excess_3y | fund_risk_metrics | **L4** |
| ret_1w / ret_1m / ret_3m / ret_6m / ret_2y / ret_ytd / ret_all | market_fund_rank | **L1** |

**覆盖率目标**：~4452 只股基 + ~5353 只债基，每只 9 成以上字段有值。

## 验证命令汇总

```bash
# 单阶段
cd backend/fund-select
python -m pytest tests/test_market_rank_fetcher.py tests/test_market_basic_refresh.py \
  tests/test_market_nav_refresh.py tests/test_market_risk_refresh.py -v

# 实测全量
python -c "from src.scheduler.tasks import refresh_market_full_sync; print(refresh_market_full_sync())"
# 跑 ~1.5 小时

# 前端
cd apps/fund-select
pnpm tsc --noEmit
pnpm build
```
