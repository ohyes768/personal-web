# 提交计划

1. `feat(skill-manager): 支持 Hermes 多 profile 安装目标`

   - `.trellis/spec/backend/skill-manager/backend/index.md`
   - `.trellis/spec/backend/skill-manager/backend/profiles.md`
   - `.trellis/spec/guides/index.md`
   - `.trellis/spec/guides/skill-manager-export-targets.md`
   - `.trellis/spec/guides/skill-manager-frontend.md`
   - `.trellis/spec/guides/skill-manager-github-cache.md`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/commit-plan.md`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/design.md`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/implement.md`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/prd.md`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/task.json`
   - `.trellis/tasks/10-14-skill-manager-hermes-profiles/verification.md`
   - `apps/skill-manager/src/app/page.tsx`
   - `apps/skill-manager/src/components/DeployBoard.tsx`
   - `apps/skill-manager/src/components/InstallDialog.test.ts`
   - `apps/skill-manager/src/components/InstallDialog.tsx`
   - `apps/skill-manager/src/components/ProfileViews.test.ts`
   - `apps/skill-manager/src/components/SkillPool.test.ts`
   - `apps/skill-manager/src/components/SkillPool.tsx`
   - `apps/skill-manager/src/components/SourceWorkspace.tsx`
   - `apps/skill-manager/src/lib/api.ts`
   - `apps/skill-manager/src/lib/collections.ts`
   - `apps/skill-manager/src/lib/installTargets.tsx`
   - `apps/skill-manager/src/lib/targets.test.ts`
   - `apps/skill-manager/src/lib/targets.ts`
   - `backend/skill-manager/src/api/routes.py`
   - `backend/skill-manager/src/config.py`
   - `backend/skill-manager/src/db.py`
   - `backend/skill-manager/src/main.py`
   - `backend/skill-manager/src/models.py`
   - `backend/skill-manager/src/services/install.py`
   - `backend/skill-manager/src/services/migration.py`
   - `backend/skill-manager/src/services/publisher.py`
   - `backend/skill-manager/src/services/targets.py`
   - `backend/skill-manager/tests/test_direct_cache_links.py`
   - `backend/skill-manager/tests/test_profiles.py`
   - `deploy/docker-compose.skill-manager-profiles.example.yml`
   - `docker-compose.nas.yml`
   - `docs/skill-manager-nas-setup.md`
   - `scripts/start-skill-manager-dev.bat`

不纳入本次提交：

- `.trellis/.template-hashes.json`：之前补齐 Codex 集成产生的独立改动。
- `.pnpm-store/`：工作开始前已存在的未跟踪依赖缓存。

验证：后端 257 项、前端 48 项、TypeScript、ESLint、生产构建均通过；浏览器模拟 API 的双目标部分成功和精确失败重试已验证。无真实 NAS/Hermes 操作。

按 `.trellis/workflow.md` Phase 3.4 的一次确认门槛等待用户答复。回复“行”/“ok”后仅按此文件清单提交，不 amend、不 push；归档与 journal 另按 finish-work 处理。
