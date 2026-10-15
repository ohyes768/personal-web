# Implement — Skill Manager profile scope switcher

## 1. 任务范围

只动以下两个前端文件：

| 文件 | 操作 |
|---|---|
| `apps/skill-manager/src/components/ProfileScopePicker.tsx` | 新增（组件本体） |
| `apps/skill-manager/src/components/ProfileScopePicker.test.ts` | 新增（vitest 单测） |
| `apps/skill-manager/src/app/page.tsx` | 改 header 区块（删旧 picker、嵌入新组件） |

**不动后端 / 不动其他组件 / 不动 installTargets 上下文**。

## 2. 执行清单（有序）

### Step 1 — 新增 `ProfileScopePicker.tsx`

- 创建文件 `apps/skill-manager/src/components/ProfileScopePicker.tsx`
- 内容按 `design.md §1 §2 §3 §6` 实现：
  - `useState` 管 popover 开关
  - `useEffect` + document listener 管外点击 / Esc 关闭
  - 颜色 / 状态映射按 `design.md §2` 表格
  - popover 布局按 `design.md §3` 完整抄
  - 类型用现有 `InstallTarget`（不引入新类型）
- 完成后跑 `pnpm typecheck` 确认类型无错

### Step 2 — 新增 `ProfileScopePicker.test.ts`

- 创建文件 `apps/skill-manager/src/components/ProfileScopePicker.test.ts`
- 测试覆盖（用 `renderToStaticMarkup` + `InstallTargetsContext.Provider`，参考 `ProfileViews.test.ts` 写法）：
  - **T1**：可用态 → button 文字 `Hermes · <name>` + 色点绿 class
  - **T2**：不可用态（`available:false, unavailable_reason:'xxx'`）→ button 琥珀边框 + 文字含 `目标不可用：xxx`
  - **T3**：loading 态（`loading:true`）→ button 显示 `加载中…`
  - **T4**：error 态（`error:'load failed'`）→ button 显示 `加载失败`
  - **T5**：空 targets（`targets:[]`）→ button 显示 `暂无 profile`
  - **T6**：click button → popover 打开（断言 `aria-label="切换发布目标"` 在 markup 里）
  - **T7**：click popover 列表项 → 调用 `onSelect` 且 popover 关闭（通过断言后续 button 状态验证）
  - **T8**：click `管理安装目标 →` → 调用 `onManage`
- 跑 `pnpm vitest run src/components/ProfileScopePicker.test.ts` 全过

### Step 3 — 改 `apps/skill-manager/src/app/page.tsx`

- 删除第 281-290 行整块 `{view === 'manage' || view === 'board') && <div>...</div>}`（旧 picker）
- header 结构按 `design.md §4` 改造：左侧 flex（title + nav），右侧 flex（nav + ProfileScopePicker）
  - 实际写法：把 header 内的 `<nav>` 提到右侧，与新组件并列；左侧只留 `← 返回首页` + `Skill 发布管理台`
  - 调整 flex 容器让两栏 `justify-between` 撑满
- 导入新组件：`import ProfileScopePicker from '@/components/ProfileScopePicker';`
- props 按 `design.md §4` 传

### Step 4 — 全量验证

按顺序跑：

```bash
# 后端不动，跳过
cd "F:/personal-projects/personal-web/apps/skill-manager"

# lint
pnpm lint

# typecheck
pnpm typecheck

# 既有测试（含 ProfileViews.test.ts）不破
pnpm vitest run

# build（确认 Next 编译通过）
pnpm build
```

期望全部通过。如果 lint 报 `react-hooks/exhaustive-deps` 警告（例如 `useEffect` 监听器），按 lint 提示修；如果 build 报错，检查 JSX 是否拼错。

### Step 5 — Live browser 验收

dev server 已在 c3 tab 运行（前端 3008 + 后端 8097）：

1. 访问 `http://localhost:3008/skills?view=manage`，截图存 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-manage.png`
2. 访问 `http://localhost:3008/skills?view=board`，截图存 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-board.png`
3. 访问 `http://localhost:3008/skills?view=install-targets`，截图存 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-install-targets.png`
4. 访问 `http://localhost:3008/skills?view=targets`，截图存 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-targets.png`
5. 在 manage 视图点开 popover，截图存 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-popover-open.png`
6. 在 popover 里点不同 profile，验证 URL 变化 + 主区列表刷新

chrome-devtools 用 mcp 工具调用；若超时则改用 `pnpm exec playwright` 截（如未装则跳过，等用户手验）。

## 3. Review gates（每步必查）

| Gate | 检查 | 通过条件 |
|---|---|---|
| **G1 类型** | `pnpm typecheck` 退出 0 | 无 TS 报错 |
| **G2 测试** | `pnpm vitest run` 全过 | 既有测试不破 + 新测试全过 |
| **G3 lint** | `pnpm lint` 退出 0 | 无 error 级别 |
| **G4 build** | `pnpm build` 退出 0 | Next.js 编译过 |
| **G5 live** | 截图四视图 + popover 开 | 视觉与 design.md §3 一致 |
| **G6 回归** | manage 视图下点列表项切换 scope | URL `?target=<id>` 变 + 主区列表更新 |

## 4. Rollback 形状

最小破坏原则：

- **Step 1-2** 完成但 Step 3 未做：组件已存在但未挂载，零风险（直接进 commit，不破现状）
- **Step 3 完成但 Step 4 失败**：`git checkout HEAD -- apps/skill-manager/src/app/page.tsx` 即可回到现状
- **完全回滚**：`git revert <commit>` 或 `git reset --hard HEAD~1`（本任务所有改动都在 `apps/skill-manager/src/components/ProfileScopePicker.*` 和 `apps/skill-manager/src/app/page.tsx` 三个文件）

## 5. 不在范围内（二期 backlog）

下列条目写进 prd.md「范围外」已记录，本任务不做：

- 切换后 toast 反馈
- 切换时破坏性操作的二次确认
- 移动端 popover → bottom sheet 适配
- `provider` 字段扩展（schema 不动）

## 6. 子 agent 派发

按 Trellis 2.1 协议，实施阶段用 `trellis-implement` 子 agent（系统自动注入 prd.md / design.md / implement.md）。

派发 prompt 模板：

```
Active task: F:\personal-projects\personal-web\.trellis\tasks\10-15-skill-manager-profile-scope-switcher

You are already the trellis-implement sub-agent. Do NOT spawn another trellis-implement or trellis-check.

Read prd.md, design.md, implement.md from the task directory in that order.

Implement Step 1 → 5 from implement.md in order. Do not skip gates.

After Step 4, report:
- Which gates passed
- Any deviation from the design with the reason
- Any new decisions made (state them in your final reply)

Do NOT commit. Do NOT open a PR. Just implement, run validation, report.
```

派发后等待子 agent 返回结果，按 `verification.md` 协议审一次，再决定 `task.py finish` 或修复。
