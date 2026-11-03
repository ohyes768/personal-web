# 移除租金页签实施计划

用户已批准范围；按轻量任务在当前会话内实施。

- [x] 更新 community-tabs.test.cjs 和 boundary-workflow.test.cjs 的既有断言：不再存在「租金与收益」，保留概况和可选轮廓；运行确认旧实现失败。
- [x] 在 CommunityDetailTabs.tsx 删除租金组件导入、rental 状态、按钮和面板，保留其余插槽及无障碍关联。
- [x] 同步 housing-map-rental-reference.md 与 boundary-workflow.md 的详情导航契约；保留未挂载租金组件，避免覆盖其他工作。
- [x] 运行前端全部 node:test、ESLint 与 TypeScript 检查，复核改动范围。仅提交本任务改动并推送，保留其他工作。

## 验证结果

- 前端 node:test：202/202 通过。
- npm run lint：通过。
- npx tsc --noEmit --incremental false：通过。
- 本次涉及文件 git diff --check：通过。
- 代码已完成；用户已授权提交并推送，仅处理本任务范围。
