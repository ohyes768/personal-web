# Skill Manager GitHub 合集卡片改为 modal 入口

## 目标

把 GitHub 合集卡片的「inline `<details>` 折叠展开」改为「入口卡 + 全屏 modal」模型，让合集在主 grid 上只承担「入口」角色，所有成员操作与批量操作统一在 modal 内完成。统一操作模型：**操作 1 个 Skill = 独立卡就地操作；操作 N 个 Skill = 合集卡 → modal**。

## 已确认背景

- 现状代码：`apps/skill-manager/src/components/SkillPool.tsx` 用 `<details><summary>` 模式实现合集折叠展开（行 379-460）；展开后 `col-span-full` 让成员卡占整行。
- 现状数据（`https://web.duomi77.cn:9443/skills?view=manage&target=hermes:profile:ohyes768&tab=github` 真机截图，2026-10-15）：
  - 1 个 12 项合集（ai-berkshire，全装 12/12）
  - 1 个 14 项合集（taste-skill，0/14 + 有远端更新）
  - 1 个 5 项合集（uzi-skill，0/5）
  - 3 张独立卡（impeccable / luopan / financial-statement）
- 已确认痛点（来自 wireframe 分析，[`skill-pool-redesign-wireframes.md`](../../../workspace/jackson.tang/screenshots/skill-pool-redesign-wireframes.md)）：
  - 独立卡 = 工作台（就地操作），合集卡 = 「折叠预览 + 展开后才是工作台」——两种卡片角色错位
  - 合集展开后 col-span-full 视觉跳变
  - 成员卡与独立卡信息架构不对称（高度差 ~70px）
  - 合集（折叠）无批量「下架整个 / 更新整个」入口
  - 成员卡 summary 重复合集前缀（如 "AI Berkshire skill: ..."）
- 既有任务 `10-13-skill-manager-repository-collections` 已完成 GitHub 合集骨架功能；本任务仅重写前端交互模型，**不动后端 API、不动 `SkillCollection` 数据结构、不动 R1-R5 既有行为**。

## 需求

### R1 主 grid 上的合集入口卡

替换 `<details><summary>` 为普通 `<button>` 触发的入口卡：

- 视觉结构与独立卡同高（差距 ≤ 50px）：
  - 顶部：sky 色「合集 · N 项」徽章 + 右上「✓ 12/12 已全部安装」或「已安装 N/M」（全装完时绿色加 ✓，未装完时 slate-500 普通文字）
  - 中部：合集 title + repo (`owner/repo`)
  - 摘要：成员名前 3 个 + 「等 N 个 Skill」
  - 状态 chip 行：📦 已导出 N 目标 · 🆕 有更新 N 项 · ⚠ 异常 N 项（仅当 N > 0 才显示）
  - 底部：「[查看成员 →]」主按钮（替代原「收起成员 / 查看成员」toggle）
- 入口卡只承载「打开 modal」一个交互；不再就地展开任何内容。
- 单成员合集仍走 `renderSkill(visibleMembers[0])` 直接显示为独立卡（现状代码 line 371 保留），不进 modal。

### R2 全屏 modal

新增组件 `apps/skill-manager/src/components/CollectionDialog.tsx`：

- 形态：覆盖整屏的 modal（不是 popover，不是 drawer），宽度 ~960px、最大高度 ~85vh、内容溢出滚动
- 关闭方式：右上 [X 关闭] 按钮 + Esc 键 + 点击 modal 背景（点击 modal 内容不关）
- 打开方式：在主 grid 的合集入口卡上点 [查看成员 →] 触发
- 路由行为：URL 不变（modal 状态用 component state，不污染 URL）；关闭 modal 时焦点回到触发它的入口卡

### R3 modal 内部布局

modal 内容分三段：

**R3.1 顶部 header**（合集身份）
- 合集 title（大字号）+ repo (`owner/repo`) + 「合集 · N 项」徽章
- 右上：当前发布目标 label + 总览状态（「✓ 12/12 已全部安装」或「已安装 N/M · 异常 X」）
- 关闭按钮 [X]

**R3.2 toolbar**（统一操作区）
- 左半：全选 / 清空 / 已选 N 项（仅在选择动作时显示）
- 右半（按视觉权重排序）：
  - 主按钮（filled sky）：「安装所选 (N)」/ 当 N=0 时禁用 + 灰化
  - 次级主按钮（outline sky）：「更新整个」「下架整个」
  - 次级操作（outline slate）：「下载合集」「＋ 添加成员」「检查更新」
- 状态 chip 摘要（在 toolbar 与 body 之间）：📦 已导出 N 目标 · 🆕 有更新 N 项 · ⚠ 异常 N 项

**R3.3 body**（成员列表，row list 形态）
- 不再是 grid，是单列 row list（一行一个成员）
- 每行结构：☐ checkbox + name + status badge + summary（去掉合集前缀 + 合集同名 tag）+ 单成员 actions
- 单成员 actions 收敛到 2 个：安装/更新 + 下架（删除/编辑标签/导出移到 hover 行或次级菜单，因为 modal 内做单成员操作违反"先选再批"的语义）
- 状态徽章统一用 `InstallationBadge`（与独立卡一致）

### R4 单成员操作的语义调整

modal 内每个成员行的 actions 精简：

| 操作 | 在 modal 内是否暴露 | 替代入口 |
|---|---|---|
| 安装/更新 | ✅ 行内按钮 | — |
| 下架 | ✅ 行内按钮 | — |
| 删除 | ❌ 不在 modal | 主 grid 入口卡暴露（点开合集前先选要管理的成员） |
| 编辑标签 | ❌ 不在 modal | 同上 |
| 导出 ZIP | ❌ 不在 modal | 同上 |
| 恢复缓存（Clone） | ⚠️ 行内琥珀按钮（cache_missing 时） | — |
| 单成员下架提示 | 沿用 `confirmUnpublish` 弹窗 | — |

理由：modal 的核心价值是"批量"，单成员操作的精细管理（删除/标签/导出）属于「对合集成员作为独立实体的操作」，应该让用户**先回到主 grid** 把这个成员升级为独立卡视角（"在主 grid 上单独看到它"），或保留进入 modal 之前的合集身份选择。

### R5 modal 状态管理

- modal 打开/关闭：`openCollection: SkillCollection | null` state，由 SkillPool 管理
- modal 内选择：modal 内部 `useState<Set<string>>(selectedIds)`，不污染 SkillPool 状态
- modal 内 action 触发后行为：
  - 「安装所选」「更新整个」「下架整个」：调用对应 on* 回调，**关闭 modal**，父组件用 `setNotice` 显示结果
  - 「下载合集」「添加成员」「检查更新」：保留 modal 打开，让用户在 modal 内继续看到更新后的状态
  - 单成员行内「安装/更新/下架」：沿用现有 `onToggleQueueTarget` / `onUnpublish` 回调，**关闭 modal** 让用户在主 grid 看到更新后的卡片状态
- URL 切换（用户切到部署看板）时强制关闭 modal：`useEffect` 监听 `view` search param

### R6 视觉一致性

- modal 边框/阴影：`border border-slate-200 rounded-xl shadow-xl`
- modal 标题字号：`text-xl font-semibold` 与主 grid h1 同级
- 主按钮（安装所选）：`bg-sky-600 text-white`，跟主 grid 上独立卡的「安装」按钮一致
- 次级主按钮：「更新整个」outline-sky-300、「下架整个」outline-rose-300
- 状态色：emerald（已装）/ amber（待 Clone、源缺失）/ rose（异常）/ slate（默认）
- 关闭按钮 + Esc + 背景点击三种关闭方式都触发同一个 `onClose`

## 验收

### AC1 主 grid 合集入口卡（R1）

- 在主 grid 上，多成员合集显示为简洁入口卡（不再用 `<details>`）
- 入口卡上有「[查看成员 →]」按钮，点击打开 modal
- 单成员合集仍显示为独立卡（`< 2 members` 走 `renderSkill`，不打开 modal）
- 入口卡与独立卡高度差 ≤ 50px

### AC2 modal 开关（R2、R5）

- 点入口卡 → modal 打开
- 关 modal 三种方式都生效：右上 X / Esc 键 / 点 modal 背景
- URL 切换（用户切 view）时 modal 自动关闭
- 关闭 modal 后焦点回到触发的入口卡

### AC3 modal 内容（R3）

- header 显示合集 title / repo / 「合集 · N 项」徽章 / 总览状态 / 关闭按钮
- toolbar 显示全选/清空/已选 + 主按钮（安装所选）+ 次级主按钮（更新整个、下架整个）+ 次级操作（下载合集、添加成员、检查更新）
- body 显示单列 row list 成员，每行有 checkbox + name + status badge + summary + 至少 1 个操作按钮

### AC4 状态指示统一（R3.2 chip 行）

- modal 顶部 toolbar 与 body 之间显示状态 chip 摘要：📦 已导出 N 目标 · 🆕 有更新 N 项 · ⚠ 异常 N 项
- 三个 chip 仅在 N > 0 时显示
- chip 颜色：📦 emerald / 🆕 sky / ⚠ amber

### AC5 完成态强化（R1 入口卡）

- 「已安装 N/M」在 N === M 时显示为绿色加 ✓「✓ 12/12 已全部安装」
- N < M 时保持 slate-500 普通文字「已安装 12/14」

### AC6 单成员操作语义（R4）

- modal 内每行只暴露「安装/更新 + 下架」两个操作按钮
- 缓存缺失时该行额外暴露「恢复缓存」按钮（琥珀色，沿用现有样式）
- 删除 / 编辑标签 / 导出 ZIP 在 modal 内不暴露（用户需回到主 grid 入口卡视角）
- 单成员行内点击「安装/更新」或「下架」后 modal 自动关闭，主 grid 卡片状态更新

### AC7 既有行为回归

- 入口卡点击「查看成员 →」弹 modal 后，成员列表、checkbox、全选/清空、批量操作、单独安装/下架行为全部保留
- 主 grid 上独立卡（操作 1 个 Skill）的所有行为不变
- install/unpublish/refresh 等 API 调用流不变
- `ProfileViews.test.ts` 既有 3 项测试 + `SkillPool.test.ts` 既有 9 项测试不破

### AC8 测试 / lint / typecheck / build

- 新增 `CollectionDialog.test.ts`，覆盖：
  - T1：modal 打开/关闭（背景点击、Esc、X 按钮）
  - T2：全选 / 清空 / 选择计数
  - T3：「安装所选 (N)」禁用当 N=0
  - T4：「更新整个」「下架整个」次级主按钮调用对应 on*
  - T5：单成员行内安装/下架调用对应 on*
  - T6：状态 chip 仅在 N>0 时渲染
  - T7：完成态「✓ 12/12 已全部安装」文本
  - T8：路由变化（view param 改变）触发 onClose
- `pnpm lint` 0 error
- `pnpm typecheck` 0 error
- `pnpm exec vitest run` 13 files / 67 + 新增测试 全过
- `pnpm build` 编译过（standalone trace copy 已知 Windows EPERM 不影响验收）

### AC9 浏览器模拟验收

- dev server（前端 3008 + 后端 8097）跑通以下场景并截图存到 `.trellis/workspace/jackson.tang/screenshots/`：
  - `collection-modal-grid.png` — 主 grid，3 个合集入口卡（不同尺寸：5 / 12 / 14 项）+ 3 张独立卡
  - `collection-modal-open-12.png` — 12 项合集 modal 打开态
  - `collection-modal-open-14.png` — 14 项合集 modal 打开态（验证 0/14 + 有更新 chip）
  - `collection-modal-selected.png` — 选 3 个成员后 toolbar 状态
  - `collection-modal-export-chip.png` — 📦 已导出 N 目标 chip 显形

## 范围外

- 抽屉（drawer）方案对比 —— 已确认选 modal
- 全屏 page 路由方案 —— 已确认选 modal
- 单成员卡（独立卡）就地操作改造 —— 独立卡维持现状
- 单成员合集（1 个 member）走 modal —— 单成员合集走 `renderSkill` 直接显示
- 删除 / 编辑标签 / 导出 ZIP 在 modal 内暴露 —— 一期不做，留 backlog
- modal 内单成员操作的 progress 状态展示 —— 一期 modal 关闭后让父组件用 notice 显示
- 移动端 bottom sheet 适配 —— 一期桌面优先，移动端基本可用即可
- 后端 API / 数据模型 / 持久化任何改动

## 规划状态

待用户 review PRD + design + implement 三件套后激活实施。dev server 仍在 c4 tab 运行（前端 3008 + 后端 8097），可复用做 live 验证。
