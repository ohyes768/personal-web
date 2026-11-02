# Implement — 采集任务弹框信息精简改造

## Preconditions

- [ ] 工作区干净：`git status` 无非本任务改动（当前有 5 个 dirty 路径，均为其他任务的，勿动）
- [ ] 基线测试通过：`cd apps/housing-map && node --test tests/directory-flow.test.cjs` → 17/17
- [ ] 后端在跑：`backend/housing-map` 端口 8096；前端 3007（复用已有实例，不另起）

## Step 1 — 新增纯函数模块 `src/lib/collection-tasks.ts`

**文件**：`apps/housing-map/src/lib/collection-tasks.ts`（新建）

导出：
- `type BadgeTone = 'idle' | 'running' | 'ok' | 'warn' | 'failed'`
- `type Metric = { label: string; value: number }`
- `taskBadge(phase, opts?)` → `{ tone, label }`
- `filterNonZero(metrics)` → 只留 `value !== 0` 且非 null/undefined
- `relativeTime(iso, now?)` → 中文相对时间；非法输入返回 `null`

设计细节见 `design.md` 的 Contracts 段。`relativeTime` 的 `now` 参数用于测试注入，生产调用不传。

**验证**：Step 2 之后由 `tests/collection-tasks.test.cjs` 覆盖。

## Step 2 — 新增纯函数测试 `tests/collection-tasks.test.cjs`

**文件**：`apps/housing-map/tests/collection-tasks.test.cjs`（新建）

沿用 `tests/rental-dashboard.test.cjs` 的 require 写法（`.ts` 用 `require.extensions` 挂 `ts.transpileModule`）。

覆盖：
- `taskBadge`：running/crawling/publishing/checking_sources/cancelling → running；succeeded/done → ok；partial_failed/cooling_down/budget_exhausted → warn；failed/error → failed；cancelled → idle + `已取消`；interrupted → idle + `已中断`；idle → idle + `尚未采集`；`idleLabel` 覆盖；未知 phase → idle + 原串
- `filterNonZero`：0 / undefined / null 剔除；正负数保留；空数组
- `relativeTime`：59s → `刚刚`；60s → `1 分钟前`；59min → `59 分钟前`；60min → `1 小时前`；23h → `23 小时前`；24h → `1 天前`；6d → `6 天前`；7d → `1 周前`；29d → `4 周前`；30d → `1 个月前`；364d → `11 个月前`；365d → `1 年前`；非法串 → `null`；`null`/`undefined` → `null`

**验证**：`node --test tests/collection-tasks.test.cjs` → 全绿

## Step 3 — 改 `DirectoryFlowWorkspace.tsx` 的 `renderTask`

**文件**：`apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx`

3.1 在 `tasks` 数组（`:73-80`）为每个任务补 `tip`（悬浮摘要一句）与 `detail`（说明正文分段）字段。pipeline 变体的说明差异沿用 `visibleTasks`（`:87-92`）的覆盖模式。

3.2 `CollectionControls` 增加 `useState<Record<string, boolean>>` 记录展开态（key = task id），`?` 按钮 `onClick` 翻转。

3.3 `renderTask`（`:152-217`）重写为：
- 头部 grid：状态点 / 任务名 / `?` 按钮 / 徽标 / 指标 / 按钮组
- 徽标文案 = `taskBadge(job?.phase, { idleLabel })` + 进度后缀（`· 120/120`）
- 指标 = 各任务「本轮产出」非零项，走 `filterNonZero`
- 说明面板（展开时渲染）：范围说明 + 全量/继续差异 + 明细（非零过滤）
- 移除原 `:185-192`（rentalMatch/amap 的重复 sub 行）、`:196-197`（association/resolutions 明细行）、`:203`（rent 续采集说明）、`:205`（rentalRefreshDiagnostics）、`:206-207`（skipped_by_state）—— 其信息分别归入说明区或徽标区
- **保留**：`:193-195` 错误行、`:198-199` position_followup、`:200-201` 证据 `<details>`、`:208-215` 三个 `<details>` 折叠块

3.4 按钮计数格式：新增 `continueLabel(base, count)`（`:174/177/180/182` 使用）。`count > 0` → `（N）`；`count === 0` 或 `null` → 无括号。禁用条件不变。

3.5 `lastRun`（`:159`）改为指标区一项：`上次结束 3 周前`，`title` 带绝对时刻（北京时间）。移除 hint 句尾拼接。

3.6 「租金流程」组头文案（`:72`）改为「先匹配来源，再更新租金；两步互斥。」

**验证**：Step 4 同步测试后 `node --test tests/directory-flow.test.cjs` 全绿。

## Step 4 — 同步 `tests/directory-flow.test.cjs`

**文件**：`apps/housing-map/tests/directory-flow.test.cjs`

按 `design.md` 的「现有测试同步」表逐条改。原则：**断言信息存在且语义正确，不绑位置**。

重点用例：
- `:113` `继续采集（7）` → 保留（数量 > 0 保留括号）
- `:115` `待采集 7 个小区` → 说明区文案，改为匹配新文案
- `:141-145` resolutions 明细 → 改匹配说明区内的文本
- `:192` `部分完成.*已处理 2 / 5` → 徽标文案变为 `部分完成`，进度后缀另计，改断言
- `:198` `仅已收录住宅` → 说明区文本
- `:206` `查询失败 1 · 未查完 5 · 未查询 99` → 说明区明细，零值过滤后仍是这 3 项
- `:229` `<details>` 数量 === 3 → **保持不变**（说明区不用 details），此条不需改

新增断言：
- 说明区存在且 `aria-expanded` 正确
- 零值指标不渲染（如 `已检查 0` 场景下 HTML 里不出现 `已检查 0`）

**验证**：`node --test tests/directory-flow.test.cjs` 全绿

## Step 5 — 改 CSS `src/app/globals.css`

**文件**：`apps/housing-map/src/app/globals.css`

改写 `.directory-task-*` 规则组（`:1376-1405`）：
- `.directory-task-row-head` 改 grid，列序 = 状态点 / 任务名 / ? / 徽标 / 指标 / 按钮
- 新增 `.directory-task-badge`（药丸，`data-tone` 决定底色/字色）
- 新增 `.directory-task-metrics`（flex，灰字 12px，数字加粗 + tabular-nums）
- 新增 `.directory-task-help`（16px 圆圈 `?`）
- 新增 `.directory-task-detail`（左侧竖线面板）
- 删掉不再使用的 `.directory-task-hint` / `.directory-task-sub` / `.directory-task-lastrun`（确认无其他引用后再删）

色调复用 `--accent-warm` / `--text-muted` / `#A97B1F` / `#a74325` / `#2E8B44`，不新增 `@theme` token。

**验证**：`pnpm lint` 通过。

## Step 6 — 浏览器验证

前端 3007 + 后端 8096 已在本机运行，复用即可。

检查项：
1. 收录审核 → 齿轮「收录采集」→ 弹框：3 任务各 1 行，高度在 1 屏内
2. 维护 → 齿轮「维护采集」→ 弹框：租金分组 2 任务 + 法拍 1 行
3. `?` 悬浮出 tooltip；点击展开说明面板，再点收起
4. 触发一次「更新全部资料」看运行中徽标（暖橘 + 进度）
5. 390px 宽度下任务行换行不破版（指标区可换行，按钮组不溢出）
6. 对照 `docs/prototypes/housing-map-collection-tasks.html` 原型

**验证**：截图确认。

## Step 7 — 全量检查与收尾

```bash
cd apps/housing-map
node --test tests/*.test.cjs     # 全套前端测试
pnpm lint
```

再跑一次 impeccable 检测器（见下）：

```bash
"C:/Users/Administrator/.claude/skills/impeccable/scripts/impeccable.cmd" detect --json apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx apps/housing-map/src/app/globals.css
```

**验证**：测试全绿、lint 无错、检测器无高危项。

## Step 8 — 提交

按仓库惯例：单仓库 `git add` + `commit` + `push origin master`。

提交前确认：
- 新增文件 `src/lib/collection-tasks.ts`、`tests/collection-tasks.test.cjs` **与引用方一起提交**（历史教训：实现 agent 抽组件时只 commit 引用方，新文件漏提交导致 build 炸）
- 不夹带其他任务的 dirty 路径（`.trellis/spec/...`、`docs/index-trends-weekly-design.md` 等）

## Rollback points

| Step | 回滚方式 |
|------|---------|
| 1-2 | 删除 `src/lib/collection-tasks.ts` + `tests/collection-tasks.test.cjs` |
| 3-4 | `git checkout` 这两个文件 |
| 5 | `git checkout apps/housing-map/src/app/globals.css` |
| 6-8 | 无提交则直接改回；有提交则 `git revert` |

## Risk register

| 风险 | 概率 | 缓解 |
|------|------|------|
| 按钮禁用条件在重写中走样，任务被误触发 | 中 | 现有 6 个任务的 onClick/禁用条件已被测试覆盖，同步时逐条对照 |
| 同步测试时改松断言，掩盖真实回归 | 中 | 同步原则：保留原语义（信息必须存在），只换载体；不删断言只改匹配对象 |
| pipeline 模式下说明文案未跟随 `visibleTasks` 覆盖 | 低 | Step 3.1 复用 `visibleTasks` 同一覆盖机制，Step 6 验证 pipeline 变体 |
| 390px 下按钮组溢出 | 低 | CSS 用 grid + `flex-wrap`，Step 6 实机验证 |
