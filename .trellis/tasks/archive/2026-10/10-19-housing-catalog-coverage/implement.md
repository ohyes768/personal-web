# Implementation plan

使用 writing-plans 整理；按已批准方案在当前会话内实施。

- [x] test_directory_flow.py 用真实 registry、CommunityBatch/publish_run 测去重、租金状态、换源和筛选分页。先确认 coverage 断言失败。
- [x] 新增 directory_coverage.py，在 directory_workflow_routes.py catalog/detail 调用，先过滤后分页。
- [x] directory-flow.test.cjs 添加SSR输出测试并确认失败；更新 DirectoryFlowWorkspace.tsx 列、筛选和详情；globals.css 调整布局。
- [x] 后端 .venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp-catalog-coverage；前端 node --test tests/*.test.cjs、pnpm exec tsc --noEmit、pnpm lint、pnpm build。
- [x] 桌面/窄屏验证、Impeccable detector、diff复核、记录结果与字段契约。未授权提交或发布，保留可审阅改动。
