# PRD：经理 tab 样式统一与刷新入口

## 背景

任务 `11-10-fund-manager-evaluation` 交付了经理维度页面（`/funds/managers`）与后端采集编排
`src/services/manager_refresh.py`，但存在两个遗留问题：

1. **样式与其余 5 个 tab 不一致**。`managers/page.tsx` 完全手写了一套页面骨架：
   - 自建 header：`max-w-6xl`、`bg-paper/95 backdrop-blur`、标题「经理·股票基金」、
     无「← 返回首页」、无总数显示、无定时任务齿轮
   - 筛选：顶部一行内联 `NumInput` + 搜索框
   - 表格：`text-sm`、表头文字箭头 `↑↓`、单击排序列/双击切方向（隐藏交互）
   其余 5 个 tab 统一用 `FundsHeader`（`max-w-[1400px]` + 返回首页 + 标题 + `共 N 只` + 齿轮）、
   左侧 `FilterPanel` 面板 + `FilterChipBar` 激活 chips、`table-fixed text-xs` + `SortableHeader` 三态图标。

2. **线上没有任何经理数据，且没有任何刷新入口**。`manager_refresh.py` 是死代码：
   - 无 API 路由、无 `scheduler.json` 任务、无 `scripts/` 脚本
   - `Dockerfile` 只 `COPY src`、`scripts` 不进镜像
   - 容器内 `managers` / `manager_tenures` 均 0 行，`/api/funds/managers/screen` 恒返回
     `{"total":0,"items":[]}`

3. **采集逻辑本身无法更新已采数据**。`manager_refresh.py` 用
   `pending_ids = [mid for mid in scoped_ids if _needs_fetch(...)]` 只挑 `fetched_at IS NULL`，
   跑第二次是空转——即便接上入口也只能首次生效。

## 目标

- 经理 tab 与其余 tab 视觉/交互完全统一（header、筛选栏、表格、分页）。
- 页面提供可用的「刷新」入口，能真正触发采集并显示进度。
- 采集支持重复全量刷新（不是一次性的）。

## 需求

### R1 页面骨架统一

改为复用 `FundsHeader`，`active` 增加 `managers`：

- 标题「经理·股票基金」，带「← 返回首页」、`共 N 人`、定时任务齿轮
- 页面容器 `max-w-[1400px]`，表格区 `bg-paper-card rounded-lg border border-rule`

### R2 筛选区统一

左栏 `FilterPanel` + 窄屏 `FilterSheet`，顶部 `FilterChipBar`：

- 维度沿用现有四类语义，但经理口径：从业年限 / 加权年化 / 最大回撤 / 在管规模
- 关键词（姓名/公司）单独输入框，放在 chip bar 行右侧（筛选面板容纳不下长文本）
- 排序改三态 `SortableHeader`（点击：desc → asc → 取消），与基金表一致

### R3 表格样式统一

- `table-fixed text-xs`，表头 `border-rule-strong`，行 `border-rule` + `hover:bg-paper-tint`
- 排序图标用 `SortableHeader`（`ArrowDownIcon`/`ArrowUpIcon`/`ArrowsUpDownIcon`）
- 展开详情行沿用现有实现（行点击展开历任基金）

### R4 刷新入口（只加页面按钮，不接定时任务）

- `FundsHeader` 的 `RefreshStatusPopover` 复用：新增经理刷新端点
- 后端新增 `GET /api/funds/managers/refresh`（BackgroundTasks + task_id）与
  `GET /api/funds/managers/refresh/status`
- 前端 `managers` tab 传入经理的 refresh/status URL，进度条按「已采经理 / 总经理数」显示
- 刷新完成后自动重载列表（`onRefreshed` 已有该语义）

### R5 采集可重复执行

`manager_refresh.refresh()` 增加 `force: bool = False`：

- `force=False`（默认，向后兼容）：保持现有断点续采语义，只采 `fetched_at IS NULL`
- `force=True`：重采 scope 内全部经理（覆盖档案变更、新增/离任），仍逐人 commit 断点续采
- 刷新入口用 `force=True`（每次全量重采）

### R6 进度可观测

`RefreshRun.completed` 在每人采完后递增（现有实现只在每 20 人 commit 时更新），
让页面进度条平滑推进；`total` = 本轮待采人数。

## 非目标

- 不接 `scheduler.json` 定时任务（用户明确只要刷新按钮）
- 不改 `min_mgr_exp` 基金维度语义
- 不改 `manager_service` 的筛选/排序契约
- 不动现有 4 个基金 tab 的行为

## 验收标准

1. `/funds/managers` 与 `/funds/bond` 在 1440px 下 header 结构一致（返回首页 / 标题 / 导航 / 总数 / 齿轮），
   无「经理·股票基金」自建 header 残留。
2. 桌面左栏有 `FilterPanel`、窄屏 `FilterSheet`、顶部 `FilterChipBar` chips。
3. 表头为图标三态排序，与基金表一致；表格 `text-xs`。
4. 点击「刷新」→ 轮询进度 → 完成后列表自动重载；进度条按人数推进。
5. 第二次点「刷新」仍会真正重采（不是空转）。
6. `GET /api/funds/managers/refresh?dry_run=1`（或等价的 limit）验证端点连通。
7. `pytest tests/ -q` 全绿（现有 516+ 用例）。
8. `tsc --noEmit` 无错。

## 风险

| 文件 | 风险 |
|---|---|
| `src/services/manager_refresh.py` | 新增 `force` 参数须默认 False，否则 `test_resume_skips_fetched` 会失败 |
| `FundsHeader.tsx` | `FundsTab` 联合类型加 `managers`，`TITLE` 映射需同步 |
| `managers/page.tsx` | 整个重写；现有展开详情逻辑要保留 |
| `manager_routes.py` | 路由注册顺序在通用 `/{code}` 之前，新端点须同在此处 |
