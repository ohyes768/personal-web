# 清理 hermes_trigger jobs.json 回退链路

## Goal

hermes_trigger.py 的 jobs.json 回退自 2026-11-07 全量迁移后已是死代码（13/13 任务 prompt 已登记进 task-web），且拖着一串只为它服务的配套机制：profiles.py 挂载改写、config jobs_dir 字段、API/前端类型、2 个测试用例。本任务把回退链路整体拆除，收敛为单一契约：**prompt 唯一来源 = task-web 登记（HERMES_PROMPT 注入），缺失即 fail-fast**，降低复杂度与误配置面。

## Background（确认事实，2026-11-11 复核）

现行架构（2026-11-07 迁移后）：

- task-web 持有调度权（APScheduler + task_schedules 表），到点由 docker 引擎拉起 `hermes-trigger:latest` 容器执行 `python hermes_trigger.py --job-id <id>`；
- `executor._task_env` 注入 `HERMES_PROMPT`（executor.py:105-107），脚本经 Runs API `POST {HERMES_BASE_URL}/p/{profile}/v1/runs` 提交并轮询终态；
- Hermes 侧 cron job 仅剩"手动靶子"作用，且 2026-11-11 已通过 `hermes cron remove` 全部删除（ohyes768 profile jobs.json 现为空，备份 `jobs.json.bak-del3-20261111-065834`；默认 profile jobs.json 亦被 11-11 prune 清空）。

支撑"回退可删"的证据：

- 13 个 hermes_trigger 任务 prompt 全部非空（tasks.yaml 登记行 :86/:165/:271/:325/:394/:438/:454/:470/:534/:552/:570/:588/:644；NAS 生产 DB 复核 prompt 长度 86~2261）；
- tasks.yaml 无任何任务通过 volumes 挂载 `.hermes` cron 目录（`apply_jobs_mount` 零消费；yaml 里 `~/.hermes/...` 全部出现在 prompt 文本与注释中，是宿主机路径，非容器挂载）；
- NAS 生产 `.env` 未设置 `TASK_WEB_HERMES_PROFILES`（用 config.py `_DEFAULT_HERMES_PROFILES` 默认值）；
- `--job-id` 现仅是日志标识（HERMES_PROMPT 在场时不发生 jobs.json 查找）。

## Requirements

- **R1 trigger 脚本**（backend/task-web/trigger/hermes_trigger.py）：删除 jobs.json 回退（:37 DEFAULT_JOBS_JSON、:40-58 load_job、:99 --jobs-json、:121-128 回退分支）；`HERMES_PROMPT` 必填，缺失时 stderr 明确报错并 exit 2；`--job-id` 参数一并移除（2026-11-11 决策，runs 表 task_id 已承担关联职责，日志标签无保留价值）；docstring 重写（prompt 唯一来源契约）。
- **R2 后端配置与执行**：src/profiles.py 删除 `apply_jobs_mount`（:88-111）及 docstring 第 3 条（:7），profile 语义从"三件事"收敛为两件事（凭证 env_file + HERMES_PROFILE）；src/executor.py `_task_volumes`（:123）去除 apply_jobs_mount 调用与相关注释；src/config.py `_DEFAULT_HERMES_PROFILES`（:14-25）与 `get_hermes_profiles`（:68-93）去掉 jobs_dir 字段，`TASK_WEB_HERMES_PROFILES` 对旧 JSON 兼容（多余 jobs_dir 键忽略，当前生产未设置该变量）。
- **R3 API 与前端**：src/api/routes.py:88 `/api/profiles` 响应去掉 jobs_dir；apps/task-web/lib/api.ts:47 `ProfileInfo` 类型同步（页面未渲染该字段，无 UI 改动）。
- **R4 测试**：tests/test_profile_override.py 删除 `test_jobs_mount_follows_profile`（:194-214）与 `test_apply_jobs_mount_ignores_non_jobs_volumes`（:217-222）；调整 AI_YAML fixture（:18-21）、`_catalog`（:142-144）、`test_profiles_endpoint_lists_catalog` 断言（:45）与模块 docstring；保留 prompt 注入用例（test_prompt_injected_as_env / test_no_prompt_no_env）；新增 trigger 脚本"无 HERMES_PROMPT → exit 2"轻量用例。
- **R5 tasks.yaml 清理**：13 条 hermes 任务命令去掉 `--job-id <id>`（变为 `python hermes_trigger.py`）；description/注释里的 job-id 引用同步清理（:81、:156、:260-262、:313-315、:519-521、:633-635 等）。`registry.sync_registry → db.upsert_task`（registry.py:118）每次同步用 yaml command 刷新 tasks 表，部署重启后生产 DB 自动更新，**无手动 SQL 迁移**。
- **R6 文档卫生**：tasks.yaml 陈旧注释更新（同 R5 各行，"jobs.json 仅作 prompt 单一事实源/pause"等表述）；trigger/Dockerfile:2 注释同步。

## Acceptance Criteria

- [ ] `cd backend/task-web && uv run python -m pytest tests/ -v` 全绿。
- [ ] 残留检查为零：`grep -rn "apply_jobs_mount\|jobs_dir\|HERMES_CRON_JOBS_JSON\|load_job" backend/task-web/src backend/task-web/trigger backend/task-web/tests apps/task-web` 无命中（docstring 中描述历史迁移的"jobs.json"字样不算）。
- [ ] tasks.yaml 全部 hermes_trigger 任务 prompt 非空（13/13）；`grep -c "job-id" backend/task-web/tasks.yaml` 为 0。
- [ ] NAS 部署 `./scripts/deploy-nas.sh task-web` 后：手动触发 hermes-gold-price 成功（run 记录 exit 0，日志含 Runs API 提交行）；生产 DB `tasks.command` 已无 `--job-id`（upsert 自动同步）；一次性 trigger 容器无任何 `.hermes` 卷挂载。
- [ ] task-web 页面 profile 切换（/api/profiles + PUT /tasks/{id}/profile）回归正常，凭证 env_file 随 profile 生效。

## Out of Scope

- task-web 调度/任务板功能改动；
- `~/.openclaw/cron/jobs.json`（OpenClaw 侧 6 个 job，与 Hermes 无关）；
- Hermes 侧 skills 内容与 cron 系统；
- task-web DB 中 27 条任务记录的其它字段清理。

## Open Questions

（无。Q1 已于 2026-11-11 决策：`--job-id` 一并移除，详见 R1/R5。）
