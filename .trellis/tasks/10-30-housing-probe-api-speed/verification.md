# 验证记录（2026-10-30）

## 原因及方案证据
线上只读查询最近两次人工选择的持久化诊断：4请求，11.797/12.001秒，限速等待8.93秒、HTTP2.78/2.93秒。检查代码发现前半段资料与入口API化，末尾仍双HTML。
单次只读上游列表API探测返回20行，全部明确属于目标nid，旧入口seed不在第一页。因此替换为列表API并使用返回行中的已核验seed，不以锚点URL、搜索结果或旧seed推断归属。未修改线上库、未触发真实关联。

## 测试
- TDD：source_api新增/更新用例实现前10失败35通过，明确为旧5请求、双HTML以及未验证新列表；前端进度用例因缺函数失败。随后补冷却回归先复现entry_not_found误报，再修复。
- 后端最终187 passed：test_xingfuli_source_api/test_rental_probe/test_matching_speed/test_xingfuli_discovery/test_xingfuli_rentals/test_rental_xingfuli_sources/test_rental_split/test_rental_refresh；F盘隔离basetemp。两个既有Starlette/httpx/anyio弃用警告，无失败。
- 前端全量178 passed；pnpm lint、pnpm exec tsc --noEmit、pnpm build退出0。恢复构建自动变更的next-env.d.ts。
- 真实适配器断言冷启动4请求、人工选择3请求；坏/空/混归属列表不绑定、从实时列表换seed、严格URL白名单、预算、取消、验证码冷却、核验不读旧缓存均覆盖。
- 浏览器以本机dev和拦截响应验证390px弹窗显示“正在核验租房列表的小区归属”；截图progress-mobile.png已查看。

## 结论及边界
默认关联减少一次真实请求和一次3秒间隔，预计比约12秒基线节省3～4秒；未部署，不能声称线上耗时已下降。保留3秒共享间隔、任务与发布锁、新鲜资料及人工决定校验。
兼容注入旧适配器仍执行原双HTML接口；默认网页适配器使用新列表API。前后端外部probe路由不变。
工作区其他会话的新房租金排除改动（association.py、rental-sources.md等）与原速度任务预览均未修改。新实现未提交、未推送、未部署；任务暂留in_progress供审阅提交。
