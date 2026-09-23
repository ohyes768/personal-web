# skill-manager 前端两级导航重构：管理看板 × 部署看板

## Goal

把 Skill 发布管理台从单页混装重构为两级导航：一级按职责分「管理看板 / 部署看板」，
二级在管理看板内切来源（自研/GitHub）、在部署看板内切 agent（OpenClaw/Hermes）。
维护视图回答「这个 skill 发布到哪了」，看板回答「agent 环境上跑了什么」，
消除两来源混杂与部署信息复制两份的粗糙感。

## 背景与问题

当前单页设计（`apps/skill-manager/src/app/page.tsx`）：

- 左栏 Skill 池两来源混装，仅靠 source 筛选项区分
- 右栏 DeployedView + PublishQueue 全局混合两来源；部署视图按 target 分组，
  skill 多时每个 tab 右栏都要长滚动，且同一部署信息在两个来源 tab 里重复
- header 上「检查 GitHub 更新」「新增 GitHub Skill」是 GitHub 专属操作，却占据全局位置

后端 `GET /api/skills` 已返回 `source / deployments / update / cache_missing / source_missing`
全部字段，自研 skill 由后端 `sync_local()` 自动对账，本任务后端零改动。

## Requirements

### R1 导航结构（两级）

- 一级 tab 两个（按职责）：`管理看板`（默认）/ `部署看板`
- 管理看板内二级 segmented 切**来源**：`自研 Skill`（默认）/ `GitHub Skill`
- 部署看板内二级 segmented 切 **agent**：`OpenClaw` / `Hermes`；未来新增 agent 只加子 tab
- 状态通过 URL query 表达：`?view=manage&tab=local|github` / `?view=board&agent=openclaw|hermes`，
  刷新/分享保持；非法值回退（view→manage，tab→local，agent→openclaw）

### R2 管理看板内容（local / github 结构对称，均为两件套）

- 该来源的 Skill 列表（沿用 SkillFilters + SkillPool，去掉 source 筛选项，子 tab 即来源）
- 该来源的独立发布队列（PublishQueue 只收该来源 skill，切子 tab 队列互不可见、互不影响）
- 卡片保留部署 badge（「OpenClaw 已发布 · rev」等），承担「skill→发布到哪」信息
- 不再内嵌已部署视图区块（部署管理集中到部署看板）

#### R2.1 视觉约定（管理看板）

- **Skill 池走 grid 多列卡片**：`grid-template-columns: repeat(3, 1fr)`，断点 1100px→2 列、680px→1 列；同列卡片同高，summary 截断 2 行 + 省略号，操作行贴卡片底部
- **发布队列走完整技能卡**（不再是单行列表项）：每项卡片含名称、ID、右上角目标 badge（OpenClaw=info / Hermes=muted）、底部 × 删除按钮
- **发布计划预览走动作优先卡片**：徽章在左（新增=ok/绿，更新=info/蓝，已阻止=err/红）→ 名字 → 右箭头 → 目标环境
- 三个区块的卡片视觉权重对等，避免右侧队列/计划显得「薄」

### R3 部署看板

- 二级 segmented 切 agent（OpenClaw / Hermes）
- 纯账本视图：列该 agent 上 status=active 的部署——skill 名、id、来源标记（自研/GitHub）、
  版本、发布时间；`link_missing` 账实核对标记保留
- 顶部筛选器：搜索、来源筛选（all/local/github）、排序（发布时间倒序为默认/名称）
- 操作仅「下架」（回滚入口已移除，见 R5）；下架确认弹窗由看板触发
- 本轮不做翻页；规模问题由筛选器承担

#### R3.1 视觉约定（部署看板）

- **部署列表走 grid 多列卡片**：`grid-template-columns: repeat(3, 1fr)`，断点 1100px→2 列、680px→1 列；同列同高
- **卡片结构对齐 Skill 池**：顶部 source badge（GitHub=info / 自研=muted）+ 名称 → `revision · 发布时间` + `link_missing` 标记（amber）→ 下架按钮贴底
- 部署看板卡片与管理看板 Skill 池卡片同款边框/圆角/间距，三处视觉对等

### R4 操作归位与行为保持

- 「检查 GitHub 更新」「新增 GitHub Skill」**挪至管理看板·GitHub 子 tab 的工具行**
  （与子 segmented 同行右侧）；管理看板·自研子 tab 同一位置显示灰字
  「自研 Skill 由源库目录自动同步，无需登记」；部署看板两者皆无。全局 header 不再
  放置 GitHub 专属按钮——按钮物理贴近其作用域，避免无关视图的视觉噪音
- 全部保留操作行为不变：登记、scan、clone、删除、发布计划预览、发布、下架、检查更新
- 弹窗（ConfirmActionDialog / RegisterGithubDialog）保持全局复用
- 后端 API 契约零改动

### R5 移除回滚入口（2026-09-23 追加）

- 所有视图（含部署看板）均不再显示「回滚」按钮；下架保留
- 原因：现有回滚实现对其声称的核心场景（发布新版翻车→退回旧版）无效——
  发布链接在两种来源下都指向稳定路径（源库目录 / 单目录原地 checkout 的缓存），
  快照记录的 previous_link_target 恒等于当前路径，且 rollback 不执行
  git checkout 旧版本；「误下架恢复」这一唯一有效场景在前端无入口
- 后端 rollback 端点与快照机制保留不动；修复作为独立后续任务

## Constraints

- 纯前端重组，仅改 `apps/skill-manager/`
- 不新增依赖
- 遵循现有 Tailwind 样式风格与组件命名习惯
- basePath `/skills` 配置不变

## Acceptance Criteria

- [ ] 访问 `/skills` 默认显示管理看板·自研子 tab，仅含 source=local 的 skill
- [ ] 管理看板·GitHub 子 tab 仅含 source=github 的 skill，源工具行右侧出现「检查更新」「新增 GitHub Skill」
- [ ] URL `?view=manage&tab=github` / `?view=board&agent=hermes` 直达对应视图；刷新后保持；非法值回退
- [ ] 自研子 tab 入队 skill 后切到 GitHub 子 tab，队列中不出现该 skill；切回后队列仍在
- [ ] 部署看板二级 segmented 可切 OpenClaw/Hermes，列表仅显示该 agent 的 active 部署，
      含来源标记与 link_missing 标记；筛选器可用
- [ ] 看板下架后该条目消失，对应管理子 tab 卡片 badge 同步变为「未发布」
- [ ] 管理看板内无已部署区块、无回滚按钮；部署看板内无回滚按钮
- [ ] 发布、下架、clone、删除、检查更新、登记全链路手工验证通过
- [ ] `pnpm build` 与 `pnpm lint` 通过；既有单元测试（queue.test.ts）通过

## Notes

- 设计决策记录（2026-09-23）：
  - 发布队列每来源独立；自研侧本轮纯重组不加管理能力
  - 回滚入口移除（详见 R5）；GitHub 回滚修复另开后续任务
  - 导航从「单页混装」→「三平级 tab」→ 定稿为「两级导航」：一级按职责
    （管理看板/部署看板），二级管理切来源、看板切 agent；用户明确提出
    「agent 类型」词汇，为未来新增 agent 环境预留扩展
  - 翻页这轮不做，筛选器承担规模
  - 「启用状态」筛选项移除：后端无路径写入 deprecated，筛选器永远只能选 active，
    是纯 UI 噪音；后端字段（RegistrySkill.status、schema CHECK、SkillCard.status、
    SkillPool deprecated badge 渲染）保留，将来要支持 deprecated 流转时把筛选器
    加回来即可
  - **视觉约定定型（R2.1 / R3.1）**：三处卡片（Skill 池 / 队列+计划 / 部署看板）统一走
    grid 多列（3→2→1 自适应）+ 同列同高 + 完整技能卡结构；队列项右上角多目标 badge，
    计划项动作优先（徽章左对齐）。设计原型见 `prototype.html`，本轮实现以此为准
