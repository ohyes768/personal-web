# Journal - jackson.tang (Part 1)

> AI development session journal
> Started: 2026-08-27

---



## Session 1: 宏观定时任务与独立管理页面

**Date**: 2026-08-27
**Task**: 宏观定时任务与独立管理页面
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

宏观后端移植 dividend scheduler 架构:新增 src/scheduler 包(run_group 组执行器,顺序 self-call 16 个 update 端点,单源失败不中断,聚合 success/partial/failed/skipped,历史含数据源级 items 明细),scheduler.json 预设 A 股组(工作日16:10+交易日校验)与全球组(工作日07:30),4 个管理 API,25 个单测;前端新增 /macro/scheduler 独立管理页(启停/立即执行/双层历史明细)+ 主页齿轮悬浮入口;浏览器端到端点验通过(真实触发 36s partial 5/6 成功,fund-flow 外部源断连属数据源问题);契约沉淀至 spec/backend/global-macro-fin/backend/scheduler.md

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `20a6b2e` | (see git log) |
| `fc94345` | (see git log) |
| `b245872` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 宏观页数据 Tab 写入 UX 统一

**Date**: 2026-08-29
**Task**: 宏观页数据 Tab 写入 UX 统一
**Package**: backend/global-macro-fin
**Branch**: `master`

### Summary

六个数据 Tab 统一初始化/更新/置灰；成交额历史改到 /fetch/volume-turnover/history；市场情绪三个增量串行，避开全局更新锁。信号首页与对比保持只读。

### Main Changes

- 六个数据 Tab（中美利差/汇率、流动性/风险、利率利差、商品、股指、市场情绪）统一 InitButton + RefreshButton：文案「初始化历史数据」/「更新数据」，成功后 onSuccess 刷图，各用独立 storageKey。
- 信号首页与对比保持只读，不加写数按钮。
- 成交额+换手率历史规范为 POST /api/fetch/volume-turnover/history；删除旧 /update/volume-turnover/history，不留别名。
- 市场情绪更新串行打 volume → turnover → margin，避开 routes.py 全局 _is_updating 锁；不抄流动性 Tab 的 Promise.all。
- 融资余额 history 与流动性并发锁修复不在本任务范围。


### Git Commits

| Hash | Message |
|------|---------|
| `26538b4` | (see git log) |
| `c394523` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 融资余额历史回补接口

**Date**: 2026-08-29
**Task**: 融资余额历史回补接口
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

新增 POST /fetch/margin/history，akshare 沪深全表按日期 outer join 回补 margin.csv；市场情绪初始化串行 volume-turnover → margin → fund-flow history。pytest tests/test_margin.py 12 passed。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ce6c8cc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: QDII/互认基金跳过业绩基准合成

**Date**: 2026-09-03
**Task**: QDII/互认基金跳过业绩基准合成
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

股票宇宙刷新时 QDII/互认基金不再合成业绩基准 TRI（公式多无免费源，fallback 中证800口径失真），直接写 tri=NULL/source=skipped:qdii，界面 IR/α/γ/α-IR/超额3y 显示 -，夏普与净值业绩不受影响；判定口径同 exclude_qdii；funds_stock.yaml 移除 968157；新增 5 用例。遗留：sh000922/000908 停更换源（中证红利→中证800 fallback 精度问题）待另立任务。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a22fd17` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## 2026-09-04 | 09-04-stock-fund-sharpe-filter

### Summary

股票 tab 筛选接入已有夏普指标（fund_risk_metrics.sharpe，近 3 年）：/stock/screen 新增 min_sharpe，NULL 指标一并排除；前端股票 tab 侧栏加夏普输入项默认 0.8（FilterPanel 改 dimensions prop 可配置，债基保持四维隔离）。实测完整默认组合 6 只、单夏普条件 53 只、移除 chip 恢复 22 只。

### Main Changes

- backend: filter_service._screen 尾参 min_sharpe + where；routes.stock_screen 加 Query(ge=-10, le=10)
- frontend: types/useFilters/api/hooks 贯通 min_sharpe；FilterSidebar 导出 STOCK_DIMENSIONS；FilterSheet 透传
- tests: 新增 min_sharpe 筛选/NULL 不受影响 2 用例（TDD，先 RED 后 GREEN）
- spec: contracts.md 关键语义区补 min_sharpe 契约

### Git Commits

| Hash | Message |
|------|---------|
| `877d18b` | feat(fund-select): 股票 tab 筛选接入夏普指标（默认 ≥0.8） |

### Testing

- 后端 pytest 全量 162 passed；ruff 通过
- 前端 tsc --noEmit 通过；build 编译成功（standalone symlink EPERM 为既有 Windows 环境问题，stash 验证无改动同样报错）
- Playwright 实测：侧栏夏普输入 0.8 / chip「夏普 ≥ 0.8」/ 共 6 只；移除 chip → 22 只；债基 tab 4 项无夏普、18 只正常

### Status

[OK] **Completed**

### Next Steps

- 未 push（等用户确认）；pnpm lint 未跑通系该 app 未初始化 ESLint 配置（既有）


## Session 5: Fund-select 4 tab 列表分页（server page/limit）

**Date**: 2026-09-09
**Task**: Fund-select 4 tab 列表分页（server page/limit）
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

市场 tab 单 tab 经常 2000+ 只基金，前端渲染慢。给 4 个 screen 端点（bond/stock/discovery-bond/discovery-stock）统一接入服务端 page/limit 经典分页：后端 FilterService._screen 排序后切片（total 仍是筛后总数），4 个 routes 加 page/limit Query；前端 FundFilters 加 page/limit 字段，4 个 useFundList* 触发串同步，新增 Pagination 组件挂在 4 个 page。Sort 在 slice 前保证多页无重叠/无遗漏；ach_map 仍按全量 codes 查，rank 字段不丢。28 个新 pytest case 全 PASS，pnpm build 编译/lint/types/8 静态页全通过。同步更新 contracts.md 分页契约段。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `25e6141` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Pre-existing pytest 修复：peer_rank 契约补 rank 键 + cbond 源迁移

**Date**: 2026-09-09
**Task**: Pre-existing pytest 修复：peer_rank 契约补 rank 键 + cbond 源迁移
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

修复 6 个 pre-existing pytest 失败（与分页任务无关）。5 个 peer_rank：d82928e 给 _parse_peer_rank 返回 dict 加 rank 键（旧 2 键 → 新 3 键 pct/total/rank），测试断言跟上；生产实现未改。1 个 cbond 源：akshare 1.18.39 移除 ak.bond_index_general_cbond API（生产代码也用了，refresh 命中会 AttributeError），迁到 ak.bond_new_composite_index_cbond()；实证新源无 B1 错位 bug（6174 行 / Sun=11 / Sat=9 调休 / Mon-Fri=144-149），无需参数。同步更新 yaml config（中债综合财富 source 字段）、benchmark_fetcher.py 注释、contracts.md B1 段落（B1.2 迁移注记）。pytest tests/ → 263 passed, 0 failed（之前 6 failed）。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `cb349d9` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: 债基·市场 tab 类型筛选修正：删 REITs 死选项 + chip 文案对齐

**Date**: 2026-09-11
**Task**: 债基·市场 tab 类型筛选修正：删 REITs 死选项 + chip 文案对齐
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

债基·市场 tab 类型筛选修正：删 REITs 死选项，chip 文案与筛选器 label 对齐；收尾同步 universe 子类数为 11。

### Main Changes

- 删 BOND_MARKET_TYPE_OPTIONS / COARSE_TO_SUBTYPES_BOND 的 REITs 死选项，避免空展开静默退回全量债基
- resolveCoarseLabel 加 kind，chip 从 OPTIONS label derive（混合型-偏债 → 混合债基）
- discovery-bond/stock 分别传 marketKind；老 /bond /stock 不传
- DISCOVERY_BOND_DEFAULT_FILTERS 同步去掉 REITs，避免 FilterChipBar 死 chip
- spec §8a 沉淀死选项三处清理 + chip 文案唯一真相源
- routes docstring / spec gotcha 子类数 10 → 11


### Git Commits

| Hash | Message |
|------|---------|
| `c26cf3f` | (see git log) |
| `dd08321` | (see git log) |
| `c7e3728` | (see git log) |
| `36ac681` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: 债基全量刷新默认 10% 收尾

**Date**: 2026-09-11
**Task**: 债基全量刷新默认 10% 收尾
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

债基全量刷新 min_ret_3y 默认改为 10%（股基保持 20%），拆分 BOND/STOCK 独立常量；4 个脏任务已归档；spec 沉淀预筛默认拆分契约后归档本任务。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `c26cf3f` | (see git log) |
| `260f8f0` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: 债基·市场 tab 详情页自给自足：新套补写 FundFees + FundHoldingsBond

**Date**: 2026-09-13
**Task**: 债基·市场 tab 详情页自给自足：新套补写 FundFees + FundHoldingsBond
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

债基·市场 tab 详情页原本依赖老 v1 yaml 写的 FundFees / FundHoldingsBond。本任务给 market_full_pipeline 加 pipeline_profile 参数（stock/bond），bond 走 5 阶段流水线（L0/L1/L2/L3/L6_fees_holdings，跳过 L4 risk + L5 achievement），复用 fetch_fees + fetch_bond_hold + persist_snapshot 写入路径，5 worker ThreadPoolExecutor 并发对齐 market_nav_fetcher 限流，单只失败仅入账 errors 不重试。前端 0 改动、schema 0 改动。测试：24 条 test_market_full_pipeline 全过（含 5 条新增 L6 + 4 条 profile + 既有 19 条回归），350 条后端全套无回归。spec §12 沉淀到 contracts.md。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `dcafbd1` | (see git log) |
| `0037748` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: 排查并修复线上流动性卡片 DR001 恒空

**Date**: 2026-09-15
**Task**: 排查并修复线上流动性卡片 DR001 恒空
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

线上宏观日频流动性卡片 DR001 显示「—」。排查:线上 /api/macro/daily-snapshot dr001 全 null 而 DR007 正常;本机同款请求拉 prr-md.json 有值;端到端复现 extract_dr001 返回 None。根因:真实响应 records 在顶层,data 下仅 showDate 字段,解析按 data.records 写,自 2026-09-01 上线起恒空;测试 mock 与代码同错致测试全绿。修复:extract_dr001 顶层优先+data.records 回退;mock 改真实结构+旧结构兼容用例(12 passed,全量 169 passed,真实接口 fetch_today 返回 1.4266);spec macro-daily-snapshot.md §2.1 沉淀真实结构与外部数据源端到端验证教训。待 push + NAS 部署生效。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `3e20e8f` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: DR001 改定时落库对齐 DR007 设计

**Date**: 2026-09-16
**Task**: DR001 改定时落库对齐 DR007 设计
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

用户发现 /update/dr007 命名易误解,排查确认 prr-chrt.csv 本就同时含 DR001/DR007/DR014 三列(index 6/7/8,与当日快照交叉验证),仅 DR007 被解析入库。按用户决策把 DR001 改为 DR007 同款定时落库:dr001_service 重写(同源 CSV 取 index 6,删 prr-md.json 实时链路)、data_service files/save/load、新增 POST /update/dr001、scheduler a_share_daily 接入、docs/api.md;daily_snapshot 零改动前端无感。测试 169 passed,端到端回补 66 行(最新 1.4266 与源一致)。DR001 从此具备 asof 回退,外部源故障不再整行消失。部署后需手动 POST /api/update/dr001 首次回补或等 16:30 定时。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `56b32a3` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: 日频信号首页补充北向/南向资金与中债利率指标

**Date**: 2026-09-20
**Task**: 日频信号首页补充北向/南向资金与中债利率指标
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

对比宏观信号首页与系统数据面找出未展示指标;补全日频快照 9→15 指标:外部压力组加北向成交额3指标(7日窗口口径,净买额已停发)、市场情绪组加南向净流入、流动性组加中债10Y/10Y-2Y利差;新增key挂曲线跳转;16测试全绿+前端build通过;spec macro-daily-snapshot 同步至15指标(§2.2/§2.3/§5)

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `54e46c6` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: 信号卡片标题追加月频/日频标注

**Date**: 2026-09-20
**Task**: 信号卡片标题追加月频/日频标注
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

宏观信号首页 7 张卡卡头追加频率弱化标注(月度·月频/日频·日频),渲染处拼 span 保证后缀不泄漏到图例;保留月度「货币政策」vs日频「流动性」概念区分;纯前端,pnpm build 通过

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `abcbee3` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## Session: skill-manager Skill 发布管理台

**Date**: 2026-09-20
**Task**: 09-20-skill-publish-console
**Package**: backend/skill-manager + apps/skill-manager
**Branch**: `master`

### Summary

新增第 7 组服务 skill-manager（前端 3008 / 后端 8097）：双栏发布工作台管理自研与 GitHub Agent Skills，密码保护发布/下架/回滚到 NAS 宿主机 OpenClaw/Hermes（受限目录内原子 symlink）。注册表从 HTML 内嵌 JSON 迁移为 skills 仓库 registry.json（17 Skill / 4 Agent）。8 个 Task 全部完成，trellis-check 发现并修复 2 个生产缺陷（nginx 无尾斜杠 404、GitHub 发布前未 fetch 受记录 revision）。

### Main Changes

- backend/skill-manager：FastAPI + SQLite 审计 + RegistryService/GitCacheService/Publisher，89 测试通过（WSL 98 全过）
- apps/skill-manager：Next.js 15 /skills 双栏工作台，queue 纯函数 6 测试
- skills 仓库：registry.json 真源 + 三个 sync 脚本改造
- 部署：compose 双服务（五类受限挂载、密码 fail-fast）、nginx 三件路由、deploy 脚本映射
- spec 沉淀：Windows 测试环境契约 + nginx 无尾斜杠警告

### Git Commits

2520687 / 0630abd(skills) / e20f1f3 / b0ee0fe / 4275438 / 59a960c / 02a5e7b / 02752dc / 5e182aa / 101de50 / 8ed182b

### Testing

- 后端 `uv run pytest tests -q`：88 passed + 13 skipped（symlink 特权跳过，WSL 98 全过）
- 前端 vitest 6 passed + lint 零错误 + 编译通过（standalone 拷贝受本机 symlink 特权限制，生产走 Docker）
- compose/deploy 静态检查通过；nginx -t 待 NAS

### Status

[OK] **Completed（NAS 实机验收待执行）**

### Next Steps

- NAS 上按 docs/skill-manager-nas-setup.md 上线验证清单执行（deploy、health、nginx -t、/skills 渲染、真实发布冒烟）


## Session 14: skill-manager 右栏改为已部署视图

**Date**: 2026-09-21
**Task**: skill-manager 右栏改为已部署视图
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

右栏从手动发布队列改为按 OpenClaw/Hermes 分组的已部署视图（仅 active），回滚/下架入口迁移至此；队列保留为辅助流程，计划预览新增'新增 N 项·更新 M 项'汇总与实底徽章。无后端改动。浏览器实测全流程通过。发现环境级问题：Windows 非提权进程 symlink 发布始终 WinError 1314（spec 已记载），本机跑通发布需开开发者模式或提权后端，或后续考虑 junction 方案。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `492b22b` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: skill-manager 删除已登记 GitHub Skill 功能

**Date**: 2026-09-21
**Task**: skill-manager 删除已登记 GitHub Skill 功能
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

新增 DELETE /api/skills/{skill_id}（仅 github 来源，active 部署 409 拒绝）：registry.remove + git commit + 尽力清理 github_check/回滚快照/缓存目录；前端 GitHub 卡片删除按钮 + 密码确认 + 队列清理。浏览器实测 401/409/成功三路径全通过，测试条目与 skills 仓库测试提交已清理。spec 补充：手工改 registry 未 commit 时删除会因 nothing-to-commit 500；删除全局生效、缓存清理仅本环境。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `032a344` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: skill-manager 登记真源迁移 SQLite

**Date**: 2026-09-21
**Task**: skill-manager 登记真源迁移 SQLite
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

登记/删除/列表改为 SQLite registry_skill 表真源，删除 registry.json 写入与 git commit 依赖（NAS git add 128 根除）。首次启动单向导入 registry.json（真实环境验证：17 条导入、二次启动不重复、文件逐字节未变、错误码契约不变）。registry.json 归还 skills 仓库 sync 工具链。质量检查 0 问题；spec 已同步新语义。后续任务：界面编辑 + 手动导入/导出 registry.json。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a77e6ff` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: skill 管理：自研对账登记 + 废弃源库 sync 工具链

**Date**: 2026-09-22
**Task**: skill 管理：自研对账登记 + 废弃源库 sync 工具链
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

1) skill-manager 自研 skill 由源库目录自动对账登记（sync_local），SKILL.md frontmatter 解析元数据，source_missing 提示，测试 111 通过；2) 废弃源库 F:/personal-projects/skills 的 sync 工具链，删除 registry.json/sync-config/skill-agent-matrix/scripts/sync_*.py，README 移交 skill-manager；3) spec 记录对账契约。已归档 09-22-skill-local-sync 与 09-22-skill-manager-replace-sync

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `c46aa14` | (see git log) |
| `b2b361d` | (see git log) |
| `555a500` | (see git log) |
| `20f0848` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
