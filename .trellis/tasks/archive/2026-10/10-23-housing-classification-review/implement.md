# 实施计划：住宅目录高德分类复核与冲突审核

依赖顺序：纯函数层 → 单小区查询/存储 → 人工确认 → eligibility 接入 → 批量任务 → API/投影 → 前端 → 回归与演练。每步先写测试（RED）再实现（GREEN）。

## 前置
- [x] `git diff HEAD` 核对共享工作区：xingfuli 任务未提交改动涉及的文件（`community_registry.py` 等），确认无冲突后基于现状开发；全程不触碰其改动语义。
- [x] 通读 spec：directory-flow.md、directory-position.md、community-admission.md（implement.jsonl 已列）。

## Phase 1 纯函数层（use_review_policy）
- [x] 测试：`amap_category` 全分类码映射（复合 `120302|120203`、空、未知码）；`compare` 矩阵 6+ 分支（含 pending_retry 三态：无证据/not_found/error）；`select_evidence` 复用 position 名称规则（exact/alias/loose、同区、0/1/多候选、候选分类冲突）。
- [x] 实现 `src/services/use_review_policy.py`；名称匹配从 directory_position 抽共享函数（两处调用，不复制逻辑）。
- 验证：`python -m pytest tests/test_use_review_policy.py -v`（backend/housing-map，独立 `--basetemp`）。

## Phase 2 单小区复核查询与存储
- [x] 测试：`review_one` 成功/身份指纹失效/取消后不写/写前快照冲突/not_found/error 持久化；`AmapClient.search_name(types=None)` 不带 types 参数（fake client 断言请求形态）。
- [x] 实现 `src/services/directory_use_review.py` 的 `review_one` + master payload `use_review` 附加写入。
- 验证：`python -m pytest tests/test_directory_use_review.py -v`。

## Phase 3 人工用途确认（registry + admission）
- [x] 测试：confirm 成功写入决定与事件；证据/理由缺失 422；revision 过期 409；目录模式下旧 `admit` 仍被拒；删除/合并目标 409；人工排除/锁不可被 confirm 绕过；确认后再次批量/刷新不覆盖。
- [x] 实现 `CommunityRegistry.confirm_use`（或等价方法）+ `admission_use_confirm` 事件。
- 验证：`python -m pytest tests/test_community_registry.py tests/test_use_review_confirm.py -v`（沿用存量 registry 测试文件名，按现状调整）。

## Phase 4 eligibility 接入矩阵
- [x] 测试：矩阵全分支的 qualification 断言；人工决定优先 + 新相反证据回待审核（TMSF 更新、use_review 更新两个方向）；**无证据等价性**——存量 eligibility 用例全绿不动 + 新增投影对比（同输入旧/新实现结果一致）。
- [x] 修改 `directory_policy.py` 类型门槛段（新 qualification 码 `use_conflict`/`use_uncertain`，incomplete）。
- 验证：`python -m pytest tests/test_directory_flow.py tests/test_directory_policy.py -v`。
- **审查门**：此步合并前人工复核 diff——eligibility 是全站资格单口。

## Phase 5 批量任务 UseReviewJob
- [x] 测试：快照目标含 admitted+excluded、同指纹同版本跳过、预算 256/2s 间隔/取消/中断续跑/取消后不写、按结果计数（updated/conflict/not_found/error/skipped）、空跑无 key 无请求、与单写互斥。
- [x] 实现 job（参照 PositionJob 结构）。
- 验证：`python -m pytest tests/test_directory_use_review.py -v`（job 用例并入）。

## Phase 6 API 与投影
- [x] 测试：`POST /catalog/{cid}/use-review`、`/use-review/confirm`、`GET/POST/DELETE /use-reviews`、`use=` 过滤分页前生效、`use_review` 投影字段与 re_review 标记、422/409/503 矩阵、inactive 409。
- [x] 实现 `directory_workflow_routes.py` + `community_views`/catalog 行投影。
- 验证：`python -m pytest tests/test_directory_flow.py tests/test_directory_workflow_api.py -v`。

## Phase 7 前端（DirectoryFlowWorkspace 及相关）
- [x] 测试（node --test）：排除页复核状态/冲突分组、确认弹窗必填校验与证据列表、待复审提示、任务摘要文案（新格式+旧回退）。
- [x] 实现：目录管理页复核列/过滤、冲突待审核入口、confirm 弹窗、use-reviews 任务卡（对齐 position 任务卡形态）。
- 验证：`npm run lint && npx tsc --noEmit && node --test tests/<新增>.test.cjs && npm run build`（apps/housing-map；注意存量 3 个失败测试属既有问题，不算回归）。

## Phase 8 回归、演练与 spec
- [x] 全量后端：`python -m pytest tests/ -v`（对照 xingfuli 验证记录的基线：258 passed / 1 deselected + 本任务新增；新房 1 失败为并行任务存量）。
- [x] 隔离数据端到端演练（AC6）：构造风雅钱塘型数据（TMSF 商贸 + fake 高德住宅小区）→ 批量复核 → use_conflict → 人工确认含住宅 → admitted → 断言进入租金/法拍目标集合。
- [x] spec 更新（trellis-update-spec）：directory-flow.md 两处契约改写、新增 use-review 契约（或独立 spec 并入 index）、directory-position.md 边界一句。
- [x] `git diff --check`；按 git-commit-push 流程提交（commit 范围严格限本任务文件，与 xingfuli 未提交改动隔离）。

## 回滚点
- 每阶段独立可回退（纯增量）；Phase 4 前无任何行为变化；payload 附加字段回滚后被忽略。
- 生产回滚：停用批量任务即可，无数据迁移需要撤销。

## 验收结果（2026-10-23）

### 与设计的偏差（两处，均已在 spec 中落账）
1. **身份指纹不含实际地址**：`use_identity` 只取 community_id/name/aliases/district。地址在采集后补全或纠正，与用途分类无关；若沿用定位任务含地址的口径，地址一次纠正就会让已确认的分类冲突静默退回透明售房网的原判定。
2. **批量任务多一个 `uncertain` 计数**：设计列的是 updated/conflict/not_found/error/skipped。`state='uncertain'`（高德候选用途不一致、匹配不确定）是独立结论，合并进 not_found 会掩盖「找到了地点但候选自相矛盾」，故单列。

### 验证
- 后端：待提交快照（`git write-tree` 独立 worktree）`pytest tests/` → **711 passed**。真实仓库全量为 730 passed + 5 个 `test_api` 存量失败（已用 stash 在改动前后对比确认为既有问题，与本任务无关）。
- 前端：`tsc --noEmit`、`eslint`、`node --test`（新增 use-review 8 例全绿，目录流与定位既有用例全绿）、`npm run build` 全通过。存量 3 个前端失败（community-management / rental-dashboard / rental-sources）已用 stash 在改动前后对比确认属 xingfuli 任务在途改动。
- 浏览器（一次性数据目录 + 生产构建，Playwright）：390×844 与 1440×900 两档，不收录列表按「分类冲突」筛出风雅钱塘世纪花园 → 行内显示「待审核」徽章 → 详情弹窗含高德用途复核面板、分类冲突结论、高德 POI 证据与人工确认表单 → 缺证据链接时「提交确认」禁用、填入链接后可提交；两档均无横向溢出、无控制台错误。
  - 浏览器检查发现并修掉一处真实缺陷：新增「高德用途复核」列后，不收录表的 `table-layout: fixed` 只定义了 1–4 列与末列宽度，第 5 列被挤成 0 宽竖排。已为不收录表单列宽规则（`.catalog-excluded`），量测列宽 273/273/150/164/314/191。
- 端到端演练（`test_use_review_scenario.py`）：透明售房网标「商贸」→ 批量复核 → `use_conflict` → 人工确认含住宅 → admitted 并进入租金/法拍目标集合；另覆盖「新相反证据回待审核、人工决定不被删除」。

### 未做
- 未触碰生产数据与部署：批量复核需用户在管理页显式发起。
- 任务状态流转与 spec 更新按 Phase 3 收尾。
