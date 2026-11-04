# 代码调研依据（2026-11-03）

## 入口与现有报告

- `apps/dividend/src/app/page.tsx:618`：主数据首次加载提前返回骨架屏。入口若仅放普通头部，会在主表加载时不可见；实现需复用同一入口组件放到两种返回分支。
- `apps/dividend/src/app/page.tsx:633`：主页面头部；新增入口建议放标题描述之后、筛选条件之前，允许手机换行，不挤入右侧操作列。
- `apps/dividend/src/app/page.tsx:549`：tab 与 fav 的 query 规则；返回参数仅保留既有有效值。
- `apps/dividend/src/components/ScreeningTab.tsx:95`：股票详情与评分弹窗互斥；本任务保留原逻辑。
- `apps/dividend/src/components/QualityReportModal.tsx:41`：重评工具条、元数据、五维表、风险、关注点、Markdown 目前写在一起。将纯内容抽出后由弹窗和阅读页共同使用，重评仍属于原弹窗。
- `apps/dividend/src/components/QualitySkillVersion.tsx:2`：已有版本/需重评提示，可直接复用。

## 数据契约与加载策略

- `apps/dividend/src/lib/api.ts:44`：`dividendApi.getQualityScores()` → `GET /api/dividend/quality`，direct response，不解包 `{success,data}`。
- `apps/dividend/src/lib/quality.ts:18`：QualityScore；QualityScoresResponse 包含 scores、current_skill_version、per_code、hermes_configured。
- `.trellis/spec/backend/dividend-select/backend/quality-rating-contract.md`：五维有 null 时保留其他维度；不得恢复总星级、加权分或边界提示；历史正文不改写。版本与耗时缺失按既有语义展示。
- `apps/dividend/src/lib/hooks/useQualityAnalysis.ts:53`：现有 hook 首屏读失败会吞错；挂载还会发现分析任务并轮询。阅读页需要明确 loading/error 和只读行为，因此新增窄范围读取 hook，复用 API/类型但不套用任务管理 hook。
- 首版全量结果一次加载，切换本地结果无需网络；仅首次和手动刷新读取。不新增后端接口；如果真实数据体积将来成为问题，另立性能任务。

## 路由与部署

- `apps/dividend/next.config.js:4`：basePath 为空。
- `nginx/web.conf:109`：location /dividend/ + proxy_pass http://dividend_frontend/ 会剥离线上前缀。
- 不能直接把 Link href=/quality-reader 当线上入口，否则浏览器离开 /dividend/；也不能在本地硬编码 /dividend/。
- 建议用普通同源 a 做主页面/独立页之间的完整导航；在客户端基于浏览器 pathname 严格识别根路径或 /dividend 边界，构造两类地址。新页内部切换仅改 query，用 History API 保留实际 pathname，避免 Next 路由缓存使用带前缀路径导致不一致。
- 新页由 Suspense 包裹 useSearchParams；History API 与 query 同步需在执行时通过当前安装版本的浏览器用例验证，不凭假定放行。
- API 路径维持 /api/dividend/quality，不随页面前缀拼接。

## 样式与测试基础

- `apps/dividend/src/app/globals.css:6`：paper/ink/rule/accent 现有 tokens；不引入新字体或新主题。
- `apps/dividend/src/app/globals.css:132`：md-body 现有报告样式。阅读页使用附加 scoped class，避免全局加大弹窗字号。
- `apps/dividend/e2e/screening.spec.ts:1`：已有 API mock、历史报告无星级、维度 null、版本及耗时用例，可复用契约，不复制整个 setup 到阅读测试。
- `apps/dividend/playwright.config.ts:1`：本地 3003，自启 next dev，reuseExistingServer=true；运行前确认该端口是本仓库应用，测试拦截 API，不触发真实分析。
- `apps/dividend/package.json`：有 build、test:e2e；lint 为 next lint，Next 15 环境执行时需核实可用性，不能把命令缺失报告成检查通过。
- `docs/dividend-testing-checklist.md`：股息率变更要求生产构建和浏览器回归；本次重点为阅读链路和被抽取内容影响的原评分弹窗。

## 方案取舍

1. **独立路由（选择）**：长文、深链接、刷新自然；需小范围处理既有部署前缀。
2. 全屏弹窗：复用快，但仍依赖主页面加载，不适合独立收藏及手机长文。
3. 主页面 query 切换为阅读模式：避开新增路由，但主页面已经承载大量行情 hook；若不拆分，阅读将受行情请求和首屏骨架影响。

选择 1；只抽取报告内容和路径小工具，不重构主页面的数据层。

## 任务归属

Trellis 未登记 apps/dividend 包，创建脚本默认误填 backend/douyin-processor；本任务已纠正为 package=null、scope=dividend、dev_type=frontend，通过 relatedFiles 明确归属。无需为本功能修改 Trellis 配置。项目默认 Codex inline，无子代理清单要求。
