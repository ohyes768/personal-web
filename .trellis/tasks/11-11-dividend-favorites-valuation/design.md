# 收藏跟踪设计边界

## Status

接口合同已核实补全（2026-11-11，实施前）：skill v1.0.0 合同、Hermes 部署现状、现有代码结构均已确认。业务方向和 HTML 原型已认可；价格条收窄，不照抄原型模拟代码。

## Data flow

`选股关注收藏 → 收藏跟踪评估入口 → dividend 独立估值任务 → Hermes stock-four-level-valuation → 候选报告 → 人工确认 → favorites alerts 生效配置 → 原 AlertService 监控`

- 基本面研究可复用，估值结果不能塞进现有 QualityScore；任务、报告及错误需要独立类型。
- 收藏身份、基本面结果、估值任务、候选报告、生效挡位、监控 enabled 分开表达；新报告待应用可与旧配置监控中并存。
- 应用时验证 code、报告 ID、ready 状态及收藏仍存在；具体并发/旧报告覆盖新报告防护在实现前设计。
- 失败或非 ready 只更新评估结果，不覆盖旧监控；保存沿用既有原子持久化原则。
- Hermes skill 只研究并输出，不持有平台写入职责。不能把本地 skill 文件存在等同于远端已部署。

## UI

- 主表：股票/基本面、现价、紧凑价格条、评估与监控状态、操作。
- 图条为四阈值五区间；首次 ready 未应用允许明确标注的候选预览，旧配置存在时主表展示生效条。
- 侧边报告面板阅读依据、来源、风险及新旧对比，底部确认应用并监控；沿用现有安全 Markdown 渲染约定及 Modal 互斥规则。
- 参考 prototype.html，但价格条收窄，不照抄原型的三段条或模拟价格算法。

## Compatibility / risks

- 保留旧 alerts 链接导航、旧收藏和手工挡位，不因迁移自动开启监控。
- 请求按收藏代码加载，避免扩大为全池行情/技术数据请求。
- 新功能故障不损坏 favorites/alerts 数据；候选/生效混用及应用竞态是重点风险。

## Evidence to load before implementation

- `.trellis/spec/backend/dividend-select/backend/quality-rating-contract.md`
- `.trellis/spec/backend/dividend-select/backend/screening-watchlist-contract.md`
- `.trellis/spec/backend/dividend-select/backend/refresh-jobs-contract.md`
- `apps/dividend/src/app/page.tsx`、`components/AlertLevelBar.tsx`、`components/AlertSettingsModal.tsx`、`components/ScreeningTab.tsx`
- `backend/dividend-select/src/services/quality_service.py`、`hermes_client.py`、`favorites_service.py`、`alert_service.py`
- 新估值 skill 的 SKILL.md、references/input-and-reuse.md、references/output-contract.md。

## Verified facts (2026-11-11, implementation baseline)

- Skill `stock-four-level-valuation` v1.0.0（skills 仓库 investment-analysis/）：单次单股，输出恰 17 字段
  （`schema_version/skill_version/code/name/currency/as_of/status/levels/valuation/evidence/data_gaps/
  confidence/risks/invalidation_conditions/summary/analysis/report_md`）。status ∈ ready/insufficient_data/
  blocked/not_applicable；仅 ready 有 `levels`（heavy_position<add_position<reduce_position<full_exit，
  各 `{price,pe,pb}`，price 严格递增正数）与非空 `valuation`；非 ready `levels`/`valuation` 为 null，
  研究五段仍在 `analysis`。运行方式与 basic-quality-rating 相同：Hermes Runs API，`run.output` 交付单个 JSON。
- Hermes profile `ohyes768`（NAS `~/.hermes/profiles/ohyes768/skills/`）已部署 `basic-quality-rating` v4.4.0；
  `stock-four-level-valuation` **尚未部署**——实现完成后需经 skill-manager 发布到 profile，并配置
  `HERMES_VALUATION_SKILL_PATH`（挂载 SKILL.md）或 `HERMES_VALUATION_SKILL_VERSION` 才能启用版本校验。
  不能把本地 skill 文件存在等同于远端已部署；未配置版本时按 `unknown-{attempt_id}` 幂等键并跳过版本比对。
- `hermes_client.py` 的 `submit_run/poll_run` 直接复用（无 cancel 需求，不需要 stop_run/get_run 轮询路径）。
- `RefreshJobManager.submit/append_codes` 为 kind 无关；`append_codes` 由 quality 扩展为 quality+valuation 共用；
  `_prune` kinds 增加 `valuation`。cancel/reorder 辅助方法仍 quality 专用。
- 收藏 alerts 存储：`favorites.json` `items[].alerts = {enabled, updated_at, levels{...}}`；
  应用估值 = `FavoritesService.update_alerts` 写入 skill 四价（enabled=true），复用既有原子写与监控链路。

## Interface contracts

### Backend — `valuation_service.py`（新）

- `ValuationReport`（pydantic）：17 字段逐项校验——`code` 必须等于请求代码、`name` 非空、`currency=='CNY'`、
  `as_of` YYYY-MM-DD、`status` 枚举、`skill_version` 语义版本；ready 时 `levels` 恰四键且价格>0 严格递增、
  `valuation` 非空；非 ready 时 `levels`/`valuation` 归一为 null（容忍全 null dict）；`report_md`/`summary` 非空；
  `analysis` 恰 business/normalization/dividend/valuation/risk 五段非空；`evidence` 为 dict 数组（保留原文，
  只做 id 唯一与 kind/verification 字段存在性轻校验）。解析容错 ```json 围栏与前后杂文（复用 quality 模式）。
- 落盘 `data/valuation_reports.json`：`{code: {…17字段, evaluated_at, data_date, analysis_duration_seconds}}`，
  file lock + `atomic_write`，逐股完成即写。报告不可变：重评生成新 evaluated_at 覆盖同 code 记录，
  应用前旧值不再单独保留（对比由前端用旧 alerts levels + 新报告完成）。
- `ValuationService`（模式同 QualityService 精简版）：无 cancel/reorder，`poll_run_fn` 阻塞轮询即可。
  per_code 状态 queued/running/completed/failed（内存，重启清空，job 置 interrupted）。
  受理快照：payload（build_stock_payload + market_snapshot + 既有评级记录）、name、data_date、expected skill_version。
  幂等键 `valuation-{code}-{data_date}-{skill_version|unknown-{attempt_id}}`；data_date 复用财务汇总 mtime（`_quality_data_date`）。
  活跃任务追加入队（append_codes，reused=true），已在队/在跑幂等跳过；收尾窗口等待后开新任务。
- Prompt 点名 `stock-four-level-valuation`：要求 bare JSON、输出 skill_version、版本不符拒绝；内联材料的
  origin 按 `inline:<日期>:<描述>` 登记；现价仅行情参考，禁止按现价比例推导四点；不足时按 skill 规则收口
  insufficient_data 而不是继续搜索。

### Backend — 路由（routes.py）

- `GET /api/dividend/valuation` → `{total, reports: {code: record}, per_code, hermes_configured, current_skill_version}`。
- `POST /api/dividend/valuation/analyze` `{codes}` → 202 job（复用/追加语义同 quality）；股票不在采集池 400；
  Hermes 未配置 503；空 codes 422。
- `GET /api/dividend/valuation/jobs/{job_id}` → job + per_code（kind=valuation，非估值 kind 404）。
- `POST /api/dividend/valuation/{code}/apply` `{evaluated_at}` → 校验收藏存在（404）、报告存在且 evaluated_at
  等于当前最新（不等 → 409 返回当前身份）、status=='ready'（否则 400）；写 `update_alerts(code,
  {enabled:true, levels:{四价含 pe/pb}})`；返回 favorites 响应。失败/非 ready/陈旧报告一律不触碰 alerts。
- `PUT /api/dividend/favorites/{code}/alerts/enabled` `{enabled}` → 仅翻转 enabled，不改 levels；
  未收藏 404，无挡位配置 400。用于收藏跟踪行的暂停/恢复。
- 竞态：apply 与重评并发——apply 按 evaluated_at 身份判定，重评完成写入新 evaluated_at 后旧 apply 409；
  取消收藏并发——update_alerts KeyError 404；同 code 重复评估任务由队列幂等吸收。

### Frontend — apps/dividend

- `lib/valuation.ts`：类型（ValuationReportRecord/ValuationPerCode/ValuationJob）+ 状态派生
  `deriveFavoriteStatus(code)`：`monitoring`（alerts.enabled 且有挡位）/ `paused`（有挡位未启用）/
  `pending_apply`（ready 报告 evaluated_at 晚于 alerts.updated_at，可与 monitoring/paused 重叠）/
  `evaluating`（per_code queued/running）/ `failed`（per_code failed）/ `not_ready`（非 ready 报告）/
  `unevaluated`（无报告无任务且无生效挡位）。筛选：全部收藏 / 待评估（unevaluated∪failed∪not_ready∪evaluating，
  且从未应用过挡位）/ 待应用（pending_apply）/ 监控中 / 已暂停；重叠仅发生在 待应用∩(监控中|已暂停)。
- `hooks/useValuation.ts`：挂载拉 `GET /valuation`，重新发现 active job 并轮询（3s），提交 `analyze`，
  追加受理复用轮询；模式同 useQualityAnalysis。
- `components/FavoritesTrackingTab.tsx`：主表 5 列（股票/基本面、现价、窄挡位条、评估与监控状态、操作），
  5 筛选 chips + 搜索框；行内操作=评估挡位/重评/重试、查看报告、对比并应用、暂停/恢复、挡位设置
  （打开既有 AlertSettingsModal）；基本面列展示五维分数文本（评级报告仍在选股关注阅读）。
- `components/ValuationPriceBar.tsx`：宽 220–260px（w-60/240px），四阈值五区间横条 + 4 价标签 +
  现价标记；现价越界（低于重仓/高于全卖）在条端显示箭头+越界文案；缺现价显示「现价缺失」；
  生效条实线、候选条虚线并角标「评估结果 · 未启用监控」；无 levels 不渲染条（不画虚构五块）。
- `components/ValuationReportModal.tsx`：侧边报告面板——身份/期间/版本/耗时、四价新旧对比
  （新值列表 + 划线旧值）、summary、risks/data_gaps/invalidation_conditions、report_md 安全 Markdown
  （react-markdown + remark-gfm，同 quality-reader 约定）；底部确认应用/暂不应用；与详情/评级弹框互斥。
- `ScreeningTab` 收藏成功消息行追加「评估挡位」快捷按钮（对本次新增 codes 提交 valuation analyze），
  不自动提交；收藏即不自动评估、不自动开监控。
- page.tsx：tab=alerts 保留（URL 兼容），标签改「收藏跟踪」，内容替换为 FavoritesTrackingTab；
  AlertLevelBar 移除引用（组件与旧用例随删）。

### Tests

- 后端 pytest：`test_valuation_service.py`（模型校验 ready/非 ready/身份不符/围栏容错、落盘合并、
  受理/追加/幂等/失败重试/重启中断、版本不符不覆盖旧报告）；`test_valuation_api.py`（GET/analyze 202 与
  503/422/400、apply 成功/陈旧 409/非 ready 400/未收藏 404、enabled 翻转、旧监控保留）；
  `test_refresh_jobs.py` 增加 valuation kind prune/append 回归。
- 前端 playwright：`e2e/favorites-tracking.spec.ts`（收藏全集与筛选计数、待应用重叠语义、隐藏条/候选条/
  生效条三态、现价越界与缺失、应用前不开启监控、暂停恢复、旧 URL ?tab=alerts 可达）。
- 实施前已登记精确命令：后端 `cd backend/dividend-select && python -m pytest tests/ -v`；
  前端 `cd apps/dividend && pnpm lint && pnpm build && npx playwright test e2e/favorites-tracking.spec.ts`。
