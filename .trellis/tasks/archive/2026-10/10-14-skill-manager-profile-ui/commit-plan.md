# 提交计划

1. `feat(skill-manager): 支持网页管理 profile 安装目标`

   - `.trellis/spec/backend/skill-manager/backend/profiles.md`
   - `.trellis/spec/guides/skill-manager-frontend.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/check.jsonl`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/commit-plan.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/design.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/implement.jsonl`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/implement.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/prd.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/research/findings.md`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/task.json`
   - `.trellis/tasks/10-14-skill-manager-profile-ui/verification.md`
   - `apps/skill-manager/src/app/page.tsx`
   - `apps/skill-manager/src/components/InstallTargetManager.test.ts`
   - `apps/skill-manager/src/components/InstallTargetManager.tsx`
   - `apps/skill-manager/src/lib/api.ts`
   - `apps/skill-manager/src/lib/installTargets.tsx`
   - `backend/skill-manager/src/api/routes.py`
   - `backend/skill-manager/src/config.py`
   - `backend/skill-manager/src/db.py`
   - `backend/skill-manager/src/models.py`
   - `backend/skill-manager/src/services/install.py`
   - `backend/skill-manager/src/services/targets.py`
   - `backend/skill-manager/tests/test_deployment_files.py`
   - `backend/skill-manager/tests/test_profiles.py`
   - `backend/skill-manager/tests/test_target_ui.py`
   - `deploy/docker-compose.skill-manager-profiles.example.yml`
   - `docker-compose.nas.yml`
   - `docs/skill-manager-nas-setup.md`
   - `scripts/start-skill-manager-dev.bat`

不纳入本任务提交（并行或既有改动）：

- `.trellis/.template-hashes.json`
- `apps/housing-map/next-env.d.ts`
- `apps/housing-map/src/components/community/CommunityWorkspace.tsx`
- `apps/housing-map/src/components/community/DirectoryCards.tsx`
- `apps/housing-map/tests/community-review.test.cjs`
- `backend/housing-map/src/api/directory_routes.py`
- `backend/housing-map/src/services/amap_directory.py`
- `backend/housing-map/src/services/community_admission.py`
- `backend/housing-map/src/services/community_auto_review.py`
- `backend/housing-map/src/services/data_loader.py`
- `backend/housing-map/src/services/directory_collection.py`
- `backend/housing-map/src/services/residential_classifier.py`
- `backend/housing-map/src/services/tmsf_property_type.py`
- `backend/housing-map/tests/test_community_auto_review.py`
- `backend/housing-map/tests/test_directory_api.py`
- `backend/housing-map/tests/test_tmsf_property_type.py`
- `.pnpm-store/`
- `.trellis/tasks/10-14-housing-new-residential/`
- `backend/housing-map/src/services/community_enrichment.py`
- `backend/housing-map/tests/test_community_enrichment.py`

后端275项、前端52项、TypeScript/ESLint/production build及本机真实测试后端浏览器联调通过。父目录挂载前置改动纳入本任务。未操作真实NAS/Hermes。

按工作流 Phase 3.4 等待一次提交确认；确认后仅按本清单提交，不 amend，不 push（除非用户另行授权）。
