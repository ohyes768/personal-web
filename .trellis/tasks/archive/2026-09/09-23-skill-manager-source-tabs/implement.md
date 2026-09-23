# implement — skill-manager 前端两级导航（管理看板 × 部署看板）

## 前置

```bash
cd apps/skill-manager && pnpm build   # 基线：改动前构建通过
```

## 执行清单

### Step 1 — SkillFilters 去 source / status 化 ✅

- [x] `FilterState` 删除 `source` 与 `status` 字段；`DEFAULT_FILTERS` 同步
- [x] UI 删除「来源」「启用状态」两个下拉
- [x] 验证：`npx tsc --noEmit` 通过

### Step 2 — 新建 SourceWorkspace（管理看板两件套）✅

- [x] `components/SourceWorkspace.tsx`：按 design §3 接口实现
- [x] 搬入：`applyFilters`（去 source/status 分支）、`allTags`（本来源）、`handleAddToQueue`、
      `handleGeneratePlan`、`performPublish`、`planToRequests`、`publishableCount`、发布确认弹窗
- [x] 不含已部署区块（部署集中到 DeployBoard）
- [x] 核实 SkillPool：删除按钮条件 `skill.source === 'github' || source_missing` ✅ 无需修改；
      Clone 按钮仅在 `cache_missing` 时渲染（local 恒 false）✅ 无需修改；onClone 签名补 skillName
- [x] **视觉约束（R2.1）**：Skill 池 `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3`（Tailwind
      标准断点 768/1024，替代原型自定义 680/1100——不新增配置）、同列同高（li flex-col +
      items-stretch）、summary `line-clamp-2`（既有）、操作行 `mt-auto` 贴底；PublishQueue
      队列项改完整技能卡（名称/ID/右上角目标 badge × 移除/底部移出）、计划项动作优先（徽章左）

### Step 3 — 新建 DeployBoard（部署看板）✅

- [x] `components/DeployBoard.tsx`：改造自 DeployedView 的 active 部署提取逻辑
- [x] 二级 segmented（OpenClaw/Hermes，受控：page 层 URL 派生传入）；筛选行：搜索/来源/排序
      （默认发布时间倒序）；列表：skill 名、id、来源标记、版本、发布时间、
      link_missing 标记、[下架]
- [x] 空态与筛选无结果态（两种文案区分）
- [x] **视觉约束（R3.1）**：grid 多列 3→2→1、卡片结构对齐 Skill 池（source badge + 名 /
      revision + 时间 + link_missing / 下架贴底）
- [x] 验证：`npx tsc --noEmit` 通过

### Step 4 — page.tsx 重构为两级导航 ✅

- [x] 导航状态：`useSearchParams` 派生（URL 唯一真源）`view/tab/agent`，`router.replace` 写；
      非法值逐级回退（view→manage，tab→local，agent→openclaw）；Suspense 包裹（Next 15 要求）
- [x] 两个 view + 两个 SourceWorkspace 常驻挂载，非活动 Tailwind `hidden`
- [x] 管理 view 顶部 source-toolbar：左侧 sourceSeg（自研/GitHub 子 segmented，带计数），
      右侧 sourceActions 按 view+source 互斥显示（自研：localHint 灰字；GitHub：
      检查更新 + 新增登记；部署看板均不显示）
- [x] header 仅保留标题 + 一级 tab
- [x] page 层保留：数据加载、notice、下架/clone/删除确认弹窗、RegisterGithubDialog
- [x] 移除回滚：`rollbackSkill` 从 api.ts 删除、page 无 rollback 分支
- [x] 删除 `components/DeployedView.tsx`
- [x] 实施中发现并修复：`router.replace('/skills?…')` 在 basePath 下双拼为 /skills/skills
      （Next router 路径不含 basePath），改为 `/?…`

### Step 5 — 手工验证（preview）✅（有环境限制，见下）

- [x] dev 前端(3010) + 后端(8097) 启动，`/skills` 全链路浏览器验证
- [x] 默认 view+tab、URL 直达（?view=board&agent=hermes）、导航后 URL 同步
- [x] 队列隔离：自研入队 1 项 → GitHub 子 tab 队列 0 → 切回仍有 1
- [x] 部署看板 segmented 切换、来源筛选、有数据渲染（直插 dev SQLite 三条记录后验证，
      已清理）、link_missing 标记、下架弹窗 + 后端 409 拒绝时错误展示、管理看板
      badge 同步（ask-me 卡显示「Hermes 已发布 · 链接缺失」）
- [x] 网络面板无未解释错误
- ⚠️ **环境限制**：本机 Windows 无 symlink 特权（WinError 1314），发布/clone 写链路无法
      端到端实测（后端原子替换依赖 symlink）；该链路代码为旧 page.tsx 原样搬移 + 原型层
      已验证交互，生产在 Linux 容器不受影响
- ⚠️ `pnpm build` 的 standalone 输出阶段因同因（symlink EPERM）失败；编译与类型检查阶段
      通过（`tsc --noEmit` 单独验证通过）

### Step 6 — 收尾

- [x] `pnpm lint` 0 error 0 warning；`npx tsc --noEmit` 通过；queue.test.ts 6/6 通过
- [ ] 按流程走 spec 更新 → commit

## 回滚点

- Step 1-4 之间：任一步失败可 `git checkout -- apps/skill-manager`（开始前确认
  `git status` 干净）
- 完成后回滚：revert 该前端提交即可，无数据迁移

## 风险

- R1 useSearchParams/Suspense：已用 Suspense 包裹解决，build 编译阶段通过
- R2 两 view 常驻挂载的重复请求：数据由 page 层单点加载下发，视图不发请求，无风险
- R3 看板下架与维护 badge 的一致性：同一 `skills` state 单点更新后全量重渲染，
  preview 已实测（下架 409 场景与渲染同步均正常）
