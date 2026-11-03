# 房天下退役实施计划

**Goal:** 删除房天下运行能力，保持幸福里流程与历史数据安全。

**Architecture:** 先迁共用类型，再收窄 provider 和刷新链路，最后退役旧来源存储、目录证据和前端操作。CommunityRegistry 是唯一当前关联存储；历史文件与人工决定不迁移、不重写。

**Tech Stack:** Python/FastAPI/SQLite/pytest，Next.js/React/TypeScript/node:test。

执行方式：在当前项目依 Trellis Phase 2 顺序实施，每步完成有意义的回归；本轮只有规划。实施前读取 trellis-before-dev、相关 spec 和本任务 design.md。用户要求开始实施后再 task.py start；不要自行新建工作树、启动子代理、提交、推送或部署。

## 0. 基线与文件边界

- [ ] 在仓库根运行 `git status --short`，记录并保留无关改动，尤其 `.trellis/spec/backend/housing-map/backend/directory-flow.md` 的现有编辑。
- [ ] 阅读 research/inventory.md 的生产、脚本、测试引用；重新运行同一清单命令以覆盖规划后新增调用方。
- [ ] 后端目录执行 `.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-fang-retirement-baseline`，记录通过数与既有失败，不能沿用旧任务测试数冒充本次验证。
- [ ] 检查 `src/main.py` 可导入、当前所有 retained tests 能收集，再开始删除。

## 1. 迁出共用类型（R2 / AC2）

Files：新增 `src/services/rental_reference/crawl_types.py`；修改 `fang_rentals.py`（暂改为导入）、`xingfuli_rentals.py`、`xingfuli_transport.py`、`rental_reference/{refresh,probe,association,discovery_checkpoint}.py` 及相关测试。以上路径相对 backend/housing-map。

- [ ] 原样迁移 SeedRunResult、RentalCrawlCancelled、CrawlProgress，补迁 datetime/dataclass 等实际需要的标准库 import，公共模块不反向引用 provider。
- [ ] 给现有取消/恢复测试更新 import，增加真实异常传递检查：

```python
from src.services.rental_reference.crawl_types import SeedRunResult, RentalCrawlCancelled

def test_cancel_carries_results():
    done = SeedRunResult(seed='done')
    partial = SeedRunResult(seed='partial')
    exc = RentalCrawlCancelled([done], partial)
    assert exc.completed == [done]
    assert exc.partial is partial
```

- [ ] 执行 `pytest -q tests/test_xingfuli_rentals.py tests/test_rental_probe.py tests/test_rental_search_pagination.py --basetemp=.pytest-tmp-fang-retirement-types`（使用本项目 venv python -m pytest）。期望通过，取消后不发布和断点复用仍成立。

## 2. 唯一 provider、快照与刷新（R1、R2、R4 / AC1、AC2、AC4）

Files：`src/services/rental_reference/{providers,refresh,storage}.py`、`src/api/rental_routes.py`、`src/services/directory_coverage.py`；tests/test_rental_{providers,refresh,storage,api,continue,split}.py。

- [ ] 先补 provider 隔离行为回归，再修改实现。最小用例：

```python
from src.services.rental_reference.providers import same_source

def test_historical_fang_is_never_current():
    assert not same_source({'source': 'fang', 'source_community_id': '7'}, 'xingfuli', '7')
    assert not same_source({'source_community_id': '7'}, 'xingfuli', '7')
    assert same_source({'source': 'xingfuli', 'source_community_id': '7'}, 'xingfuli', '7')
```

- [ ] 在现有 registry fixture 加入 matched Fang 与 Xingfuli 同 sid，验证 active_sources 只返回幸福里；解除幸福里后结果为空，旧 JSON 存在也不回退。
- [ ] provider 统一只选幸福里；删除 xingfuli_only 开关、Fang 默认工厂和所有调用参数；refresh 只运行幸福里，不再触发 prepare_sources。
- [ ] 删除 load_legacy_mappings/load_verified_mappings 的 Fang fallback 及调用方；无 registry 时产生空采集计划。保留 mapping 错误类仅当当前调用方仍需要，不能留循环依赖。
- [ ] API summary/detail 和 coverage 统一显式 provider+sid；删除 Fang 样本合成路径，保留同幸福里来源旧内部 cid 复用。
- [ ] preserved_sources 改为显式二元身份；新增旧字符串身份拒绝、current 指针字节不变测试。旧历史快照可 load_current，不可作当前统计。
- [ ] 更新以 Fang 为默认 fixture 的“公共行为”测试为幸福里 fixture，保留锁冲突、缓存、不完整批次、失败保留、取消原子性断言；不要整批删掉这些测试。
- [ ] 运行本步骤列出的测试，期望全部通过；用 fake transport 记录请求，仅能出现允许的幸福里请求。

## 3. 来源存储与 API 收尾（R3、R4 / AC3、AC4）

Files：`src/services/rental_reference/sources.py`、`src/api/rental_source_routes.py`、`src/services/rental_reference/association.py`；tests/test_rental_sources.py、test_rental_association_flow.py、test_rental_probe.py。

- [ ] 根据 design.md 接口表写退役入口回归：POST search、PUT confirm 和 DELETE candidates 合法旧参数返回 410，旧库/权威 registry 文件无修改，无 HTTP 调用。原 search/confirm 输入非法仍 422。
- [ ] 精简 SourceStore 为 registry 适配层；GET mapping 仅幸福里、candidates 不暴露 Fang；DELETE 解除幸福里并遵守 change_sources 互斥。无 registry 管理端 503，禁止创建 rental_sources.sqlite3。
- [ ] 清理旧数据库连接/种子导入/发现函数，更新 rental_routes 中的 import；GET 对未知社区 404、权威库损坏 503 的错误语义保留。
- [ ] 保留 association 的 eligibility、review prefix/read 及 skip/reopen；按引用删除 Fang 搜索/候选池/prepare_sources，匹配/探查不得失去 metadata 和人工保护。
- [ ] 用完整 FastAPI fixture 测试 GET→探查选择→GET→解除→GET；同时覆盖更新中解除返回 409、人工 skip/reopen 不丢失。执行本步骤相关测试。

## 4. 目录、初始化和用途证据（R1、R4 / AC1、AC4）

Files：`src/services/{directory_collection,community_directory,residential_classifier,community_auto_review,community_admission,community_registry}.py`、`scripts/filter_residential_communities.py`；现有 directory/admission/auto-review/classifier 相关测试。

- [ ] 使用隔离 registry 对比已保存人工 admission/rejected/ignored/review payload；退役前后原记录相同，Fang-only 新记录不能自动准入或关联。
- [ ] 删除 fang_names 和适配器注册；目录初始化取消旧 Fang 映射/候选导入，保留其他来源和原备份。用旧 JSON、旧 SQLite、损坏旧文件、空目录四种输入验证无重新导入/复活。
- [ ] classifier 不再读取 Fang 样本；旧 CLI --fang-samples 及脚本调用一起删除。TMSF 明确住宅保持住宅，明确非住宅保持非住宅，无 TMSF 证据保持待核对，历史 Fang 冲突不再改变新结论。
- [ ] auto_review 移除 Fang 用途/唯一性分支，确保历史 Fang 不被自动 merge/admit；community_admission 只清理失效假设，不自动重审已有人工决定。
- [ ] registry 通用关联/创建路径阻止 Fang 新写入，保留历史读取和显式解绑；merge 只按当前幸福里检查租金冲突。测试通过通用目录 API 绕过的请求返回 409 且库不变。
- [ ] 历史迁移报告可保留身份及计数，记录为历史项；无需改 migration marker、激活流程或运行迁移脚本。
- [ ] 运行 `pytest -q tests/test_directory_collection.py tests/test_directory_integration.py tests/test_directory_api.py tests/test_directory_flow.py tests/test_residential_classifier.py tests/test_filter_residential_communities.py tests/test_community_admission.py tests/test_community_auto_review.py tests/test_community_auto_review_integration.py --basetemp=.pytest-tmp-fang-retirement-directory`。

## 5. 前端清理（R3 / AC3）

Files：apps/housing-map 下 `src/lib/{rental-sources,rental-types}.ts`、`src/components/rental/RentalSourceManager.tsx`、`src/components/community/{DirectoryCards,UseReviewPanel}.tsx`；tests/rental-sources.test.cjs、rental-xingfuli.test.cjs、rental-probe.test.cjs、directory-flow.test.cjs。

- [ ] safeSourceLink 加入断言：两种旧 Fang 主机均返回 undefined；原合法幸福里路径通过，userinfo/异常端口/非 HTTPS 拒绝。
- [ ] 删除未使用 SourceCandidate 和来源 PUT 确认逻辑；confirming 仅保留解除状态，mapping 文案固定幸福里，事件与刷新保持。
- [ ] 旧目录/人工用途证据只显示“房天下（历史）”，不再有 Fang 操作；保留其他来源标签和筛选，不把历史身份误改为幸福里。
- [ ] 跑前端既有测试；390px/1440px 用隔离服务或拦截 fixture 检查未关联/已关联/解除/失败/维护列表，确认无横向溢出，记录到 verification.md。

## 6. 物理删除、容器与规范（R1、R5 / AC1、AC5）

- [ ] 删除 design.md 指定 5 个专属源码/脚本/说明文件；删除 tests/test_fang_rentals.py、test_fang_rentals_run.py、test_fang_resilience.py，先把取消、共享锁、快照保护等仍有意义的断言移入幸福里/公共测试。
- [ ] Dockerfile 删除 rental_community_mappings seed COPY，其余 COPY/CMD 保持；数据文件留存，不在启动中解析旧 Fang 映射。
- [ ] 更新 design.md 列出的当前 specs，旧 Fang guide 保留简短退役事实并从 backend 必读列表移除；脚本 XINGFULI_RENTALS.md 去除当前 Fang 回退指引。
- [ ] 用 `rg -n 'fang_rentals|fang_request_policy|fang_detail_cache|fetch_fang_rentals' backend/housing-map/src backend/housing-map/scripts apps/housing-map/src` 检查，期望无运行 import/命令。历史说明可有引用，但须在 verification.md 中解释。
- [ ] 逐项复查 research/inventory.md 的历史身份、数据隔离、410、历史报表保留项，不以字符串零命中代替行为验证。

## 7. 最终验证与收尾（全部 AC）

在 backend/housing-map：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-fang-retirement-final
.\.venv\Scripts\python.exe -c "from src.main import app; print(app.title)"
```

在 apps/housing-map，串行执行：

```powershell
npm run lint
npx tsc --noEmit
node --test tests/*.test.cjs
npm run build
```

在仓库根：

```powershell
git diff --check
python .trellis/scripts/task.py validate 11-03-housing-fang-retirement
```

- [ ] 全部命令成功；如真实 symlink 用例受限，按 Windows 测试规范记录 skip/WSL 结果，不能伪造通过。无需修改其他包或重复无关测试。
- [ ] 记录真实通过数、浏览器证据、残留引用用途和任何未完成项到 verification.md；AC 仅在证据通过后勾选。
- [ ] 如具备本地 Docker 执行能力，验证 backend Dockerfile build，禁止发布镜像；无法执行则明确记录容器构建未实测，不声称已部署。
- [ ] 运行 trellis-check 做规范与跨层自检；本任务原 PRD 不包含生产部署或全量公网采集，不因这些不在范围的动作阻塞代码退役验收。
- [ ] 提交/推送/部署仅在用户要求后执行。产品代码完成后再按 trellis-finish-work 归档，当前规划阶段不提前标 completed。

## 回滚点

每步骤均应保持可导入与相应测试通过；第 1 步共用类型迁移可独立保留，第 2–6 步必须完整验证后再交付。无 DB schema 迁移，不需要整库覆盖回滚，不删除历史数据。若 provider 过滤引起当前幸福里覆盖回归，先修复 fixture/ID 匹配或恢复代码，不启用 Fang 回退掩盖问题。
