# 房天下退役：实施验证记录

任务：`.trellis/tasks/11-03-housing-fang-retirement`（prd.md / design.md / implement.md）

## 0. 基线

- `git status --short`：改动前仓库有 13 处未提交路径，均与本任务无关（`.trellis/tasks/10-29-*` 归档、
  `.trellis/spec/.../directory-flow.md` 的其它工作、journal），全部保留未动。
- 后端基线（`backend/housing-map`）：
  `./.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-tmp-fang-retirement-baseline`
  → **1359 passed, 3 warnings in 285.92s**（既有警告为 starlette/httpx 弃用与一条 GBK 解码线程告警）。
- `from src.main import app` 在改动后可导入。

## 1. 共用类型迁移（R2 / AC2）

- 新增 `src/services/rental_reference/crawl_types.py`，迁入 `SeedRunResult` / `RentalCrawlCancelled` /
  `CrawlProgress`（字段、默认值、`snapshot()`、取消异常的 `completed`/`partial` 语义原样保留）。
- 调用方改用公共模块：`xingfuli_rentals.py`、`xingfuli_transport.py`、`rental_reference/probe.py`、
  `discovery_checkpoint.py`、`association.py`、`refresh.py`；测试侧 `test_rental_continue.py`、
  `test_rental_providers.py`、`test_rental_split.py`、`test_matching_speed.py`、
  `test_rental_association_flow.py`。
- 新增 `tests/test_crawl_types.py`：取消异常携带 completed/partial、默认字段、progress 不是百分比。
- 验证：`pytest -q tests/test_crawl_types.py tests/test_xingfuli_rentals.py tests/test_rental_probe.py
  tests/test_rental_search_pagination.py --basetemp=.pytest-tmp-fang-retirement-types`
  → **120 passed in 42.88s**。

## 2. 唯一 provider、快照与刷新（R1 / R2 / R4）

- `providers.py`：`CURRENT_RENTAL_PROVIDER='xingfuli'`；`active_sources(registry)` 只选幸福里
  （matched + 社区有效），移除 `xingfuli_only` 开关；`same_source()` 要求显式 provider，
  缺 provider 的旧快照不补为幸福里；`source_url()` 只生成幸福里链接，其它 provider 抛 ValueError。
- `refresh.py`：只跑幸福里采集；`load_verified_mappings()` 只认社区台账（无台账 → 空采集计划），
  删除旧映射文件/旧映射库回退与 `prepare_sources` 自动发现；删除 Fang 默认客户端、请求策略与详情缓存接线；
  `xingfuli_only` 参数删除。
- `storage.py`：`publish_run(preserved_sources=...)` 只接受显式 `(xingfuli, sid)`，旧字符串身份抛
  ValueError（在替换 current 指针之前）。
- `rental_routes.py`：来源链接白名单收窄到 `m.xflapp.com`（`_safe_source_url` 拒绝房天下主机）；
  `_verified_source_ids()` 改为基于台账（台账损坏 → 503）；`_mapped_entry()` 删除房天下区域样本合成分支，
  只复用显式幸福里 provider+sid；`_source_links()` 不再构造任何已退役来源 URL。
- `directory_coverage.py`：覆盖统计只索引显式 provider 为幸福里的快照。
- `matching.py` / `probe.py` / `xingfuli_sources.py`：`xingfuli_only` 参数全部移除。
- 行为回归（新增/改写）：
  - `test_rental_providers.py::test_historical_fang_is_never_current`
  - `::test_only_xingfuli_is_an_active_source_and_unlink_does_not_fall_back`
  - `::test_legacy_fang_mapping_file_is_not_imported`
  - `test_rental_refresh.py::test_legacy_fang_mapping_file_is_not_a_crawl_source`
  - `::test_unlinked_community_is_not_crawled`
  - `test_rental_storage.py`：旧字符串 preserved_sources 拒绝、current 指针不变。
- 验证：`pytest -q tests/test_rental_providers.py tests/test_rental_refresh.py tests/test_rental_storage.py
  tests/test_rental_api.py tests/test_rental_sources.py tests/test_rental_association_flow.py
  tests/test_rental_split.py tests/test_rental_continue.py tests/test_rental_probe.py
  tests/test_rental_xingfuli_sources.py tests/test_rental_statistics.py tests/test_xingfuli_rentals.py
  tests/test_xingfuli_pilots.py tests/test_crawl_types.py --basetemp=.pytest-tmp-fang-p3` → 全部通过。

## 3. 来源存储与 API 收尾（R3 / R4）

- `sources.py` 精简为社区台账适配层（`get`/`all_mappings`/`pending_counts`/`remove`）：
  删除旧 SQLite 映射库、种子导入、候选 confirm/reject 与房天下发现实现；
  无台账抛 `SourceRegistryUnavailable` → API 返回 503「小区目录尚未准备好，租金来源暂不可用」，
  不再创建第二份映射库。
- `association.py` 只保留 `eligible_communities` / `PREFIX` / `read_review` / `save_review` /
  `fingerprint` / `decide`（skip/reopen）；删除房天下候选池、`candidates_for`、`reviews`、`prepare_sources`。
- `rental_source_routes.py`：`POST .../rental-source/search`、`PUT .../rental-source`、
  `DELETE .../rental-source/candidates/{id}` 全部 410 且无副作用（不建库、不发请求）；
  `DELETE .../rental-source` 只解除当前幸福里关联，绝不回退房天下。
- 验证：`pytest -q tests/test_rental_providers.py tests/test_rental_sources.py
  tests/test_rental_association_flow.py --basetemp=.pytest-tmp-fang-p3` → **25 passed**；
  `tests/test_rental_api.py` → **49 passed**。

## 5. 前端清理（R3 / AC3）

由子代理执行，产出：

- `src/lib/rental-sources.ts`：`RentalSource.source` 收窄为 `'xingfuli'`；`safeSourceLink` 删除
  `zu.fang.com` / `hz.zu.fang.com`，只保留 `m.xflapp.com` 的 HTTPS/路径/端口/凭据约束；
  新增 `RENTAL_SOURCE_LABEL`。
- `src/lib/rental-types.ts`：删除房天下专属 `regional_sample` 字段。
- `src/components/rental/RentalSourceManager.tsx`：删除 `SourceCandidate`、PUT 确认分支与 search notice
  分支；`confirming` 改为只表达解除态的 `removing`；保留幸福里 mapping 展示、解除与 XingfuliProbe。
- `src/components/community/DirectoryCards.tsx`、`UseReviewPanel.tsx`：历史标签显示「房天下（历史）」，
  不提供启用/确认/采集动作。
- `src/components/community/CommunityRentalReference.tsx`：删除房天下区域样本提示（超出初始文件清单，
  因它是 `safeSourceLink` 的唯一消费方）。
- 测试：`rental-sources.test.cjs`、`rental-xingfuli.test.cjs`、`rental-reference.test.cjs`、
  `community-management.test.cjs`。
- 验证（`apps/housing-map`）：`npm run lint` 通过；`npx tsc --noEmit` 通过；
  `node --test tests/*.test.cjs` → **202 tests, 202 pass, 0 fail**；
  `npm run build` → `Compiled successfully`。
- 浏览器走查：见步骤 7「浏览器走查」小节（1440px 与窄屏均已实测，无横向溢出、无房天下文案；
  带一次性来源数据的来源弹窗三态未实测，原因见步骤 7「未实测项」）。

## 4. 目录、初始化与用途证据（R1 / R4）

由子代理执行，产出：

- `directory_collection.py`：删除 `fang_names()` 适配器与 `ADAPTERS['fang']`；显式请求房天下来源时
  抛 `ValueError('房天下采集已停止…')`（与既有高德守卫同形）。
- `community_directory.py`：`prepare_directory` 不再导入旧房天下映射/候选，删除 `_import_fang()`；
  旧文件仍按原流程复制进 `directory-backup`，但不读取为当前来源；旧 SQLite 损坏时退回原始字节
  备份，不再阻断启动。
- `residential_classifier.py`：Fang 样本退出 `classify` / `classify_sources` / `classify_directory`；
  移除 `fang_samples` / `fang_samples_by_community` 参数与 CLI `--fang-samples`；
  TMSF 分类、共用常量与「普通住宅」归一化语义保留。
- `community_registry.py`：新增 `RETIRED_RENTAL_SOURCES`；`associate()` / `create_from_source()` 拒绝
  `source='fang'`（ValueError → 既有 API 层 409）；`_associate()` 允许同小区已有房天下行保持原状
  （历史不改写），但禁止新建或迁移；租金来源唯一性与合并唯一性只检查当前幸福里；
  `unlink` / `ignore_source` / `restore_source` 与读取路径不变。
- `community_auto_review.py`：房天下不再是新增用途证据；历史房天下成员若需要新建关联则自动结论为
  `pending`（不自动合并/准入），已匹配的同小区历史成员不阻塞。
- `community_admission.py`：仅清理失效表述，不自动重审任何人工决定。
- `scripts/filter_residential_communities.py`：删除 `--fang-samples`。
- 新增 `tests/test_fang_retirement_directory.py`（11 项）：目录初始化不导入旧 Fang 映射/旧 SQLite/
  损坏文件/空目录；registry 拒绝新 Fang 关联与新建 Fang 小区但历史可读可解绑可忽略；
  合并唯一性忽略历史 Fang、仍拦两个当前幸福里来源；Fang 样本不构成住宅证据；人工准入与拒绝记录
  在退役前后不变。
- 改写：`test_residential_classifier.py`、`test_filter_residential_communities.py`、
  `test_directory_collection.py`、`test_directory_api.py`、`test_directory_flow.py`、
  `test_directory_integration.py`。
- 验证：子代理负责的 9 个测试文件 + 新文件 → **120 passed**。

### 步骤 4 引起的主会话连锁修正

registry 拒绝新建房天下关联后，既有测试里用 `associate()` 建立房天下关联的 fixture 全部失效，
按新契约改成「历史台账行」构造（直接写 `sources` 行）或改用未退役来源：

- `tests/test_rental_providers.py`、`test_rental_sources.py`、`test_rental_refresh.py`、
  `test_rental_probe.py`、`test_community_missing_address.py`、`test_matching_speed.py`：
  房天下关联改为历史数据直写（`UPDATE sources SET cid=?,status='matched'`）。
- `tests/test_community_registry.py`：通用 ingest/自动关联/删除/合并用例改用未退役的 `laipai`
  来源（这些用例测的是通用行为，不是房天下行为），另加
  `test_retired_fang_source_cannot_be_associated_anymore`。
- `tests/test_community_enrichment.py`：房天下冲突样本不再把结论拉回 `pending`，改为
  「TMSF 明确住宅 → residential」。
- `tests/test_rental_xingfuli_sources.py`：自动发现只被**当前**来源挡住，样例改为幸福里来源。

## 6. 物理删除、容器与规范（R1 / R5）

- 删除：`src/services/fang_rentals.py`、`src/services/fang_detail_cache.py`、
  `src/services/fang_request_policy.py`、`scripts/fetch_fang_rentals.py`、`scripts/FANG_RENTALS.md`、
  `tests/test_fang_rentals.py`、`tests/test_fang_rentals_run.py`、`tests/test_fang_resilience.py`。
  取消、共享锁、快照保护等仍有意义的断言已迁入幸福里/公共测试
  （`test_crawl_types.py`、`test_rental_refresh.py`、`test_rental_storage.py`、
  `test_rental_sources.py`）。
- `Dockerfile`：删除 `COPY data/rental_community_mappings.json ./seed-data/...`；其余 COPY/CMD 不变。
  仓库里的旧映射数据文件保留，不再作为种子分发。
- `scripts/XINGFULI_RENTALS.md`：删除当前房天下回退指引（改为「采集只认幸福里，缺来源走匹配流程」）。
- 规范更新（子代理执行）：
  - `backend/housing-map/backend/index.md`：移除房天下采集指南的必读条目（主会话）。
  - `guides/housing-map-fang-rentals.md`：整篇改为退役事实说明（主会话）。
  - `rental-sources.md`、`xingfuli-rentals.md`、`xingfuli-discovery.md`、`community-directory.md`、
    `community-auto-review.md`、`directory-flow.md`、`guides/housing-map-rental-reference.md`：
    逐段改写为幸福里唯一来源，`directory-flow.md` 只合并与退役冲突的两段，保留其既有未提交改动。

### 残留 Fang 标识及用途（均为退役守卫或历史只读，非运行逻辑）

| 位置 | 用途 |
|---|---|
| `api/directory_routes.py` 的 `source` 过滤枚举 | 目录来源筛选仍可按历史房天下过滤（只读展示） |
| `api/rental_source_routes.py` 三处 410 文案 | 退役端点的 410 说明文字 |
| `services/community_registry.py` `RETIRED_RENTAL_SOURCES` | 拒绝新建房天下关联的守卫 |
| `services/directory_collection.py` `_check_sources` | 拒绝房天下采集的守卫 |
| `services/community_auto_review.py` | 历史房天下成员不自动合并/准入的守卫 |
| `services/rental_reference/providers.py` `RENTAL_PROVIDERS` / `rejected_rental_communities` | 历史人工拒绝记录仍然生效（只读审计） |
| `services/rental_reference/xingfuli_sources.py` `protected` | 同上，人工解绑/拒绝继续保护小区 |
| `services/collection_pipeline_migration.py`、`directory_migration.py` | 历史迁移报告里的来源计数（历史项） |
| `services/rental_routes.py`、`directory_coverage.py` 注释 | 说明历史快照不参与当前统计 |
| 前端 `DirectoryCards.tsx`、`UseReviewPanel.tsx` | 历史只读标签「房天下（历史）」 |

`grep -rn "fang_rentals|fang_request_policy|fang_detail_cache|fetch_fang_rentals" backend/housing-map/src
backend/housing-map/scripts apps/housing-map/src` → 仅命中 `__pycache__` 编译产物，无运行 import/命令。

## 7. 最终验证

### 后端（`backend/housing-map`）

```
./.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-tmp-fang-retirement-final
```
→ **1304 passed, 3 warnings in 241.12s**（3 个 warning 是既有的 starlette/httpx 弃用与一条 GBK
解码线程告警，与基线一致）。基线为 1359 passed，差值 55 来自删除的三个房天下专属测试文件。

```
./.venv/Scripts/python.exe -c "from src.main import app; print(app.title)"
```
→ `Housing Map API`，导入正常。

### 前端（`apps/housing-map`）

| 命令 | 结果 |
|---|---|
| `npm run lint` | 通过（无输出） |
| `npx tsc --noEmit` | 通过（exit 0） |
| `node --test tests/*.test.cjs` | **202 tests, 202 pass, 0 fail**（与改动前基线同为 202，未减少覆盖） |
| `npm run build` | `✓ Compiled successfully in 4.7s`，静态页生成成功 |

`next build` 会改写受版本控制的 `apps/housing-map/next-env.d.ts`（Next 生成的产物，
`.next/dev/types` → `.next/types`），已 `git checkout` 还原并复验 `tsc --noEmit` 仍通过。

### 浏览器走查（生产构建 + 重启后的后端）

- 后端重启加载新代码（8096），前端用生产构建起在 3007（dev server 与 `next start` 共享 `.next`
  会导致 chunk 500，故改用生产构建，与项目既有 QA 方式一致）。
- 1440×900：`/map` 地图页正常渲染（地图、图层、筛选、价格图例齐全）；
  「小区数据维护 → 租金来源」面板正常渲染，仅有筛选标签与「刷新清单」，无任何房天下来源操作入口。
- 窄屏（视口 502px）：`scrollWidth == clientWidth`，**无横向溢出**；页面正文不含「房天下」字样。
- 控制台：无 error；仅一条既有 Canvas `willReadFrequently` 性能警告。
- 退役端点实测（重启后的后端）：
  | 请求 | 结果 |
  |---|---|
  | `POST /api/communities/{id}/rental-source/search` | **410**「房天下租金来源查找已停用，请使用“匹配租金来源”查找幸福里」 |
  | `PUT /api/communities/{id}/rental-source` | **410**「房天下租金来源确认已停用，请使用幸福里主页选择」 |
  | `DELETE /api/communities/{id}/rental-source/candidates/{source_id}` | **410**「房天下候选来源已停用…」 |
  | `GET /api/communities/{unknown}/rental-source` | **404**「小区不存在」 |
  | `GET /api/rentals/sources` | **200**，响应形状不变 |

### 未实测项（如实记录）

- **带一次性来源数据的来源弹窗走查未做**：本机生产数据目录为空（地图显示「收录 0」、价格数据为
  「—」），无法在真实页面上打开某个小区的「关联租金来源」弹窗去核对「已关联 / 未关联 / 解除」
  三态与「房天下（历史）」标签的视觉呈现。相关行为已由后端 API 契约测试
  （`tests/test_rental_sources.py`、`tests/test_rental_api.py`）与前端组件测试
  （`rental-sources.test.cjs`、`community-management.test.cjs`，均断言历史标签与无来源操作）
  覆盖，但**没有**真实浏览器像素级证据。
- **容器构建未实测**：本机未执行 `docker build`，Dockerfile 的 seed 删除只做了代码层核对。
- 未做生产部署、未运行生产采集、未迁移生产数据（均不在本任务范围）。

## 8. 质量自检（主会话抽查，替代中断的 trellis-check 子代理）

trellis-check 子代理因 API 用量上限（429）中断，以下为主会话按同一清单完成的抽查：

| 检查项 | 结果 |
|---|---|
| spec 提到的符号在代码中存在 | `SourceRegistryUnavailable` / `CURRENT_RENTAL_PROVIDER` / `crawl_types` / `RETIRED_RENTAL_SOURCES` 全部存在且被 spec 引用 |
| `index.md` 必读条目指向的文件 | 16 条全部存在，无指向已删除文件（房天下采集指南条目已移除） |
| 悬空引用 | `load_legacy_mappings` / `MappingFileError` / `confirmed_pairs` / `database_path` / `save_candidates` / `prepare_sources` / `candidates_for` / `xingfuli_only` 在运行代码中已全部消失 |
| 房天下运行逻辑残留 | 无（只剩退役守卫与历史只读路径，见步骤 6 残留表） |
| 前端类型收窄 | `RentalSource.source` 收窄为 `'xingfuli'`，与后端 `_rental()` 返回一致 |

**已知 LOW 项（有意保留，不改）**：`api/rental_routes.py` 的详情响应仍带 `regional_sample` 键（房天下区域样本
标记）。该标记路径已删除，运行时恒为 `false`；保留它是为了遵守 design「公共 API 响应形状不变」，
前端已不再声明该字段，也不依赖它。
