# 基金筛选平台 - v1 债基筛选

## Goal

在独立项目 `F:/personal-projects/fund-select` 做出可筛、可对比、可导出的债基工作台。v1 宇宙是后端配置的 **31 只精选基金**（预研 `FUND_CODES`），不是全市场扫描。用户能按成立年限 / 规模 / 近 3 年回撤 / 经理从业年限收窄列表，并横向对比最多 5 只。

## 背景

- 对比交互复用 `apps/dividend`：`useCompare`（`src/lib/hooks.ts:323`）+ `CompareFloatingBar` + `CompareDrawer` + `CompareTable`
- `F:/personal-projects/fund-select/` 已有预研脚本与缓存，**尚无 FastAPI / Next.js**。采集链路移植预研，不另起数据源
- 股基全市场筛选留给后续版本；本名单里已有的混合 / QDII **照常采集展示**

## 预研资产（必须复用）

| 资产 | v1 用法 |
|---|---|
| `demo_two_funds.py` | 单测夹具 / 手工回归 |
| `fund_select.py` | 并发与缓存模式参考；**全市场宇宙与纯债初筛 v1 不启用** |
| `fund_screen_31.py` | 单只快照权威实现（基础信息 + 净值收益/回撤 + 季报利率债分类） |
| `results_31.csv` | fixture、空库引导数据、对比样例 |
| `cache/bond_hold_{code}_2025.json` | 移植 `fetch_bond_hold` / `analyze_holdings` |
| `cache/fees_{code}.json` | 费率字段契约；**fetcher 源码缺失，v1 必须补回** |

初始 31 只代码与 `fund_screen_31.py` 的 `FUND_CODES` 一致：`003547, 161119, 110017, 100050, 006824, 001756, 003102, 007823, 007744, 217022, 009625, 017970, 015530, 004419, 010430, 016239, 002286, 100058, 003376, 110050, 005159, 017024, 510080, 016526, 007360, 675091, 400009, 013138, 675111, 006672, 004010`。含纯债、债券指数、普通债券、QDII，以及混合 `001756`、`004010`。

## Requirements

### 筛选

- 四个可选维度：成立年限 ≥ X；规模 ≥ Y 亿；近 3 年最大回撤 ≤ Z%；经理总从业年限 ≥ W
- 默认不设阈值，进页 31 只全部可见；未填 = 不限制
- 桌面左侧面板 + 移动端底部 sheet；slider + number input；顶部 chip；URL 同步
- v1 不分页；默认按规模降序，表头可点排序

### 主表列

基金代码、名称、基金类型、规模、成立年限、近 3 年回撤、基金经理姓名/公司/从业年限、近 1/3/5 年收益、近 3 年回撤进度条、利率债占比、年费。

### 费用

- 采集字段对齐 `cache/fees_{code}.json`：申购小额档、赎回各档、管理费、托管费、销售服务费
- 年费 `fee_annual = fee_mgmt + fee_custody + (fee_service or 0)`
- 主表 1 列「年费」：管理费 + 托管费（有销售服务费再加一行）
- 申购 / 赎回各档只在对比抽屉展示，不高亮

### 对比

行末「对比」→ 底部浮动栏（最多 5 只）→ 右侧抽屉。

- **最优高亮**：规模、成立年限、经理从业、近 3 年回撤（越小越好）、近 1/3/5 年收益、年费（越低越好）
- **只展示不高亮**：利率债占比、申购费、赎回各档
- 不展示近 1 年回撤（主表无此列）

### 采集与刷新

- 宇宙：`backend/config/funds.yaml`，改文件后生效；v1 无名单 CRUD / 管理页
- 每日定时拉取配置名单 + 手动刷新（调度形态对齐 dividend `scheduler.json`）
- 单只流程移植 `fund_screen_31.py`：经理表一次拉取 → 基础信息 → 净值 → 东财季报持仓 → 费率
- 空库可用 `results_31.csv` / cache 引导，不必等第一次联网刷新才能看表
- 全市场 `fund_open_fund_rank_em` 不当作 v1 验收；fetcher 保持「codes 列表进、快照出」以便后接

### 导出与工程

- CSV 导出当前筛选结果，UTF-8 BOM，文件名含日期
- 前端 Next.js 15，端口 3005，`basePath: /funds`
- 后端 FastAPI，端口 8095
- Windows `.bat` 启动前后端

## Out of scope

- 股基 / 混合 / 货币的独立全市场筛选产品
- 债基二级分类筛选（短债 / 中长债 / 可转债）
- 持仓详情页 / 收益曲线
- 收藏 / 自选 / 监控
- 用户系统
- A4 / 轮播报告
- 基金经理详情页
- 全市场债基扫描
- 名单管理页 / CRUD API

## 验收标准

### 后端

- [ ] `uvicorn src.main:app --port 8095` 启动成功，OpenAPI 可访问
- [ ] `GET /api/funds/screen` 无参数返回配置名单全部（31 只）；带参数按四维过滤
- [ ] `GET /api/funds/161119` 返回易方达中债新综指详情，含业绩与年费字段
- [ ] `GET /api/funds/refresh` 刷新配置名单，返回 `task_id`；31 只数分钟内完成
- [ ] `GET /api/funds/export/csv` 下载 UTF-8 BOM，列名中文
- [ ] `pytest tests/ -v` 覆盖率 ≥ 60%
- [ ] `scripts/start-fund-select-backend.bat` 可在 Windows 启动

### 前端

- [ ] `http://localhost:3005/funds` 可见筛选页；无 query 时 31 只全部可见
- [ ] 四维可独立调整，表格实时刷新；URL 带参刷新后状态保留
- [ ] 表头可排序
- [ ] 行末对比 → 浮动栏 → 满 5 只后其它按钮 disabled → 抽屉滑出
- [ ] 抽屉含高亮维度（回撤 / 年费有最优标记）以及申购/赎回/利率债占比（不高亮）
- [ ] CSV 导出可用，文件名含日期
- [ ] ≤640px：筛选转底部 sheet，对比抽屉接近全屏
- [ ] `scripts/start-fund-select-frontend.bat` 可启动

### 端到端

- [ ] 后端启动 → 手动刷新（或空库引导数据）→ 前端可筛 → 选 3 只对比 → 导出 CSV

## 风险

| 风险 | 缓解 |
|---|---|
| akshare 接口变动 | 单一 `FundDataFetcher` 入口 |
| 东财季报反爬 | 利率债列显示 "-"，筛选不依赖持仓 |
| 费率 fetcher 源码缺失 | 按 `cache/fees_*.json` 契约补实现，单测用缓存夹具 |
| 经理从业为空 | 该维跳过或显示 "-" |
| 净值停更 / 清盘 | `is_active=false`，默认不进筛选结果 |

## 参考

- Dividend 对比：`apps/dividend/src/lib/hooks.ts:323`、`CompareDrawer.tsx`、`CompareTable.tsx`
- 预研：`F:/personal-projects/fund-select/{demo_two_funds,fund_select,fund_screen_31}.py`、`results_31.csv`、`cache/`
- 后端参考：`backend/dividend-select/`（FastAPI、scheduler.json、Windows 启动脚本）
