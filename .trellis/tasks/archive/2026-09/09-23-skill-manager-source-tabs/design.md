# design — skill-manager 前端两级导航（管理看板 × 部署看板）

## 1. 总体结构

自包含 workspace + 独立看板方案：一级导航按职责分两个 view（常驻挂载 + hidden 切换），
各 view 内二级 segmented 切维度。page.tsx 瘦身为：数据加载、导航状态、全局 notice、
下架/clone/删除/登记弹窗。

```
app/page.tsx                        # 数据加载 + 导航容器 + URL 同步 + 全局 notice + 弹窗
├── view: 管理看板（二级 segmented：自研 | GitHub）
│   ├── components/SourceWorkspace.tsx ×2    # 新增：维护两件套（自包含状态 + 发布确认弹窗）
│   │   ├── SkillFilters                     # 改：去掉 source 筛选项
│   │   ├── SkillPool                        # 基本不变（Clone/删除仅 github skill 出现）
│   │   └── PublishQueue                     # 不变
└── view: 部署看板（二级 segmented：OpenClaw | Hermes）
    └── components/DeployBoard.tsx           # 改造自 DeployedView：agent 维度账本看板
        ├── 筛选行：搜索 / 来源 / 排序（看板内部 state）
        └── 部署列表：active 部署 + 来源标记 + link_missing + [下架]
```

## 2. 关键决策与理由

| 决策 | 选择 | 理由 |
|------|------|------|
| 导航层级 | 两级：一级按职责（管理/部署），二级管理切来源、看板切 agent | 两个职责 × 各自正交维度，心智清晰；用户以「agent 类型」命名二级维度，为未来新增 agent 预留 |
| 一级样式 | 下划线 tab；二级用 segmented control | 视觉区分层级，避免两级同款 tab 的混淆 |
| 维护视图内容 | 两件套（池 + 队列），卡片部署 badge 保留 | badge 已回答「这个 skill 发布到哪」；完整部署管理集中看板 |
| 状态保留方式 | 三个视图常驻挂载 + `hidden` 切换 | 把现有 page.tsx 逻辑「搬家」而非改线；切换不丢队列 |
| 视图内状态归属 | SourceWorkspace 内部（filters/queue/plan/results/发布确认弹窗）；DeployBoard 内部（agent、筛选、排序） | 「每来源独立队列」天然成立，page.tsx 不因重构膨胀 |
| 全局弹窗去留 | 发布确认在 workspace 内；下架/clone/删除/登记确认留 page 层（回调上抛） | 下架入口在看板，clone/删除/登记仍从管理看板触发；page 层保持单一入口 |
| FilterState.source | 删除字段 | 子 tab 即来源；applyFilters 同步移除 source 分支 |
| FilterState.status | 删除字段 | 后端 schema/模型保留 deprecated 值，但系统无任何路径写入 deprecated；筛选器永远只能选「全部/active」，纯 UI 噪音 |
| 看板规模 | 筛选器 + 排序，本轮不做翻页 | 个人管理台现状几十个 skill；虚拟滚动/分页待真需要再加 |
| 回滚入口 | 所有视图移除 | 现有实现对核心场景无效（链接路径恒定 + 不 checkout 旧版本，见 PRD R5）；后端保留 |
| URL 持久化 | `?view=manage&tab=local\|github` / `?view=board&agent=openclaw\|hermes`；`useSearchParams` 读 + `router.replace` 写 | 语义化两级状态；可刷新、可分享；非法值逐级回退 |
| 卡片视觉 | Skill 池 / 队列 / 计划 / 部署列表三处统一走 grid 多列（3→2→1）+ 同列同高 + 完整技能卡结构 | 三处视觉对等，避免右侧队列/计划显得「薄」；设计原型见 `prototype.html`，本轮以此为准 |

## 3. 组件接口（草案）

```ts
// SourceWorkspace：维护两件套（local/github 各一个实例）
interface SourceWorkspaceProps {
  source: SkillSource;
  skills: SkillCard[];          // page 层已按 source 过滤
  loading: boolean;
  onRefresh: () => Promise<void>;
  onNotify: (notice: Notice | null) => void;
  onUnpublish: (op: { skillId: string; skillName: string; target: TargetKey }) => void; // 备用：badge 长按/后续扩展；本轮下架入口在看板
  // 以下仅 github 实例传入：
  onCheckUpdates?: () => Promise<void>;
  onRegister?: () => void;
  onClone?: (skillId: string, skillName: string) => void;
  onDelete?: (skill: SkillCard) => void;
}

// DeployBoard：部署看板（单实例，内部二级 segmented）
interface DeployBoardProps {
  skills: SkillCard[];          // 全量（看板自行按 agent + 筛选器过滤）
  onUnpublish: (op: { skillId: string; skillName: string; target: TargetKey }) => void;
}
```

内部搬运 page.tsx 现有逻辑：SourceWorkspace 收编 `applyFilters`（去 source 分支）、
`allTags`（本来源）、`handleAddToQueue`、`handleGeneratePlan`、`performPublish`、
`planToRequests`、`publishableCount`、发布确认弹窗。DeployBoard 收编 DeployedView 的
active 部署提取逻辑，改造为「单 target 全宽列表 + 筛选排序」。

## 4. 现有组件改动清单

| 文件 | 改动 |
|------|------|
| `app/page.tsx` | 重构：两个 view 容器 + 两个 SourceWorkspace + DeployBoard + 全局弹窗 + notice；两级导航（setView/setSourceTab/setAgent）；移除 rollbackSkill 调用与 PendingTargetOp 的 rollback 分支；header 仅保留标题 + 一级 tab，GitHub 专属按钮下沉到管理 view 源工具行 |
| `components/SourceWorkspace.tsx` | 新增；含 SkillPool（grid 多列 3→2→1，同列同高，summary 2 行截断）+ PublishQueue（队列项走完整技能卡：右上角多目标 badge；计划项动作优先：徽章左对齐） |
| `components/DeployBoard.tsx` | 新增（逻辑改造自 DeployedView，按单 target grid 多列 3→2→1 + 完整技能卡：顶部 source badge + 名 / revision + 时间 + link_missing / 下架贴底） |
| `components/DeployedView.tsx` | 删除（被 DeployBoard 取代） |
| `components/SkillFilters.tsx` | `FilterState` 删 `source`/`status` 字段；UI 删来源下拉、启用状态下拉 |
| 其余组件 | 不动（PublishQueue/SkillPool 已按 props 解耦） |

## 5. 实现期需核实的点

- SkillPool 的 Clone/删除按钮是否已按 `skill.source === 'github'` 条件渲染；
  若否（local skill 也渲染），需补条件 — 属于本任务的直接修复。
- `planToRequests` / `publishableCount` 留在 SourceWorkspace 文件内（单处使用，避免过早抽象）。
- Next.js 15 `useSearchParams` 在静态渲染下要求 Suspense 边界：若 build 报
  `useSearchParams() should be wrapped in a suspense boundary`，将读参组件包进
  `<Suspense>`；不改 `force-dynamic`（保持构建产物为静态）。
- DeployBoard 排序默认值：发布时间倒序（最近发布的在上），比名称序更贴近运维视角。

## 6. 兼容与回滚

- 后端零改动，API 契约不变；旧 URL `/skills`（无 query）默认自研 tab，行为向后兼容。
- 回滚 = revert 前端提交，无数据迁移。
