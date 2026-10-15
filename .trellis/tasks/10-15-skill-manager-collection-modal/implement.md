# Implement — Skill Manager GitHub 合集 modal

## 1. 任务范围

只动以下两个前端文件：

| 文件 | 操作 |
|---|---|
| `apps/skill-manager/src/components/CollectionDialog.tsx` | 新增（modal 组件） |
| `apps/skill-manager/src/components/CollectionDialog.test.ts` | 新增（vitest 单测） |
| `apps/skill-manager/src/components/SkillPool.tsx` | 改：合集由 `<details>` 改为入口卡 + 渲染 `CollectionDialog` |

**不动**：`SourceWorkspace.tsx`（回调 props 不变）/ `lib/collections.ts` / `lib/types.ts` / 后端 / API 契约。

## 2. 执行清单（有序）

### Step 1 — 新增 `CollectionDialog.tsx`

- 创建文件 `apps/skill-manager/src/components/CollectionDialog.tsx`
- 内容按 `design.md §2 §3 §5` 实现：
  - 内部 `useState<Set<string>>` 管 `selectedIds`
  - `useEffect` 监听 Esc 键关闭
  - 背景遮罩 `<div onClick={onClose}>` + 内容 `<div onClick={stopPropagation}>`
  - 完整布局：header + toolbar + chip 摘要行 + body row list
- 类型用现有的 `SkillCollection` / `SkillCard` / `InstallTarget` / `ExportTarget` / `QueueEntry` / `TargetKey` / `ExportTargetKey`
- 复用 `InstallationBadge`（需要从 SkillPool 提取或重新 export；具体看实现）
- 复用 `CollectionIcon`（在 `@/components/icons` 已存在）
- 跑 `pnpm typecheck` 确认类型无错

### Step 2 — 新增 `CollectionDialog.test.ts`

- 创建文件 `apps/skill-manager/src/components/CollectionDialog.test.ts`
- 测试覆盖（用 `renderToStaticMarkup` 或 jsdom + react testing library）：
  - **T1**：modal 关闭时不渲染内容；`open=true` 时渲染 `[X 关闭]` 按钮 + 「合集 · N 项」徽章
  - **T2**：「全选」点击后 selectedIds 包含所有 member id；「清空选择」点击后为空
  - **T3**：「安装所选 (N)」在 N=0 时 `disabled` 属性存在
  - **T4**：「更新整个」在 `installed > 0` 时可点击；调用 `onInstallSelection(collection.members.map(s => s.id))`
  - **T5**：「下架整个」点击触发弹确认；确认后调用批量下架 on*
  - **T6**：单成员行内「安装」按钮点击 → 调用 `onToggleQueueTarget(skill.id, current)`
  - **T7**：单成员行内「下架」按钮点击 → 调用 `onUnpublish(skill.id, skill.name, [...targets])`
  - **T8**：📦/🆕/⚠ chip 仅在对应 N > 0 时渲染
  - **T9**：完成态 `✓ 12/12 已全部安装` 文本出现于 `installed === members.length`
  - **T10**：背景点击关闭（`onClose` 调用）；Esc 键关闭
- 跑 `pnpm vitest run src/components/CollectionDialog.test.ts` 全过

### Step 3 — 改 `SkillPool.tsx`

- 删除第 379-460 行的 `<details>` 合集渲染块
- 替换为入口卡：按 `design.md §4` 实现
- 在 SkillPool 内部 state 加 `const [openCollection, setOpenCollection] = useState<SkillCollection | null>(null)`
- SkillPool 末尾（`</ul>` 后）渲染 `<CollectionDialog>`，传入 `open={openCollection !== null}` + `collection={openCollection}` + `onClose={() => setOpenCollection(null)}`
- 新增 `exportCount` 计算（`design.md §4`）：遍历 collection.members 累加所有非 install target 的 active export 数
- 监听 view 变化：`useEffect(() => { setOpenCollection(null); }, [view])` （需要 page.tsx 把 view 透传进来；通过新增 prop `currentView?: ViewKey`）
- `SkillPool.test.ts` 中关于 `<details>` 的断言（如有）需更新或删除
- 跑 `pnpm typecheck` + `pnpm lint` + `pnpm vitest run` 全过

### Step 4 — 既有测试更新（如必要）

- 检查 `SkillPool.test.ts` 9 项测试是否还在新结构下通过
- 如有失败（多半是依赖 `<details>` 的断言），更新测试断言以匹配新结构（entry 卡 + modal 入口）
- 跑 `pnpm vitest run` 全过

### Step 5 — 全量验证

按顺序跑：

```bash
cd "F:/personal-projects/personal-web/apps/skill-manager"

# lint
pnpm lint

# typecheck
pnpm typecheck

# 所有测试
pnpm exec vitest run

# build（确认 Next 编译通过）
pnpm build
```

期望全部通过。如果 lint 报 `react-hooks/exhaustive-deps` 警告，按 lint 提示修。

### Step 6 — Live browser 验收

dev server 仍在 c4 tab 运行（前端 3008 + 后端 8097）：

1. 访问 `http://localhost:3008/skills?view=manage&tab=github`，截图存 `.trellis/workspace/jackson.tang/screenshots/collection-modal-grid.png`（验证主 grid 入口卡）
2. 点开 12 项合集入口卡（如果有），截图存 `collection-modal-open-12.png`
3. 点开 14 项合集入口卡（如果有），截图存 `collection-modal-open-14.png`
4. 选 3 个成员后截图存 `collection-modal-selected.png`
5. chrome-devtools mcp 工具调用；若超时则用 Playwright（如未装跳过，等用户手验）

## 3. Review gates（每步必查）

| Gate | 检查 | 通过条件 |
|---|---|---|
| **G1 类型** | `pnpm typecheck` 退出 0 | 无 TS 报错 |
| **G2 测试** | `pnpm vitest run` 全过 | 既有测试不破 + 新测试全过 |
| **G3 lint** | `pnpm lint` 退出 0 | 无 error 级别 |
| **G4 build** | `pnpm build` 退出 0（standalone trace 已知 Windows EPERM 不影响） | Next.js 编译过 |
| **G5 live** | 截图 grid + modal open + modal selected | 视觉与 design.md §5 一致 |
| **G6 回归** | modal 内「安装所选」点击 → 主 grid 卡片状态更新；modal 关闭 | 端到端流程通 |

## 4. Rollback 形状

最小破坏原则：

- **Step 1-2 完成但 Step 3 未做**：组件已存在但未挂载，零风险
- **Step 3 完成但 Step 4 失败**：`git checkout HEAD -- apps/skill-manager/src/components/SkillPool.tsx` 即可回到现状
- **完全回滚**：`git revert <commit>`（本任务改动只在 `apps/skill-manager/src/components/{CollectionDialog.tsx, CollectionDialog.test.ts, SkillPool.tsx}` 三个文件）

## 5. 不在范围内（backlog）

下列条目写进 prd.md「范围外」已记录，本任务不做：

- modal 内单成员操作 progress 状态展示
- modal 内 hover 菜单（删除/编辑标签/导出）
- 移动端 bottom sheet 适配
- 抽屉（drawer）方案对比
- 独立卡就地操作改造
- 后端 API / 数据模型任何改动

## 6. 子 agent 派发

按 Trellis 2.1 协议，实施阶段用 `trellis-implement` 子 agent（系统自动注入 prd.md / design.md / implement.md）。

派发 prompt 模板：

```
Active task: F:\personal-projects\personal-web\.trellis\tasks\10-15-skill-manager-collection-modal

You are already the trellis-implement sub-agent. Do NOT spawn another trellis-implement or trellis-check.

Read prd.md, design.md, implement.md from the task directory in that order.

Implement Step 1 → 6 from implement.md in order. Do not skip gates.

After Step 5, report:
- Which gates G1-G6 passed
- Any deviation from the design with the reason
- Any new decisions made (state them in your final reply)

Then proceed to Step 6 live browser verification (dev server is already running on c4 terminal tab at frontend port 3008 + backend 8097 — DO NOT start a new dev server, use the existing one). Take screenshots and save to .trellis/workspace/jackson.tang/screenshots/.

Do NOT commit. Do NOT open a PR. Just implement, run validation, report results.

Key constraints:
- Only modify apps/skill-manager/src/components/CollectionDialog.tsx (new), apps/skill-manager/src/components/CollectionDialog.test.ts (new), apps/skill-manager/src/components/SkillPool.tsx (modify collection rendering only)
- Do not introduce new UI dependencies (self-written modal with Tailwind, mirroring ProfileScopePicker)
- Use existing types: SkillCollection, SkillCard, InstallTarget, ExportTarget, QueueEntry, TargetKey, ExportTargetKey
- Reuse existing on* callbacks from SourceWorkspace
- Do not touch SourceWorkspace, lib/collections.ts, lib/types.ts, backend, or API contracts
- ProfileViews.test.ts and SkillPool.test.ts must keep passing (update SkillPool.test.ts assertions if necessary)
```

派发后等待子 agent 返回结果，按 `verification.md` 协议审一次，再决定 `task.py finish` 或修复。
