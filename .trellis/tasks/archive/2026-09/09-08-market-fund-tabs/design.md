# Design: fund-select 市场筛选 tab（债基·市场 / 股基·市场）

## 1. 范围与边界

### 在范围内

| 层 | 改动 |
|---|---|
| DB schema | `funds` 表新增 `market_type VARCHAR(64) NULL` |
| 后端 fetcher | 新增 `data/market_universe_fetcher.py` |
| 后端 refresh | 新增 `services/market_universe_refresh.py` |
| 后端 scheduler | `scheduler/tasks.py` + `daily_refresh.py` 新增 `refresh_market_universe_sync()` 与定时触发 |
| 后端 API | `api/routes.py` 新增 `router_discovery_bond` / `router_discovery_stock`，前缀 `/discovery-bond`、`/discovery-stock` |
| 后端 service | `services/filter_service.py` 新增 `screen_discovery_bond()` / `screen_discovery_stock()` + `_screen` 加 `market_types` 参数 |
| 前端 API client | `lib/api.ts` 新增 `discoveryBondApi` / `discoveryStockApi` |
| 前端 hooks | `lib/hooks.ts` 新增 `useDiscoveryBondFundList` / `useDiscoveryStockFundList` |
| 前端类型 | `lib/types.ts` `FundFilters` 加 `market_types?: string[] \| null` |
| 前端筛选 hook | `lib/useFilters.ts` 序列化 `market_types` 到 URL |
| 前端页面 | `app/discovery-bond/page.tsx` + `app/discovery-stock/page.tsx` + `app/discovery-bond/layout.tsx` + `app/discovery-stock/layout.tsx` |
| 前端 header | `components/FundsHeader.tsx` `active` 扩为 4 态；RefreshStatusPopover 传 4 种 URL |

### 不在范围内（保持原样）

- `funds.yaml` / `funds_stock.yaml` 不变
- `resolve_universe_codes(kind='bond'/'stock')` 路径不变
- 现有 `screen()` / `screen_stock()` 方法不变
- 现有 FundsHeader / FilterSidebar / FundTable / RowDetailDrawer 不重构（仅参数扩展）
- 雪球 type_desc → `Fund.fund_type` 字段不变
- 业绩 / 费率 / 持仓 / 风险指标 refresh 流程不变

### 兼容性

- 老接口 `GET /api/funds/screen` 与 `GET /api/funds/stock/screen` 返回不变
- 老 tab `/funds/bond` `/funds/stock` 渲染不变
- `Fund.fund_type` 字段不被覆盖
- `is_active` 不被批量改写

## 2. 数据库 Schema

```sql
-- migration: add funds.market_type
ALTER TABLE funds ADD COLUMN market_type VARCHAR(64) NULL;
CREATE INDEX ix_funds_market_type ON funds(market_type);
```

### 实现方式

`db/session.py` 启动时执行 `ALTER TABLE`：
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

启动时一次幂等检查，避免 Alembic 引入新依赖。SQLite 无 IF NOT EXISTS for ADD COLUMN，需手动查列存在。

### 字段语义

| 字段 | 来源 | 粒度 | 用途 |
|---|---|---|---|
| `fund_type` | 雪球 `type_desc` | 细 | 老 tab 展示、exclude_qdii 判定 |
| `market_type`（新） | akshare `基金类型` | 粗 | 市场 tab 宇宙筛选 |

## 3. 数据流

```
每日 06:30
  └─ scheduler.daily_refresh.refresh_market_universe_sync()
       └─ market_universe_fetcher.fetch_market_universe()
       │    └─ ak.fund_name_em()  # 单次 HTTP，~1 万行
       └─ market_universe_refresh.refresh(session, df)
            └─ 对每行：
                 - 已存在：UPDATE funds SET name=?, market_type=?, updated_at=NOW() WHERE code=?
                 - 不存在：INSERT INTO funds(code, name, market_type, is_active=True)
       └─ RefreshRun 记录进度

用户访问 /funds/discovery-bond
  └─ Next.js 渲染 discovery-bond/page.tsx
       └─ useDiscoveryBondFundList(filters)
            └─ discoveryBondApi.screen(filters) → GET /funds/api/funds/discovery-bond/screen
                 └─ catch-all proxy → FastAPI FilterService.screen_discovery_bond(...)
                      └─ resolve_market_codes(kind='bond') → ['债券型','定开债券']
                      └─ _screen(kind='bond', market_types=filters.market_types, ...)
                           └─ SELECT ... WHERE fund.is_active AND fund.market_type IN (...)
                           └─ 4 join → DTO → 排序 → 返回

定时业绩刷新（已有）
  └─ refresh_configured_funds_sync() / refresh_stock_funds_sync() 不变
```

## 4. API 契约

### Discovery tab 路由

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/funds/discovery-bond/screen` | 筛选债基·市场 |
| GET | `/api/funds/discovery-bond/refresh` | 触发市场名单刷新 |
| GET | `/api/funds/discovery-bond/refresh/status` | 刷新进度 |
| GET | `/api/funds/discovery-bond/stats` | 库内概况 |
| GET | `/api/funds/discovery-bond/{code}` | 单只详情 |
| GET | `/api/funds/discovery-stock/screen` | 筛选股基·市场 |
| GET | `/api/funds/discovery-stock/refresh` | 触发市场名单刷新 |
| GET | `/api/funds/discovery-stock/refresh/status` | 刷新进度 |
| GET | `/api/funds/discovery-stock/stats` | 库内概况 |
| GET | `/api/funds/discovery-stock/{code}` | 单只详情 |

### screen query 参数

```
min_age, min_size_yi, max_dd_3y, min_mgr_exp, min_sharpe (债基 tab 不用)
sort, order, exclude_qdii
market_type=债券型,定开债券  # CSV，可选；空 = 走默认 universe
```

`market_type` 参数语义：
- 不传 / 空 → 用各 tab 默认 universe（discovery-bond = ['债券型','定开债券']，discovery-stock = ['股票型','指数型','混合型','QDII']）
- 传 `债券型,定开债券` → 缩窄到这两类
- 传 `债券型` → 只剩债券型

### ScreenResponse

不变，复用现有 `ScreenResponse { total, items: FundListItem[] }`。

### 单只详情

复用 `get_detail(code)`，但 market tab 的 detail 仍走 `/api/funds/{code}`（复用现有接口），或单独 `/discovery-bond/{code}` → 内部调用 `get_detail(code)`。**MVP 选择复用 `/api/funds/{code}` 不重写**。

> 决策：单只详情接口不分子 tab，前端直接调 `/api/funds/{code}`，避免重复代码。

## 5. 关键设计决策

### D1 market_type 默认 universe 内置 vs 走 URL

**选择**：内置在 service 层
```python
DEFAULT_DISCOVERY_UNIVERSE = {
    "discovery-bond": ["债券型", "定开债券"],
    "discovery-stock": ["股票型", "指数型", "混合型", "QDII"],
}
```
URL 不传 market_type 时走默认；前端切换 tab 时重新初始化默认。

### D2 单只详情复用 `/api/funds/{code}`

**理由**：`get_detail` 已 join 4 张表，不依赖 universe 来源；前端从哪个 tab 点进去都拿到一致数据。

### D3 market_type 写入 URL 用 CSV

**理由**：与现有 `exclude_qdii=1` 单值开关不同，market_type 是多选；CSV 字符串最短。

### D4 `is_active` 不在 market refresh 中修改

**理由**：akshare `fund_name_em` 返回的都是「当前显示在天天基金的代码」，无法判定是否清盘；MVP 假设全为活跃。后续如需精准，可加业绩停更判断。

### D5 业绩 / 费率 refresh 不变

**理由**：市场 tab 里的基金业绩由现有 yaml refresh 触发；那些基金不在 yaml 里 → 没有业绩数据 → 表里 NULL。
- 缺点：市场 tab 里大部分基金没业绩
- 优点：解耦，refresh 复杂度可控
- 后续：可加 market_funds_perf_refresh（遍历 market universe 跑 fetch_basic + 业绩），超出 MVP

### D6 _screen 内部签名扩展而非新方法

```python
def _screen(self, kind, min_age, ..., universe_codes, exclude_qdii, min_sharpe, market_types=None):
    ...
    # 关键差异
    if market_types is not None:
        q = q.where(Fund.market_type.in_(market_types))
    elif kind in ("discovery-bond", "discovery-stock"):
        q = q.where(Fund.market_type.in_(DEFAULT_DISCOVERY_UNIVERSE[kind]))
    elif kind == "bond":
        # 老逻辑：fund.code.in_(yaml codes)
        pass
    ...
```

保留 `_screen` 单一逻辑路径；通过 `kind` 与 `market_types` 参数控制。

### D7 funds 表 upsert 策略

```python
# refresh 时
existing = session.execute(select(Fund.code, Fund.name, Fund.market_type).where(Fund.code.in_(batch))).all()
existing_map = {row.code: row for row in existing}

for row in df.itertuples():
    if row.code in existing_map:
        # 已存在：仅更新 name/market_type/updated_at，保留 fund_type/is_active
        session.execute(
            update(Fund).where(Fund.code == row.code)
            .values(name=row.name, market_type=row.market_type, updated_at=now())
        )
    else:
        # 新增：is_active=True，fund_type=空
        session.execute(insert(Fund).values(
            code=row.code, name=row.name, market_type=row.market_type,
            fund_type="", is_active=True,
        ))
```

每 500 行 commit 一次，避免 SQLite lock。

## 6. 前端契约

### FundsHeader

```typescript
type FundsTab = 'bond' | 'stock' | 'discovery-bond' | 'discovery-stock';

interface FundsHeaderProps {
  active: FundsTab;  // 扩
  ...
  exportKind: 'bond' | 'stock' | 'discovery-bond' | 'discovery-stock';
}
```

tab 渲染：
```tsx
<TabLink href="/bond" active={active === 'bond'}>债基</TabLink>
<TabLink href="/stock" active={active === 'stock'}>股票</TabLink>
<TabLink href="/discovery-bond" active={active === 'discovery-bond'}>债基·市场</TabLink>
<TabLink href="/discovery-stock" active={active === 'discovery-stock'}>股基·市场</TabLink>
```

RefreshStatusPopover URL 选择：
```typescript
const refreshUrl = exportKind === 'stock' ? '/funds/api/funds/stock/refresh'
  : exportKind === 'discovery-bond' ? '/funds/api/funds/discovery-bond/refresh'
  : exportKind === 'discovery-stock' ? '/funds/api/funds/discovery-stock/refresh'
  : undefined;  // bond 走默认
```

### FundFilters 扩展

```typescript
export interface FundFilters {
  ... // 老字段
  market_types: string[] | null;  // 新增；null = 走默认 universe
}
```

### useFilters 扩展

- `NUMERIC_KEYS` 不变
- `market_types` 用 CSV 序列化：`?market_type=债券型,定开债券` 或空
- `parseFiltersFromSearch` 解析 `market_type` query
- `clearAll()` 把 `market_types` 也置 null

### 各 tab 默认值

```typescript
export const DEFAULT_FILTERS: FundFilters = {
  ...老字段,
  market_types: null,
};

export const STOCK_DEFAULT_FILTERS: FundFilters = {
  ...,
  market_types: null,
};

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

### Page

```typescript
// app/discovery-bond/page.tsx
'use client';
// 与 stock/page.tsx 几乎一致：
// - useFilters(DISCOVERY_BOND_DEFAULT_FILTERS)
// - useDiscoveryBondFundList(filters)
// - FundsHeader active='discovery-bond' exportKind='discovery-bond'
// - FilterPanel dimensions 加 marketType 多选
// - FundTable showBondColumns / showRiskColumns 根据 tab
// - RowDetailDrawerBond（债券 tab）/ RowDetailDrawer（股票 tab）
```

## 7. FilterSidebar / FilterChipBar 扩展

新增 `marketType` 维度：
- 维度枚举：`['债券型', '定开债券', '股票型', '指数型', '混合型', 'QDII', '货币型', 'FOF']`（akshare 实际值全集）
- UI：多选 chip 或 checkbox 列表
- chip 显示："基金类型: 债券型、定开债券 (2)"

为简化 MVP：把 marketType 做成简单多选 checkbox，列出全部枚举值（按字母排序），不做搜索框。

## 8. Rollback 策略

| 步骤 | 回滚 |
|---|---|
| Schema 变更 | 不删列（保留 market_type NULL）；前端不引用即可 |
| 新增 fetcher / refresh | 删文件即可 |
| 新增 API 路由 | 删 router 即可 |
| 新增前端页面 | 删 app/discovery-* 目录 |
| FundsHeader 扩展 | git revert |

无破坏性变更；最坏情况是回滚到 4 个 tab 但只显示 2 个有效 tab。

## 9. 测试策略

### 单元测试

```python
# tests/test_market_universe_fetcher.py
def test_fetch_returns_dataframe_with_expected_columns(): ...
def test_fetch_handles_akshare_exception(): ...  # mock ak.fund_name_em

# tests/test_market_universe_refresh.py
def test_refresh_inserts_new_codes(): ...
def test_refresh_updates_existing_codes_without_touching_fund_type(): ...  # 关键回归点
def test_refresh_does_not_change_is_active(): ...

# tests/test_filter_service.py
def test_screen_discovery_bond_filters_by_market_type(): ...
def test_screen_discovery_stock_excludes_bond_types(): ...
def test_screen_with_custom_market_type_narrows(): ...
def test_existing_screen_bond_unchanged(): ...  # 关键回归点
def test_existing_screen_stock_unchanged(): ...  # 关键回归点
```

### 手工验证

- `curl http://localhost:8095/api/funds/discovery-bond/screen` 返回 total > 1000
- 浏览器访问 4 个 tab URL 都能渲染
- 老 tab 数据不变（对比 yaml refresh 后的截图）

## 10. 不在本次设计范围

- 二级分类（"中长期纯债 / 短期纯债"）
- 自动判断清盘
- 市场 tab 单只业绩 refresh
- 跨 tab 收藏 / 对比持久化
- 新增详情页字段
