# 待确认的提交计划

1. `feat(housing-map): unify rental updates and candidate review`

包含本任务代码、测试、规范及任务文档：

- .trellis/spec/backend/housing-map/backend/rental-sources.md
- .trellis/spec/guides/housing-map-rental-reference.md
- apps/housing-map/src/components/community/CommunityManagement.tsx
- apps/housing-map/src/components/rental/RentalAssociationReview.tsx
- apps/housing-map/src/components/rental/RentalRefreshButton.tsx
- apps/housing-map/src/lib/rental-dashboard.ts
- apps/housing-map/src/lib/rental-types.ts
- apps/housing-map/src/lib/use-rental-refresh.ts
- apps/housing-map/tests/rental-dashboard.test.cjs
- backend/housing-map/src/api/rental_routes.py
- backend/housing-map/src/api/rental_source_routes.py
- backend/housing-map/src/services/rental_reference/association.py
- backend/housing-map/src/services/rental_reference/refresh.py
- backend/housing-map/tests/test_rental_api.py
- backend/housing-map/tests/test_rental_association_flow.py
- .trellis/tasks/10-13-housing-rental-update-flow/task.json
- .trellis/tasks/10-13-housing-rental-update-flow/prd.md
- .trellis/tasks/10-13-housing-rental-update-flow/design.md
- .trellis/tasks/10-13-housing-rental-update-flow/implement.md
- .trellis/tasks/10-13-housing-rental-update-flow/implement.jsonl
- .trellis/tasks/10-13-housing-rental-update-flow/check.jsonl
- .trellis/tasks/10-13-housing-rental-update-flow/verification.md
- .trellis/tasks/10-13-housing-rental-update-flow/commit-plan.md

不包含的其他改动：

- `apps/housing-map/src/app/globals.css`（本轮未编辑）
- `.pnpm-store/`（运行环境缓存）

用户已确认提交并推送。只暂存上面的明确文件，不包含其他改动，不部署。
