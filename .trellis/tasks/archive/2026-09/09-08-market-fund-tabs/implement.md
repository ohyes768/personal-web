# Implement: fund-select 市场筛选 tab

## 概览

按 5 个阶段交付，每阶段独立可验证：

1. **阶段 1：DB schema + fetcher + refresh** — 后端基础
2. **阶段 2：filter_service + API 路由** — 后端筛选能力
3. **阶段 3：scheduler + daily_refresh 接入** — 定时任务
4. **阶段 4：前端 API client + hooks + 类型** — 前端基础
5. **阶段 5：前端页面 + FundsHeader + FilterSidebar** — 前端 UI

每阶段末尾设 review gate。

---

## 阶段 1：DB Schema + fetcher + refresh

### 1.1 改 `db/models.py`

加列：
```python
class Fund(Base):
    ...
    market_type = Column(String(64), nullable=True, index=True)
```

### 1.2 改 `db/session.py`

启动时幂等 `ALTER TABLE`（见 design §2）：
```python
def _ensure_schema(engine):
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(funds)").fetchall()
        names = {row[1] for row in cols}
        if "market_type" not in names:
            conn.exec_driver_sql("ALTER TABLE funds ADD COLUMN market_type VARCHAR(64)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_funds_market_type ON funds(market_type)")
        conn.commit()
```

在 `init_db()` 或 startup hook 里调一次。

### 1.3 新增 `data/market_universe_fetcher.py`

```python
"""
全市场基金名单 fetcher：ak.fund_name_em() 一次拉取。
"""
import akshare as ak
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_universe")

EXPECTED_COLUMNS = ["基金代码", "基金简称", "基金类型"]


def fetch_market_universe() -> pd.DataFrame:
    """返回 DataFrame[code, name, market_type]。失败抛异常。"""
    df = ak.fund_name_em()
    if df.empty:
        return pd.DataFrame(columns=["code", "name", "market_type"])
    out = pd.DataFrame({
        "code": df["基金代码"].astype(str).str.zfill(6),
        "name": df["基金简称"].astype(str).str.strip(),
        "market_type": df["基金类型"].astype(str).str.strip(),
    })
    # 去重（code 唯一）；同名 / 空名保留
    out = out.drop_duplicates("code", keep="first")
    return out.reset_index(drop=True)
```

### 1.4 新增 `services/market_universe_refresh.py`

```python
"""
全市场基金名单 refresh：upsert Fund.name / market_type，不动 fund_type / is_active。
"""
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import Fund, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_refresh")

BATCH_SIZE = 500


def refresh(session: Session, df: pd.DataFrame, task_id: str | None = None) -> dict:
    """upsert，返回 {'total': N, 'inserted': x, 'updated': y, 'failed': z, 'errors': [...]}"""
    total = len(df)
    inserted = updated = failed = 0
    errors: list[str] = []

    run = None
    if task_id:
        run = session.get(RefreshRun, task_id)
        if run:
            run.total = total
            run.started_at = datetime.now(UTC)

    for start in range(0, total, BATCH_SIZE):
        batch = df.iloc[start:start + BATCH_SIZE]
        codes = batch["code"].tolist()
        existing = {
            row.code for row in session.execute(
                select(Fund.code).where(Fund.code.in_(codes))
            ).scalars().all()
        }
        now = datetime.now(UTC)
        for row in batch.itertuples():
            try:
                if row.code in existing:
                    session.execute(
                        update(Fund).where(Fund.code == row.code)
                        .values(name=row.name, market_type=row.market_type, updated_at=now)
                    )
                    updated += 1
                else:
                    session.execute(
                        insert(Fund).values(
                            code=row.code, name=row.name, market_type=row.market_type,
                            fund_type="", is_active=True, updated_at=now,
                        )
                    )
                    inserted += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                if len(errors) < 20:
                    errors.append(f"{row.code}: {str(e)[:120]}")
        session.commit()
        if run:
            run.completed = min(start + BATCH_SIZE, total)
            session.commit()

    if run:
        run.status = "done" if failed == 0 else "error"
        run.failed = failed
        run.errors = json.dumps(errors, ensure_ascii=False)
        run.finished_at = datetime.now(UTC)
        session.commit()

    logger.info("market_refresh: total=%d inserted=%d updated=%d failed=%d", total, inserted, updated, failed)
    return {"total": total, "inserted": inserted, "updated": updated, "failed": failed, "errors": errors}
```

### 1.5 单测

- `tests/test_market_universe_fetcher.py`：mock `ak.fund_name_em` 返回固定 DataFrame
- `tests/test_market_universe_refresh.py`：mock session，验证 insert/update 不动 fund_type / is_active

### 1.6 验证

```bash
cd backend/fund-select
python -c "
from src.data.market_universe_fetcher import fetch_market_universe
df = fetch_market_universe()
print(df['market_type'].value_counts())
print('total:', len(df))
"
python -m pytest tests/test_market_universe_fetcher.py tests/test_market_universe_refresh.py -v
```

**Review Gate 1**：跑通 fetcher 实拉，DB 列存在，upsert 不污染 fund_type。

---

## 阶段 2：filter_service + API 路由

### 2.1 改 `services/filter_service.py`

新增常量与方法：
```python
DEFAULT_DISCOVERY_UNIVERSE = {
    "discovery-bond": ["债券型", "定开债券"],
    "discovery-stock": ["股票型", "指数型", "混合型", "QDII"],
}


def screen_discovery_bond(self, ..., market_types=None):
    return self._screen("discovery-bond", ..., market_types=market_types or DEFAULT_DISCOVERY_UNIVERSE["discovery-bond"])

def screen_discovery_stock(self, ..., market_types=None):
    return self._screen("discovery-stock", ..., market_types=market_types or DEFAULT_DISCOVERY_UNIVERSE["discovery-stock"])
```

`_screen` 签名加 `market_types: list[str] | None = None`，sql 拼接里加：
```python
if market_types is not None:
    if not market_types:
        return {"total": 0, "items": []}  # 显式空 = 无结果
    q = q.where(Fund.market_type.in_(market_types))
```

### 2.2 改 `api/routes.py`

新增两个 router：
```python
router_discovery_bond = APIRouter(prefix="/discovery-bond", tags=["discovery-bond"])
router_discovery_stock = APIRouter(prefix="/discovery-stock", tags=["discovery-stock"])
```

注册路由：
- `GET /discovery-bond/screen` → `FilterService.screen_discovery_bond`
- `GET /discovery-bond/{code}` → 复用 `FilterService.get_detail`
- `GET /discovery-bond/stats` → `universe_stats(kind='discovery-bond')`（复用，但 universe 走 market_type）
- `GET /discovery-bond/refresh` → 触发 `refresh_market_universe_sync`
- `GET /discovery-bond/refresh/status` → 复用 `RefreshRun`

⚠️ `universe_stats(kind)` 当前用 yaml 读 universe 路径，要扩展支持 `kind in {"bond", "stock", "discovery-bond", "discovery-stock"}`：
- bond / stock → 走 yaml
- discovery-* → 走 DEFAULT_DISCOVERY_UNIVERSE + DB market_type IN

### 2.3 单测

```python
def test_screen_discovery_bond_default_universe(): ...
def test_screen_discovery_bond_custom_market_types(): ...  # market_type=债券型
def test_screen_discovery_bond_empty_market_types_returns_zero(): ...
def test_screen_discovery_stock_default_excludes_bonds(): ...
def test_existing_screen_bond_unchanged(): ...  # 关键回归
def test_existing_screen_stock_unchanged(): ...
```

### 2.4 验证

```bash
cd backend/fund-select
python -m uvicorn src.main:app --reload --port 8095

curl -s 'http://localhost:8095/api/funds/discovery-bond/screen' | jq '.total'
curl -s 'http://localhost:8095/api/funds/discovery-stock/screen' | jq '.total'
curl -s 'http://localhost:8095/api/funds/discovery-bond/screen?market_type=债券型' | jq '.total'
curl -s 'http://localhost:8095/api/funds/screen' | jq '.total'  # 应与改前一致
curl -s 'http://localhost:8095/api/funds/stock/screen' | jq '.total'  # 应与改前一致
```

**Review Gate 2**：4 个 screen 接口都通，老接口 total 与改前一致。

---

## 阶段 3：scheduler + daily_refresh 接入

### 3.1 改 `scheduler/tasks.py`

```python
def refresh_market_universe_sync(preset_task_id: str | None = None):
    """全市场基金名单 refresh。"""
    from src.data.market_universe_fetcher import fetch_market_universe
    from src.services.market_universe_refresh import refresh
    from src.db.session import SessionLocal
    from src.db.models import RefreshRun

    task_id = preset_task_id or str(uuid.uuid4())
    session = SessionLocal()
    try:
        run = RefreshRun(task_id=task_id, status="running", total=0)
        session.add(run)
        session.commit()
        df = fetch_market_universe()
        result = refresh(session, df, task_id=task_id)
        return {"task_id": task_id, **result}
    except Exception as e:
        session.rollback()
        run = session.get(RefreshRun, task_id)
        if run:
            run.status = "error"
            run.finished_at = datetime.now(UTC)
            run.errors = json.dumps([str(e)[:200]])
            session.commit()
        raise
    finally:
        session.close()
```

### 3.2 改 `scheduler/daily_refresh.py`

接入定时（建议 06:30，早于现有 07:00 的 yaml refresh）：
```python
# 在 scheduler 注册处
@scheduler.scheduled_job("cron", hour=6, minute=30, id="refresh_market_universe")
def _daily_market_universe():
    refresh_market_universe_sync()
```

### 3.3 改 `api/routes.py` 的 refresh 路由

```python
@router_discovery_bond.get("/refresh", response_model=RefreshResponse)
async def discovery_bond_refresh(background: BackgroundTasks):
    task_id = str(uuid.uuid4())
    background.add_task(refresh_market_universe_sync, preset_task_id=task_id)
    return RefreshResponse(task_id=task_id, status="started")
```

（discovery-stock 的 refresh 路由直接共用同一个 `refresh_market_universe_sync`——只刷新名单，没有按 tab 区分的语义。）

### 3.4 验证

```bash
cd backend/fund-select
python -c "
from src.scheduler.tasks import refresh_market_universe_sync
print(refresh_market_universe_sync())
"
```

数据库 `funds.market_type IS NOT NULL` 数量 ≥ 8000。

**Review Gate 3**：手动触发 refresh 跑通；RefreshRun 状态正确。

---

## 阶段 4：前端 API client + hooks + 类型

### 4.1 改 `lib/types.ts`

```typescript
export interface FundFilters {
  ... // 老字段
  market_types: string[] | null;
}

export const DISCOVERY_BOND_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 5,
  min_mgr_exp: 5,
  min_sharpe: null,
  exclude_qdii: false,
  sort: 'size_yi',
  order: 'desc',
  market_types: ['债券型', '定开债券'],
};

export const DISCOVERY_STOCK_DEFAULT_FILTERS: FundFilters = {
  min_age: 3,
  min_size_yi: 5,
  max_dd_3y: 30,
  min_mgr_exp: 5,
  min_sharpe: 0.8,
  exclude_qdii: false,
  sort: 'ret_5y',
  order: 'desc',
  market_types: ['股票型', '指数型', '混合型', 'QDII'],
};
```

`DEFAULT_FILTERS` / `STOCK_DEFAULT_FILTERS` 加 `market_types: null`。

### 4.2 改 `lib/api.ts`

```typescript
const DISCOVERY_BOND_BASE = '/funds/api/funds/discovery-bond';
const DISCOVERY_STOCK_BASE = '/funds/api/funds/discovery-stock';

export const discoveryBondApi = {
  screen(filters: Partial<FundFilters>, signal?: AbortSignal) { ... },
  getDetail(code: string) { ... },  // 复用 /api/funds/{code}
  getStats() { ... },
  refresh(limit?: number) { ... },
  getRefreshStatus(taskId?: string) { ... },
};

export const discoveryStockApi = { ... 同上 ... };
```

`buildQuery` 加：
```typescript
if (filters.market_types && filters.market_types.length > 0) {
  params.set('market_type', filters.market_types.join(','));
}
```

### 4.3 改 `lib/hooks.ts`

```typescript
export function useDiscoveryBondFundList(filters: FundFilters) {
  // 与 useFundList 同骨架，调 discoveryBondApi.screen
}

export function useDiscoveryStockFundList(filters: FundFilters) {
  // 与 useStockFundList 同骨架，调 discoveryStockApi.screen
}
```

### 4.4 改 `lib/useFilters.ts`

URL 序列化：
```typescript
function filtersToSearch(filters: FundFilters): URLSearchParams {
  ...
  if (filters.market_types && filters.market_types.length > 0) {
    params.set('market_type', filters.market_types.join(','));
  }
  return params;
}
```

`parseFiltersFromSearch`：
```typescript
const marketTypeRaw = search.get('market_type');
if (marketTypeRaw) {
  filters.market_types = marketTypeRaw.split(',').map(s => s.trim()).filter(Boolean);
} else {
  filters.market_types = null;
}
```

`clearAll` 把 `market_types: null` 加上。

### 4.5 验证

```bash
cd apps/fund-select
pnpm tsc --noEmit
```

**Review Gate 4**：tsc 通过，老 type 不破坏。

---

## 阶段 5：前端页面 + FundsHeader + FilterSidebar

### 5.1 改 `components/FundsHeader.tsx`

```typescript
type FundsTab = 'bond' | 'stock' | 'discovery-bond' | 'discovery-stock';

interface FundsHeaderProps {
  active: FundsTab;
  ...
  exportKind: FundsTab;
}

export function FundsHeader({ active, ..., exportKind }: FundsHeaderProps) {
  const title = {
    'bond': '债券基金筛选',
    'stock': '股票基金筛选',
    'discovery-bond': '债券基金·市场',
    'discovery-stock': '股票基金·市场',
  }[active];

  // RefreshStatusPopover URL
  const refreshUrl = {
    'stock': '/funds/api/funds/stock/refresh',
    'discovery-bond': '/funds/api/funds/discovery-bond/refresh',
    'discovery-stock': '/funds/api/funds/discovery-stock/refresh',
  }[exportKind];
  const statusUrl = refreshUrl?.replace('/refresh', '/refresh/status');

  return (
    <header ...>
      ...
      <TabLink href="/bond" active={active === 'bond'}>债基</TabLink>
      <TabLink href="/stock" active={active === 'stock'}>股票</TabLink>
      <TabLink href="/discovery-bond" active={active === 'discovery-bond'}>债基·市场</TabLink>
      <TabLink href="/discovery-stock" active={active === 'discovery-stock'}>股基·市场</TabLink>
      ...
    </header>
  );
}
```

### 5.2 改 `components/FilterSidebar.tsx`

新增 `MARKET_TYPE_DIMENSION`：
```typescript
export const MARKET_TYPE_DIMENSION: FilterDimension = {
  key: 'market_types',
  label: '基金类型',
  type: 'multi-select',
  options: [
    { value: '债券型', label: '债券型' },
    { value: '定开债券', label: '定开债券' },
    { value: '股票型', label: '股票型' },
    { value: '指数型', label: '指数型' },
    { value: '混合型', label: '混合型' },
    { value: 'QDII', label: 'QDII' },
    { value: '货币型', label: '货币型' },
    { value: 'FOF', label: 'FOF' },
  ],
};

export const DISCOVERY_BOND_DIMENSIONS = [/* 老 4 维 + 市场类型 */];
export const DISCOVERY_STOCK_DIMENSIONS = [...];
```

`FilterPanel` 与 `FilterSheet` 的 `onChange` 透传 `market_types: string[]`。

### 5.3 改 `components/FilterChipBar.tsx`

新增 market_types chip：移除时置 `[]` 或 `null`（按 tab 默认值决定）。

### 5.4 新增 `app/discovery-bond/page.tsx`

```typescript
'use client';

import { useFilters } from '@/lib/useFilters';
import { DISCOVERY_BOND_DEFAULT_FILTERS, type FundListItem } from '@/lib/types';
import { useDiscoveryBondFundList, useCompare, useFeeDetails } from '@/lib/hooks';
import { FundsHeader } from '@/components/FundsHeader';
import { FilterPanel, DISCOVERY_BOND_DIMENSIONS } from '@/components/FilterSidebar';
import { FilterSheet } from '@/components/FilterSheet';
import { FilterChipBar } from '@/components/FilterChipBar';
import { FundTable } from '@/components/FundTable';
import { RowDetailDrawerBond } from '@/components/RowDetailDrawerBond';
import { CompareDrawer } from '@/components/CompareDrawer';
import { CompareFloatingBar } from '@/components/CompareFloatingBar';

export default function DiscoveryBondPage() {
  // 与 bond/page.tsx 同骨架：
  // - useFilters(DISCOVERY_BOND_DEFAULT_FILTERS)
  // - useDiscoveryBondFundList(filters)
  // - FundsHeader active='discovery-bond' exportKind='discovery-bond'
  // - FundTable showBondColumns
  // - FilterPanel dimensions=DISCOVERY_BOND_DIMENSIONS
  // - RowDetailDrawerBond
}
```

### 5.5 新增 `app/discovery-stock/page.tsx`

```typescript
// 与 stock/page.tsx 同骨架：
// - useFilters(DISCOVERY_STOCK_DEFAULT_FILTERS)
// - useDiscoveryStockFundList
// - FundsHeader active='discovery-stock' exportKind='discovery-stock'
// - FundTable showRiskColumns
// - RowDetailDrawer (非 Bond 版)
```

### 5.6 新增 layout 文件

```typescript
// app/discovery-bond/layout.tsx
export const metadata: Metadata = { title: '债券基金·市场' };
export default function Layout({ children }) { return children; }

// app/discovery-stock/layout.tsx
export const metadata: Metadata = { title: '股票基金·市场' };
export default function Layout({ children }) { return children; }
```

### 5.7 验证

```bash
cd apps/fund-select
pnpm tsc --noEmit
pnpm lint
pnpm build
pnpm dev  # 浏览器访问 /funds/discovery-bond 和 /funds/discovery-stock
```

手工验证清单：
- 4 tab 都能渲染
- 切换 tab URL 同步
- 筛选项变更触发重拉
- 老 tab `/funds/bond`、`/funds/stock` 数据不变
- 筛选维度（min_age、min_size_yi、max_dd_3y、min_mgr_exp、market_types）正常工作
- 单只详情跳转正常
- 刷新按钮触发后端 refresh，弹窗显示进度

**Review Gate 5**：4 tab UI 一致、筛选有效、老 tab 不破坏。

---

## Review Gates 总览

| Gate | 检查项 | 命令 |
|---|---|---|
| 1 | schema + fetcher + refresh | `pytest tests/test_market_universe_* -v` + 实拉 |
| 2 | filter_service + API 路由 | curl 4 接口，total 对比 |
| 3 | scheduler | 手动触发 refresh，DB 计数 |
| 4 | 前端类型 + API client | `pnpm tsc --noEmit` |
| 5 | 前端页面 | `pnpm build` + 浏览器手工 |

## Rollback 节点

| 阶段 | 回滚方法 |
|---|---|
| 1 | 删 fetcher + refresh 文件；market_type 列保留（NULL） |
| 2 | 删 router；filter_service 还原 |
| 3 | scheduler 移除 cron job |
| 4 | git revert 类型/api/hooks 变更 |
| 5 | 删 app/discovery-* 目录；FundsHeader 还原 |

每个阶段独立可回滚，不影响其他阶段。

## 验证命令汇总

```bash
# 后端
cd backend/fund-select
python -m pytest tests/ -v
python -m uvicorn src.main:app --reload --port 8095

curl -s 'http://localhost:8095/api/funds/discovery-bond/screen' | jq '.total'
curl -s 'http://localhost:8095/api/funds/discovery-stock/screen' | jq '.total'
curl -s 'http://localhost:8095/api/funds/discovery-bond/screen?market_type=债券型' | jq '.total'
curl -s 'http://localhost:8095/api/funds/screen' | jq '.total'  # 老接口不变
curl -s 'http://localhost:8095/api/funds/stock/screen' | jq '.total'  # 老接口不变

# 前端
cd apps/fund-select
pnpm tsc --noEmit
pnpm lint
pnpm build
pnpm dev
```

## 不在范围内（明确排除）

- 二级分类
- 自动清盘判断
- 跨 tab 收藏
- 新增详情页字段
- 实时行情
