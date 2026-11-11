# 技术设计：拆除 hermes_trigger jobs.json 回退链路

## 设计原则（第一性）

回退机制存在的唯一理由是"未迁移任务的 prompt 还在 Hermes jobs.json 里"。2026-11-07 迁移完成后该前提不复存在（13/13 prompt 已登记），且回退数据源（Hermes jobs.json）已被清空/删除——保留它只剩下误配置掩盖风险：任务漏配 prompt 时会静默去翻一个已空的文件，报"job 未找到"这种离题错误。收敛为显式契约：**prompt 缺失 = 配置错误 = fail-fast**。

## 保留不变式

- task-web 调度、docker 引擎、一次性容器执行流程不变；
- profile 覆盖机制（task_overrides 表、PUT /api/tasks/{id}/profile）不变；
- `_task_env` 合并顺序不变：登记 env_file → 生效 profile 凭证 env_file → yaml 显式 env → 强制 HERMES_PROFILE → HERMES_PROMPT 注入；
- 后端 compose 对 `~/.hermes` 的只读挂载保留（task-web-backend 自身要读 gw-8642/8643.env 凭证）。

## 删除项与新的 profile 语义

| 位置 | 删除 | 理由 |
| --- | --- | --- |
| trigger/hermes_trigger.py | DEFAULT_JOBS_JSON、load_job()、--jobs-json、回退分支 | 数据源已空，零调用 |
| src/profiles.py | apply_jobs_mount()、docstring 第 3 条 | 零消费（tasks.yaml 无 .hermes cron 挂载） |
| src/executor.py | _task_volumes 中的 apply_jobs_mount 调用 | 同上 |
| src/config.py | profiles schema 的 jobs_dir | 唯一用途是 apply_jobs_mount |
| src/api/routes.py + apps/task-web/lib/api.ts | /api/profiles 的 jobs_dir 字段 | 前端未渲染 |

Profile 语义从"绑定三件事"收敛为"绑定两件事"：

1. 凭证 env_file（BASE_URL / API_KEY 属于哪个网关）；
2. 容器环境变量 HERMES_PROFILE（Runs API 前缀 /p/&lt;profile&gt;/）。

## 接口契约变化

### hermes_trigger.py（CLI 契约）

- 输入：`HERMES_PROMPT`（**必填** env）+ `HERMES_BASE_URL`/`HERMES_API_KEY`/`HERMES_PROFILE`（默认 ohyes768）/轮询参数；无命令行参数；
- 删除：`--jobs-json` 与 `HERMES_CRON_JOBS_JSON`、`--job-id`（runs 表 task_id 已承担任务关联，日志标签无保留价值，2026-11-11 决策移除）；
- 行为变化：无 HERMES_PROMPT 时 exit 2（原先会尝试回退查 jobs.json）；
- 退出码语义不变：0=completed；1=run 失败终态；2=配置/参数/提交错误；3=轮询超时。

### TASK_WEB_HERMES_PROFILES（env JSON schema）

- 新 schema：`{name: {label?, env_file}}`；旧 JSON 中的 jobs_dir 键**忽略不报错**（向后兼容；生产当前未设置该变量，纯防御）。

### GET /api/profiles

- item 由 `{name, label, env_file, jobs_dir, tasks}` 变为 `{name, label, env_file, tasks}`；前端同仓同部署，类型同步即可。

## 改后数据流

```
task-web APScheduler 到点
  → docker 引擎拉起 hermes-trigger 容器（env 注入凭证/profile/prompt，**无任何卷挂载，无 CLI 参数**）
  → POST {base}/p/{profile}/v1/runs {"input": HERMES_PROMPT}
  → 轮询至 completed/failed/cancelled/interrupted
  → exit code + 日志落 task-web runs 表
```

## 部署与回滚

- 部署：`./scripts/deploy-nas.sh task-web`（compose 会重建 hermes-trigger-image 与 task-web-backend/task-web-frontend）；
- 生产验证：页面手动触发 hermes-gold-price（16:35 前的黄金研判 15:30 下一档亦可观察）；
- 回滚：单 commit git revert + 重新部署；无 DB schema 变更、无 prod 数据迁移（本任务零数据迁移）。

## 权衡记录

- **fail-fast vs 静默回退**：选 fail-fast。回退源已空，"兼容"名存实亡；缺 prompt 是登记错误，应立即暴露。
- **--job-id 移除（2026-11-11 决策）**：runs 表以 task_id 关联任务，历史日志对照价值低；同步改 tasks.yaml 13 行命令 + description 注释，registry upsert 自动刷新生产 DB（registry.py:118），零迁移。
- **jobs_dir 键忽略 vs 报错**：选忽略。生产未设置该变量，报错只会增加未来切换 NAS 配置时的摩擦。
