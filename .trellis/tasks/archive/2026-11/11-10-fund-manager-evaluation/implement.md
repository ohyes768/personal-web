# 实施计划：基金经理维度评价（股票基金）

对应：`prd.md` / `design.md`

> **归档说明（2026-11-13）**：本清单原为 55 项全未勾选的初始计划，实际实现已于 2026-11-11 ~ 2026-11-12 随 `fund-select` 经理系列提交落地。
> 下列勾选状态按**仓库当前代码实际状态**回填，与原计划有三处文件布局偏差，已在对应条目内标注「实现与计划不同」。
> 后续如需继续演进，建议新开任务而非复用本任务。

## 总览

| 阶段 | 内容 | 可独立交付 | 前置 |
|---|---|---|---|
| P1 | 数据层：managers / manager_tenures 表 + 采集 | ✅ 可测试 | 无 |
| P2 | 指标计算：任职年化 / 加权年化 / 风险指标 | ✅ 可测试 | P1 |
| P3 | API：/managers/screen + 详情 | ✅ 可 curl | P2 |
| P4 | 前端：经理 tab | ✅ 可看 | P3 |

每个阶段结束都应保持 516 项测试全绿。

---

## P1 数据层

### P1.1 模型

- [x] `src/db/models.py` 新增 `Manager`、`ManagerTenure`
- [x] `Base.metadata.create_all` 自动建表（无需 ALTER，新表）
- [x] 索引：`managers.name`、`manager_tenures.manager_id`、`manager_tenures.fund_code`
- [x] 唯一约束：`manager_tenures(manager_id, fund_code, start_date)`

### P1.2 采集器

- [x] 扩展 `src/data/manager_fetcher.py`
  - [x] 新增 `fetch_manager_table_with_id()`：直接请求 `dt=14`，保留第 0 列经理 ID —— **实现与计划不同**：函数落在 `src/data/manager_profile_fetcher.py`
  - [x] 用 `akshare.utils.demjson.decode` 解析（非标准 JSON）
  - [x] **保留** `fetch_manager_table` / `fetch_manager_by_fund_code` 原函数签名（现有调用方不动）
- [x] 新增 `src/data/manager_profile_fetcher.py`
  - [x] `fetch_manager_tenures(manager_id)` → 解析档案页第 2 个 `<table>`
  - [x] **必须 `resp.content.decode("utf-8")`**（BOM 陷阱）
  - [x] 解析 `任职时间`（`~至今` / `~日期`）、`任职天数`（`7年又56天` / `82天`）
- [x] 新增复权净值采集 —— **实现与计划不同**：未单独建 `manager_nav_fetcher.py`，
      `fetch_adjusted_series(code)` 并入 `src/data/manager_profile_fetcher.py`
  - [x] `fetch_adjusted_series(code)` → 解析 `pingzhongdata` 的 `Data_netWorthTrend[].equityReturn`
  - [x] 连乘重建复权净值曲线

### P1.3 采集编排

- [x] 新增 `src/services/manager_refresh.py`
  - [x] M0 拉经理表 → 建 managers 骨架
  - [x] M1 库内主动权益基金（`market_subtype in ('股票型','混合型-偏股')`）→ 姓名→ID 映射
  - [x] M2 逐人拉档案页（限速 0.3s + 重试 3 次）→ manager_tenures
  - [x] 断点续采：`fetched_at IS NULL` 优先
  - [x] 写 `RefreshRun` 进度（复用现有机制）

### P1.4 验证

```bash
cd backend/fund-select
.venv/Scripts/python.exe -m pytest tests/ -q          # 必须 516+
```

- [x] 新增单测：`test_manager_profile_fetcher.py`（mock HTML 夹具，验证 BOM/天数解析）
- [x] 新增单测：`test_manager_refresh.py`（mock 采集，验证重名经理落不同主键）

---

## P2 指标计算

### P2.1 任职年化

- [x] `src/services/manager_metrics.py`
  - [x] `annualize(return_pct, days)` — 见 design §4.1
  - [x] 边界：`days=0` / `return<=-100` → None
  - [x] 回填 `manager_tenures.annual_return`

### P2.2 加权年化

- [x] `weighted_annual(tenures)` — 按 tenure_days 加权，见 design §4.2
- [x] **只统计主动权益段**（排除该经理管的债基/QDII 段）
- [x] 写入 `managers.tenure_weighted_annual`

### P2.3 代表基金与风险

- [x] `pick_representative(tenures)` — 主动权益 + 最长任期 + 在管优先
- [x] `compute_risk(code, start, end)` — 基于复权曲线算 mdd/vol/sharpe/calmar
- [x] 口径版本 `mgr-3y-v1` 写入常量（`ALGORITHM_VERSION = "mgr-3y-v1"`）

### P2.4 验证（关键）

- [x] **断言 161005 全历史复权收益 ≈1500%（不是 462%）** ← 锁死复权口径
- [x] 断言张坤 `30189744`：最长任期年化 ≈10.5%、加权 ≈5.2%（允许小数误差）
- [x] 断言共管基金不会被 min 误杀（已有回归用例，保持绿）

---

## P3 API

> **实现与计划不同**：路由未落在 `src/api/routes.py`，而是独立成 `src/api/manager_routes.py`，
> 由 `src/main.py` 以 `app.include_router(router_managers, prefix="/api/funds")` 挂载。
> 实际路径为 `/api/funds/managers/screen` 与 `/api/funds/managers/{manager_id}`。

- [x] `src/api/models.py` 新增 `ManagerListItem`、`ManagerDetailResponse`
- [x] `src/api/manager_routes.py` 新增 `router_managers`（prefix `/api/funds`）
  - [x] `GET /api/funds/managers/screen`（参数见 design §5）
  - [x] `GET /api/funds/managers/{manager_id}`
  - [x] 附带 `GET /api/funds/managers/refresh`、`GET /api/funds/managers/refresh/status`
- [x] `src/services/manager_service.py` 实现筛选/分页/排序
- [x] 排序白名单防注入
- [x] 分页不变量：`total` = 筛后总数（对齐现有契约）

### 验证

```bash
curl 'http://127.0.0.1:8095/api/funds/managers/screen?min_career_years=5&limit=3'
curl 'http://127.0.0.1:8095/api/funds/managers/30189744'   # 张坤
```

- [x] 张坤详情返回 5 只基金（含 2 只已离任）
- [x] 分页 total 不随 limit 变化

---

## P4 前端

> **实现与计划不同**：类型与请求层未落在 `src/lib/types.ts` / `src/lib/api.ts`，
> 而是集中在新文件 `src/lib/managers.ts`（`ManagerListItem`、`ManagerDetail`、
> `ManagerScreenResponse`、`managerApi`），由 `src/app/managers/page.tsx` 消费。

- [x] `apps/fund-select/src/app/managers/page.tsx` 新 tab
- [x] `src/lib/managers.ts` 加 `ManagerListItem` 等类型（实现与计划不同，未放 `types.ts`）
- [x] `src/lib/managers.ts` 加 `managerApi` 请求层（实现与计划不同，未放 `api.ts`）
- [x] 列表列：姓名 / 公司 / 从业年限 / 在管规模 / 加权年化 / 最大回撤 / 在管只数
- [x] 点击行展开历任基金抽屉
- [x] 顶部导航加入口（`FundsNavigation.tsx` 中 `key: 'managers'`）
- [x] 经理详情在任/已离任双 tab（提交 `8a11b2a`）
- [x] 经理↔基金双向关联徽章跳转与反向链接（提交 `8bf41c2`）

### 验证

```bash
cd apps/fund-select
./node_modules/.bin/tsc --noEmit
pnpm build
```

---

## 风险文件（改动需谨慎）

| 文件 | 风险 |
|---|---|
| `src/data/manager_fetcher.py` | 现有 schedule 依赖，改签名会炸；**只加不改** |
| `src/db/models.py` | 影响全部测试夹具 |
| `src/services/filter_service.py` | 四 tab 核心，本任务尽量不碰 |
| `src/scheduler/scheduler.json` | 加任务需同步 cron_human 与测试 |

## 回滚点

- P1 后：删两张新表，无影响
- P2 后：仅数据，删列/表即可
- P3 后：下线路由
- P4 后：删页面

## 完成前必查

```bash
cd backend/fund-select && .venv/Scripts/python.exe -m pytest tests/ -q    # 516+ 全绿
cd apps/fund-select && ./node_modules/.bin/tsc --noEmit                   # 无错
```

- [x] 现有四个 tab 行为未变
- [x] `min_mgr_exp` 语义未变
- [x] 重名经理可区分
- [x] 复权口径断言通过

## 相关提交

| 提交 | 内容 |
|---|---|
| `2415110` | 经理筛选三项派生指标：胜率/独管/代表作背离 |
| `a410b5f` | 经理筛选分层默认值 + 在管只数筛选 |
| `162e9a1` | 经理年化双口径拆分：含离任 + 在管 |
| `8a11b2a` | 经理详情拆在任/已离任双 tab |
| `8bf41c2` | 经理↔基金双向关联：徽章跳转 + 在榜汇总 + 反向链接 |
| `a023440` | 经理 tab 样式统一与刷新入口 |
