# 执行计划

> 顺序刻意如此：先做后端并验证口径，再做前端页面，最后接入口。每一步都有可独立验证的产出。

## Step 1 · 后端服务层

**文件**：`backend/fund-select/src/services/sharpe_trend_service.py`（新建）

实现：
- `rolling_sharpe_series(nav_df, rf_series) -> list[Point]`（纯函数，无 IO，可单测）
- `compute_trend_stats(points, threshold) -> Stats`（纯函数）
- `build_trend(db, code, range) -> Response dict`（编排：读 rf → 缓存拉 nav → 算 → 裁 range）
- `_cached_nav(code)`（TTL 1h 进程内缓存）

**验证**：写临时脚本对生产库的 000628 跑一遍，确认：
- 最新点夏普 ≈ `fund_risk_metrics.sharpe`（纯净值口径）
- 2024-09-30 附近点 sample_days ≈ 729（未被基准截断）

## Step 2 · API 路由

**文件**：
- `backend/fund-select/src/api/sharpe_trend.py`（新建）：`GET /sharpe-trend/{code}`
- `backend/fund-select/src/api/models.py`：加 3 个 DTO
- `backend/fund-select/src/main.py`：在 `router` **之前** include

**验证**：`curl` 本地 8105/8095 起服务，打 `/api/funds/sharpe-trend/000628`、`/sharpe-trend/notexist`、`?range=1y`。

## Step 3 · 后端测试

**文件**：`backend/fund-select/tests/test_sharpe_trend.py`（新建）

按 design §7 的 7 组用例写。关键回归：**benchmark 截断防护**（历史窗口 sample_days 不被 join 缩短）。

**验证**：`/tmp/fsvenv/bin/python -m pytest tests/ -q` → 597 + 新增全绿。

## Step 4 · 前端 lib 层

**文件**：
- `apps/fund-select/src/lib/sharpe-trend.ts`（新建）：DTO 接口、`parseTrendSearch`、`fetchSharpeTrend`
- `apps/fund-select/src/lib/sharpe-trend.test.ts`（新建）

**验证**：`node --experimental-strip-types --test src/lib/sharpe-trend.test.ts`。

## Step 5 · 前端页面 + KPI 组件

**文件**：
- `apps/fund-select/src/app/sharpe-trend/page.tsx`（新建）
- `apps/fund-select/src/components/sharpe-trend/SharpeTrendStats.tsx`（新建）
- `apps/fund-select/src/components/FundsNavigation.tsx`（加第七项）

页面结构：头部（返回首页 + 标题 + FundsNavigation）→ 代码输入/基金名 → 区间选择 → KPI 行 → 图表。

**验证**：dev server 打开 `/funds/sharpe-trend?code=000628`，图出、KPI 显示、切区间不整页刷新。

## Step 6 · 三处入口

**文件**：
- `apps/fund-select/src/components/FundTable.tsx`（`trendEnabled` prop + Link + stopPropagation）
- `apps/fund-select/src/app/stock/page.tsx`、`discovery-stock/page.tsx`（传 trendEnabled）
- `apps/fund-select/src/components/RowDetailDrawer.tsx`（夏普 KPI → Link）
- `apps/fund-select/src/components/sharpe-board/SharpeBoardTable.tsx`（code → Link）

**验证**：逐一点击，确认不误触发选中/抽屉；债基两 tab 代码不可点。

## Step 7 · 全量验证

- 后端 597+ 测试全绿
- 前端 `tsc --noEmit`
- 浏览器 375 / 1440 两档截图
- 6 个既有路由 + 新路由冒烟 200

## Step 8 · 文档与收尾

- `contracts.md` 加 §17（夏普走势页契约：纯净值口径的决定与实测证据、API、KPI 定义、入口清单）
- `frontend/fund-sharpe-board.md` 或新建 frontend spec 记录走势页前端契约
- 提交 + `add_session.py` 记录
- `task.py archive`

## 依赖与并行约束

- Step 1–3（后端）与 Step 4–5（前端 lib/页面）可并行，但前端联调需后端就绪。
- Step 6 触碰 `FundTable.tsx` 等共享文件——**动手前先 `git status`**，避免与并行会话冲突（近期曾被 `8a11b2a` 覆盖过一次）。
- 部署验证走 `./scripts/deploy-nas.sh fund-select both --no-pull`（需 `danger-full-access` + SERVICE_MANAGER 环境变量）。
