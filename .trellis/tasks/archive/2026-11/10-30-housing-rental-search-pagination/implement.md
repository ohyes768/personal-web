# 实施计划：搜索分页续查与失败状态区分

前置：`task.py start` 后执行。工作区有其他任务未提交改动（10-30-housing-review-maintenance 等），只改、只提交本任务文件。

## 步骤

1. **后端搜索分页** `backend/housing-map/src/services/xingfuli_discovery.py`
   - `SEARCH_PAGE_SIZE = 20`；`search(name, channel, offset=0)`，URL 透传 offset。
   - 验证：`uv run python -m pytest tests/test_xingfuli_discovery.py -q`

2. **checkpoint v3** `backend/housing-map/src/services/rental_reference/discovery_checkpoint.py`
   - `VERSION = 3`；搜索键含 offset；删除 complete=False 搜索步不复用的条件及旧注释。
   - 验证：`uv run python -m pytest tests/test_matching_speed.py -q`（预期部分缓存类测试需同步修改）

3. **探查分页循环** `backend/housing-map/src/services/rental_reference/probe.py`
   - `_search` 分页循环 + page_errors/degraded/truncated 信号重组 + 自动绑定门槛收紧 + deferred 文案。
   - 验证：`uv run python -m pytest tests/test_rental_probe.py -q`

4. **批次统计** `backend/housing-map/src/services/rental_reference/matching.py`
   - outcome 映射加 `'deferred': 'deferred'`；association 加 `incomplete` 计数（初始化与 `_run` 两处）。
   - 验证：`uv run python -m pytest tests/test_matching_speed.py -q`

5. **测试更新**
   - `tests/test_rental_probe.py`：FakeDiscovery.search 加 `offset=0` 参数（calls 记 4 元组）；`test_identity_search_uses_only_second_hand_and_neighborhood` 等 calls 断言同步。
   - `tests/test_matching_speed.py`：重写 `test_incomplete_cached_search_is_retried_live_within_window` 为断点续查语义；`test_complete_unique_channel_stops_search_but_verifies_both_owners`、`test_failed_competitor_never_allows_automatic_binding`、`test_steps_survive_process_recreation_after_partial_search`、`test_completed_http_step_survives_abrupt_process_exit` 的 calls 元组加 offset；`test_truncated_search_never_autobinds` 语义保持（重复页保护路径）。
   - 新增 `tests/test_rental_search_pagination.py`（复用 test_rental_probe 的 setup/FakeDiscovery/homepage/service/run）：
     1. 首页满页无关、第二页强候选 → 找到并绑定（验收1）
     2. 预算停在分页中途 → deferred；续跑 offset=0 零请求（cache_hits）、真实请求下一 offset（验收2）
     3. 第二页请求失败 → upstream_failed + message 含原因；续跑重试失败页、已成功页缓存命中（验收3）
     4. 翻到 complete 页且无候选 → homepage_not_found（验收4）
     5. 分页未完时唯一强候选不自动绑定（deferred），续跑补完页后才绑定（验收6）
     6. offset>0 重复页 → 停止翻页且不自动绑定（needs_selection）
     7. v2 旧缓存被忽略重查
     8. 批次 deferred outcome 计入 association.incomplete、incremental 重新入队
   - 验证：`uv run python -m pytest tests/ -q`（全量）

6. **前端**
   - `apps/housing-map/src/lib/rental-probe.ts`：deferred 文案。
   - `apps/housing-map/src/components/rental/RentalAssociationReview.tsx`：search_deferred 文案。
   - `apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx`：统计行加未查完 + 类型字段。
   - 同步 `apps/housing-map/tests/rental-dashboard.test.cjs`（211 行 search_deferred 文案断言）、检查 `directory-flow.test.cjs` association 渲染。
   - 验证：`cd apps/housing-map && pnpm build`；`node --test tests/rental-dashboard.test.cjs tests/directory-flow.test.cjs`（按仓库测试入口实际方式）

7. **spec 更新** `.trellis/spec/backend/housing-map/backend/xingfuli-discovery.md`
   - 新增"搜索分页与状态三分"小节；改写"首页不完整的搜索步不参与缓存复用"条款为翻页进度语义。

8. **提交**
   - 只 add 本任务文件：上述源码/测试 + `.trellis/tasks/10-30-housing-rental-search-pagination/` + spec。
   - `DirectoryFlowWorkspace.tsx` 混有 review-maintenance 任务的未提交 hunk（review prop 位置、reopen-review 时机）：提交前 `git diff` 逐 hunk 检查，仅暂存本任务改动（`git add -p` 或 `git apply --cached`），无法干净拆分时先问用户。
   - 不提交：`.tmp-qa-*.png`、`community_registry.sqlite3`、其他任务目录。

## 回滚点

每步独立可验证；任一步失败先修复再前进，不跳步。全部完成后 `uv run python -m pytest tests/ -q` 全绿再提交。
