# 股票基金筛选 tab — Technical Design

> 严格参照现 apps/fund-select（债基）实现，保持代码一致性。复用 `useFilters` / `FilterPanel` / `FundTable` / `FundAchievementRank` 等契约最小化新增面。

## 1. 边界 (Boundaries)

**In scope（第一阶段）**：
- 后端：新增 `src/data/achievement_fetcher.py`、`FundAchievementRank` 模型、`screen_stock` filter service、`refresh_stock_funds_sync` 任务、`/api/funds/stock/*` 路由组、`config/funds_stock.yaml`。
- 前端：新增 `app/stock/page.tsx`、`components/FundsHeader.tsx`、扩展 `lib/api.ts` + `lib/hooks.ts`，扩展 `lib/useFilters` 接受 initial override。
- 测试：新增 `tests/test_achievement_fetcher.py`、`tests/test_stock_filter_service.py`。

**Out of scope（第二阶段 PRD 单开）**：
- 业绩比较基准 / IR / 选股 α / 择时 γ / 选股 α IR / 夏普比率 — 全部不实现。

**不复用债基的**：
- 不与债基页共享 `useFilters` 实例（useState 隔离，每个 page 自己的 useFilters）。
- 不把现有 `funds` 表中已有债基数据搬到股票筛选（不混用）。

## 2. 现有契约（参照债基，复用基础）

| 契约 | 现实现（后端）| 复用方式 |
|---|---|---|
| DB 自动建表 | `init_db()` 调 `Base.metadata.create_all(engine)` | 直接复用，新表加进 Base 即可（无 alembic 迁移）|
| Fund 模型 | `code / name / fund_type / size_yi / age_years / mgr_* / is_active` | **不改 schema**，新增股票基金由现有 Fund 容纳 |
| FundPerformance 模型 | `ret_1m/6m/1y/3y/5y` + `dd_1y/3y/5y` | **不改 schema**，新增字段直接读 |
| FundFees 模型 | 管理 / 托管 / 销售服务 | **不改 schema** |
| 配置 yaml | `version`, `funds: [6 位代码]` 数组 | 复用结构，新增 `funds_stock.yaml` |
| 名单元数据 | `src/data/fund_universe.py` 提供 `load_fund_codes(path=None)` | 复用，传入不同 path 即可 |
| refresh 主流程 | `refresh_configured_funds_sync(limit)`、`snapshot_fund(...)` | 复用，新增分支 |
| APIRouter 前缀 | `/api/funds/*`（主路由文件 `routes.py`）| 新增 `router_stock = APIRouter(prefix="/stock")`，主 `app.include_router(router_stock)` |
| 前端 basePath | `/funds` | 复用 |
| 前端 BASE | `/funds/api/funds` (`api.ts`) | 扩展常量，给股票：`/funds/api/funds/stock` |
| 共享组件 | `FilterPanel` / `FilterSheet` / `FilterChipBar` / `FundTable` / `ExportCsvButton` / `RefreshStatusPopover` / `CompareDrawer` / `CompareFloatingBar` | **直接复用**，不改 props 契约 |
| `useFilters` | 同步 URL + 默认值 | **扩展**接受 `initial?: FundFilters` 覆盖默认（见 §3.3） |

## 3. 后端设计

### 3.1 新增 fetcher：`src/data/achievement_fetcher.py`

```python
"""
业绩排名 fetcher（雪球源）：按周期返回区间收益 / 区间最大回撒 / 同类排名
源：ak.fund_individual_achievement_xq(symbol)
返回 DataFrame: columns = [业绩类型, 周期, 本产品区间收益, 本产品最大回撒, 周期收益同类排名]
失败抛异常；无数据返回空 DataFrame。
"""
import akshare as ak
import pandas as pd


def fetch_achievement(code: str) -> pd.DataFrame:
    df = ak.fund_individual_achievement_xq(symbol=code)
    if df.empty:
        return df
    df["code"] = code
    return df
```

仅一只函数，调用模式与 `nav_fetcher.fetch_nav`、`basic_fetcher.fetch_basic` 一致。

### 3.2 新增模型：`src/db/models.py`

```python
class FundAchievementRank(Base):
    """业绩排名（雪球 achievement_xq）
    每只基金多条记录，(code, period_kind, period) 复合主键。
    第一阶段只入库 schema、不展示"周期最大回撒"列（决策 7：避免与窗口回撤混淆）。
    但 achievement_xq 一次返回多周期，全量入表便于未来展示拓展。
    """
    __tablename__ = "fund_achievement_rank"
    code = Column(String(6), primary_key=True)
    period_kind = Column(String(32), primary_key=True)   # 年度业绩 / 季度业绩 / 周业绩
    period = Column(String(32), primary_key=True)         # 1y / 3y / 5y / 2025 / ...
    ret = Column(Float, nullable=True)
    max_dd = Column(Float, nullable=True)
    peer_rank = Column(String(32), nullable=True)        # '1694/5606'
    as_of_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))
```

### 3.3 新增 filter service：`src/services/filter_service.py`

复用现有 `FilterService` class，新增 `screen_stock(...)` method，**不共享现有 screen 的 sort 字段白名单**——sort 字段集合允许 `'ret_3y', 'ret_5y', 'peer_rank_1y'` 等扩展（按实现期枚举枚举决定）。

```python
def screen_stock(self, *, min_age, min_size_yi, max_dd_3y, min_mgr_exp,
                  peer_rank_periods: dict[str, str] | None = None,
                  sort: str = "size_yi", order: str = "desc") -> ScreenResponse:
    """按 fund_type IN ('股票型-%', 'QDII%') 过滤现有 Fund 模型。
    rank 子筛选（可选）：只暴露同行号合约，前端不暴露 rank 筛选 UI（第一阶段。
    """
    q = (
        select(Fund, FundPerformance, FundFees)
        .join(FundPerformance, Fund.code == FundPerformance.code, isouter=True)
        .join(FundFees, Fund.code == FundFees.code, isouter=True)
        .where(Fund.is_active.is_(True))
        .where(
            or_(
                Fund.fund_type.like("股票型-%"),
                Fund.fund_type.like("QDII%"),
                Fund.fund_type == "QDII",
            )
        )
    )
    # 应用四维度筛选（同 screen 现有逻辑，不再赘述）
    ...
    return ScreenResponse(total=len(items), items=[FundListItem(**...) for ... in items])
```

实现参考现有 `FilterService.screen` 行 47-58（白名单 `sort` 字段），保持显式白名单避免 SQL injection。

### 3.4 Refresh 流程改造：`src/scheduler/tasks.py` + `src/services/refresh_service.py`

`refresh_service.snapshot_fund(code, mgr_worktime, mgr_company)` 新增分支：传入 fund_type 后决定是否跑 achievement_fetcher；persistence 中 upsert `FundAchievementRank`（先 `delete` 当前 code + `insert` 新行）。

**改动点（伪代码）**：

```python
def snapshot_fund(code, mgr_worktime, mgr_company, today=None):
    ...
    # 1-4. 同现状
    out["is_active"] = True
    out["achievement"] = None  # 默认空

    # 5. 仅股票型 + QDII 跑 achievement（避免无谓请求）
    if out["fund_type"].startswith("股票型-") or out["fund_type"].startswith("QDII"):
        try:
            ach_df = fetch_achievement(code)
            if not ach_df.empty:
                out["achievement"] = ach_df
        except Exception as e:
            logger.warning("achievement_xq 失败 %s: %s", code, str(e)[:150])
    return out
```

`persist_snapshot(db, snap)` 新增：

```python
if snap.get("achievement") is not None and not snap["achievement"].empty:
    _replace_achievement(db, snap["code"], snap["achievement"], snap["achievement_as_of_date"])
```

> 注意：`FundAchievementRank` 表**不存** max_dd 列？— 经决策 7，最终保留 schema 列但前端不展示（保留拓展性）。如需更紧，可只入 ret + peer_rank。第一版全入。

### 3.5 新增刷新任务：`src/scheduler/tasks.py`

```python
def refresh_stock_funds_sync(limit: int | None = None, preset_task_id: str | None = None) -> dict:
    """读 config/funds_stock.yaml，按股票/QDII 名单跑 snapshot_fund。"""
    codes = load_fund_codes(get_stock_funds_config_path())
    ...  # 与 refresh_configured_funds_sync 同骨架
```

`get_stock_funds_config_path()` 加在 `src/utils/config.py`，对偶 `get_funds_config_path`。

### 3.6 新增路由：`src/api/routes.py`

```python
router_stock = APIRouter(prefix="/stock", tags=["stock"])

@router_stock.get("/screen", response_model=ScreenResponse)
async def stock_screen(...): ...

@router_stock.get("/export/csv")
async def stock_export_csv(...): ...

@router_stock.get("/{code}", response_model=FundDetailResponse)
async def stock_fund_detail(code, db=Depends(get_db)): ...

@router_stock.get("/refresh", response_model=RefreshResponse)
async def stock_refresh(background: BackgroundTasks, limit: int | None = None): ...

@router_stock.get("/refresh/status", response_model=RefreshStatusResponse)
async def stock_refresh_status(...): ...

@router_stock.get("/stats", response_model=StatsResponse)
async def stock_stats(db=Depends(get_db)): ...
```

主入口 `src/main.py` 添加 `app.include_router(router_stock)`。`/api/funds/health` 保持顶端。

### 3.7 FundListItem 增量列

现有 `FundListItem` 已基本满足展示，无需新增列。同类排名（peer_rank）单独接口拉取（在 detail 接口返回；列表页不展开）。

`FundDetailResponse` 加字段：

```python
class FundAchievementRankDTO(BaseModel):
    period_kind: str
    period: str
    ret: Optional[float] = None
    peer_rank: Optional[str] = None

class FundDetailResponse(BaseModel):
    ...
    achievement_ranks: list[FundAchievementRankDTO] = []
```

## 4. 前端设计

### 4.1 路由布局（Next.js app router）

```
apps/fund-select/src/app/
├── layout.tsx                 # 现存 root layout（继承，无改动）
├── page.tsx                   # 现存 /funds → 债基（几乎不动，仅 nav 链接从硬编码的"← 返回首页"改成 FundsHeader）
├── globals.css
└── stock/
    └── page.tsx               # 新增 /funds/stock 入口
```

`app/stock/page.tsx` 几乎照搬 `app/page.tsx`，差异：
- `useFilters(STOCK_DEFAULT_FILTERS)`（见 §3.3）
- `fundApi.screen` → `stockApi.screen`
- 顶 header 换成 `<FundsHeader active="stock" />`

### 4.2 共用 Header 抽出：`components/FundsHeader.tsx`

```tsx
interface FundsHeaderProps {
  active: 'bond' | 'stock';
}
export function FundsHeader({ active }: FundsHeaderProps) {
  return (
    <header>
      <a href="/">← 返回首页</a>
      <h1>基金筛选</h1>
      <nav>
        <Link href="/funds" aria-current={active === 'bond' ? 'page' : undefined}>债基</Link>
        <Link href="/funds/stock" aria-current={active === 'stock' ? 'page' : undefined}>股票</Link>
      </nav>
      {/* 右侧：ExportCsvButton + RefreshStatusPopover + count */}
    </header>
  );
}
```

> 注：basePath 由 Next.js 自动加在 `<Link>`，fetch 走完整路径（`/funds/api/...`）。原 `<a href="/">` 现建议改成 `<Link>`，但保持现状也 OK。

### 4.3 `useFilters` 扩展：`lib/useFilters.ts`

```typescript
export function useFilters(initial?: Partial<FundFilters>) {
  const merged = useMemo(() => ({ ...DEFAULT_FILTERS, ...initial }), [initial]);
  const filters = useMemo(() => parseFiltersFromSearch(searchParams, merged), [searchParams, merged]);
  ...
}
```

`parseFiltersFromSearch` 接受第二参数 fallback，新增：

```typescript
export function parseFiltersFromSearch(search: URLSearchParams, fallback: FundFilters = DEFAULT_FILTERS): FundFilters { ... }
```

> 注意：债基页调 `useFilters()` 走原有默认值；股票页调 `useFilters({ min_age: 3, ... })` 覆盖。URL 参数始终优先。

### 4.4 默认值常量

在 `lib/types.ts` 加：

```typescript
export const STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 20,
  min_mgr_exp: 5,
  sort: 'ret_5y',
  order: 'desc',
};
```

> 默认按 `ret_5y desc`（5 年期收益，从高到低）排序，匹配"业绩优先"心智。如果用户倾向 size 也可改。

### 4.5 API 扩展：`lib/api.ts`

```typescript
const STOCK_BASE = '/funds/api/funds/stock';

export const stockApi = {
  screen(filters, signal) { return getJson(`${STOCK_BASE}/screen${buildQuery(filters)}`); },
  getDetail(code) { return getJson(`${STOCK_BASE}/${code}`); },
  refresh(limit) { return getJson(`${STOCK_BASE}/refresh${limit ? `?limit=${limit}` : ''}`); },
  getRefreshStatus(taskId) { ... },
  async exportCsv(filters) { ... },
};
```

### 4.6 Hook 扩展：`lib/hooks.ts`

```typescript
export function useStockFundList(filters: FundFilters) { /* 类同 useFundList，调 stockApi.screen */ }
```

## 5. 数据流

### 5.1 采集 → 入库

```
            ┌─────────────────────────────────────────────────┐
config/funds_stock.yaml   30 只股票型 + QDII 基金代码
            ↓
load_fund_codes(get_stock_funds_config_path())
            ↓
snapshot_fund(code, ...)
   ├─ fetch_basic            → Fund.name / fund_type / size_yi / mgr_*
   ├─ fetch_nav               → nav DataFrame
   │     └─ compute_performance → FundPerformance (ret_1y/3y/5y, dd_1y/3y/5y)
   ├─ fetch_bond_hold         → FundHoldingsBond （第一阶段股票基金不用，但函数留着）
   ├─ fetch_fees              → FundFees
   └─ fetch_achievement [if 股票型/QDII]
                              → FundAchievementRank
            ↓
persist_snapshot(db, snap)
            ↓
SQLite (5 张表：funds / fund_performance / fund_fees / fund_holdings_bond / fund_achievement_rank)
```

### 5.2 列表展示

```
浏览器 /funds/stock
            ↓
useStockFundList(filters)  ──► fetches /funds/api/funds/stock/screen?min_age=3&...
            ↓                              ↑
                                       stock_filter_service.screen_stock()
            ↓                              ↑
                                       SQLite JOIN 5 表（funds outer join others）
            ↓
FundTable（复用现组件）展示行
            ↓
顶部 chip / 筛选 sidebar（复用 FilterPanel，初始值 STOCK_DEFAULT_FILTERS）
```

### 5.3 详情（暂不做，保留）

> 第一阶段主表即详情；如需进 fund detail 页，路由 `/funds/stock/[code]/page.tsx` 后续追加。

## 6. Trade-offs

| 决策 | A 选项 | B 选项 | 选 | 理由 |
|---|---|---|---|---|
| 名单范围 | 全市场自动拉 | 手工 yaml 30 只 | B | 控制规模、可验证、不引入新 fetcher |
| Achievement 入库 | 全入表（含 max_dd）| 仅入 ret + peer_rank | 全入 | schema 多一列不影响代码、未来展示灵活 |
| 排序默认 | size_yi desc | ret_5y desc | ret_5y desc | 股票基金心智"业绩优先" |
| Header 抽出 | 每 page 各写 | 抽 FundsHeader 组件 | 抽 | nav 链接一致、两路由互通 |
| QDII fund_type 匹配 | `fund_type='QDII'` | `LIKE 'QDII%'` | LIKE 兜底 | 实际 QDII 类目有时混排，统一 LIKE |
| 不开 detail 页 | 复用债基 detail | 新开 stock detail | 不开（后续） | 第一阶段聚焦主表 |

## 7. Compatibility / 风险

- **`init_db()` 自动建表**：新加 `FundAchievementRank` 不修改现有表，幂等，老部署升级安全。
- **`get_db()` 用 SQLite `check_same_thread=False`**：FastAPI + 后台采集线程都安全。新路由同样用 `Depends(get_db)`。
- **`refresh_configured_funds_sync` 改动只新增分支**，现有债基刷新逻辑 0 影响。
- **新增 fetcher 失败**：必须不阻塞整个 refresh try/except 包好（参考 nav_fetcher 失败抛出的契约）。
- **achievement_xq 部分基金无"年度业绩"行**：upsert 0 行时 ensure code 没有死锁；空 DataFrame 时删全部旧行后不插入。
- **路由顺序**：`/api/funds/stock/refresh/status` 必须先于 `/api/funds/stock/{code}` 注册（FastAPI 按注册顺序匹配）。本设计单独 router 无歧义。

## 8. Rollback

| 改动 | 回退方式 |
|---|---|
| `config/funds_stock.yaml` | 删文件即可 |
| `FundAchievementRank` 表 | `DROP TABLE fund_achievement_rank` 不会影响其他表 |
| `achievement_fetcher.py` | 删文件 |
| `screen_stock` / `refresh_stock_funds_sync` | 删 method / function 即可 |
| `/api/funds/stock/*` routes | `app.include_router(router_stock)` 删一行 |
| 前端 `app/stock/page.tsx` | 删目录 |
| `FundsHeader` 抽出 | 还原两 page 各自的内联 header |
| `useFilters(initial)` 扩展 | 删除 fallback 参数，还原单参数版本 |

**最坏情况下的全回退**：后端涉及 ~6 个文件、前端涉及 ~4 个文件，git revert 一次即可。

## 9. Files to Add / Modify（清单）

### Backend
- ✏️ `src/db/models.py`：追加 `FundAchievementRank`
- ✏️ `src/services/refresh_service.py`：分支跑 achievement、persistence upsert
- ✏️ `src/services/filter_service.py`：追加 `screen_stock`
- ✏️ `src/scheduler/tasks.py`：追加 `refresh_stock_funds_sync`
- ✏️ `src/utils/config.py`：追加 `get_stock_funds_config_path`
- ✏️ `src/api/routes.py`：追加 `router_stock`
- ✏️ `src/api/models.py`：追加 `FundAchievementRankDTO`、`FundDetailResponse.achievement_ranks`
- ✏️ `src/main.py`：追加 `app.include_router(router_stock)`
- ➕ `src/data/achievement_fetcher.py`
- ➕ `config/funds_stock.yaml`
- ➕ `tests/test_achievement_fetcher.py`
- ➕ `tests/test_stock_filter_service.py`

### Frontend
- ✏️ `lib/useFilters.ts`：扩展接受 initial override
- ✏️ `lib/types.ts`：追加 `STOCK_DEFAULT_FILTERS`、`FundAchievementRank` 类型
- ✏️ `lib/api.ts`：追加 `stockApi`
- ✏️ `lib/hooks.ts`：追加 `useStockFundList`
- ✏️ `app/page.tsx`：把 inline header 改成 `<FundsHeader active="bond" />`
- ➕ `app/stock/page.tsx`
- ➕ `components/FundsHeader.tsx`

### 不变
- ✨ 现有 `Funds` / `FundPerformance` / `FundFees` / `FundHoldingsBond` / `RefreshRun` schema
- ✨ 现有 `compute_performance` / `fetch_basic` / `fetch_nav` / `fetch_fees` / `fetch_bond_hold`
- ✨ 现有 `FilterPanel` / `FilterSheet` / `FilterChipBar` / `FundTable` / `ExportCsvButton` / `RefreshStatusPopover` / `CompareDrawer` / `CompareFloatingBar`
- ✨ 现有 `FilterService.screen`（债基接口不动）
- ✨ 第二阶段字段（业绩基准 / IR / 夏普 / 选股 / 择时 / α-IR）—— 不引入
