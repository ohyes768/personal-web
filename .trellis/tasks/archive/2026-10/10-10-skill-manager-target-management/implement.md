# 导出目标管理执行计划

Goal: 在管理台持久化维护 ZIP 导出目标并复用现有台账。
Architecture: SQLite export_target + 管理 API + 页面共享目标状态。
Tech Stack: FastAPI/Pydantic/SQLite，Next.js/React/TypeScript。

- [x] 后端先补测试：默认目标一次迁移、CRUD、重复与保留 ID、停用导出、记录阻止删除、自定义目标列表/stale/清除、发布拒绝。范围 backend/skill-manager/tests/test_api.py 与 test_exporting.py，可拆 test_targets.py。
- [x] 在 src/models.py 声明目标配置与请求响应模型；src/db.py 增加目标表、一次性种子迁移和存储 CRUD。
- [x] API 增加 /api/export-targets 读写；调整导出/清除与部署列表按动态目标读取，保护 link 发布边界。检查 src/services/migration.py、publisher.py 等全部 TargetKey 转换。
- [x] 前端 src/lib/types.ts、targets.ts、api.ts 增加动态目标契约；新增 ExportTargetManager.tsx；page.tsx 加导航和统一加载/刷新；SourceWorkspace/SkillPool/ExportDialog 消费动态配置。
- [x] 前端补有意义测试覆盖动态选择与空/停用状态，执行 pnpm exec tsc --noEmit、pnpm lint、pnpm test。
- [x] 后端在包目录用虚拟环境运行 pytest tests/test_api.py tests/test_exporting.py tests/test_targets.py --basetemp .pytest-tmp/target-management（新增文件实际名称为准）；随后完整回归，区分既有失败。
- [x] 用隔离数据进行浏览器验收：新增目标、导出并出现台账、改名、停用、删除拦截、清除、删除；保留旧目标与 link 发布。记录证据。
- [x] 更新 .trellis/spec/guides/skill-manager-export-targets.md 与 docs/skill-manager-nas-setup.md；git diff --check；最终按全任务范围审查。

不自动提交、推送或部署。已有未跟踪文件不纳入任务。
