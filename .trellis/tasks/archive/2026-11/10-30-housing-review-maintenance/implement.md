# 实施计划

## 三状态转换补充
- [x] 先补重新审核/完成审核API、持久化、旧决定保护和下游范围测试，确认失败；补前端操作矩阵测试。
- [x] 扩展准入事务及投影、专用路由，前端列表与详情共用操作组件，文案解释复核和完成后的分类。
- [x] 跑后端准入/流水线/位置/用途及前端测试、lint/tsc/build，更新契约与验证记录。

目标：撤销统一待处理后，以两个主 Tab 组织原审核及数据关联流程。

- [x] 检查后续提交与未提交文件，git revert 04e0380，保留股息率改动。
- [x] 在 apps/housing-map/tests/catalog-filters.test.cjs 增加主导航和审核/维护隔离断言，运行 node --test tests/catalog-filters.test.cjs 确认预期失败。
- [x] 修改 apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx：增加 ManagementTabs；CatalogTabs 仅保留审核三状态；按 mode 选择二级控件；原业务分支不变。
- [x] 更新 community-review.test.cjs 入口断言，运行相关 node:test 回归与 pnpm exec tsc --noEmit、pnpm lint、pnpm build。
- [x] 浏览器验证审核地点筛选、维护两事项及窄屏；静态核对 laipai 初始 mode 与 focusPosition 的 mode 分支未改变；按 trellis-check 检查并记录结果，更新 directory-flow.md 导航契约。

实施方式：本会话内联执行。此次仅授权回退提交；新实现留在工作区供审阅，不自动推送。
