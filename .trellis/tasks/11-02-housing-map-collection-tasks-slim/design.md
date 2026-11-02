# Design — 采集任务弹框信息精简改造

## Architecture & boundaries

改动全部落在前端 `apps/housing-map`，两层：

```
apps/housing-map/src/lib/collection-tasks.ts          ← 新增：纯展示逻辑，无 React
apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx  ← 改：renderTask 重写
apps/housing-map/src/app/globals.css                   ← 改：.directory-task-* 规则组
apps/housing-map/tests/collection-tasks.test.cjs        ← 新增：纯函数测试
apps/housing-map/tests/directory-flow.test.cjs          ← 改：同步现有断言
```

边界：
- **不改后端**。所有数据来自现有 `Job` 类型字段。
- **不改 `tasks` 数组**（`DirectoryFlowWorkspace.tsx:73-80`）的 id / path / body / mode。
- **不改按钮的 onClick 与禁用条件**。只改呈现。
- 不碰 `CollectionTasksButton`（弹框外的齿轮入口）。

## 为什么拆出 `src/lib/collection-tasks.ts`

三件事需要纯函数 + 独立测试覆盖：

1. **phase → 徽标归并**（tone + 文案）：11 种 phase 的映射表，纯查表
2. **指标零值过滤**：`[{label, value}]` → 只留 value !== 0 的项
3. **相对时间**：`finished_at` ISO 串 → 「3 周前」

这些都不依赖 React，放 `src/lib/` 便于 node:test 直接 require（`rental-dashboard.ts` 同款模式，见 `tests/` 下 `rental-dashboard.test.cjs` 的用法）。

## Data flow

```
Job (后端) ──► collection-tasks.ts 纯函数 ──► renderTask JSX
                     │
                     ├─ taskBadge(job, t)      → { tone, label, progress }
                     ├─ filterNonZero(pairs)   → 标题行指标 / 明细指标
                     └─ relativeTime(finished_at) → 「3 周前」
```

不新增后端字段，不改 `normalizeCollectionJob`（`:62-66`）。

## Contracts

### `collection-tasks.ts` 导出

```ts
export type BadgeTone = 'idle' | 'running' | 'ok' | 'warn' | 'failed';

export type Metric = { label: string; value: number };

/** phase → 徽标。未识别 phase 落到 idle，tone 与文案都在这里定死。 */
export function taskBadge(
  phase: string | undefined,
  opts?: { progress?: string; idleLabel?: string },
): { tone: BadgeTone; label: string };

/** 零值过滤。value 为 0 / undefined / null 一律剔除。 */
export function filterNonZero(metrics: Metric[]): Metric[];

/** ISO 时间 → 相对时间。非法值返回 null。 */
export function relativeTime(iso: string | undefined | null, now?: number): string | null;
```

`taskBadge` 的 phase 映射表（design 决策，prd R2）：

| phase | tone | label |
|-------|------|-------|
| idle | idle | `尚未采集`（rentalMatch 传 `idleLabel: '尚未匹配'`） |
| running / crawling / publishing / checking_sources / cancelling | running | `运行中` |
| succeeded / done | ok | `已完成` |
| partial_failed / cooling_down / budget_exhausted | warn | `部分完成` |
| failed / error | failed | `失败` |
| cancelled / interrupted | idle | `已取消` / `已中断` |

未列出的 phase → `idle` tone + 原 phase 字符串（保留信息，不吞掉后端新增状态）。

进度后缀（如 `· 120/120`、`· 40/61`）由调用方拼，因为 `processed`/`total` 的组合每个任务不同。

`relativeTime` 阈值：
- < 60 秒 → `刚刚`
- < 60 分 → `N 分钟前`
- < 24 小时 → `N 小时前`
- < 30 天 → `N 天前`
- < 365 天 → `N 周前`（7 天以上才升级到周；30 天以上升级到月）
- 更久 → `N 个月前` / `N 年前`

实现口径：先算「天」，1~6 天用天，7~29 天用周，30~364 天用月，365 天以上用年。

### `renderTask` 新结构

```tsx
<div className="directory-task-row" data-state={state}>
  <div className="directory-task-row-head">
    <span className="directory-task-dot" aria-hidden="true" />
    <strong>{t.label}</strong>
    <button className="directory-task-help" type="button"
      aria-expanded={open} aria-label={`${t.label} 说明`} title={t.tip}
      onClick={() => toggle(t.id)}>?</button>
    <span className={`directory-task-badge`} data-tone={badge.tone}>{badge.label}</span>
    <div className="directory-task-metrics">{/* 非零指标 */}</div>
    <div className="directory-task-actions">{/* 原有按钮 */}</div>
  </div>
  {open && <div className="directory-task-detail">{/* 说明 + 明细 */}</div>}
  {problem && <p className="directory-task-line" data-state={state}><span role="alert">{problem}</span></p>}
  {job?.evidence_issues?.length > 0 && <details …>}   {/* 原有折叠块不动 */}
  …
</div>
```

关键点：
- **网格布局**：`.directory-task-row-head` 用 grid，列序 = 状态点 / 任务名 / ? / 徽标 / 指标 / 按钮。指标区 `flex: 1`，按钮右对齐。
- **展开态存 React state**：`useState<Record<string, boolean>>({})`，key 是 task id。`?` 按钮 `aria-expanded` 绑定。
- **不用 `<details>`**：现有测试断言 `<details>` 元素数量恰为 3（`directory-flow.test.cjs:229`），多一个就断。用 div + state 避开。
- **不用自定义 tooltip**：`?` 用原生 `title` 属性。项目 community 组件既有约定（21 处 `title=`），自定义 tooltip 只在地图图层。
- **明细零值过滤**：说明面板里的明细同样走 `filterNonZero`。

### 按钮计数格式

```ts
function continueLabel(base: string, count: number | null | undefined): string {
  return count == null ? base : `${base}（${count}）`;
}
```

- `count == null`（字段缺失）→ `继续采集`，按钮禁用
- `count === 0` → `继续采集（0）`，按钮禁用 —— **保留现有测试断言的 `（0）` 形态**？

查证：现有测试 `directory-flow.test.cjs:113-124` 断言的是 `继续采集（7）`（数量已知时），以及 `rent: { continuable: 0 }` 等场景下 `disabled === true`，**没有断言 `（0）` 的文案**。所以 0 值可以不显示括号。prd R5 写的是「数量未知或为 0 时不显示括号」。

→ `count === 0` → `继续采集`（无括号），禁用。
→ `count > 0` → `继续采集（N）`。
→ `count == null` → `继续采集`，禁用。

现有测试 `:180-187` 断言 `继续采集（5）`/`继续匹配（13）`（数量 > 0）→ 保持通过。

### 时间

`lastRun`（`:159`）从 hint 句尾移出，改为指标区一项：`上次结束 3 周前`。

`finished_at` 是 UTC ISO 串（后端给的是 `...Z` 或带时区的串）。`relativeTime` 用 `new Date(iso).getTime()` 解析后与 `Date.now()` 比较，自动处理时区，用户看到的是「3 周前」而非绝对时刻。

**口径诚实性**：用户偏好明确「数字口径零容忍」。相对时间不精确（3 周前可能是 21~27 天前），所以**悬浮提示仍给绝对时刻**：`title` 上带 `2026-10-12 08:01`（北京时间）。这样既简洁又不丢口径。

### CSS

新增/改写的规则（替换现有 `.directory-task-*` 组，`globals.css:1376-1405`）：

```css
.directory-task-row-head {
  display: grid;
  grid-template-columns: 10px auto auto auto 1fr auto;
  align-items: center;
  gap: 10px;
}
.directory-task-badge { /* 药丸，data-tone 决定底色/字色 */ }
.directory-task-metrics { display: flex; flex-wrap: wrap; gap: 4px 12px; color: var(--text-muted); font-size: 12px; }
.directory-task-help { /* 16px 圆圈 ? */ }
.directory-task-detail { margin-left: 22px; padding: 10px 12px; border-left: 2px solid var(--border); }
```

色调沿用项目既有 token：`--accent-warm`（运行中）、`--text-muted`（idle）、`#A97B1F`（warn）、`#a74325`（failed）、`#2E8B44`（ok）。

不新增 `@theme` token —— 这些是弹框内的局部状态色，走 `--accent-warm` 等既有变量 + 少量状态色，与 `.directory-task-line[data-state="failed"]`（`:1399`）的既有做法一致。

### 现有测试同步

`tests/directory-flow.test.cjs` 中会被新结构影响的断言：

| 断言 | 现状 | 改造后 |
|------|------|--------|
| `:113` `/继续采集（7）/` | 保留 | 通过（数量 > 0 保留括号） |
| `:115` `/待采集 7 个小区/` | 副标题文案 | 移入说明区，文案可能调整 → 需同步 |
| `:129-133` 租金同组 | 保留 | 通过 |
| `:141-145` `/待地点匹配 3/` 等 | resolutions 明细行 | 移入说明区 → 需同步 |
| `:192` `/部分完成.*已处理 2 \/ 5/` | 状态小字 | 变徽标文案 → 需同步 |
| `:198` `/仅已收录住宅/` | hint 正文 | 移入说明区（仍在 DOM 内）→ 需同步文本 |
| `:206` `/查询失败 1 · 未查完 5 · 未查询 99/` | association 明细 | 移入说明区 + 零值过滤 → 需同步 |
| `:229` `<details>` 数量 === 3 | 保持 | 通过（说明区不用 details） |

**同步原则**：断言的是「信息存在且语义正确」，不是「出现在第几行」。新结构下同样的信息仍在 DOM 里，只是位置和载体变了，断言改为匹配新载体。

### 新增测试 `tests/collection-tasks.test.cjs`

覆盖：
- `taskBadge`：11 种 phase → tone/label；未知 phase → idle + 原串；`idleLabel` 覆盖
- `filterNonZero`：0 / undefined / null 剔除，负数与正数保留
- `relativeTime`：各阈值边界（59 秒 / 60 秒 / 59 分 / 60 分 / 23 小时 / 24 小时 / 6 天 / 7 天 / 29 天 / 30 天 / 364 天 / 365 天）、非法输入返回 null

## Trade-offs

| 决策 | 选择 | 代价 / 理由 |
|------|------|-------------|
| 说明区实现 | React state + `?` 按钮 | 多一份状态；但避开了 `<details>` 计数断裂，且 `aria-expanded` 比 `<summary>` 语义更清楚 |
| 悬浮提示 | 原生 `title` | 样式不可控、延迟约 1 秒；但与项目既有 21 处一致，且零额外 DOM。地图图层那套自定义 tooltip 是绝对定位 + 防裁切，搬过来成本高于收益 |
| 相对时间 | 相对时间 + `title` 给绝对时刻 | 两处时间信息；换取可读性且不丢口径 |
| 明细数字位置 | 说明区内 | 总量类数字要点两次才看到。取舍是标题行留给「本轮产出」，语义更清晰 |
| 明细是否进标题行 | 否 | 曾考虑把「已关联 38」也放标题行，但它与「已检查 45」同义不同量级，会让人误读为两笔账 |

## Rollback

改动集中在 3 个文件，回滚即 `git checkout` 这几个路径。`src/lib/collection-tasks.ts` 是新增文件，删除即回滚。无数据迁移、无后端变更、无配置开关。

风险点：
- 按钮禁用条件若在重写中走样，会导致任务被误触发。缓解：`directory-flow.test.cjs` 已覆盖 6 个任务的 onClick 与禁用条件，同步更新时逐条对照。
- 现有测试断言的文案若改错含义，会掩盖真实回归。缓解：同步时保留原断言语义（信息必须存在），只换载体。

## Operational notes

- 无新依赖、无新环境变量、无后端部署
- 本地验证：`cd apps/housing-map && pnpm dev`（端口 3007）+ `backend/housing-map`（端口 8096）
- 浏览器验证：桌面 1440px + 390px 两个宽度，两个弹框各看空闲态与有数据态
