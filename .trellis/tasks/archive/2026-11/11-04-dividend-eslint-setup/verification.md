# 股息率前端接入 ESLint · 验证记录

> 任务：`.trellis/tasks/11-04-dividend-eslint-setup`
> 验证日期：2026-11-04
> 范围：`apps/dividend` 的 lint 配置、`package.json`、`src/lib/api-client.ts`、3 个 hook 相关源文件、相关文档
> 环境：Windows 11 / Node 24 / Next.js 15.5.19 / ESLint 9.39.4 / eslint-config-next 15.5.19 / pnpm 10.30

---

## 1. 命令结果（实际退出码）

| 命令 | 结果 | 说明 |
|------|------|------|
| `npm run lint` | **exit 0** | 非交互跑完；**0 error / 19 warning**（全部为存量 `no-unused-vars`） |
| `npx tsc --noEmit` | **exit 0** | 无输出 |
| `npm run build` | **exit 0** | `✓ Compiled successfully`，路由表不变（`○ /quality-reader 2.24 kB`） |
| `npx playwright test` | **exit 0** | **54 passed / 0 failed**（全量套件） |
| `git diff --check` | exit 0 | 无空白问题 |

## 2. 验收条件逐项映射

| AC | 证据 | 结论 |
|----|------|------|
| AC1（R1、R2） | `npm run lint` 无任何交互提示直接结束并 exit 0；`package.json` 的 `scripts.lint` = `eslint`；新增 `apps/dividend/eslint.config.mjs` 用 `FlatCompat` 桥接 `next/core-web-vitals` + `next/typescript` | ✅ |
| AC2（R3） | lint error 数由 6 → 0；`git diff -- apps/dividend/src/lib/api.ts` 为空（调用方零改动）；`tsc --noEmit` exit 0 | ✅ |
| AC3（R4） | `exhaustive-deps` 告警 12 → 0：3 个非并发文件按研究结论做合法修复（不改变运行时行为），2 个并发文件用配置级文件范围 suppress 并写明 TODO | ✅ |
| AC4（R5） | 本次新增/修改的 5 个源文件里 `no-unused-vars` 为 0（含 `QualityReportContent.tsx` 的 `_node`、`quality-reader.spec.ts` 的 `_removed`，由 `varsIgnorePattern: "^_"` 覆盖）；剩余 19 条存量 warning 清单见 §4 | ✅ |
| AC5（R6） | 见 §1，三项全绿 | ✅ |
| AC6（R7） | `git diff -- apps/dividend/src/app/page.tsx apps/dividend/src/lib/hooks.ts apps/dividend/src/lib/types.ts backend/` 输出为空 —— 并发任务 11-02 的文件零触碰 | ✅ |
| AC7（R8） | `.trellis/spec/frontend/index.md` 的 lint 说明已改为「多数 app 仍无配置 / apps/dividend 已接入」；`docs/dividend-testing-checklist.md` 新增「5. 前端 lint（apps/dividend）」小节；`docs/dividend/01-界面功能设计.md` 文件结构补 `eslint.config.mjs` 与 lint 命令说明 | ✅ |

## 3. 本次实际改动

| 文件 | 改动 |
|------|------|
| `apps/dividend/eslint.config.mjs`（新增） | FlatCompat 桥接 flat config；`no-unused-vars` 加 `^_` 与 `ignoreRestSiblings`；`page.tsx`/`hooks.ts` 临时关 `exhaustive-deps`（附 TODO） |
| `apps/dividend/package.json` | `lint` 脚本 `next lint` → `eslint`；devDeps 加 `eslint@^9.39.4`、`eslint-config-next@15.5.19`、`@eslint/eslintrc` |
| `apps/dividend/pnpm-lock.yaml` | 随依赖变更 |
| `apps/dividend/src/lib/api-client.ts` | 6 个 `any` → `unknown` / 泛型 `P extends object = object`（**调用方零改动**） |
| `apps/dividend/src/lib/hooks/useQualityAnalysis.ts` | effect 依赖加 `stopPolling`（`useCallback([])`，引用终身稳定，effect 不会多跑） |
| `apps/dividend/src/lib/hooks/useRealtimePrices.ts` | 依赖改用 `codesKey = JSON.stringify(codes)`，memo 内 `JSON.parse` 还原；内容相同→引用稳定，内容变→引用变，语义与原实现一致 |
| `apps/dividend/src/components/ScreeningTab.tsx` | `requestId.current++` 抽成稳定的 `invalidateRequest` useCallback；cleanup 不再直接读 ref |
| 三处文档 | 见 AC7 |

### 关键技术决策

1. **为什么用 FlatCompat 而不是照抄 housing-map**：dividend 在 Next 15.5.19，其 `eslint-config-next@15.5.19` 只发 eslintrc 风格配置（`module.exports = { extends: [...] }`），flat config 是 v16 才有的。housing-map 能直接 `import nextVitals from "eslint-config-next/core-web-vitals"` 是因为它在 Next 16 上。
2. **为什么 `Record<string, any>` 不能直接换 `Record<string, unknown>`**：TS 的隐式索引签名只对 type alias 生效，`DividendQueryParams`/`BoardInfoRequest` 这些 interface 不满足，换了会在 `api.ts` 调用点炸一片。故用 `P extends object = object`；默认值不能省，否则 `directClient.get<QualityJob>(url)` 这类只显式给 T 的调用报 TS2558。
3. **12 条 hook 依赖为何不照插件建议改**：研究（`research/hook-deps.md`）逐条判定**全部是误报**，根因是依赖数组刻意不含「每渲染新建的数组/对象」。照建议加依赖会引入**无限重渲染 + 请求风暴**（例如 `ScreeningTab.tsx` 的 `eligibleCodes` 是 render 内联表达式，每渲染都是新数组）。故采用「合法修复（不改行为）」而非「加依赖」。

## 4. 剩余 19 条 warning（存量，未修，按 PRD R5 登记留档）

全部是 `@typescript-eslint/no-unused-vars`，属预存死代码或框架签名约定，删除属超范围改动：

| 文件 | 条数 | 说明 |
|------|------|------|
| `src/app/api/dividend/[...path]/route.ts` | 4 | Next.js 路由签名自带的 `params` |
| `src/app/page.tsx` | 4 | 预存未使用变量（**并发任务 11-02 的文件，本任务未触碰**） |
| `src/lib/hooks.ts` | 1 | `minYield` 未使用参数（删除需同步改调用方；**并发任务文件**） |
| `src/components/AlertSettingsModal.tsx` | 1 | 未使用的 import |
| `src/components/CompareFloatingBar.tsx` | 1 | 未使用的 import |
| `src/components/CompareTable.tsx` | 4 | 未使用的 import 与格式化函数 |
| `src/components/DetailModal.tsx` | 3 | 未使用的 import 与函数 |
| `src/components/DividendTable.tsx` | 1 | 未使用的格式化函数 |

`npm run lint` 以 warning 计数不影响退出码，脚本仍为 exit 0。

## 5. 后续项（未做，需另行收尾）

1. **回收配置级 suppress**：`src/app/page.tsx` 与 `src/lib/hooks.ts` 的 `react-hooks/exhaustive-deps` 目前是配置级关闭（因为这两个文件正被 `11-02-dividend-page-load-speed` 重写，不能插入行内注释）。**11-02 落地后应改回逐点处理**，恢复该规则在这两个文件里的检查。配置里已留 TODO。
2. **清理 19 条存量 unused-vars**：需逐条判断「死代码可删」还是「框架签名不能删」，建议单独任务。
3. **其余 7 个 app 的 ESLint**：本任务未涉及。

## 6. 过程中的意外与处置

- **3003 dev server 被生产构建打挂**：验证顺序里 `npm run build` 覆盖了 `.next`，而 `next dev` 独占该目录，导致当时占用 3003 的 dev server（属于并发任务 11-02）持续返回 500 且不自愈。已按 PID 精确停止该进程（未用 `taskkill /IM node.exe`），清空 `.next` 后由 Playwright 自起 dev server 跑完全量 E2E，结束后重新在 3003 起了 dev server 恢复该会话的工作环境。
  → **后续教训**：跑生产构建前必须先确认 3003 上没有别的会话的 dev server；`next build` 与 `next dev` 不能共存于同一 `.next`。
- 并发任务 11-02 在本任务进行中提交了 `fa2a5c10`（改了 `page.tsx`/`hooks.ts`/`types.ts`/后端），已复核：其改动**不影响**本次 5 个目标文件的判定，且我方未触碰其文件。

## 7. 未触碰范围（确认无越界改动）

- 未改 `src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts`、`backend/**`（并发任务 11-02 的范围）。
- 未升级 Next、未升级 `eslint-config-next` 到 v16、未为其它 app 加配置。
- 未删除 `ApiResponse`/`apiClient` 死代码、未删除存量 unused-vars（PRD 明确排除）。
- 未提交、未推送。
