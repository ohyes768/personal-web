# 设计：经理 tab 样式统一与刷新入口

## 1. 问题成因

### 1.1 样式漂移

`11-10` 交付经理 tab 时，`managers/page.tsx` 是照 PRD 的「列表列」清单新写的，
没有沿用 `FundsHeader` / `FilterPanel` / `SortableHeader` 三个共享件。后果：

| 维度 | 其余 5 tab | 经理 tab（改前） |
|---|---|---|
| header 容器 | `max-w-[1400px]` | `max-w-6xl` |
| header 内容 | 返回首页 + 标题 + 导航 + 总数 + 刷新 + 齿轮 | 仅标题 + 导航 |
| 筛选 | 左栏 `FilterPanel` + chip bar | 顶部一行内联输入 |
| 表格 | `table-fixed text-xs` + 图标三态排序 | `text-sm` + 文字箭头，单击排序/双击切向 |
| 窄屏 | `FilterSheet` 底部 sheet | 无 |

`FundsHeader` 的 `FundsTab` 联合类型只有四个采集 tab（`REFRESH_URL` / `FULL_REFRESH_API`
都按键索引），经理 tab 当时无法直接塞进去——这是它另起炉灶的直接原因。

### 1.2 刷新是死代码

`src/services/manager_refresh.py` 的 `refresh()` 在 `11-10` 落地时只被单测引用：

- `src/api/manager_routes.py` 只有 `/screen` 与 `/{manager_id}`
- `src/scheduler/scheduler.json` 只有四个基金 tab 任务
- `backend/fund-select/scripts/` 无 manager 脚本，且 `Dockerfile` 只 `COPY src`，
  脚本根本不进镜像

因此线上 `managers` / `manager_tenures` 恒为 0 行。

### 1.3 采集无法二次更新

```python
pending_ids = [mid for mid in scoped_ids if _needs_fetch(session, mid)]  # fetched_at IS NULL
```

首采之后所有经理 `fetched_at` 非空，再次调用 `refresh()` 的 `pending_ids` 为空——
即使接上入口，也只有第一次有效。经理档案的任职变更、新发/离任基金永远更新不进来。

## 2. 后端改动

### 2.1 `force` 参数（`services/manager_refresh.py`）

```python
def refresh(..., force: bool = False):
    pending_ids = (list(scoped_ids) if force
                   else [mid for mid in scoped_ids if _needs_fetch(session, mid)])
```

- 默认 `False` 保持断点续采语义，`test_resume_skips_fetched` 不受影响。
- 刷新入口固定传 `force=True`：产品口径是「每次刷新都是全量重采」，
  因为经理档案没有增量口径（东财不提供变更时间），只能全量覆盖。
- 重采幂等靠 `_replace_tenures`（按 `manager_id` 先 delete 再 insert），
  已由 `test_manager_tenure_re_fetch_replaces_tenures` 锁住。

### 2.2 进度口径

`RefreshRun` 三字段的含义统一为「按人」：

| 字段 | 改前 | 改后 |
|---|---|---|
| `total` | 一直 0（从未赋值） | 本轮 `pending_ids` 人数 |
| `completed` | 每 20 人 commit 时更新 | 每人递增内存值，每 `PROGRESS_COMMIT_EVERY=5` 人落库 |
| `failed` | 只在结束时写 | 同上，随采集推进 |

`total` 在 M1 之后才确定（要先算 scope 集合），所以先 commit 空行拿到 `task_id`，
再由采集线程回填 —— 页面在 M0/M1 阶段看到 `0/0`，进入 M2 后开始推进。

### 2.3 `errors` 契约

`RefreshRun.errors` 的既有契约是 **JSON 数组字符串**（`/refresh/status` 用
`json.loads` 解析再返回 `list[str]`）。`manager_refresh` 原来写的是 `"\n".join(...)`，
与契约不符；改为 `json.dumps(list)`，并在状态端点对非 JSON 旧行做降级（单元素列表），
避免老数据 500。

### 2.4 路由（`api/manager_routes.py`）

| 路由 | 说明 |
|---|---|
| `GET /managers/refresh?limit=` | BackgroundTasks 起任务，立即返回 `task_id` |
| `GET /managers/refresh/status?task_id=` | 查 `RefreshRun`，空 `task_id` 取最近一次 |

**注册顺序**：两者必须排在 `/{manager_id}` 之前，否则 `refresh` 会被当成经理 ID。
`test_refresh_route_not_swallowed_by_detail_route` 同时断言存在性与顺序。

**并发保护**：`threading.Lock` 单飞。全量采集 20-40 分钟，重复点击只会 409，
不重复起线程（两个线程同时写同一批经理会撞唯一键）。

**Session 生命周期**：`BackgroundTasks` 与请求的 `get_db` 依赖不同生命周期，
后台体自己开 `SessionLocal()`，`finally` 里关闭并释放锁。

### 2.5 顺带修复的 bug

页面「最长任期」列绑的是 `managed_fund_count`（在管只数），而后端 `VALID_SORTS`
根本不含 `longest_tenure_years` —— 这一列点了排序会按「管理过几只」排，语义错。
已在 `SORT_COLUMNS` / getter / `VALID_SORTS` 三处补齐 `longest_tenure_years`，
页面改绑正确字段，并加 `TestSortLongestTenure`。

## 3. 前端改动

### 3.1 共享件扩展

| 组件 | 改动 |
|---|---|
| `FundsNavigation` | 无（六 tab 早已包含 managers） |
| `FundsHeader` | `FundsTab` 加 `'managers'`；`TITLE` 加「经理·股票基金」；`REFRESH_URL` 加 managers；新增 `totalUnit`（只/人）；删除从未使用的 `filters` prop |
| `FilterSidebar` | 抽出 `FilterPanelShell`（标题+清空外壳）与导出 `DimensionControl`；`Dimension.key` 放宽为 `NumericFilterKey \| string` 供经理复用 |
| `RefreshStatusPopover` | 加经理文案；`partial` 状态显示「部分完成」；长任务（managers）轮询 10s（1s 轮询 20-40 分钟会打出上千次请求） |
| `SortableHeader` | 无（直接复用三态排序） |

`FundsHeader` 里 `filters` 是 `11-10` 之前遗留的未使用 prop（只在解构里出现），
顺手删掉，四个调用点同步移除该 prop。

### 3.2 经理页重写

保留原有数据逻辑（`managerApi.screen` / `getDetail`、`AbortController` 防串台、
行点击展开历任基金），替换全部表现层：

- `FundsHeader active="managers" totalUnit="人"`
- 顶部 chip 行：数值条件 chip 与 `FilterChipBar` 同构（`bg-info-tint text-info` 圆角 +
  `XMarkIcon` 移除），关键词因为要输入框，独占该行右侧
- 左栏 `FilterPanelShell` + 4 个 `DimensionControl`（从业年限 / 加权年化 / 最大回撤 / 在管规模）
- 表格 `table-fixed text-xs`、`border-rule-strong` 表头、`SortableHeader` 图标三态
- 窄屏底部 sheet（与 `FilterSheet` 同一套表单，内联避免再加一层 props 透传）
- 加载态用 `FundTable` 同款骨架屏，空态文案与基金表一致

`Suspense` 包裹：`FundsHeader` 内部用 `useSearchParams`（`?scheduler=1` 自动开齿轮弹框），
静态预渲染要求页面在 Suspense 边界内，与其余四个 tab 一致。

## 4. 未采纳的方案

- **接 `scheduler.json` 定时任务**：用户明确只要页面刷新按钮，不加每周任务。
- **只采候选池**：用户选全量重采，保证榜单完整。
- **把经理塞进 `FULL_REFRESH_API`**：全量刷新按钮的语义是「带预筛参数跑 pipeline」，
  经理采集没有预筛参数，硬塞会让 `FullRefreshDialog` 多一堆无意义分支；
  走 `REFRESH_URL`（与 bond/stock 的刷新按钮同一条路径）更贴合。

## 5. 风险与边界

| 项 | 处理 |
|---|---|
| 全量采集耗时长（1881 人 × ~1.3s ≈ 40 分钟） | 单飞锁防重复；进度 10s 轮询；断点续采（每 5 人 commit）保证中断可继续 |
| 东财限流 | 沿用既有 `profile_fetch_delay_s=0.3` + 3 次指数退避重试 |
| `force` 破坏续采 | 默认 `False`，只有 API 入口传 `True` |
| 旧 `RefreshRun.errors` 非 JSON | 状态端点降级为单元素列表 |
| 经理 tab 无导出 | 不传 `filters`，`FundsHeader` 的导出逻辑分支不受影响 |
