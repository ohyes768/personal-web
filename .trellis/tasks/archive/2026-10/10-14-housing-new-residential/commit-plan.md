# 已确认的提交方案

## 工作提交
`feat(housing-map): 支持新房住宅证据与位置补全`

仅提交以下 housing-map 代码、行为回归、规范及本任务文档；用户已批准提交并推送至 origin/master；不部署。

- .trellis/spec/backend/housing-map/backend/community-admission.md
- .trellis/spec/backend/housing-map/backend/community-auto-review.md
- .trellis/spec/backend/housing-map/backend/community-directory.md
- .trellis/spec/backend/housing-map/backend/index.md
- apps/housing-map/src/components/community/CommunityWorkspace.tsx
- apps/housing-map/src/components/community/DirectoryCards.tsx
- apps/housing-map/tests/community-review.test.cjs
- backend/housing-map/src/api/directory_routes.py
- backend/housing-map/src/services/amap_directory.py
- backend/housing-map/src/services/community_admission.py
- backend/housing-map/src/services/community_auto_review.py
- backend/housing-map/src/services/data_loader.py
- backend/housing-map/src/services/directory_collection.py
- backend/housing-map/src/services/residential_classifier.py
- backend/housing-map/src/services/tmsf_property_type.py
- backend/housing-map/tests/test_community_auto_review.py
- backend/housing-map/tests/test_directory_api.py
- backend/housing-map/tests/test_tmsf_property_type.py
- .trellis/spec/backend/housing-map/backend/community-enrichment.md
- backend/housing-map/src/services/community_enrichment.py
- backend/housing-map/tests/test_community_enrichment.py
- .trellis/tasks/10-14-housing-new-residential/implement.md
- .trellis/tasks/10-14-housing-new-residential/prd.md
- .trellis/tasks/10-14-housing-new-residential/qa.md
- .trellis/tasks/10-14-housing-new-residential/task.json
- .trellis/tasks/10-14-housing-new-residential/implement.jsonl
- .trellis/tasks/10-14-housing-new-residential/check.jsonl
- .trellis/tasks/10-14-housing-new-residential/design.md

- .trellis/tasks/10-14-housing-new-residential/commit-plan.md

## 其他改动（不纳入）
- .trellis/.template-hashes.json
- .pnpm-store/（本机依赖缓存）

## 确认后收尾
先提交上述工作，再按 trellis-finish-work 归档当前任务并记录会话；其他任务不归档。
工作树还有并行工作时，只处理以上明确列出的文件。
