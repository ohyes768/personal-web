# 执行计划：已收录小区多选合并

前置：PRD、design 已评审；`task.py start` 已执行。

## 步骤清单

1. [x] 新建 `MergeDialog.tsx`：保留方单选、预览（别名并入/地址坐标差异/记录迁移）、市场状态混合高亮、提交逻辑（逐条 `POST /directory/communities/{id}/merge`，收集逐条结果）
   - 验证：`cd apps/housing-map && pnpm build` 通过（组件暂未被引用时用临时引用编译验证）
2. [x] `DirectoryFlowWorkspace.tsx`：CatalogTable 加 `selected`/`onToggle` 可选 props 与 `catalog-selectable` class；admitted 模式下接入 selection 状态；`filterChanged` 清空；批量操作条；挂 MergeDialog
   - 验证：`pnpm build` 通过；待处理/不收录模式表格 DOM 无 checkbox
3. [x] `globals.css`：`.catalog-selectable` 8 列列宽规则；窄屏卡片态检查（必要时隐藏选择列）
   - 验证：浏览器宽屏 checkbox 列正常宽度，待处理/不收录列宽不变；窄屏（≤ 手机宽度）布局不塌
4. [x] 浏览器端到端验证（隔离副本库造 5 条假小区，开发库未改动）
   - 验证：多选 → 弹框预选正确 → 合并成功 → 列表只剩保留方 → 保留方别名含被并方名称 → 逐条失败场景（造租金来源冲突）已成功项不回滚
   - 实测细节见 `prd.md` 验证记录表
5. [ ] 真实数据操作由用户决定：水晶城 3 条在页面自行合并（实施者不碰生产数据）

## 验证命令

```bash
cd apps/housing-map && pnpm build
# 浏览器：pnpm dev 后经 preview 工具走验收清单（端口 3007，basePath /map）
```

注意：同一 app 只跑一个 dev server 实例；改 CSS 不生效时删 `.next` 重启。

## 回滚点

- 每步一个 commit；任一步 build 失败回退该步。
- 整体回滚 = revert 前端提交，后端无改动。
