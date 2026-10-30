# 实施计划

## 启动前
- [x] 用户明确批准本轮最终规划，再运行 task.py start。
- [x] 读取 trellis-before-dev、后端 housing-map index、rental-sources、租金参考和名称匹配契约；检查最新差异与并行幸福里任务影响。

## 顺序
1. 提取小区待处理筛选复用点，建立聚合行及 issue 类型，增加服务和只读接口；保留旧 API。
2. 增加 unified_pending 汇总字段并复用同一聚合计数规则，落实地区、状态、去重、排序、先合并后分页。
3. 提取租金详情交互，接入 PendingWorkspace，构建工具栏、统一列表与窄屏卡片；保留其他调用兼容。
4. 顶部移除 rental/auctions，接通 laipai、focusPosition、刷新与任务完成通知；清理失效样式及文案。
5. 补有意义的后端契约及前端交互测试，按 trellis-check 验证，再更新规格与会话记录。

## 验证
- 后端使用项目既有虚拟环境运行 pytest，覆盖新增聚合测试与 tests/test_directory_flow.py、tests/test_rental_api.py；实际测试文件名实现前确认。
- pnpm --dir apps/housing-map exec tsc --noEmit
- pnpm --dir apps/housing-map lint
- pnpm --dir apps/housing-map build
- 沿用 apps/housing-map/tests 的 node:test / TypeScript 装载方式，运行受影响的 directory-flow、catalog-filters、community-management 和 rental-sources 测试及新增统一待处理测试（先检查现有执行方式）。
- 聚合用例：同 ID 多问题、同名不同 ID、独立法拍、多页边界、跳过恢复、未查询排除、地区缺失、筛选计数、pipeline 未启用。
- UI 验证：三类筛选、各弹窗完整处理、行剩余事项、异步切换无旧响应覆盖、空/错/加载状态、手机宽度、地图法拍跳转和定位核对。

## 风险文件及回滚点
DirectoryFlowWorkspace.tsx、CatalogFilters.tsx、RentalAssociationReview.tsx、directory_workflow_routes.py 为主要风险点；不修改并行任务的匹配/采集逻辑。后端只读能力与前端入口迁移分步骤验证；失败时恢复入口即可，不需要数据回滚。

## 执行记录（2026-10-30）
- 已实现聚合服务/API、全局待办计数、三入口导航、统一筛选表格、独立事项弹窗和窄屏样式。
- 未查询识别以存储的 probe stage 为准：旧 source_reviews 的 missing 包括 idle，不直接作为人工待办。
- 原详情弹窗继续负责小区准入，法拍保留原 revision 写入校验和历史同步入口；租金复用幸福里选择确认。
- 新增真实目录数据库只读和法拍绑定集成测试。
- 浏览器视觉及完整点击验收尚未完成：自动审批服务因额度限制拒绝访问本机预览，不绕过。
- 等待最终提交确认；不执行归档，避免将未完成的视觉验收标成完成。
