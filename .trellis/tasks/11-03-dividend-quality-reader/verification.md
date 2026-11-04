# 基本面资料手机阅读界面 · 验证记录

> 任务：`.trellis/tasks/11-03-dividend-quality-reader`（dividend-quality-reader）
> 验证日期：2026-11-04
> 验证范围：`apps/dividend` 前端新增的独立阅读页、共享报告内容、只读加载 hook、主页面入口、作用域样式
> 环境：Windows 11 / Node 24 / Next.js 15.5.19 / Playwright（本地 3003 dev server）

---

## 1. 命令结果（实际退出码）

| 命令 | 结果 | 说明 |
|------|------|------|
| `node --experimental-strip-types --test src/lib/quality-reader.test.ts` | **19 pass / 0 fail**（6 suites） | 阅读集合排序、code 选择、线上前缀判定、入口/返回链接参数白名单 |
| `npx tsc --noEmit` | **exit 0**，无输出 | 类型检查通过 |
| `npm run build` | **exit 0**，`✓ Compiled successfully` | 路由表新增 `○ /quality-reader 2.24 kB`（静态预渲染） |
| `npx playwright test e2e/quality-reader.spec.ts e2e/screening.spec.ts` | **48 passed / 3 failed**（共 51） | 新增 28 例全通过；3 例失败为存量问题，见 §3 |
| `npx playwright test`（全量套件） | **51 passed / 3 failed**（共 54） | 含 `data-update-drawer.spec.ts` / `refresh-jobs.spec.ts`，其余全绿 |
| `npm run lint` | **不可用（未执行）** | 项目无 ESLint 配置，`next lint` 进入交互式向导（`Strict/Base/Cancel`）。按 `implement.md` 阶段 6 约定不为此迁移全项目 lint。`next build` 内建的类型检查已通过。 |

## 2. 验收条件逐项映射

| AC | 对应需求 | 证据 | 结论 |
|----|---------|------|------|
| AC1 | R1、R8 | E2E：`main page shows the reader entry in the 全部/挡位监控/选股关注 view`（3 例）、`main page shows the reader entry while the stock table is still loading`、`reader entry keeps the source view for the return link`（断言 `fromTab=screening` / `fromFav=1`）、`clicking the reader entry opens the independent reader page`；`screening.spec.ts` 的「重评」按钮与星级隐藏断言仍通过 | ✅ |
| AC2 | R2、R3 | E2E：`reader lists saved reports by code, keeps null dimension as 未评分 and hides aggregate stars`（下拉项断言严格等于 `['000001 甲公司','000002 乙公司','000003 丙公司']`；null 维度显示「未评分」；`3.7` / `⭐` / `踩线` 计数均为 0） | ✅ |
| AC3 | R4、R5 | E2E：`dropdown and prev/next navigation sync company, body, progress and URL`、`first and last article disable the matching nav button`、`only one article disables both nav buttons`、`rapid next clicks advance one article each time`、`browser back and forward restore the company from the URL` | ✅ |
| AC4 | R5、R7 | E2E：`unknown code shows unavailable state and does not silently show another company`、`an empty code parameter is treated as an unavailable report`、`empty result set shows empty state instead of an error`、AC2 用例中的「暂无完整报告正文」提示 | ✅ |
| AC5 | R6 | E2E：`reader layout does not overflow horizontally on phone and desktop`（360×800 / 390×844 / 1440×900，断言 `documentElement.scrollWidth ≤ clientWidth`，表格容器 `scrollWidth > clientWidth`）、`a very long company name does not stretch the select or overflow the page`、`last paragraph is not hidden behind the fixed bottom navigation`、`keyboard can reach and operate the reader controls`（可读 label、focus 轮廓、Enter 触发翻篇）；另人工核对 3 张截图 | ✅ |
| AC6 | R7 | E2E：`read failure shows retry and never pretends the collection is empty`、`refresh failure keeps previous content and reports the error`、`refresh keeps the selected code, ignores newly added reports and detects deleted ones`、`reading works even when Hermes is not configured`、`reader never polls for analysis jobs and only reads the scores endpoint`（全程只发 1 次 `GET /api/dividend/quality`，0 次 `/refresh/jobs`） | ✅ |
| AC7 | R8 | E2E：`online /dividend prefix keeps the prefix in the address bar across navigation`（直入 / 翻篇 / 刷新 / 前进后退 / 返回链接全程保留 `/dividend/`）。**模拟 nginx 剥前缀转发，未跑真实容器** | ⚠️ 模拟通过，真实部署形态未测 |
| AC8 | 全部 | 见 §1；截图人工核对记录见 §4 | ⚠️ 见 §5 存量失败与 §6 未测项 |

## 3. 存量失败（非本次引入，已复核）

`e2e/screening.spec.ts` 3 例失败：

- `compact rating preserves partial scores and opens report with skill version`
- `skill version display: v4.3.0`
- `skill version display: 版本未知`

失败断言形如 `expect(button).toHaveText('4/4/3/3/5（v4.3.0）')`，实际渲染为 `业务模式4护城河4行业前景3管理层3财务质量5`。

复核过程：把本任务改动的 4 个已跟踪文件（`src/app/page.tsx`、`src/components/QualityReportModal.tsx`、`src/app/globals.css`、`e2e/screening.spec.ts`）`git stash` 后在基线上重跑，**同样 3 例失败**（行号相应前移）。

根因：上游提交 `66b268af`（2026-11-02，「选股关注表格五维评级改为分维度直读」）改了 `ScreeningTab.tsx` 的评分单元格渲染为「维度名 + 分」网格，`3cf5836e` 又去掉了版本号占位格，但 `e2e/screening.spec.ts` 的断言没有同步更新。本任务未触碰 `ScreeningTab.tsx`，属上游遗留。

处理：**未修改**这些断言（避免用改断言掩盖问题、也避免跨任务范围改动）。修复合入 `66b268af` 所属任务，或单独立项。

## 4. 截图人工核对

| 截图 | 尺寸 | 核对结论 |
|------|------|---------|
| `reader-360x800.png` | 手机 | 入口与正文单栏、无整页横向滚动；12 列表格在容器内局部横滑；代码块局部横滑 |
| `reader-390x844.png` | 手机 | 元信息（数据日期/评分时间/分析耗时）三项各自成行不折断；长链接 `overflow-wrap` 换行；末段「末段标记」可见 |
| `reader-1440x900.png` | 桌面 | 正文容器限宽 48rem，行长可读；底部翻页栏与正文对齐 |
| 主页面 390×844 | 手机 | 「基本面资料阅读」入口在标题描述下方、页签上方，单行不折行，触控高度 44px |

E2E 断言的响应式结论（`documentElement.scrollWidth ≤ clientWidth`）已覆盖上表三种尺寸，未出现整页横向溢出。

## 5. 设计与实现的偏差（已确认为有意为之）

1. **入口位置**：design 建议放在头部 grid 内「标题描述之后、筛选条件之前」，实测 390px 下会被右侧「数据更新/导出」挤成三行折行，改为独占一行放在 grid 之后。R1/R6 的「手机可见」优先。
2. **元信息换行**：reader 变体把「数据日期 / 评分时间 / 分析耗时」拆成三个独立 span；modal 变体保持 `·` 连接的原格式不变。
3. **URL 同步实现**：Next 15.5.19 的 App Router 会 patch `history.pushState/replaceState` 并派发 `ACTION_RESTORE`，`useSearchParams` 随之更新，因此采用 design 方案 A（query 派生 + History API 写回），无需独立的 popstate 兜底订阅，也不存在「既存下标又存 code」的双状态。

## 6. 未测项 / 遗留风险（未测即未通过）

1. **真实 nginx 部署形态未验证**：AC7 用 Playwright route 模拟 `location /dividend/ { proxy_pass http://dividend_frontend/; }` 的剥前缀转发。已核对 `nginx/web.conf`：`/dividend/` → 前端根、`/_next/static` → dividend 前端、`/api/dividend/` → 后端，与应用 `basePath: ''` 一致；但**未启动真实容器验证**。上线前需按 `docs/dividend-testing-checklist.md` 做一次部署形态 smoke。
2. **未测真实后端数据**：全部 E2E 使用 mock 的 `QualityScore` fixture，未连真实 dividend-select 后端验证全量 `report_md` 的真实体积与真实字段完整性。
3. **全量 Markdown 响应体积未测量**：首版一次性加载全部结果（现有接口本就返回全量），未引入分页，也未记录实际响应体积作为后续性能依据。
4. **lint 未执行**：项目无 ESLint 配置，`next lint` 不可用（见 §1）。
5. **真实 nginx + 真实浏览器组合下的滚动位置行为未测**：浏览器前进后退按 URL 还原公司，但不会恢复该公司上次的滚动位置（design 明确不要求）。

## 7. 未触碰范围（确认无越界改动）

- 未改 `nginx/web.conf`、未改 `basePath`、未改 `backend/`、未改 `apps/dividend/src/components/ScreeningTab.tsx`。
- 未新增 npm 依赖（`react-markdown` / `remark-gfm` / `remark-breaks` 沿用既有；未引入 `rehype-raw`）。
- 未提交、未推送、未部署；`.trellis/` 下其他任务目录未改动。

## 8. 清理

实现过程中产生的调试探针文件 `apps/dividend/e2e/__tmp-probe.spec.ts`（未被任何用例引用）已删除，避免污染全量 E2E 套件。删除后全量 `npx playwright test` 结果见 §1。
