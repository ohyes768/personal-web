# 基金筛选平台 v1 - 执行计划

> 按 Trellis 工作流 Phase 2：Execute 设计。每个阶段独立可验证、可回滚。

## 阶段划分

```
P0: 项目骨架              ← 30 min，最小可启动
P1: 后端数据采集          ← 3 h，跑通配置 31 只 + 费率
P2: 后端 API + 单元测试   ← 3 h，6 个接口
P3: 前端骨架 + 表格       ← 3 h，可见筛选页
P4: 筛选面板 + URL 同步   ← 3 h，4 个维度可用
P5: 对比三件套（复用）    ← 2 h，对比抽屉工作
P6: 刷新 + 导出 + 启动脚本 ← 2 h，端到端打通
P7: 验证 + 收尾           ← 1 h，覆盖验收标准
```

总计约 **18 小时**，可分 2-3 个 session 完成。

---

## P0: 项目骨架（30 min）

**目标**：目录结构 + 空 FastAPI + 空 Next.js，能起服务

### 步骤

1. 创建目录结构
   ```bash
   mkdir -p F:/personal-projects/fund-select/{backend/{src/{api,services,data,db,scheduler,utils},tests,data,cache,scripts},frontend/src/{app/{funds,api/funds/'[...path]'},components,lib,tests},scripts}
   ```

2. 写 `backend/pyproject.toml`：复制 dividend-select 的，改 name = "fund-select"

3. 写 `backend/.env.example`：`SERVER_PORT=8095`, `DATABASE_URL=sqlite:///./data/funds.db`, `LOG_LEVEL=INFO`

4. 写 `backend/src/main.py`：最小 FastAPI app + CORS + `/health`

5. 写 `frontend/package.json`：复制 dividend 的，删掉 watchlist 相关依赖

6. 写 `frontend/next.config.ts`：`basePath: '/funds'`, `BACKEND_URL: 'http://localhost:8095'`

7. 写 `frontend/src/app/layout.tsx` + `frontend/src/app/page.tsx`（redirect）

### 验证

```bash
cd F:/personal-projects/fund-select/backend
uv sync
uvicorn src.main:app --port 8095 --reload
# 访问 http://localhost:8095/health → {"status": "ok"}

cd F:/personal-projects/fund-select/frontend
pnpm install
pnpm dev
# 访问 http://localhost:3005/funds → 看到占位页面
```

### 回滚

直接删目录。

---

## P1: 后端数据采集（4 h）

**目标**：能跑通单只基金的完整数据采集，写入 SQLite

### 步骤

1. **P1.1 ORM（45 min）**
   - `src/db/models.py`：`Fund` / `FundPerformance` / `FundHoldingsBond` / `FundFees`
   - `src/db/session.py`：`engine` + `SessionLocal` + `init_db()`
   - 验证：`python -c "from src.db.models import Fund; print(Fund.__tablename__)"`

2. **P1.2 fetcher（1.5 h）**
   - `src/data/fund_universe.py`：读 `backend/config/funds.yaml`（31 只）
   - `src/data/manager_fetcher.py`：封装 `ak.fund_manager_em()`，缓存到 `cache/manager_em.json`
   - `src/data/fund_basic_fetcher.py`：封装 `ak.fund_individual_basic_info_xq(code)`
   - `src/data/nav_fetcher.py`：封装 `ak.fund_open_fund_info_em(code, indicator='单位净值走势')`
   - `src/data/holdings_fetcher.py` + `bond_classifier.py`：从 `fund_screen_31.py` 抽出
   - `src/data/fee_fetcher.py`：补回实现，输出对齐 `cache/fees_{code}.json`
   - 验证：单测 mock；夹具可用现有 cache JSON

3. **P1.3 业绩计算（45 min）**
   - `src/services/performance_service.py`：移植 `fund_screen_31.py` 净值窗口算法
   - 验证：`tests/test_performance_service.py`

4. **P1.4 采集入口（1 h）**
   - `refresh_configured_funds()`：只拉 yaml 名单，不是全市场
   - 空库引导：可导入 `results_31.csv`
   - APScheduler 每日任务 + `python -m src.scheduler.daily_refresh --once`
   - 验证：`--once` 对 31 只或先 `--limit 5`

### 验证

```bash
cd F:/personal-projects/fund-select/backend
python -m src.scheduler.daily_refresh --once --limit 5
sqlite3 data/funds.db "SELECT code, name, size_yi, age_years, mgr_experience_years FROM funds LIMIT 5"
sqlite3 data/funds.db "SELECT code, dd_3y, ret_3y FROM fund_performance LIMIT 5"
```

### 回滚

清空 `data/funds.db`，代码改动回退到 P0。

---

## P2: 后端 API + 单元测试（3 h）

**目标**：6 个接口全部工作，单测覆盖率 ≥ 60%

### 步骤

1. **P2.1 Pydantic 模型（30 min）**
   - `src/api/models.py`：`FundDTO`, `FundDetailDTO`, `PerformanceDTO`, `ScreenResponse`, `StatsResponse`, `RefreshResponse`, `RefreshStatusResponse`
   - 全部从 ORM 模型转换，避免直接返回 ORM 对象

2. **P2.2 filter_service（45 min）**
   - `src/services/filter_service.py`：按 design.md §2.3 实现
   - 单测 `tests/test_filter_service.py`：4 个维度组合 / 排序 / 默认无过滤返回全部；**不分页**

3. **P2.3 routes（1 h）**
   - `src/api/routes.py`：6 个接口
   - 错误处理：参数越界 422、找不到基金 404、内部错误 500
   - CORS：允许 `http://localhost:3005`

4. **P2.4 export_service（30 min）**
   - `src/services/export_service.py`：复用 filter_service.screen() 逻辑，生成 UTF-8 BOM CSV
   - 接口 `GET /api/funds/export/csv`

5. **P2.5 单测（45 min）**
   - `tests/test_filter_service.py` + `tests/test_performance_service.py` + `tests/test_api.py`
   - 用 in-memory SQLite fixture（`sqlite:///:memory:`）
   - 跑：`pytest tests/ -v --cov=src --cov-report=term-missing`

### 验证

```bash
cd F:/personal-projects/fund-select/backend
pytest tests/ -v --cov=src --cov-report=term-missing
# 启动服务
uvicorn src.main:app --port 8095 --reload
# 测 6 个接口
curl http://localhost:8095/api/funds/screen?min_size_yi=2
curl http://localhost:8095/api/funds/161119
curl http://localhost:8095/api/funds/stats
curl "http://localhost:8095/api/funds/screen?min_age=3&min_size_yi=2&max_dd_3y=5&min_mgr_exp=5" -o /tmp/test.csv
cat /tmp/test.csv | head
```

### 回滚

回退代码到 P1，接口未发布，无外部影响。

---

## P3: 前端骨架 + 表格（3 h）

**目标**：能看到债基列表，可点击列头排序

### 步骤

1. **P3.1 catch-all 代理（30 min）**
   - `frontend/src/app/api/funds/[...path]/route.ts`：按 design.md §3.5
   - 测试：`curl http://localhost:3005/funds/api/funds/screen`

2. **P3.2 types + api client（30 min）**
   - `frontend/src/lib/types.ts`：`Fund`, `FundPerformance`, `FundDetail`
   - `frontend/src/lib/api.ts`：`fundApi.screen(params)`, `fundApi.getDetail(code)`, `fundApi.getStats()`

3. **P3.3 useFunds hook（30 min）**
   - `frontend/src/lib/useFunds.ts`：`useFundList(filters)`, `useFundDetail(code)`, `useRefresh()`
   - 内部用 `useEffect` + fetch + 简单 loading/error state

4. **P3.4 FundTable + SortableHeader（1.5 h）**
   - `frontend/src/components/SortableHeader.tsx`：点击切换 asc/desc，三态（asc/desc/none）
   - `frontend/src/components/FundTable.tsx`：PRD 主表列（含年费、利率债占比、3 年回撤进度条）、表头排序、行末「对比」
   - 空状态：表格为空时显示"暂无数据，请调整筛选条件"
   - 骨架屏：loading 时显示 placeholder

### 验证

```bash
cd F:/personal-projects/fund-select/frontend
pnpm dev
# 访问 http://localhost:3005/funds
# 看到债基列表，表头可点击切换排序
```

### 回滚

回退到 P0 占位页。

---

## P4: 筛选面板 + URL 同步（3 h）

**目标**：4 个筛选维度可用，URL 同步，chip 显示已选

### 步骤

1. **P4.1 useFilters hook（1 h）**
   - `frontend/src/lib/useFilters.ts`：
     - state: `{min_age, min_size_yi, max_dd_3y, min_mgr_exp, sort, order}`（均可空）
     - 双向同步 `useSearchParams`
     - 默认：无阈值，`sort=size_yi&order=desc`
   - 单测 `tests/useFilters.test.ts`

2. **P4.2 FilterSidebar（1 h）**
   - 4 个折叠组：成立年限 / 规模 / 3 年回撤 / 经理从业
   - 数值类用 `<input type="number">` + 滑块条（`<input type="range">`）
   - 单位后缀：「年」「亿」「%」
   - "清空全部"按钮

3. **P4.3 FilterChipBar（30 min）**
   - 顶部横向 chip，显示已选条件
   - 点 × 移除单个条件 → URL 同步
   - 空时显示"未筛选"灰字

4. **P4.4 整合到 page.tsx（30 min）**
   - 桌面布局：`grid grid-cols-[280px_1fr]`
   - 移动布局：FilterSheet（底部弹出），< 640px 时切换

### 验证

```bash
# 访问 http://localhost:3005/funds，调整任意筛选条件，URL 立即更新
# 复制 URL 到新窗口，状态保留
# 调整"规模 ≥ 2亿"，表格立刻刷新
```

### 回滚

保留表格，只回退筛选面板。

---

## P5: 对比三件套（2 h）

**目标**：复用 dividend 的对比交互，泛型化到基金

### 步骤

1. **P5.1 复用 useCompare（30 min）**
   - 从 `apps/dividend/src/lib/hooks.ts:323` 复制
   - 改名 `useCompare.ts`，加 `<T extends Comparable>` 泛型
   - 单测 `tests/useCompare.test.ts`：5 个测试覆盖 toggle/limit/clear

2. **P5.2 复用浮动栏 + 抽屉（30 min）**
   - 复制 `CompareFloatingBar.tsx` + `CompareDrawer.tsx`
   - 把 "股票" → "基金" 文案替换
   - 响应式宽度原样

3. **P5.3 改 CompareTable 为泛型（45 min）**
   - 复制 `CompareTable.tsx`
   - 改成 `<CompareTable<T> items={...} dimensions={...} onRemove={...}>`
   - 维度来自 `fundCompareDimensions`（含年费）+ `fundCompareDisplayOnly`（利率债/申购/赎回）
   - `useHighlights`：只对带 direction 的维度高亮；不包含近 1 年回撤

4. **P5.4 行内对比按钮（15 min）**
   - 在 FundTable 行末放 <CompareButton>，调用 `useCompare().toggleStock(fund)`
   - 到上限时其它行按钮 disabled

### 验证

```bash
# 访问 http://localhost:3005/funds
# 点任意 3 行的"对比"按钮
# 浮动栏浮出，显示 3/5 进度
# 点"开始对比" → 抽屉从右侧滑出
# 每行对比维度中，最优值有 ⭐ 高亮
```

### 回滚

保留筛选 + 表格，只回退对比组件。

---

## P6: 刷新 + 导出 + 启动脚本（2 h）

**目标**：端到端可用，一键启动

### 步骤

1. **P6.1 RefreshStatusPopover（45 min）**
   - 头部右侧加按钮，显示「刷新数据」+ 进度
   - 弹窗显示：当前进度 / 已完成 / 失败列表
   - 调用 `fundApi.refresh()` 启动，`fundApi.refreshStatus()` 轮询（5s 一次）

2. **P6.2 CSV 导出按钮（15 min）**
   - 头部右侧「CSV」按钮
   - 调用 `GET /api/funds/export/csv?...`
   - 前端 fetch → blob → download

3. **P6.3 启动脚本（30 min）**
   - `scripts/start-fund-select-backend.bat`
   - `scripts/start-fund-select-frontend.bat`
   - `scripts/stop-fund-select-backend.bat`
   - 参考 `personal-web/scripts/start-dividend-dev.bat`

4. **P6.4 README（30 min）**
   - `F:/personal-projects/fund-select/README.md`
   - 项目说明 / 启动步骤 / 数据采集说明 / 已知限制

### 验证

```bash
# 点"刷新数据" → 后端开始采集，前端进度条更新
# 点"CSV" → 文件下载，含当前筛选结果
# 双击 .bat → 服务正常启动
```

### 回滚

P0-P5 已可工作，新增功能可独立回滚。

---

## P7: 验证 + 收尾（1 h）

**目标**：对照 PRD §验收标准 逐条勾选

### 步骤

1. **后端 7 项验收**
   - [ ] 后端启动 + `/health` 200
   - [ ] `/api/funds/screen` 无参数返回 31 只
   - [ ] `/api/funds/{code}` 详情完整
   - [ ] `/api/funds/refresh` 3 分钟内完成
   - [ ] `/api/funds/export/csv` 含 BOM
   - [ ] pytest 覆盖 ≥ 60%
   - [ ] 启动 .bat 可用

2. **前端 8 项验收**
   - [ ] `http://localhost:3005/funds` 可访问
   - [ ] 4 个筛选维度实时生效
   - [ ] URL 同步
   - [ ] 表头可排序
   - [ ] 对比按钮 → 浮动栏 → 抽屉 → 高亮
   - [ ] CSV 导出文件名含日期
   - [ ] 移动端布局不破
   - [ ] 启动 .bat 可用

3. **E2E**
   - [ ] 端到端：后端起 → 数据采集 → 前端筛 → 对比 → 导出

4. **commit + push**
   ```bash
   cd F:/personal-projects/fund-select
   git init
   git add .
   git commit -m "feat(fund-select): v1 债基筛选前后端 MVP

   - 后端 FastAPI + akshare + 东财混合数据源
   - 4 个核心筛选维度（成立年限/规模/3年回撤/经理从业）
   - 复用 dividend 对比三件套（useCompare 泛型化）
   - SQLite 存储 + APScheduler 每日采集
   - URL 状态同步 + CSV 导出

   Co-Authored-By: Claude <noreply@anthropic.com>"
   ```

### 验证

对照 PRD §验收标准 逐条勾选。

---

## Review Gates

每个阶段结束都做一次代码 review：
- P1 结束：review fetcher 实现，确认错误处理覆盖
- P2 结束：review API 设计，确认 SQL 注入防住
- P3 结束：review 表格性能（虚拟滚动？v1 不需要，但确认）
- P5 结束：review 对比泛型，确认 dividend 不受影响
- P7 结束：完整 review

## Rollback Points

| 阶段 | 回滚成本 | 影响的外部功能 |
|---|---|---|
| P0 | 极低（删目录） | 无 |
| P1 | 低（清 db） | 无 |
| P2 | 中（API 未发布） | 无 |
| P3-P6 | 低（前后端独立部署） | 无（独立项目） |
| P7 | 不可回滚（已发布） | — |

## Sub-agent Dispatch Hints

如果用 sub-agent 并行：
- P3 + P4 可以并行（前端）
- P1 + P2 必须串行（先采集后 API）
- P5 必须 P3 + P4 完成后（需要 hook）
- P6 必须 P5 完成后（端到端）

## Time Tracking

预估 18h，实际可能 ±30%。建议拆 2-3 个 session：
- Session 1（8h）：P0 + P1 + P2（后端打通）
- Session 2（6h）：P3 + P4 + P5（前端核心）
- Session 3（4h）：P6 + P7（收尾验证）
