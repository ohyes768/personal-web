# 实施计划

## 激活前

- [x] 加载 trellis-before-dev 和目标包 specs，检查当前工作区改动。
- [x] 读取现有 AlertLevelBar 并核实四阈值五区间的最小调整方式（结论：新写 ValuationPriceBar 窄条，AlertLevelBar 随 Tab 替换移除）。
- [x] 核实 Hermes 部署 skill 版本（basic-quality-rating v4.4.0 已部署；stock-four-level-valuation v1.0.0 未部署，需经 skill-manager 发布后配置 HERMES_VALUATION_SKILL_PATH/VERSION）。
- [x] 完成接口、任务持久化/重启恢复、幂等与应用并发合同，补全 design.md（已核实：ValuationReport 17 字段校验、valuation-{code}-{data_date}-{version} 幂等键、apply 按 evaluated_at 身份 409 防护）。
- [x] 核对首次未应用预览语义（候选条虚线 + 「评估结果 · 未启用监控」角标），收敛 PRD；用户请求实施后再启动任务（2026-11-11 用户已请求）。

## 实施顺序

1. [x] 独立估值结果模型、完整校验及持久化，覆盖四种结果状态（valuation_service.py + valuation_reports.json）。
2. [x] Hermes 队列提交、重复提交处理、轮询/恢复及失败重试（kind='valuation'，append_codes 扩展共用；GET /refresh/jobs kind pattern 扩展修复 quality/valuation 重发现）。
3. [x] 报告读取与人工应用，保护旧配置并处理取消收藏/陈旧报告竞态（POST /valuation/{code}/apply + PUT /favorites/{code}/alerts/enabled）。
4. [x] 替换 alerts 页为全部收藏表格，接入筛选、搜索及状态（FavoritesTrackingTab，?tab=alerts URL 保留）。
5. [x] 报告阅读、价格对比、确认应用、监控暂停/恢复（ValuationReportModal + 安全 Markdown）。
6. [x] 紧凑四阈值五区间条、现价标记及无有效结果时隐藏（ValuationPriceBar 400px，按用户复核加宽；随后再精简到 3 层，行高 130px → 86px；单挡位/未评估/失败/非 ready 均有明确非条形）。
7. [x] 收藏成功快捷评估入口及旧 URL 兼容（ScreeningTab 收藏消息行「评估挡位」按钮；旧 ?tab=alerts 直达收藏跟踪）。
8. [x] trellis-check、相关 specs 更新（新增 valuation-contract.md、index 与 refresh-jobs 合同更新）；提交和部署按用户后续指示处理。

## 验证

- [x] 后端：skill 合同、非 ready 禁止应用、同股重复任务、失败/重启恢复、原子应用与竞态、旧监控保留（test_valuation_service.py 20 用例 + test_valuation_api.py 15 用例；全套 423 passed / 3 skipped）。
- [x] 前端：收藏全集、重叠筛选、隐藏/候选/生效三种图条语义、现价越界/缺失、监控启停与报告互斥（e2e/favorites-tracking.spec.ts 8 用例全过；screening/refresh-jobs 回归 32 用例全过）。
- [x] 浏览器桌面/窄屏：窄屏 390px 无横向溢出、主操作可达（narrow viewport 用例）；真实 Hermes 全链路（首次评估到应用、非 ready、失败重试）待 skill 发布后联调。
- [x] 实施前读取 package.json/pyproject.toml 后登记精确检查命令（后端 pytest、前端 tsc+lint+playwright）。

## 遗留（实施完成待用户处理）

- skill 部署：经 skill-manager 把 stock-four-level-valuation v1.0.0 发布到 Hermes profile ohyes768，再配置 HERMES_VALUATION_SKILL_PATH（挂载 SKILL.md）或 HERMES_VALUATION_SKILL_VERSION=1.0.0。
- 生产构建：Windows 本机 `pnpm build` 在 standalone symlink 步骤 EPERM（既有环境限制），TS 编译经 `tsc --noEmit` 验证干净；生产构建按现有 Docker/Linux 流程。
- quality-reader.spec.ts 溢出用例在本机因字体渲染差异失败（Expected >1104 Received 1104），与本次改动无关的既有问题。
- git commit / push 按用户指示执行。
