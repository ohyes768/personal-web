# 基本面资料手机阅读界面 Implementation Plan

**Goal:** 给股息率页面添加手机友好的独立基本面报告阅读界面，支持上下篇与股票下拉选择。

**Architecture:** 独立 `/quality-reader` 路由读取已有 quality API，报告纯内容由原弹窗与阅读页共享。URL code 决定当前报告；线上前缀由浏览器实际 pathname 保留，跨页完整导航，页内 History API 切换。

**Tech Stack:** 现有 Next.js 15 / React 19 / TypeScript / Tailwind 4 / react-markdown / Playwright；不新增依赖。

**执行方式与状态：** 当前仅规划，未执行下列清单。收到实现指令后按 Trellis 默认 Codex inline 流程逐项执行；开始前加载 trellis-before-dev，结束前加载 trellis-check 与 verification-before-completion。无需派生新任务或新 worktree，不自动提交、推送或部署。本文件是唯一实施计划，不在 docs 下复制一份。

## 0. 实现前检查

- [ ] 阅读同目录 prd.md、design.md、research/codebase.md，确认用户未调整首版范围。运行 `python .trellis/scripts/get_context.py` 核对当前 git 状态，保留其他任务未提交内容。
- [ ] 读取 `.agents/skills/trellis-before-dev/SKILL.md`、`.trellis/spec/guides/code-reuse-thinking-guide.md`、`.trellis/spec/backend/dividend-select/backend/quality-rating-contract.md` 和 `docs/dividend-testing-checklist.md`；apps/dividend 无单独注册 spec，不能误用 douyin 包规范。
- [ ] 按 Impeccable 当前技能加载 reader/operate 与 craft-floor，核对 incumbent tokens；本轮已经做过 context，不重复执行。未来新会话按技能重新加载一次。
- [ ] 用户授权实现后运行 `python .trellis/scripts/task.py start .trellis/tasks/11-03-dividend-quality-reader`，再读取 phase 2.1；任务仍为 planning 时不得修改产品代码。
- [ ] 检查 3003 的服务归属和 Node 可用性；测试期间所有 quality 写接口拦截并记录，不能真实发起收费分析。

## 1. 添加阅读集合与路径工具及其测试（R3/R5/R8）

文件：新增 `apps/dividend/src/lib/quality-reader.ts`、`apps/dividend/src/lib/quality-reader.test.ts`。

- [ ] 先写纯函数契约测试：乱序代码升序；null 维度仍入集合；无 code 选首篇；未知或非法 code 返回 null；空集合不产生当前项。
- [ ] 路径测试覆盖 `/`、`/quality-reader`、`/dividend/`、`/dividend/quality-reader`、`/dividend-other/`；仅正确边界保留 dividend 前缀。fromTab 只接受 all/alerts/screening，fromFav 仅 all 时生效，外部 returnUrl 被忽略。
- [ ] 用下面的最小接口实现并通过单测，不把路由信息塞入 QualityScore：

```ts
export function sortReports(scores: Record<string, QualityScore>): QualityScore[];
export function selectReport(reports: QualityScore[], code: string | null): QualityScore | null;
export function getDividendPrefix(pathname: string): '' | '/dividend';
export function readerHref(pathname: string, sourceQuery: URLSearchParams): string;
export function returnHref(pathname: string, readerQuery: URLSearchParams): string;
```

实现要点：Object.values 后用 code.localeCompare 排序；selectReport 仅当 code===null 时默认首篇；以正则 `/^\/dividend(?:\/|$)/` 判定前缀；query 均通过 URLSearchParams 组装并只复制白名单参数。

- [ ] 在 apps/dividend 下运行 `node --experimental-strip-types --test src/lib/quality-reader.test.ts`。预期所有用例通过；首次运行应先观察缺少实现导致的失败。工具文件的类型导入使用 `import type`，不引入运行时 alias 以便沿用现有原生 TS 单测方式。

## 2. 抽出共享报告内容（R2/R6，保护既有弹窗）

文件：新增 `QualityReportContent.tsx`；修改 `QualityReportModal.tsx` 与局部 `globals.css`。

- [ ] 在现有 screening 浏览器用例基础上增加「report_md 为空仍保留评分/元数据并有提示」场景，先验证旧版缺少该提示。
- [ ] 将现有元信息、QualitySkillVersion、摘要、五维表、风险、关注点、Markdown 原样移动到共享组件；接口采用 design.md 的 QualityReportContentProps。Modal 保留其 props、重评工具条、标题和 onClose，仅替换内容：

```tsx
<QualityReportContent score={score} currentSkillVersion={currentSkillVersion} variant="modal" />
```

- [ ] 沿用既有 Markdown 插件；reader 变体定制 table wrapper 和 code overflow，不使用 rehype-raw；空正文提示与 null 评分都有稳定可访问文本。
- [ ] 运行 `npm run test:e2e -- e2e/screening.spec.ts`，重点检查旧星级隐藏、null 维度、版本提示、耗时与重评行为。抽取内容必须保持这些测试通过，不以修改断言掩盖回归。

## 3. 只读数据 hook 与独立阅读路由（R2–R7）

文件：新增 `useQualityReports.ts`、`QualityReader.tsx`、`app/quality-reader/page.tsx`，新增 `e2e/quality-reader.spec.ts`。

- [ ] 先写 mock 读取测试：三份已保存报告及一个 queued 状态；Hermes false 仍可读；请求 500 显示重试，不能显示空结果；第二次请求成功后恢复正文。只 mock 所需 quality GET，其他 API 请求作为不必要依赖失败检查。
- [ ] hook 按 design.md 状态契约调用 `dividendApi.getQualityScores()`，实现首读/刷新分离、失败保留快照、请求序号和卸载保护；不使用 useQualityAnalysis，不发 latest-job 或轮询请求。
- [ ] 路由 page 使用服务端 metadata title「基本面资料阅读 · 股息率」，Suspense 包裹客户端 QualityReader。渲染次序：返回/刷新 → 选择/进度 → 公司标题 → QualityReportContent(reader) → 固定翻页。
- [ ] 实现空集合、单篇、代码不存在、正文缺失及末篇禁用，所有文案按 design.md；未找到 code 时不默认选其他公司。
- [ ] 当前公司从 URL code 和 snapshot 派生，不另存 selectedIndex。首次无 code 成功后 replaceState 补首篇；用户翻篇 pushState 保留 pathname/from 参数并清除 hash。浏览器前进后退测试确认 query 与内容同步。
- [ ] 主动换篇后回顶并聚焦标题；刷新不动滚动/焦点。刷新成功以 code 保留当前公司，即使新增更小代码；删除当前公司进入不存在状态。刷新失败保留内容并提示。
- [ ] 添加防回归断言：下拉切换、快速两次下一篇、首末边界、reload、goBack/goForward、未知代码、code 为空字符串、刷新增删数据；页面全程 quality POST 数为零。

建议核心导航用例（fixture 提供两篇以上的完整 QualityScore，按现有类型填写，不从真实后端取数）：

```ts
await page.goto('/quality-reader?code=000001');
await expect(page.getByRole('heading', { name: '测试公司甲', exact: true })).toBeVisible();
await page.getByRole('button', { name: '下一篇', exact: true }).click();
await expect(page).toHaveURL(/code=000002/);
await page.reload();
await expect(page.getByRole('combobox', { name: '选择公司' })).toHaveValue('000002');
```

## 4. 主页面入口与部署路径（R1/R8）

文件：新增 `QualityReaderEntry.tsx`；修改 `app/page.tsx`；扩展阅读页 E2E。

- [ ] 先测主表 API 持续等待时入口仍可见；同一测试在 all/alerts/screening 各视图断言入口，确保非表格工具条专属。
- [ ] 入口作为普通同源 a，初始同目录相对 href，挂载后用 readerHref(window.location.pathname, query) 生成地址；插入主页面加载骨架和正常头部。手机能换行，不改变三列头部已有操作。
- [ ] 阅读页返回使用 returnHref 和有效的 fromTab/fromFav，无来源则默认首页；空结果的「返回选股关注」强制 tab=screening。不可直接使用 href="/" 或 history.back 作为唯一返回方式。
- [ ] 在 E2E 用 `page.route('**/dividend/**', ...)` 对文档/Next RSC请求做测试专用前缀剥离并转发给本地 Next（用 route.fetch 的 url 覆写）；其他资源放行。覆盖线上风格 URL 的直接进入、入口点击、翻篇、刷新和返回，验证浏览器地址始终保留 `/dividend/`。
- [ ] 若 Next 绝对资源路径影响代理模拟，使用同等剥前缀行为的临时本地 HTTP 代理验证；测试代码不修改生产 nginx/basePath。最终仍须按 nginx/web.conf 原规则做部署形态 smoke，不能用路径纯函数测试代替浏览器验证。

## 5. 手机阅读样式与可访问性（R6）

文件：`globals.css`、`QualityReader.tsx`、`QualityReportContent.tsx`。

- [ ] 只给 reader wrapper 增加样式：48rem 最大宽度、16/24px 留白、17px/1.8 正文、16px select、44px 触摸目标、focus-visible、min-width:0 与 overflow-wrap:anywhere。
- [ ] 底栏共用 `--quality-reader-nav-height`，高度与正文 padding-bottom 均叠加 env(safe-area-inset-bottom)；避免使用 100vh 强制锁住正文滚动。
- [ ] 测试正文放长链接、12 列表格、长代码块和末段标记。360×800、390×844、1440×900 批量截图；断言 document.scrollWidth 不超过 clientWidth，表格容器 scrollWidth 可大于 clientWidth，滚至末段时内容不被底栏遮挡。
- [ ] 键盘 Tab 操作返回、刷新、选择、上下篇；有可读 label、disabled 状态和焦点轮廓。按 Impeccable 规则集中检查一轮、修正一批，必要时仅复核一轮。

## 6. 验证、文档与交接

- [ ] 依次在 apps/dividend 运行：

```powershell
node --experimental-strip-types --test src/lib/quality-reader.test.ts
npm run test:e2e -- e2e/quality-reader.spec.ts e2e/screening.spec.ts
npx tsc --noEmit
npm run build
```

预期：单测/E2E 全通过、类型检查无错误、生产构建成功。构建与 E2E 不并行，避免共享 .next 目录竞争。lint 命令可用性按 research/codebase.md 说明核实；不为本功能顺手迁移全项目 lint。

- [ ] 从仓库根运行 Impeccable detect（一次，目标为本次修改的 TSX/CSS）；区分真实可访问性问题与有设计依据的提示，修复确认的缺陷。
- [ ] 更新 `docs/dividend/01-界面功能设计.md` 与 `docs/dividend-testing-checklist.md`，说明独立阅读入口、集合顺序、深链接、错误状态和前缀验收；共享报告合同若有新增稳定约定，按 trellis-update-spec 写入已有合适位置，不创建空 frontend spec 树。
- [ ] 生成任务 `verification.md`，逐项映射 AC1–AC8，记录实际命令退出码、测试数量、截图路径和反代验证结果；未测项必须标未测，不能声称通过。
- [ ] 运行根目录 `git diff --check`，检查 git status 仅含授权范围变更；质量门通过后向用户交付。Git 提交/推送/部署等待相应授权，任务归档遵循后续 finish-work 流程。

## 风险检查与回滚点

1. 阶段 2 后原弹窗回归未通过：先修复共享抽取，不继续扩大页面改动。
2. 阶段 4 前缀导航不通过：限定修正路径工具与跨页导航，不改全站 basePath 或 nginx。
3. 最终失败需要撤销：按本任务变更 hunks 撤销入口、阅读页及共享抽取，不触碰已有评分文件、队列或其他任务的改动。

## 规划自查

- R1→阶段4，R2→阶段2/3，R3→阶段1/3，R4→阶段3，R5→阶段1/3/4，R6→阶段5，R7→阶段3，R8→阶段1/4；验收映射无缺口。
- 已明确列表范围/顺序、URL 身份、首末边界、失败与空结果、刷新时增删、手机安全区和线上前缀，不留待实现者猜测。
- 本轮未运行应用测试；以上是执行计划，不能视为已有验证结果。
