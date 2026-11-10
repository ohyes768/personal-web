# 实施计划：基金经理维度评价（股票基金）

对应：`prd.md` / `design.md`

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

- [ ] `src/db/models.py` 新增 `Manager`、`ManagerTenure`
- [ ] `Base.metadata.create_all` 自动建表（无需 ALTER，新表）
- [ ] 索引：`managers.name`、`manager_tenures.manager_id`、`manager_tenures.fund_code`
- [ ] 唯一约束：`manager_tenures(manager_id, fund_code, start_date)`

### P1.2 采集器

- [ ] 扩展 `src/data/manager_fetcher.py`
  - [ ] 新增 `fetch_manager_table_with_id()`：直接请求 `dt=14`，保留第 0 列经理 ID
  - [ ] 用 `akshare.utils.demjson.decode` 解析（非标准 JSON）
  - [ ] **保留** `fetch_manager_table` / `fetch_manager_by_fund_code` 原函数签名（现有调用方不动）
- [ ] 新增 `src/data/manager_profile_fetcher.py`
  - [ ] `fetch_manager_tenures(manager_id)` → 解析档案页第 2 个 `<table>`
  - [ ] **必须 `resp.content.decode("utf-8")`**（BOM 陷阱）
  - [ ] 解析 `任职时间`（`~至今` / `~日期`）、`任职天数`（`7年又56天` / `82天`）
- [ ] 新增 `src/data/manager_nav_fetcher.py`
  - [ ] `fetch_adjusted_series(code)` → 解析 `pingzhongdata` 的 `Data_netWorthTrend[].equityReturn`
  - [ ] 连乘重建复权净值曲线

### P1.3 采集编排

- [ ] 新增 `src/services/manager_refresh.py`
  - [ ] M0 拉经理表 → 建 managers 骨架
  - [ ] M1 库内主动权益基金（`market_subtype in ('股票型','混合型-偏股')`）→ 姓名→ID 映射
  - [ ] M2 逐人拉档案页（限速 0.3s + 重试 3 次）→ manager_tenures
  - [ ] 断点续采：`fetched_at IS NULL` 优先
  - [ ] 写 `RefreshRun` 进度（复用现有机制）

### P1.4 验证

```bash
cd backend/fund-select
.venv/Scripts/python.exe -m pytest tests/ -q          # 必须 516+
```

- [ ] 新增单测：`test_manager_profile_fetcher.py`（mock HTML 夹具，验证 BOM/天数解析）
- [ ] 新增单测：`test_manager_refresh.py`（mock 采集，验证重名经理落不同主键）

---

## P2 指标计算

### P2.1 任职年化

- [ ] `src/services/manager_metrics.py`
  - [ ] `annualize(return_pct, days)` — 见 design §4.1
  - [ ] 边界：`days=0` / `return<=-100` → None
  - [ ] 回填 `manager_tenures.annual_return`

### P2.2 加权年化

- [ ] `weighted_annual(tenures)` — 按 tenure_days 加权，见 design §4.2
- [ ] **只统计主动权益段**（排除该经理管的债基/QDII 段）
- [ ] 写入 `managers.tenure_weighted_annual`

### P2.3 代表基金与风险

- [ ] `pick_representative(tenures)` — 主动权益 + 最长任期 + 在管优先
- [ ] `compute_risk(code, start, end)` — 基于复权曲线算 mdd/vol/sharpe/calmar
- [ ] 口径版本 `mgr-3y-v1` 写入常量

### P2.4 验证（关键）

- [ ] **断言 161005 全历史复权收益 ≈1500%（不是 462%）** ← 锁死复权口径
- [ ] 断言张坤 `30189744`：最长任期年化 ≈10.5%、加权 ≈5.2%（允许小数误差）
- [ ] 断言共管基金不会被 min 误杀（已有回归用例，保持绿）

---

## P3 API

- [ ] `src/api/models.py` 新增 `ManagerListItem`、`ManagerDetailResponse`
- [ ] `src/api/routes.py` 新增 `router_managers`（prefix `/managers`）
  - [ ] `GET /api/funds/managers/screen`（参数见 design §5）
  - [ ] `GET /api/funds/managers/{manager_id}`
- [ ] `src/services/manager_service.py` 实现筛选/分页/排序
- [ ] 排序白名单防注入
- [ ] 分页不变量：`total` = 筛后总数（对齐现有契约）

### 验证

```bash
curl 'http://127.0.0.1:8095/api/funds/managers/screen?min_career_years=5&limit=3'
curl 'http://127.0.0.1:8095/api/funds/managers/30189744'   # 张坤
```

- [ ] 张坤详情返回 5 只基金（含 2 只已离任）
- [ ] 分页 total 不随 limit 变化

---

## P4 前端

- [ ] `apps/fund-select/src/app/managers/page.tsx` 新 tab
- [ ] `src/lib/types.ts` 加 `ManagerListItem`
- [ ] `src/lib/api.ts` 加 `fetchManagers`
- [ ] 列表列：姓名 / 公司 / 从业年限 / 在管规模 / 加权年化 / 最大回撤 / 在管只数
- [ ] 点击行展开历任基金抽屉
- [ ] 顶部导航加入口

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

- [ ] 现有四个 tab 行为未变
- [ ] `min_mgr_exp` 语义未变
- [ ] 重名经理可区分
- [ ] 复权口径断言通过
