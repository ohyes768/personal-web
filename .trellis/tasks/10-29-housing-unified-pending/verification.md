# 验证与交付状态（2026-10-30）

## 已通过
- 前端全套 node --test tests/*.test.cjs：177 passed。
- 最后修改后的受影响前端目录/待处理测试：38 passed。
- TypeScript --noEmit：通过；全项目 ESLint：通过；最后改动文件 ESLint：通过。
- 生产构建：首次沙箱内因 Turbopack 内部端口被拒失败，放行内部端口后通过；最终代码构建也已通过。
- 后端全量：1181 passed，9 errors；全部9项错误均为 test_tmsf_browser_protocol.py 的本机端口绑定 PermissionError，放行本地测试端口后该文件33项全部通过。
- 新增 test_directory_pending.py：5 passed，包含真实数据库读取不写库、非pipeline模式、法拍关联后队列更新、跳过与准入不变。
- git diff --check：通过。

## 尚未完成
- 桌面及390px浏览器视觉和完整点击验收。尝试打开隔离本地预览时，自动审批服务因账户额度限制拒绝了该动作；不是产品运行错误，未绕过审批检查。隔离开发服务和示例API已经停止，未修改线上数据。
- 用户已于2026-10-30授权提交并推送。任务保持 in_progress，待视觉验收完成后再归档。

## 提交计划（用户已确认提交并推送）
拟单一提交：`feat(housing-map): 统一小区租金与法拍待处理工作台`

文件范围：
- `apps/housing-map/src/app/globals.css`
- `apps/housing-map/src/components/community/DirectoryFlowWorkspace.tsx`
- `apps/housing-map/src/components/community/PendingWorkspace.tsx`
- `apps/housing-map/src/components/rental/RentalReviewDialog.tsx`
- `apps/housing-map/tests/catalog-filters.test.cjs`
- `apps/housing-map/tests/community-review.test.cjs`
- `apps/housing-map/tests/pending-workspace.test.cjs`
- `backend/housing-map/src/api/directory_workflow_routes.py`
- `backend/housing-map/src/services/directory_pending.py`
- `backend/housing-map/tests/test_directory_pending.py`
- `.trellis/spec/backend/housing-map/backend/directory-flow.md`
- `.trellis/tasks/10-29-housing-unified-pending/（本任务规划与验证文档）`

不包含既有 `.trellis/.template-hashes.json` 和 `.pnpm-store/`，不包含其他任务变更；按用户授权推送到当前分支对应远端。
