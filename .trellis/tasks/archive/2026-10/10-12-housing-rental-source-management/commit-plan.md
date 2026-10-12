# 提交计划

1. `feat(housing-map): 添加租金来源管理与顶部更新入口`

本次代码、回归测试、来源限制说明、规范和任务规划/验收一并提交；归档和journal另行收尾。

文件清单：

- `.trellis/spec/backend/housing-map/backend/index.md`
- `.trellis/spec/backend/housing-map/backend/rental-sources.md`
- `.trellis/spec/guides/housing-map-rental-reference.md`
- `.trellis/spec/guides/index.md`
- `.trellis/tasks/10-12-housing-rental-source-management/check.jsonl`
- `.trellis/tasks/10-12-housing-rental-source-management/commit-plan.md`
- `.trellis/tasks/10-12-housing-rental-source-management/design.md`
- `.trellis/tasks/10-12-housing-rental-source-management/implement.jsonl`
- `.trellis/tasks/10-12-housing-rental-source-management/implement.md`
- `.trellis/tasks/10-12-housing-rental-source-management/prd.md`
- `.trellis/tasks/10-12-housing-rental-source-management/task.json`
- `.trellis/tasks/10-12-housing-rental-source-management/verification.md`
- `apps/housing-map/src/app/globals.css`
- `apps/housing-map/src/app/page.tsx`
- `apps/housing-map/src/components/community/CommunityRentalReference.tsx`
- `apps/housing-map/src/components/map/BinjiangMap.tsx`
- `apps/housing-map/src/components/rental/RentalRefreshButton.tsx`
- `apps/housing-map/src/components/rental/RentalSourceManager.tsx`
- `apps/housing-map/src/lib/rental-sources.ts`
- `apps/housing-map/src/lib/rental-types.ts`
- `apps/housing-map/src/lib/use-rental-data.ts`
- `apps/housing-map/src/lib/use-rental-refresh.ts`
- `apps/housing-map/src/lib/use-rental-summary.ts`
- `apps/housing-map/tests/rental-dashboard.test.cjs`
- `apps/housing-map/tests/rental-reference.test.cjs`
- `apps/housing-map/tests/rental-sources.test.cjs`
- `backend/housing-map/.gitignore`
- `backend/housing-map/Dockerfile`
- `backend/housing-map/scripts/FANG_RENTALS.md`
- `backend/housing-map/src/api/rental_routes.py`
- `backend/housing-map/src/api/rental_source_routes.py`
- `backend/housing-map/src/main.py`
- `backend/housing-map/src/services/rental_reference/refresh.py`
- `backend/housing-map/src/services/rental_reference/sources.py`
- `backend/housing-map/tests/test_rental_sources.py`

未识别本地文件（不纳入提交）：

- `.pnpm-store/`（任务开始前已存在）

用户已于 2026-10-12 回复“行”，批准按此清单提交；不推送、不部署。
