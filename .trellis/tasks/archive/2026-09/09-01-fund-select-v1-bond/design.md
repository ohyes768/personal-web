# 基金筛选平台 v1 - 技术设计

> 基于 PRD 编写。复杂任务，包含前后端 + 定时采集 + 对比交互。

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户浏览器 (Chrome)                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Next.js 15 Frontend (port 3005, basePath=/funds)                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ /funds/page.tsx                                              │    │
│  │ ├─ <FilterSidebar> (左, 桌面) / <FilterSheet> (底, 移动)    │    │
│  │ ├─ <FilterChipBar> (顶)                                     │    │
│  │ ├─ <FundTable> (中)                                         │    │
│  │ │   └─ 行末 <CompareButton>                                 │    │
│  │ ├─ <CompareFloatingBar> (底, 选中后浮出)                    │    │
│  │ └─ <CompareDrawer> (右抽屉) → <CompareTable<T>>             │    │
│  │                                                              │    │
│  │ Hooks: useFilters, useCompare<T>, useFunds (SWR/fetch)      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  /api/funds/[...path]/route.ts  ← catch-all 代理 → 后端            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP (proxy)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8095)                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ API Layer (src/api/)                                         │    │
│  │ ├─ routes.py     GET /funds/screen, /funds/{code}, /refresh │    │
│  │ └─ models.py     Pydantic DTOs                              │    │
│  ├─────────────────────────────────────────────────────────────┤    │
│  │ Service Layer (src/services/)                                │    │
│  │ ├─ filter_service.py     筛选逻辑                            │    │
│  │ ├─ performance_service.py 业绩/回撤计算                      │    │
│  │ ├─ export_service.py     CSV 导出                            │    │
│  │ └─ refresh_service.py     刷新进度跟踪                       │    │
│  ├─────────────────────────────────────────────────────────────┤    │
│  │ Data Layer (src/data/ + src/db/)                             │    │
│  │ ├─ fund_basic_fetcher.py   ak.fund_individual_basic_info_xq │    │
│  │ ├─ nav_fetcher.py          ak.fund_open_fund_info_em        │    │
│  │ ├─ manager_fetcher.py      ak.fund_manager_em               │    │
│  │ ├─ holdings_fetcher.py     东财 FundArchivesDatas.aspx      │    │
│  │ ├─ fee_fetcher.py          费率（契约 cache/fees_*.json）   │    │
│  │ ├─ bond_classifier.py      利率/信用/可转债分类              │    │
│  │ ├─ db.py                   SQLAlchemy + SQLite               │    │
│  │ └─ models.py               ORM 模型                          │    │
│  ├─────────────────────────────────────────────────────────────┤    │
│  │ Scheduler (src/scheduler/)                                   │    │
│  │ └─ daily_refresh.py   每日拉取 config/funds.yaml 31 只      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└────────┬──────────────────────┬──────────────────────────┬─────────┘
         │                      │                          │
         ▼                      ▼                          ▼
   ┌──────────┐           ┌──────────┐              ┌──────────┐
   │  akshare │           │ 东方财富  │              │ SQLite   │
   │  (Python │           │ (HTTP    │              │ data/    │
   │   lib)   │           │  季报)   │              │ funds.db │
   └──────────┘           └──────────┘              └──────────┘
```

## 2. 后端模块设计

### 2.1 目录结构（与 dividend-select 对齐）

```
backend/
├── pyproject.toml                # uv 依赖管理
├── .env / .env.local             # 环境变量（git ignore）
├── README.md
├── data/
│   └── funds.db                  # SQLite 数据库
├── cache/                        # 原始 JSON 响应缓存（已有目录）
│   ├── bond_hold_*.json
│   └── manager_em.json
├── src/
│   ├── main.py                   # FastAPI app + lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py             # 路由
│   │   └── models.py             # Pydantic
│   ├── services/
│   │   ├── __init__.py
│   │   ├── filter_service.py     # 筛选逻辑（核心）
│   │   ├── performance_service.py # 业绩计算（回撤/收益）
│   │   ├── export_service.py     # CSV
│   │   └── refresh_service.py    # 刷新进度
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fund_basic_fetcher.py
│   │   ├── nav_fetcher.py
│   │   ├── manager_fetcher.py
│   │   ├── holdings_fetcher.py
│   │   ├── fee_fetcher.py        # 费率（补回；契约 cache/fees_*.json）
│   │   ├── bond_classifier.py    # 利率债/信用债/可转债
│   │   └── fund_universe.py      # 读 config/funds.yaml，不扫全市场
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py             # ORM
│   │   └── session.py            # engine + SessionLocal
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── daily_refresh.py      # APScheduler 入口
│   │   └── tasks.py              # 任务函数
│   └── utils/
│       ├── __init__.py
│       ├── config.py             # AppConfig
│       └── logger.py             # 日志
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_filter_service.py
    ├── test_performance_service.py
    └── test_api.py
```

### 2.2 ORM 模型（`src/db/models.py`）

```python
from datetime import date, datetime
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Index
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Fund(Base):
    __tablename__ = "funds"
    code: str = Column(String(6), primary_key=True)
    name: str = Column(String(64), nullable=False)
    fund_type: str = Column(String(64), nullable=False)
    category: str = Column(String(16), nullable=False, index=True)  # bond/stock/mix/money
    established_date: date = Column(Date, nullable=True)
    age_years: float = Column(Float, nullable=True)
    size_yi: float = Column(Float, nullable=True)
    mgr_name: str = Column(String(128), nullable=True)
    mgr_company: str = Column(String(64), nullable=True)
    mgr_days: int = Column(Integer, nullable=True)
    mgr_experience_years: float = Column(Float, nullable=True)
    is_active: bool = Column(Boolean, default=True, index=True)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FundPerformance(Base):
    __tablename__ = "fund_performance"
    code: str = Column(String(6), primary_key=True)
    as_of_date: date = Column(Date, nullable=False)
    nav_latest: float = Column(Float, nullable=True)
    nav_date: date = Column(Date, nullable=True)
    ret_1m: float = Column(Float, nullable=True)
    ret_6m: float = Column(Float, nullable=True)
    ret_1y: float = Column(Float, nullable=True)
    ret_3y: float = Column(Float, nullable=True)
    ret_5y: float = Column(Float, nullable=True)
    dd_1y: float = Column(Float, nullable=True)
    dd_3y: float = Column(Float, nullable=True)  # v1 筛选关键字段
    dd_5y: float = Column(Float, nullable=True)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("ix_perf_dd3y", "dd_3y"),)

class FundFees(Base):
    __tablename__ = "fund_fees"
    code: str = Column(String(6), primary_key=True)
    fee_buy_small: float = Column(Float, nullable=True)
    fee_redeem_lt7d: float = Column(Float, nullable=True)
    fee_redeem_7d_1y: float = Column(Float, nullable=True)
    fee_redeem_ge1y: float = Column(Float, nullable=True)
    fee_redeem_ge7d: float = Column(Float, nullable=True)
    fee_mgmt: float = Column(Float, nullable=True)
    fee_custody: float = Column(Float, nullable=True)
    fee_service: float = Column(Float, nullable=True)

class FundHoldingsBond(Base):
    __tablename__ = "fund_holdings_bond"
    code: str = Column(String(6), primary_key=True)
    report_date: date = Column(Date, primary_key=True)
    rate_bond_pct: float = Column(Float, nullable=True)
    credit_bond_pct: float = Column(Float, nullable=True)
    convertible_pct: float = Column(Float, nullable=True)
    top5_concentration: float = Column(Float, nullable=True)
```

### 2.3 筛选逻辑（`src/services/filter_service.py`）

```python
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.db.models import Fund, FundPerformance
from typing import Optional

class FilterService:
    def __init__(self, db: Session):
        self.db = db

    def screen(
        self,
        min_age: Optional[float] = None,        # 成立年限（年）
        min_size_yi: Optional[float] = None,     # 规模（亿）
        max_dd_3y: Optional[float] = None,       # 3 年最大回撤（%，绝对值）
        min_mgr_experience_years: Optional[float] = None,
        sort: str = "size_yi",
        order: str = "desc",
    ) -> dict:
        # 宇宙 = 库内 is_active 基金（即配置名单已采集成功的）。不要按 category==bond 过滤：
        # 31 只里含混合/QDII。
        q = (
            self.db.query(Fund, FundPerformance)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .filter(Fund.is_active == True)
        )
        if min_age is not None:
            q = q.filter(Fund.age_years >= min_age)
        if min_size_yi is not None:
            q = q.filter(Fund.size_yi >= min_size_yi)
        if max_dd_3y is not None:
            q = q.filter(FundPerformance.dd_3y <= max_dd_3y)
        if min_mgr_experience_years is not None:
            q = q.filter(Fund.mgr_experience_years >= min_mgr_experience_years)

        # 排序：白名单字段防 SQL 注入
        sort_col = {
            "size_yi": Fund.size_yi,
            "age_years": Fund.age_years,
            "mgr_experience_years": Fund.mgr_experience_years,
            "dd_3y": FundPerformance.dd_3y,
            "ret_3y": FundPerformance.ret_3y,
            "ret_1y": FundPerformance.ret_1y,
            "code": Fund.code,
        }.get(sort, Fund.size_yi)
        q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

        rows = q.all()
        return {
            "total": len(rows),
            "items": [self._to_dto(f, p) for f, p in rows],
        }

    @staticmethod
    def _to_dto(f: Fund, p: FundPerformance) -> dict:
        return {
            "code": f.code,
            "name": f.name,
            "fund_type": f.fund_type,
            "size_yi": f.size_yi,
            "age_years": f.age_years,
            "mgr_name": f.mgr_name,
            "mgr_company": f.mgr_company,
            "mgr_experience_years": f.mgr_experience_years,
            "ret_1m": p.ret_1m,
            "ret_1y": p.ret_1y,
            "ret_3y": p.ret_3y,
            "dd_3y": p.dd_3y,
        }
```

### 2.4 数据采集流程（`src/scheduler/daily_refresh.py`）

```
每日定时 / 手动 refresh 触发
  ↓
[Step 0] 读 backend/config/funds.yaml（31 只）。空库可先导入 results_31.csv
  ↓
[Step 1] 全市场经理表（ak.fund_manager_em）一次，cache/manager_em.json
  ↓
[Step 2] 仅遍历配置 codes（并发可小，31 只不必 10 路打满）
  - 基础信息 → funds
  - 净值 → 计算业绩 → fund_performance
  - 东财季报 → fund_holdings_bond（利率债分类复用 PoC 关键词）
  - 费率 → fund_fees（补回 fetcher，字段对齐 cache/fees_{code}.json）
  ↓
[Step 3] 进度写 refresh_progress，前端 GET /refresh/status
```

**关键技术决策**：
- **并发控制**：`asyncio.Semaphore(10)`，避免触发反爬
- **断点续传**：每完成一只基金立即 commit（单条 SQL），进程崩溃后下次跳过已完成的
- **失败重试**：单只基金失败 3 次后跳过，记录到 refresh_errors 表，不影响其它
- **缓存**：akshare 返回值 + 东财 JSON 写到 cache/，调试和回放方便

### 2.5 API 详细定义

| 方法 | 路由 | Query / Body | 返回 |
|---|---|---|---|
| GET | `/api/funds/screen` | 均可选：`min_age`, `min_size_yi`, `max_dd_3y`, `min_mgr_exp`, `sort`, `order` | `{total, items: [...]}` 不分页 |
| GET | `/api/funds/{code}` | - | `{...fund, performance, holdings}` |
| GET | `/api/funds/refresh` | - | `{task_id, status: "started"}` |
| GET | `/api/funds/refresh/status` | `task_id` | `{task_id, status, completed, total, errors}` |
| GET | `/api/funds/export/csv` | 同 screen | `text/csv` (BOM) |
| GET | `/api/funds/stats` | - | `{total, by_category, by_size_bucket, by_age_bucket, last_refresh_at}` |
| GET | `/health` | - | `{status: "ok"}` |

### 2.6 错误处理

- **筛选参数越界**：返回 422（Pydantic 自动）
- **数据库无数据**：返回 `{total: 0, items: []}`，前端显示空状态
- **单只基金缺失业绩**：fund_performance 表无记录，filter_service 走 LEFT JOIN 而非 INNER（不让数据缺失的基金从筛选中消失）
- **refresh 失败**：单只基金失败不阻塞整体，进度接口返回 errors 列表

## 3. 前端架构

### 3.1 目录结构（与 dividend 对齐）

```
frontend/
├── package.json
├── next.config.ts                # basePath: '/funds'
├── tsconfig.json
├── tailwind.config.ts            # 与 dividend 同步
├── postcss.config.mjs
├── .env.local                    # BACKEND_URL=http://localhost:8095
├── src/
│   ├── app/
│   │   ├── layout.tsx            # 全局 layout
│   │   ├── globals.css
│   │   ├── page.tsx              # → redirect('/funds')
│   │   ├── funds/
│   │   │   ├── page.tsx          # 债基筛选主页
│   │   │   └── layout.tsx        # 子 layout
│   │   └── api/
│   │       └── funds/
│   │           └── [...path]/
│   │               └── route.ts  # catch-all 代理
│   ├── components/
│   │   ├── FilterSidebar.tsx     # 左筛选面板
│   │   ├── FilterSheet.tsx       # 移动底部 sheet
│   │   ├── FilterChipBar.tsx     # 顶部 chip
│   │   ├── FundTable.tsx         # 主表格
│   │   ├── SortableHeader.tsx
│   │   ├── CompareFloatingBar.tsx # 从 dividend 复制
│   │   ├── CompareDrawer.tsx     # 从 dividend 复制
│   │   ├── CompareTable.tsx      # 泛型化 + 债基维度
│   │   ├── CompareButton.tsx     # 行内小按钮
│   │   ├── RefreshStatusPopover.tsx # 刷新状态
│   │   └── shared-ui/
│   │       └── Button.tsx
│   ├── lib/
│   │   ├── api.ts                # fetch wrapper
│   │   ├── types.ts              # 共享类型
│   │   ├── hooks.ts
│   │   ├── useCompare.ts         # 从 dividend 复制后泛型化
│   │   ├── useFilters.ts         # 新增：筛选状态 + URL 同步
│   │   └── useFunds.ts           # 新增：列表 + 详情 + refresh
│   └── tests/
│       ├── useCompare.test.ts
│       └── useFilters.test.ts
```

### 3.2 复用 dividend 的对比 hook（泛型化）

从 `apps/dividend/src/lib/hooks.ts:323` 复制 useCompare，改成泛型：

```typescript
export interface Comparable {
  code: string;
}

export function useCompare<T extends Comparable>(maxSelect: number = 5) {
  const [selectedStocks, setSelectedStocks] = useState<T[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const toggleStock = useCallback((stock: T) => {
    setSelectedStocks(prev => {
      const exists = prev.some(s => s.code === stock.code);
      if (exists) return prev.filter(s => s.code !== stock.code);
      if (prev.length >= maxSelect) return prev;
      return [...prev, stock];
    });
  }, [maxSelect]);

  const clearSelection = useCallback(() => {
    setSelectedStocks([]);
    setIsDrawerOpen(false);
  }, []);

  const openDrawer = useCallback(() => {
    if (selectedStocks.length < 2) return false;
    setIsDrawerOpen(true);
    return true;
  }, [selectedStocks.length]);

  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);
  const removeStock = useCallback((code: string) => {
    setSelectedStocks(prev => prev.filter(s => s.code !== code));
  }, []);
  const isSelected = useCallback((code: string) =>
    selectedStocks.some(s => s.code === code), [selectedStocks]);

  return {
    selectedStocks,
    isDrawerOpen,
    toggleStock,
    clearSelection,
    openDrawer,
    closeDrawer,
    removeStock,
    isSelected,
  };
}
```

### 3.3 对比维度

```typescript
export const fundCompareDimensions: CompareDimension<Fund>[] = [
  { key: 'size', label: '规模', extract: f => f.size_yi, format: v => `${v.toFixed(2)}亿`, direction: 'max' },
  { key: 'age', label: '成立年限', extract: f => f.age_years, format: v => `${v.toFixed(1)}年`, direction: 'max' },
  { key: 'mgr_exp', label: '经理从业年限', extract: f => f.mgr_experience_years, format: v => `${v.toFixed(1)}年`, direction: 'max' },
  { key: 'dd_3y', label: '近 3 年最大回撤', extract: f => f.dd_3y, format: v => `${v.toFixed(2)}%`, direction: 'min-abs' },
  { key: 'ret_1y', label: '近 1 年收益', extract: f => f.ret_1y, format: v => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, direction: 'max' },
  { key: 'ret_3y', label: '近 3 年收益', extract: f => f.ret_3y, format: v => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, direction: 'max' },
  { key: 'ret_5y', label: '近 5 年收益', extract: f => f.ret_5y, format: v => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, direction: 'max' },
  { key: 'fee_annual', label: '年费', extract: f => f.fee_annual, format: v => `${v.toFixed(2)}%`, direction: 'min' },
];

// 只展示、不参与 useHighlights
export const fundCompareDisplayOnly = [
  { key: 'rate_bond_pct', label: '利率债占比' },
  { key: 'fee_buy_small', label: '申购费' },
  { key: 'fee_redeem', label: '赎回档' },  // lt7d / 7d-1y / ge1y / ge7d 按有值展示
];
```

近 3 年回撤进度条（主表）：`fill = min(|dd_3y| / 10, 1)`，满刻度 10%；缺失显示 "-"。

### 3.4 URL 状态同步

```
# 默认无筛选参数。有筛选时例如：
?min_age=3&min_size_yi=2&max_dd_3y=5&min_mgr_exp=5&sort=size_yi&order=desc
```

`useFilters` hook 内部用 `useSearchParams` 双向绑定，类似 dividend `?tab=alerts&fav=1` 的实现。

### 3.5 Next.js catch-all 代理

```typescript
// src/app/api/funds/[...path]/route.ts
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8095';

export async function GET(request: Request, { params }: { params: { path: string[] } }) {
  const path = params.path.join('/');
  const url = new URL(request.url);
  const search = url.search;  // 保留所有 query params
  const target = `${BACKEND_URL}/api/funds/${path}${search}`;

  const res = await fetch(target, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: {
      'Content-Type': res.headers.get('Content-Type') || 'application/json',
    },
  });
}
```

## 4. 关键技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| ORM | SQLAlchemy 2.x + DeclarativeBase | 类型友好，async 支持好；与 dividend 一致 |
| 数据库 | SQLite（dev → prod） | v1 数据量小；后续可平滑迁 Postgres |
| Web 框架 | FastAPI | 与 dividend-select 一致 |
| 定时任务 | APScheduler 3.x | dividend 验证过；不升级 4.x（API 不兼容） |
| 并发 | `asyncio.Semaphore(10)` | 控制 akshare / 东财请求速率 |
| 缓存层 | 文件缓存（`cache/*.json`） | 简单够用，调试可读 |
| 前端状态 | React useState + URL params | 无需 Redux；URL 同步已够 |
| 前端数据获取 | 原生 fetch + SWR 不引入 | 与 dividend 一致；4 个接口不需要缓存库 |
| 部署 | 独立 Windows .bat 启动 | 与 personal-web 其它项目一致 |

## 5. 错误处理策略

| 层级 | 策略 |
|---|---|
| 数据采集 | 单只基金失败 → log + 跳过；进程崩溃 → 下次跳过已完成部分 |
| API 层 | Pydantic 422 校验；显式 HTTPException；全局 try/except → 500 |
| 前端 fetch | try/catch → 显示"加载失败" + 重试按钮 |
| URL 参数异常 | useFilters 默认值兜底 |
| 对比抽屉 | 空状态："请从列表中选择 2-5 只基金开始对比" |

## 6. 测试策略

### 后端（pytest）

- `test_filter_service.py`：4 个筛选维度组合 / 边界值 / 排序
- `test_performance_service.py`：回撤算法 / 收益算法（给定 mock 净值数据）
- `test_api.py`：HTTP 接口 / 422 / 404
- 覆盖率目标 ≥ 60%（v1 暂不要求 80%，留给 v2）

### 前端

- `useCompare.test.ts`：toggleStock 边界（到上限）/ clearSelection / openDrawer 最小 2 只
- `useFilters.test.ts`：URL 同步 / 默认值 / 参数清除
- 视觉验证靠手动（Playwright v1 不上）

## 7. 部署与回滚

### 启动脚本

```bat
@echo off
REM scripts/start-fund-select-backend.bat
cd /d %~dp0\..\backend
.venv\Scripts\activate
uvicorn src.main:app --host 0.0.0.0 --port 8095 --reload
```

```bat
@echo off
REM scripts/start-fund-select-frontend.bat
cd /d %~dp0\..\frontend
pnpm dev
```

### 数据备份

- `backend/data/funds.db` → 每周一次 git 提交（v1 阶段）
- 后续 v2 接定时备份

### 回滚

- 前后端独立部署 → 任意一边回滚不影响另一边
- 后端数据库 schema 变更 → 先备份 db 文件再 migration

## 8. 与 dividend 项目的差异

| 维度 | dividend | fund-select v1 |
|---|---|---|
| 标的 | A 股持仓筛选 | 配置 31 只精选基金（含少量混合/QDII） |
| 数据维度 | 14 个（含 M120/PE 等） | 主表列 + 年费 + 利率债占比 |
| 实时性 | M120 + 实时价 + 季报 | 净值日频 + 季报持仓 + 费率 |
| 收藏/监控 | ✅ | ❌（v1 不做） |
| 详情弹框 | ✅（季度/行业/年报/波动） | ❌（v1 不做） |
| 报告导出 | A4 + 轮播 | ❌（v1 不做） |
| 定时任务 | ✅ APScheduler | ✅ APScheduler |
| 对比功能 | ✅ 三件套 | ✅ 三件套（泛型化复用） |
| 数据库 | 无（CSV） | ✅ SQLite |

差异决定 fund-select 可以更简单（无 CSV 解析、无 4 个详情弹框、无报告生成），工作量集中在数据采集和筛选 UI。
