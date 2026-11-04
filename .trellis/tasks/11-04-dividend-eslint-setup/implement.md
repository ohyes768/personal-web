# 股息率前端接入 ESLint · Implementation Plan

**Goal:** 让 `apps/dividend` 的 `npm run lint` 真正可用（非交互、exit 0），并修掉全部 error。

**Architecture:** flat config + `FlatCompat` 桥接 `eslint-config-next@15.5.19`（Next 15 只发 eslintrc 风格配置）；lint 脚本从 `next lint` 换成 `eslint` CLI；6 个 `no-explicit-any` 用「泛型 `P extends object = object` + `data?: unknown`」在单文件内修掉，调用方零改动。

**Tech Stack:** 现有 Next.js 15.5.19 / React 19 / TypeScript / pnpm；新增 devDependency `eslint@^9`、`eslint-config-next@15.5.19`、`@eslint/eslintrc`。

**并发约束（硬边界）：** `11-02-dividend-page-load-speed` 正在改 `src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts` 与 `backend/**`。本任务**一律不写**这三个 dividend 文件与 `backend/**`。每阶段结束与提交前都要 `git diff` 复核。

## 0. 实现前检查

- [ ] 读同目录 `prd.md`、`design.md`、`research/hook-deps.md`；确认用户未调整范围。
- [ ] `python .trellis/scripts/get_context.py` 核对 git 状态；记录 11-02 当前已改动的文件清单（作为隔离基线）。
- [ ] 读 `.trellis/spec/guides/code-reuse-thinking-guide.md` 与 `docs/dividend-testing-checklist.md`。
- [ ] 运行 `python .trellis/scripts/task.py start .trellis/tasks/11-04-dividend-eslint-setup` 后再改产品代码；任务为 planning 时不得改。
- [ ] 确认 3003 无其它 dev server 实例占用；lint 与 build 不并行（共享 `.next`）。

## 1. 接入 ESLint 配置（AC1、R1、R2）

文件：新增 `apps/dividend/eslint.config.mjs`；修改 `apps/dividend/package.json`、`pnpm-lock.yaml`。

- [ ] `pnpm add -D eslint@^9 eslint-config-next@15.5.19 @eslint/eslintrc`
- [ ] 写 `eslint.config.mjs`：`FlatCompat` 桥接 `next/core-web-vitals` + `next/typescript`，`globalIgnores` 掉 `.next/out/build/next-env.d.ts/test-results/playwright-report`
- [ ] 加 `@typescript-eslint/no-unused-vars` 的 `argsIgnorePattern`/`varsIgnorePattern` = `^_`、`ignoreRestSiblings`（见 design.md「规则调整」）
- [ ] 加文件范围规则覆盖：`src/app/page.tsx`、`src/lib/hooks.ts` 关 `react-hooks/exhaustive-deps`，并写注释指向 `research/hook-deps.md` 与「11-02 落地后回收」
- [ ] `package.json` 的 `scripts.lint` 改为 `eslint`
- [ ] 验证：`npm run lint` 无交互直接结束；此时应有 6 error + 少量 warning（error 属预期，下一阶段修）

## 2. 修掉 6 个 error（AC2、R3）

文件：`apps/dividend/src/lib/api-client.ts`。

- [ ] `ApiResponse<T = any>` → `ApiResponse<T = unknown>`
- [ ] `get<T>(endpoint, params?: Record<string, any>)` → `get<T, P extends object = object>(endpoint, params?: P)`
- [ ] `delete<T>(endpoint, params?: Record<string, any>)` → 同上
- [ ] `post/put/patch<T>(endpoint, data?: any)` → `data?: unknown`
- [ ] **关键**：`P extends object = object` 的默认值不能省（否则 `directClient.get<QualityJob>(url)` 报 TS2558）；`Record<string, unknown>` 不能用（interface 无隐式索引签名）
- [ ] 验证：`npx tsc --noEmit` exit 0；`git diff -- apps/dividend/src/lib/api.ts` 为空（调用方零改动）；`npx eslint .` 的 error 数归零

## 3. 处理 3 个文件的 exhaustive-deps（AC3、R4 的 A 类）

文件：`src/lib/hooks/useQualityAnalysis.ts`、`src/lib/hooks/useRealtimePrices.ts`、`src/components/ScreeningTab.tsx`。

- [ ] `useQualityAnalysis.ts`：`stopPolling` 加进 useEffect 依赖（引用终身稳定，effect 不会多跑）
- [ ] `useRealtimePrices.ts`：抽 `codesKey = JSON.stringify(codes)`，memo 依赖改用 `codesKey`
- [ ] `ScreeningTab.tsx`：`requestId.current++` 抽成稳定 `useCallback` 包装器
- [ ] 每处改完跑 `npx tsc --noEmit`；确认 `npx eslint .` 的 exhaustive-deps 只剩 `page.tsx`/`hooks.ts` 两条路径（已被配置级覆盖）
- [ ] 回归：这三个文件涉及选股查询与现价轮询，改完必须跑全量 E2E

## 4. 文档同步（AC7、R8）

- [ ] `.trellis/spec/frontend/index.md`：把「next lint currently needs initial ESLint configuration」改成现状描述（flat config + `eslint` CLI 已就位；`next lint` 已废弃）
- [ ] `docs/dividend-testing-checklist.md`：在「一、每次改动都必须检查」补 lint 条目（`npm run lint` 非交互、exit 0、error 为 0；存量 unused-vars warning 属已知留档）
- [ ] `docs/dividend/01-界面功能设计.md`：文件结构里补 `eslint.config.mjs` 与 lint 命令

## 5. 验证（AC1–AC6）

依次在 `apps/dividend` 执行（build 与 E2E 不并行）：

```powershell
npm run lint            # 期望 exit 0，非交互
npx tsc --noEmit        # 期望 exit 0
npm run build           # 期望 exit 0
npx playwright test     # 期望 54 passed / 0 failed
```

- [ ] 记录 lint 的 error/warning 精确数量与剩余 warning 清单（文件 + 行号 + 规则名）到 `verification.md`
- [ ] `git diff --check`；`git status` 只含授权范围
- [ ] 复核 `git diff` 不含 `src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts`、`backend/**`

## 6. 交接

- [ ] 写 `verification.md`：逐项映射 AC1–AC7，实际命令退出码、lint 数量明细、剩余 warning 清单、11-02 冲突隔离证据
- [ ] 登记后续项：11-02 落地后把两个文件的配置级 suppress 改回逐点处理 + 清理那 5 个存量 unused-vars
- [ ] 提交前向用户确认提交范围；不自动推送

## 风险检查与回滚点

1. **阶段 1 后 `npm run lint` 仍交互** → 检查是否仍在用 `next lint`，以及 `eslint.config.mjs` 是否被 ESLint 9 识别（文件名与位置须在包根）。
2. **阶段 2 后 tsc 报 TS2558/类型不兼容** → 检查 `P extends object = object` 的默认值是否被误删，或误把 `Record<string, unknown>` 用在了 interface 参数上。
3. **阶段 3 后 E2E 出现选股查询/现价轮询回归** → 立刻回滚该文件的改动，改用定向 `eslint-disable` + 理由注释替代合法修复。
4. **与 11-02 撞车** → 发现 `git diff` 出现自己没写过的 dividend 文件改动时停下并报告，不自行 `git checkout` 覆盖。

## 规划自查

- AC1→阶段1，AC2→阶段2，AC3→阶段1+3，AC4→阶段1+5，AC5→阶段5，AC6→阶段0/5，AC7→阶段4。
- R7 的隔离要求已落到 0/2/3/5/6 各阶段的检查项。
- 本轮尚未执行任何命令，除 prd/design/implement 外的结论均来自实测（安装试跑 + 研究代理沙箱验证），不是推测。
