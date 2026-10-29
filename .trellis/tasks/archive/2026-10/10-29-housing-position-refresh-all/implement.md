# 楼盘地点与类型全量更新 Implementation Plan

**Goal:** 为已确认的三个入口补齐真正的全量重查。
**Architecture:** 新增 refresh_all 模式，沿用 PositionJob 和 position_one(force=True, automatic=True)。旧 all 保持内部补缺语义；人工保护、失败保留有效结果及请求预算沿用现有实现。
**Tech Stack:** FastAPI/Pydantic、pytest、React/Next.js、Node test。

## 执行
- [x] test_collection_pipeline.py 覆盖各状态全量重查、人工地点/决定保护、类型更新和 API 枚举；directory-flow.test.cjs 覆盖三按钮请求及禁用状态。
- [x] 先运行新增测试，确认因 refresh_all/按钮缺失失败。
- [x] directory_position.py 接受 refresh_all，该模式放开自动结果状态跳过，传 force=True，保留 manual 和 fresh automatic scope 保护。
- [x] directory_workflow_routes.py 的 PositionStart.mode 加 refresh_all；DirectoryFlowWorkspace.tsx 增加更新全部按钮及范围说明，继续匹配保持 unqueried。
- [x] 更新 collection-pipeline.md 与 directory-position.md，记录新模式和旧默认兼容。
- [x] 后端 .venv/Scripts/python -m pytest --basetemp=.pytest-tmp-position-refresh；前端 node --test tests/*.test.cjs、npm run lint、npx tsc --noEmit、npm run build。

## 回滚
移除 refresh_all 枚举、按钮及服务分支，无需迁移数据。只修改本任务文件，不操作 fund-select 改动。
