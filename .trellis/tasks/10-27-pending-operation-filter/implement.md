# 实现清单

> **进度快照(2026-10-27 恢复后)**
> - 步骤 1/2(后端)已完成:`pending_operation_bucket`、catalog `operation` 筛选、用途确认可省略证据。`pytest` 全量 915 passed。
> - 步骤 3/4/5(前端)沿用暂停前的改动。`catalog-filters` / `use-review` / `position-status` 均通过。
> - 工作树另有他 session 的「地图收录口径统计」改动(page.tsx / types.ts / tests/admission-stats.test.cjs / backend routes.py / backend test_api.py),与本任务无关,提交时不得夹带。
> - 全量 `node --test tests/*.test.cjs` 另有 3 个既有失败,与本任务无关:community-management 的 details 断言,以及 rental-dashboard / rental-sources 找不到 `RentalRefreshButton.tsx`。

测试命令(Windows):
- 后端:`cd backend/housing-map && .venv/Scripts/python -m pytest -q`
- 前端单测:`node apps/housing-map/tests/catalog-filters.test.cjs`、`node apps/housing-map/tests/position-status.test.cjs`(在 apps/housing-map 下)
- 构建:`cd apps/housing-map && pnpm build`

## 1. 后端:归桶 + operation 筛选

- 在 `backend/housing-map/src/services/`(collection_pipeline.py 或新文件)新增 `pending_operation_bucket(row) -> 'position' | 'use' | 'facts'`,分支顺序对齐 `apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx` 的 `pipelineStageLabel`(180-191 行):先判 `type_uncertain` 且定位未选定 → position;再按 qualification 映射;未知兜底 facts。
- `backend/housing-map/src/api/directory_workflow_routes.py` `catalog()`(98 行起)新增 `operation: Literal['', 'position', 'use', 'facts'] = ''` 参数,pending 行按桶过滤。
- 新增 pytest 用例覆盖各分支(参考现有 workflow/api 测试的自造数据方式,勿依赖快照 registry)。

验证:`.venv/Scripts/python -m pytest tests/ -q`

## 2. 后端:用途确认免证据(前端不再发送证据,后端兼容默认空)

- `directory_workflow_routes.py:280-291`:`UseEvidence.url` 由 `Field(min_length=1, max_length=500)` 改为 `Field('', max_length=500)`;`UseConfirm.use_evidence` 由 `min_length=1` 改为 `Field(default=[], max_length=10)`。
- 同步修改断言"空 evidence 422"的用例:`tests/test_use_review_api.py:104` 一带,改为可提交;确认住宅缺类型 / 非住宅缺理由仍 422 的断言保留。

验证:`.venv/Scripts/python -m pytest tests/test_use_review_api.py tests/test_use_review_confirm.py tests/test_use_review_scenario.py -q`

## 3. 前端:筛选维度

- `apps/housing-map/src/components/community/CatalogFilters.tsx`:
  - `CatalogFilterKey` 增加 `'operation'`;`catalogFilterLabels` 增加 `operation: '待处理操作'`。
  - `catalogFilterOptions` 增加 case:全部 / 地点待处理 / 用途待确认 / 资料待补。
  - `scopes.pending` 由 `['q','district','property_type','position'] + more:['use']` 改为 `['q','district','operation'] + more:['use']`。
- 请求参数经既有 `catalogFilterParams` 自动携带,`DirectoryFlowWorkspace` 无需改请求拼装。
- 同步更新 `apps/housing-map/tests/catalog-filters.test.cjs` 中 pending scope 相关断言。

验证:`node tests/catalog-filters.test.cjs`

## 4. 前端:待处理操作列

- `apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx` `CatalogTable`(208-232 行):
  - pending 时第 5 列表头「住宅用途核对」→「待处理操作」(不收录页签维持原文案)。
  - 单元格内 `pipelineStageLabel(c)` 由 `<small>` 升级为 badge(`<span className="directory-badge ...">`),pending 行恒显示(去掉 `collection_pipeline_version &&` 前置);`UseReviewBadge` compact 保留为辅助。
- `apps/housing-map/src/app/globals.css` 按需补三桶 badge 配色(如 directory-op-position/use/facts),沿用现有 directory-badge 风格。
- 表列宽若受 `table-layout: fixed` 约束(见目录表列宽规则),确认该列宽度规则无需调整。

验证:`node tests/position-status.test.cjs`

## 5. 前端:UseReviewPanel 移除证据表单

- `apps/housing-map/src/components/community/UseReviewPanel.tsx`:
  - 人工确认表单移除 证据来源 / 证据链接 / 证据说明 三个输入及对应 state(source/url/note)。
  - `ready` 只看决定与理由:`decision === 'residential' || !!reason.trim()`。
  - 提交体只含 revision / decision / property_type / reason,不带 use_evidence。
  - 理由 placeholder 保留"确认为非住宅必填"提示;历史人工结论(human.evidence)只读展示保留。

## 6. 全量回归

- 后端全量 pytest;前端两个 .cjs 测试;`pnpm build`。
- 手动:dev server 打开 /map 收录目录待处理页签,验证筛选与操作列显示(如环境可用)。
