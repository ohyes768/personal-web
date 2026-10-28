# 技术设计：已收录小区多选合并

## 改动面

| 文件 | 改动 |
|------|------|
| `apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx` | CatalogTable 加多选列（仅 admitted 且启用时）；selection 状态；批量操作条；接入 MergeDialog |
| `apps/housing-map/src/components/community/MergeDialog.tsx`（新文件） | 合并弹框：保留方单选 + 预览 + 提交 |
| `apps/housing-map/src/app/globals.css` | `.catalog-selectable` 列宽规则（含 checkbox 列）；窄屏卡片态处理 |

后端零改动。

## 数据与接口

- 合并：`POST /api/map/directory/communities/{被并方id}/merge`，body `{ community_id: 保留方id }`（`AssociationInput`）。
- 保留 N 条提交 N-1 次调用，全部指向保留方；`workflowRequest` 逐条 await，收集 `{id, ok, error}` 结果。
- 行数据已含 `position`、`sources`、`coverage`、`market_state` 等字段（CatalogRow），预览不需要额外请求。
- 默认预选：`position` 有坐标 → `sources.length` 降序 → 原顺序。

## 交互与状态

- `selection: string[]` 存于 DirectoryFlowWorkspace；`filterChanged()`（翻页/筛选/切 Tab）时清空，与 `removal` 先例一致。
- CatalogTable 新增可选 props：`selected?: string[]`、`onToggle?: (id) => void`，仅 admitted 模式传入；表格加 `catalog-selectable` class 区分列宽。
- 批量操作条：复用 `directory-actions` 样式，放列表上方工具栏区，文案「已选 N 条 · 合并所选（N） · 取消选择」。
- MergeDialog 用现有 `DirectoryDialog` 外壳；确认按钮在市场状态混合时文案为「确认合并（保留方市场状态将生效）」。
- 提交中逐条执行并在弹框内显示进度/结果；全部结束后触发列表 revision 刷新（复用现有加载机制）。

## CSS 列宽

`.catalog-admitted` 现为 7 列：25/10/17/12/10/15/11%。加 checkbox 后 8 列，在 `.catalog-selectable.catalog-admitted` 下重排，例如：选择 4% + 其余按 24/10/16/12/10/14/10 压缩（实现时按视觉微调）。不带 selectable 的表沿用现有规则，互不影响。窄屏卡片态：checkbox 单元格不带 data-label 语义问题不大，但需确认窄屏规则（globals.css ~1291 媒体查询）不因新列错位；必要时窄屏隐藏选择列。

## 权衡记录

- 前端循环调用 vs 后端 batch 端点：选循环。个位数条目、每条本身是事务，失败可逐条报告；batch 端点是为不值得的抽象。
- 合并确认不另做 confirm dialog：MergeDialog 本身带预览和明确按钮，即是确认步骤。
- 不做跨页多选：重复项通常相邻（同名搜索可聚齐），跨页状态管理复杂度不值。

## 回滚

纯前端改动，`git revert` 单提交即可回滚；线上数据合并操作有事件记录（merge event 含 previous payload），数据层面可人工恢复。
