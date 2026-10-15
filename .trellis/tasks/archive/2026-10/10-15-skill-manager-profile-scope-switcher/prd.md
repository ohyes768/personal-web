# Skill Manager profile scope switcher 重设计

## 目标

把 Skill 发布管理台当前的 profile 切换器从「header 下方一行的裸 `<select>`」升级为「应用级 scope bar（顶栏右侧常驻的 button + popover）」，让用户在所有视图下都能瞬时感知并切换当前发布目标；切换器成为 operate-mode 工具的标配 scope 控件，承载状态指示、可用性反馈和路径预览。

## 已确认背景

- 现状代码：`apps/skill-manager/src/app/page.tsx:281-290` 用 `<select id="install-profile">` 渲染 profile picker，label 为 `Hermes profile`；该控件**仅在 `view === 'manage' || view === 'board'` 时渲染**，在 install-targets / targets 视图下完全消失。
- 现状视觉：picker 在 header 下方单独占一行，旁边挤 `install_path` 长字符串 + 「管理安装目标」链接，路径用 `break-all` 但仍会撑宽 row；install-targets 视图下用户改完 profile 配置后**没有任何方式知道自己当前还在哪个 profile scope**。
- 现状文案：`<label>Hermes profile</label>` 把 Hermes provider 和 scope 名混在一起；target id 形如 `hermes:profile:ohyes768`，未来理论上可能扩 provider，文案不应耦合。
- 现状状态指示：可用性靠下拉选项尾巴「（不可用）」文字表达；当前选中态无色点、无边框、无 toast 反馈。
- 既有任务 `10-14-skill-manager-profile-ui` 已完成 profile 安装目标的 CRUD 后端 + UI + 验证（275 后端测试 / 52 前端测试通过），等待最终提交确认；本任务仅触及前端 `apps/skill-manager/src/app/page.tsx` 的 header 区块，**不动后端、不动 R1-R5 既有行为**。
- 设计参考（截图）：`.trellis/workspace/jackson.tang/screenshots/skill-manager-current-manage.png`、`.trellis/workspace/jackson.tang/screenshots/skill-manager-current-install-targets.png`。
- 设计方案：`.trellis/workspace/jackson.tang/screenshots/profile-switcher-design.md`。

## 需求

### R1 scope picker 组件

替换 `<select id="install-profile">` 为一个 button + popover 组件 `ProfileScopePicker`：

- 触发器 button 显示当前 scope：`● <provider> · <profile_name> ▾`（如 `● Hermes · Default dev ▾`）
- 左侧色点：可用=绿、不可用=琥珀、已移除=灰
- 不可用时 button 自身加琥珀边框 + 文字 `目标不可用：<reason>`
- 点击 button 打开 popover，popover 内容：
  - 标题 `切换发布目标` + `刷新` 按钮（复用现有 `refreshInstallTargets`）
  - profile 列表，每行：`● <provider> · <profile_name>` + `install_path`（monospace chip + 折叠）+ `active_installation_count` 安装数
  - 不可用 profile 行额外显示 `unavailable_reason`
  - 底部 `管理安装目标 →` 链接，跳到 `view=install-targets` 视图
- 点击 popover 列表项 = 切换 scope（沿用现有 `navigate({ agent: id })`）
- popover 外点击、Esc、再次点击 button = 关闭

### R2 位置与常驻

picker 改为常驻在 `apps/skill-manager/src/app/page.tsx` 的 `<header>` 同一行右侧：

- 与四个视图 tab（管理看板 / 部署看板 / 安装目标 / 导出目标）平级，靠右对齐
- 不再单独占一行挤压主区
- **跨视图常驻**：在 `view ∈ {manage, board, install-targets, targets}` 全部四个视图下都显示当前 scope；用户在 install-targets 改完配置后切回时仍能看到当前 scope
- header 当前 flex 布局：`flex items-center justify-between gap-3 border-b border-slate-100 pb-1`，新 picker 作为右侧第二项加在 `<nav>` 后

### R3 文案修正

- `<label>Hermes profile</label>` → 改为 `当前发布目标` 或 `操作目标`（不耦合 provider 名）
- 沿用语义：`provider` 字段仍来自 `InstallTarget.provider`，渲染时用 `provider · profile_name` 格式（中间中点 `·`）
- popover 标题：`切换发布目标`

### R4 状态视觉强化

- 色点状态映射（installTargets 数据的 `available` / `removed` 字段）：
  - `available && !removed` → 绿 `bg-emerald-500`
  - `!available && !removed` → 琥珀 `bg-amber-500`
  - `removed` → 灰 `bg-slate-300`
- 不可用态：button 加 `border-amber-400` 边框 + 文字 `目标不可用：<reason>`（取 `unavailable_reason` 第一行）
- 已移除态：不显示在 popover 默认列表（沿用现有 `installTargets.filter(t=>!t.removed)` 过滤逻辑）；但**button 仍显示当前选中的已移除 target**，色点为灰

### R5 install_path 收纳

- `install_path` 不再显示在 header row（现在用 `break-all text-xs text-slate-500` 撑宽）
- `install_path` 显示在 popover 列表项里，用 monospace 字体 + 浅灰 chip + 长路径折叠（hover 显示全）
- 不可用态的 `unavailable_reason` 摘要也显示在 popover 列表项里，不显示在 header

### R6 popover 交互细节

- popover 用现有 react state 控制开关（不引入额外 popover 库，避免依赖膨胀；如果 Tailwind 自写绝对定位即可）
- popover 宽 ~360px、列表项高度约 48px、内容溢出时滚动
- 列表项 hover = `bg-slate-50`，选中项 = `bg-sky-50` + 左侧 2px sky 色 border
- popover 内 `刷新` 按钮独立 clickable，刷新时按钮变 `刷新中…`，禁用列表项

### R7 切换反馈（一期可选，二期再做）

- 一期：切换后 URL 立即变化（沿用 `navigate({ agent })`），主区列表会因 `InstallTargetsContext` 重新渲染；不主动加 toast
- 二期（不在本任务）：切换后顶部滑出 toast `已切换到 profile '<name>'`，3 秒淡出
- 二期（不在本任务）：切换时若存在 pending 破坏性操作（下架/删除/clone），弹二次确认

## 验收

### AC1 组件形态（R1、R6）

- header 中出现 button + 色点 + 文字 `Hermes · <name> ▾`，不再是 `<select>`
- 点击 button 打开 popover，popover 内容与 R1 描述一致
- popover 外点击 / Esc 关闭

### AC2 常驻性（R2）

- 在 `view=manage` / `view=board` / `view=install-targets` / `view=targets` 四个视图下，picker 都显示当前 scope
- picker 不再单独占一行，与视图 tab 同行

### AC3 文案（R3）

- 原 `Hermes profile` label 不再出现
- button 文字用 `Hermes · <name>` 格式（provider · profile_name）

### AC4 状态视觉（R4）

- 选可用 profile：色点绿、button 正常边框
- 选不可用 profile：色点琥珀、button 琥珀边框 + 文字 `目标不可用：<reason>`
- 不可用 profile 在 popover 列表中显示 `unavailable_reason`

### AC5 install_path 收纳（R5）

- header 不再展示 `install_path` 长字符串
- `install_path` 在 popover 列表项里以 monospace chip 显示

### AC6 切换可用性（回归）

- 点击 popover 列表项切换 scope，URL `?target=<id>` 变化，主区列表重新加载（R1-R5 既有行为不变）
- popover 底部 `管理安装目标 →` 跳到 `view=install-targets`

### AC7 测试 / lint / typecheck / build

- 新组件 `ProfileScopePicker` 加单元测试（vitest + react-dom/server）：色点状态映射、点击/关闭交互、文案格式
- 现有 `ProfileViews.test.ts` 不破
- 前端 `pnpm lint` / `pnpm typecheck` / `pnpm build` 全过
- 后端无改动，原 275 测试不动

### AC8 浏览器模拟验收

- 用 dev server（前端 3008 + 后端 8097）跑 manage / board / install-targets / targets 四个视图，截图存到 `.trellis/workspace/jackson.tang/screenshots/scope-switcher-{view}.png`
- popover 打开状态截图：`scope-switcher-popover-open.png`

## 范围外

- 移动端 popover → bottom sheet 适配（不影响桌面端通过验收即可）
- 切换 toast 反馈（写进二期 backlog，不进本期）
- 切换时破坏性操作的二次确认（写进二期 backlog）
- 后端任何改动、R1-R5 既有行为（已有任务 `10-14-skill-manager-profile-ui` 处理）
- `provider` 字段扩展（当前固定为 `hermes`，方案留了口子但不实装）
- 抽屉式 sidebar 方案（已被排除，理由记录在 `.trellis/workspace/jackson.tang/screenshots/profile-switcher-design.md`）

## 规划状态

待用户 review PRD + design + implement 三件套后激活实施。dev server 已起（c3 tab，前端 3008 + 后端 8097），可复用做 live 验证。
