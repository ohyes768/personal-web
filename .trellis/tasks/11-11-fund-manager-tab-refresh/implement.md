# 实施清单：经理 tab 样式统一与刷新入口

## P1 后端：采集可重复执行

- [x] `src/services/manager_refresh.py`
  - [x] `refresh(..., force: bool = False)`；`force=True` 时 `pending_ids = list(scoped_ids)`
  - [x] `run.total = len(pending_ids)`（M1 后回填）
  - [x] `run.completed/failed` 每人更新，`PROGRESS_COMMIT_EVERY=5` 人落库
  - [x] `run.errors` 改为 `json.dumps(list)`（对齐 `/refresh/status` 的 `json.loads` 契约）
  - [x] 顺手清理 `is_active_equity` 未用 import、`scoped_table` 未用变量

- [x] 测试
  - [x] `test_force_refetches_even_when_fetched`
  - [x] `test_force_false_default_keeps_resume_semantics`
  - [x] `test_progress_total_reports_pending_count`
  - [x] `test_errors_persisted_as_json_array`

## P2 后端：刷新 API

- [x] `src/api/manager_routes.py`
  - [x] `GET /managers/refresh`（BackgroundTasks + `_refresh_lock` 单飞 + 预建 RefreshRun）
  - [x] `GET /managers/refresh/status`（errors 非 JSON 降级）
  - [x] **两个路由注册在 `/{manager_id}` 之前**
- [x] `_run_manager_refresh`：后台自开 `SessionLocal`，异常回写 `status=error`，`finally` 释放锁

- [x] 测试
  - [x] `test_refresh_status_404_when_no_run`
  - [x] `test_refresh_status_reads_run`
  - [x] `test_refresh_status_errors_parsed_as_list`
  - [x] `test_refresh_route_not_swallowed_by_detail_route`（存在性 + 顺序）
  - [x] `test_refresh_409_when_already_running`

## P3 后端：最长任期排序（顺带修复）

- [x] `manager_service.SORT_COLUMNS` 加 `longest_tenure_years`
- [x] getter 补 `longest_tenure_years`
- [x] `manager_routes.VALID_SORTS` 加 `longest_tenure_years`
- [x] `test_sort_longest_tenure_years`
- [x] 清理既有 lint：`and_` 未用 import、`col` 未用解包

## P4 前端：共享件

- [x] `FundsHeader`
  - [x] `FundsTab` 加 `'managers'`
  - [x] `TITLE['managers'] = '经理·股票基金'`
  - [x] `REFRESH_URL['managers'] = '/funds/api/funds/managers/refresh'`
  - [x] 新增 `totalUnit?: string`（默认「只」）
  - [x] 删除未使用的 `filters` prop + 四个调用点同步移除
- [x] `FilterSidebar`
  - [x] 抽出并导出 `FilterPanelShell`
  - [x] 导出 `DimensionControl`
  - [x] `Dimension.key: NumericFilterKey | string`
- [x] `RefreshStatusPopover`
  - [x] 经理采集文案
  - [x] `partial` → 「部分完成」
  - [x] managers 轮询 `POLL_INTERVAL_SLOW_MS = 10000`
- [x] `lib/types.ts`：`RefreshStatus.status` 加 `'partial'`
- [x] `FundsNavigation` 注释更新为六 tab 语义

## P5 前端：经理页重写

- [x] `app/managers/page.tsx`
  - [x] 用 `FundsHeader active="managers" totalUnit="人"`
  - [x] 顶部 chip 行（与 FilterChipBar 同构）+ 关键词输入框
  - [x] 左栏 `FilterPanelShell` + 4 `DimensionControl`
  - [x] `table-fixed text-xs` + `SortableHeader` 三态排序
  - [x] 窄屏底部 sheet
  - [x] 骨架屏 / 空态文案与基金表一致
  - [x] `Suspense` 包裹（`FundsHeader` 内部 `useSearchParams`）
  - [x] 保留展开历任基金 + `AbortController` 防串台
  - [x] 「最长任期」列改绑 `longest_tenure_years`

## 验证

- [x] `pytest tests/ -q` → 581 passed
- [x] `ruff check` 改动文件全绿（剩余 8 处来自本次未触碰的文件）
- [x] `tsc --noEmit` 无错
- [x] `pnpm build` 通过（11 路由，`/managers` 4.32 kB）
- [x] 本地部署后逐页冒烟：bond / stock / discovery-bond / discovery-stock / managers /
      sharpe-board 全 200
- [x] 容器内实跑：`/managers/refresh` 触发成功，M0 4388 人 → M1 1881 人 → M2 开始采集
- [x] 前端点击「刷新」→ 弹框显示「进行中：25/1881」→ 进度条推进
- [x] 幂等性：重采过程中 `dupe tenures = 0`
- [x] `sort=longest_tenure_years` 生效（8.16 → 7.01 → NULL 排尾）
