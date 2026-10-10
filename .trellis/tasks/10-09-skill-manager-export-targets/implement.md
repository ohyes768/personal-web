# 执行计划：外部导出目标与版本台账

基线：master 或其上的活跃分支（开工时确认；上一任务分支未合则先合/先处理）。
上下文顺序：implement.jsonl → prd.md → design.md → implement.md。

## Task 1：目标模型 + 守卫 + DB 迁移

- [x] models.py：TargetKey 加 WINDOWS_CODEX/WINDOWS_CLAUDE；TargetKind、
  TARGET_KINDS、target_kind()；前端 lib/targets.ts 同步（后端先行提交内
  仅后端部分）。
- [x] db.py：deployment 加 content_hash 列（_SCHEMA + PRAGMA/ALTER 启动
  迁移）；DeploymentRecord 加字段；store 提供 record_export（upsert）与
  delete_export（按 skill+target 清除）。
- [x] 守卫：`_require_link_target` 进 publish/unpublish/plan/回滚入口；
  test_api：export 目标走发布 → 400（AC1）；link 全流程既有测试零回归。
- 验证：`python -m pytest backend/skill-manager/tests/ -q`（仅 2 项既有漂移）。

## Task 2：内容哈希 + 导出端点

- [x] 新 src/services/hashing.py（dir_hash）+ 单测（字节变/改名变/跨平台 posix）。
- [x] routes.py `POST /skills/{id}/export`：zip 打包（固定 date_time、目录为根、
  流式）、台账 upsert、history action="export"、GitHub 缓存缺失 400（AC3）；
  免密。
- [x] 单测：自研导出 zip 内容与源目录一致（zipfile 读回断言，AC2）、重复
  导出覆盖哈希、GitHub 缺缓存 400、export 后 list_deployments 出记录。
- 验证：定向 pytest 绿。

## Task 3：stale 计算 + 前端

- [x] list_skills 组装：export 记录的 stale=dir_hash(当前源/缓存)≠recorded；
  TargetDeployment 加 stale 字段（link 恒 False）；单测（AC4：改源文件→
  stale，重新导出→不 stale）。
- [x] 前端：lib/targets.ts、TargetDeployment.stale 类型、卡片 export chip
  （版本短码/时间/stale 黄点）、ExportDialog（选目标→下载 zip→notice→
  刷新）、chip 删除记录、发布队列只列 link 目标。
- [x] 验证：后端定向 + 全量（2 项既有漂移例外）；前端
  `pnpm exec tsc --noEmit && pnpm lint && pnpm test`；preview E2E：
  导出自研 skill 下载 zip → chip 出现 → 改源文件 → 黄点"源已更新" →
  重新导出 → 黄点消失（截图）。

## Task 4：收尾

- [x] 旧库迁移单测（AC5：无列旧库启动补列、旧记录不 stale）。
- [x] docs/skill-manager-nas-setup.md 增 export 目标段落；spec 沉淀
  （目标两类模型进 skill-manager-github-cache.md 或 frontend 契约）。
- [x] trellis-check 全量审查完成（3 项既有部署配置漂移单列）。
- [ ] 提交（后端/前端/docs 分 commit）：2026-10-10 用户已授权，执行中。
- [ ] 推送：2026-10-10 用户已授权，提交与归档后执行；不创建 PR。

## 回滚点

- 每 Task 一 commit；Task 1（模型/DB）向后兼容可独立 revert；Task 3 前后端
  契约同 PR。整体 revert 无数据迁移负担（新列默认值无害）。
