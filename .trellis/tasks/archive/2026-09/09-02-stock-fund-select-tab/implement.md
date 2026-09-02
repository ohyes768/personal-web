# 股票基金筛选 tab — Implementation Plan

> 严格遵循 design.md 边界。先后端 fetcher → DB → service → API → 前端 → 端到端跑通。每个阶段都跑测试。

## Phases 总览

```
P1 (后端 fetcher + DB)     ~半天
P2 (后端 service + API)    ~半天
P3 (前端页面 + 组件)        ~半天
P4 (端到端跑通 + 配置)      ~半天
P5 (review + 微调 + 提交)   ~半天

合计 ~2 个工作日（含 review gate）
```

## Review Gates

| Gate | 进入条件 | 通过条件 |
|---|---|---|
| G1 | P1 完成 | `pytest tests/test_achievement_fetcher.py -v` 全过 + 现有 `tests/` 不退步 |
| G2 | P2 完成 | 新接口 smoke test 用 curl/fastapi testclient 全过 |
| G3 | P3 完成 | `pnpm exec tsc --noEmit` 0 错；`pnpm build` 类型检查 + 静态生成都过 |
| G4 | P4 完成 | 用浏览器打开 `/funds` 与 `/funds/stock` 两个 URL；筛选 chip + 默认值 + 表头列名一致；导出 CSV 正常；刷新任务跑通 |
| G5 | P5 完成 | 三个 PR commit 都已落到 master 分支；后端 + 前端 `pnpm build` / `pytest` 都过 |

## P1 — 后端 fetcher + DB 模型

### Tasks

- [ ] **T1.1** 新建 `backend/fund-select/src/data/achievement_fetcher.py`
  - 单函数 `fetch_achievement(code) -> pd.DataFrame`
  - 直接调 `ak.fund_individual_achievement_xq(symbol=code)`
  - 空值返回空 DataFrame，失败抛异常（与 `nav_fetcher.fetch_nav` 契约一致）

- [ ] **T1.2** 在 `backend/fund-select/src/db/models.py` 末尾追加 `FundAchievementRank`
  - 复合主键 `(code, period_kind, period)`
  - 字段：`ret / max_dd / peer_rank / as_of_date / updated_at`
  - 字符长度：`period_kind=32, period=32, peer_rank=32`

- [ ] **T1.3** 单测：`tests/test_achievement_fetcher.py`
  - mock akshare，验证返回 DataFrame columns 与 upsert 入库逻辑不报错
  - 验证空 DataFrame 不抛异常

- [ ] **T1.4** 单测加一条：`tests/test_stock_filter_service.py::test_screen_stock_qdii_match`
  - 准备 3 只 Fund（混合型 / 股票型 / QDII），断言只后两条进入结果

### Validation

```bash
cd backend/fund-select
.venv/Scripts/python.exe -c "from src.data.achievement_fetcher import fetch_achievement; print(fetch_achievement('005827').head())"
.venv/Scripts/python.exe -c "from src.db.models import FundAchievementRank; print(FundAchievementRank.__tablename__)"
uv run pytest tests/test_achievement_fetcher.py tests/test_stock_filter_service.py -v
uv run pytest tests/ -v   # 全跑，确保不退步
```

### Rollback

- 删 `achievement_fetcher.py` + `models.py` 移除 FundAchievementRank 类 + 删两个 test 文件

## P2 — 后端 service + API

### Tasks

- [ ] **T2.1** `src/utils/config.py` 新增 `get_stock_funds_config_path()`
  - 对偶 `get_funds_config_path`，返回 `Path(__file__).parents[1] / "config" / "funds_stock.yaml"`

- [ ] **T2.2** `src/services/refresh_service.py` 分支
  - `snapshot_fund` 内，在 fund_type 形如 `股票型-*` / `QDII*` 时调 `fetch_achievement(code)`
  - 失败仅 warning，不抛
  - `persist_snapshot` 内：先删 `FundAchievementRank` 该 code 所有行，再批量 insert

- [ ] **T2.3** `src/services/filter_service.py` 新增 `screen_stock(...)`
  - 与现有 `screen` 并列
  - fund_type 过滤 `LIKE '股票型-%' OR LIKE 'QDII%' OR = 'QDII'`
  - 同维度筛选；sort 白名单与现有 screen 兼容（共用同一白名单函数）

- [ ] **T2.4** `src/scheduler/tasks.py` 新增 `refresh_stock_funds_sync(...)`
  - 同 `refresh_configured_funds_sync` 骨架
  - 调 `load_fund_codes(get_stock_funds_config_path())`

- [ ] **T2.5** `src/api/routes.py` 新增 `router_stock = APIRouter(prefix="/stock", ...)`
  - 6 个路由：`/screen` / `/export/csv` / `/{code}` / `/refresh` / `/refresh/status` / `/stats`
  - 注册顺序注意：`/{code}` 必须放最后

- [ ] **T2.6** `src/api/models.py`
  - 加 `FundAchievementRankDTO`
  - 加 `FundDetailResponse.achievement_ranks: list[FundAchievementRankDTO] = []`

- [ ] **T2.7** `src/main.py`
  - `app.include_router(router_stock)`

- [ ] **T2.8** `config/funds_stock.yaml`
  - `version: 1`
  - `funds:` 30 只股票型 + QDII 6 位代码
  - 名单采用代表性原则：覆盖沪深 300 ETF、白酒、医药、半导体、恒生科技、QDII 等

### Validation

```bash
cd backend/fund-select
uv run pytest tests/ -v
.venv/Scripts/python.exe -c "
from src.db.session import init_db
init_db()   # 幂等：新表被创建
from src.db.models import FundAchievementRank
print('table created:', FundAchievementRank.__tablename__)
"
.venv/Scripts/python.exe -m uvicorn src.main:app --port 8095 &
sleep 3
curl -fsS http://127.0.0.1:8095/api/funds/health
curl -fsS 'http://127.0.0.1:8095/api/funds/stock/screen?min_age=3&min_size_yi=5&min_mgr_exp=5&max_dd_3y=20'
curl -fsS 'http://127.0.0.1:8095/api/funds/stock/stats'
curl -fsS http://127.0.0.1:8095/api/funds/stock/000001   # 应 404
```

### Rollback

- 整体回退：reset branch 至 P1 前
- 部分回退：删 `routes.py` 里新加的 `router_stock` + 移除 `app.include_router` 一行；stock 业务静默 404

## P3 — 前端页面 + 组件

### Tasks

- [ ] **T3.1** `apps/fund-select/src/components/FundsHeader.tsx`
  - props: `active: 'bond' | 'stock'`
  - 把现有 `app/page.tsx` 第 41-67 行 header 区抽出来
  - 增加 `<nav>` 链接 `/funds` 与 `/funds/stock`
  - 用 `<Link>` 保持 basePath 语义

- [ ] **T3.2** `apps/fund-select/src/app/page.tsx`
  - inline header 区替换为 `<FundsHeader active="bond" />`
  - 其余不动

- [ ] **T3.3** `apps/fund-select/src/lib/types.ts`
  - 加 `export const STOCK_DEFAULT_FILTERS: FundFilters = { min_age: 3, min_size_yi: 5, max_dd_3y: 20, min_mgr_exp: 5, sort: 'ret_5y', order: 'desc' };`
  - 加 `export interface FundAchievementRank { period_kind: string; period: string; ret: number | null; peer_rank: string | null; }`
  - `FundDetail.achievement_ranks: FundAchievementRank[]`

- [ ] **T3.4** `apps/fund-select/src/lib/useFilters.ts`
  - `useFilters(initial?: Partial<FundFilters>)`
  - `parseFiltersFromSearch(search, fallback = DEFAULT_FILTERS)`

- [ ] **T3.5** `apps/fund-select/src/lib/api.ts`
  - `STOCK_BASE = '/funds/api/funds/stock'`
  - `stockApi = { screen, getDetail, refresh, getRefreshStatus, exportCsv }`，与 `fundApi` 对偶

- [ ] **T3.6** `apps/fund-select/src/lib/hooks.ts`
  - `useStockFundList(filters)`：类同 `useFundList`，调 `stockApi.screen`

- [ ] **T3.7** `apps/fund-select/src/app/stock/page.tsx`
  - 几乎 1:1 复制 `app/page.tsx`
  - 改：`useFilters(STOCK_DEFAULT_FILTERS)`、`useStockFundList`、`stockApi`
  - 改：`<FundsHeader active="stock" />`

### Validation

```bash
cd apps/fund-select
pnpm exec tsc --noEmit
pnpm build
```

期望：
- `tsc --noEmit` 0 错
- `pnpm build`：类型检查 + 静态生成 (4/4) 全过；最后的 EPERM standalone 是 Windows 已知问题（与本次改动无关）

### Rollback

- 删 `app/stock/page.tsx` 与 `components/FundsHeader.tsx`
- `app/page.tsx` 还原 inline header
- `lib/*` 全部还原

## P4 — 端到端跑通

### Tasks

- [ ] **T4.1** 后端 `init_db` + 手动触发 stock 刷新
  ```bash
  curl -fsS 'http://127.0.0.1:8095/api/funds/stock/refresh?limit=30'
  # 跟踪 task_id 拿 /refresh/status 直到 status=done
  ```

- [ ] **T4.2** 浏览器打开 `http://localhost:3005/funds` 与 `http://localhost:3005/funds/stock`
  - 检查 nav 链接互相跳转
  - 检查 `/funds/stock` 默认筛选 chip 显示
  - 检查表头列名与债基一致
  - 检查至少一只基金有 ret_5y / dd_3y 等数字（不全是 null）

- [ ] **T4.3** 测筛选
  - 调高 min_age 到 5，验证结果数下降
  - 点 chip 上的 ✕，验证回到默认（4 个 chip 出现）

- [ ] **T4.4** 测对比
  - 选择两只基金加入对比，验证对比 drawer 行为一致

- [ ] **T4.5** 测导出 CSV
  - 股票 tab 导出 CSV，验证文件下载 + 列名

### Validation

```bash
cd backend/fund-select
uv run pytest tests/ -v
cd ../../apps/fund-select
pnpm exec tsc --noEmit
pnpm build
```

### Rollback

- `init_db` 不会破坏已有债基数据
- 删 `funds_stock.yaml` 即可避免下一次调度拉取
- UI 与 API 互不干扰债基

## P5 — Review + 提交

### Tasks

- [ ] **T5.1** 自审：
  - 现有债基 tab 回归（检查没有改坏）
  - 跑 PR 前 `git diff` review

- [ ] **T5.2** 提交策略
  - 三个 atomic commit：
    1. `feat(fund-select): 新增 FundAchievementRank 表 + achievement fetcher`
    2. `feat(fund-select): 新增 /api/funds/stock 路由组 + screen_stock + refresh_stock_funds_sync`
    3. `feat(fund-select): 新增 /funds/stock 前端页面 + FundsHeader 共享组件`

- [ ] **T5.3** 跑完整测试 + 类型检查

### Validation

```bash
cd backend/fund-select
uv run pytest tests/ -v
cd ../../apps/fund-select
pnpm exec tsc --noEmit
```

## Undo / Reset

任何一个 P 没达到 review gate，回退到 P1 前即可（git reset --hard），因为所有改动都是 additive。

## No-touch 列表（实施期间不能动）

- ❌ `apps/fund-select/src/components/{FilterPanel,FilterSheet,FilterChipBar,FundTable,ExportCsvButton,RefreshStatusPopover,CompareDrawer,CompareFloatingBar,SortableHeader}.tsx`
- ❌ `backend/fund-select/src/services/performance_service.py`（已含 1y/3y/5y + dd_1y/3y/5y）
- ❌ `backend/fund-select/src/services/filter_service.py::screen`（债基接口不动）
- ❌ `backend/fund-select/src/data/{nav_fetcher,fund_basic_fetcher,manager_fetcher,holdings_fetcher,fee_fetcher,bond_classifier}.py`
- ❌ `backend/fund-select/src/db/models.py` 中现 Fund / FundPerformance / FundFees / FundHoldingsBond / RefreshRun schema
- ❌ 任何 `.env.local` / 新依赖
