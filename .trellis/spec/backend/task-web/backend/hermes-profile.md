# 生效 Hermes Profile 契约

> 2026-11-07 起 profile 从「只读推导」变成「用户可设置」；同日 prompt 事实源收编进
> tasks.yaml（`prompt:` 字段 → tasks 表 → 执行注入 `HERMES_PROMPT`），AI 定时任务
> 与 stock-info-dingding 解耦（镜像 `hermes-trigger:latest`，源码在本仓
> `backend/task-web/trigger/`——它是 task-web 的执行基础设施，不属于任何业务或
> skill 内容仓库）。改这块先读本文。
>
> **2026-11-11 起 jobs.json 回退与 `--job-id` 参数退役**：prompt 唯一来源 =
> 登记注入的 `HERMES_PROMPT`（缺失 exit 2）；profile 只绑凭证 env_file +
> `HERMES_PROFILE` 两件事；触发命令统一为 `python hermes_trigger.py`（无 CLI 参数）。

## 0. prompt 事实源（2026-11-07 收编，2026-11-11 收敛为唯一来源）

- tasks.yaml `prompt:` 字段是 AI 任务 prompt 的**唯一事实源**（登记制、进 git）；
  sync 后存 `tasks.prompt` 列，执行时经 `executor._task_env` 注入容器 env
  `HERMES_PROMPT`。
- 触发脚本（本仓 `backend/task-web/trigger/hermes_trigger.py`）**只认
  `HERMES_PROMPT`**（jobs.json 回退与 `--job-id` 已移除）；缺失即登记配置错误，
  exit 2 并在 stderr 指明去 tasks.yaml 补登记。历史命令残留 `--job-id` 等参数
  会被静默忽略（无 argparse），滚动部署兼容。
- jobs.json 回归「Hermes 侧原生 cron job 的定义文件」，与 task-web 执行链路
  无关；切换 profile 不要求目标 profile 有同名 job。
- AI 任务凭证在 `~/.hermes/gw-8642.env` / `gw-8643.env`（纯 HERMES_* 键，
  chmod 600），经 compose 只读挂到后端容器 `/hermes-home`；env_file 容器路径
  与 profile 目录里的 env_file 一致，是登记推导的匹配依据。

## 1. profile 不只是标签

一个 profile 绑定两件事，切换时必须一起换，否则「选了不生效」：

| 绑定项 | 默认 default | 默认 ohyes768 |
| --- | --- | --- |
| 凭证 env_file（BASE_URL/API_KEY） | `/hermes-home/gw-8642.env` | `/hermes-home/gw-8643.env` |
| 容器内 `HERMES_PROFILE` | `default`（网关 8642） | `ohyes768`（网关 8643） |

目录来自 `config.get_hermes_profiles()`（schema `{label, env_file}`）：代码内默认值
对齐上表，环境变量 `TASK_WEB_HERMES_PROFILES`（JSON）整体覆盖，新增 profile 不必改
代码；旧 JSON 里的 `jobs_dir` 键读入时忽略（2026-11-11 前的字段，向后兼容）。

## 2. 生效值优先级

1. `task_overrides.profile`（页面下拉设置的覆盖值，可为空 = 未覆盖）；
2. tasks.yaml 登记推导：`env.HERMES_PROFILE` > `env_file` 与某 profile 的 env_file 相等/同名；
3. `None`（非 Hermes 触发的 AI 任务与所有脚本任务）。

覆盖值必须命中 profile 目录，否则 API 400；脚本任务（group≠ai）不可设置。

## 3. 存储位置：不能放 tasks 表

`registry.sync_registry()` 每次启动都用 tasks.yaml upsert `tasks` 表，可编辑项必须另存：

- cron / 启停 / 超时 → `task_schedules`（既有）；
- profile 覆盖 → `task_overrides`（本契约新增，`db.set_profile_override`）。

`db.delete_task` 同步清理覆盖；yaml 重新同步不覆盖用户设置（有回归用例）。

## 4. 执行期应用（`executor.py`）

- `_task_env`：登记 env_file → profile 凭证 env_file → yaml 显式 env → 强制写入
  `HERMES_PROFILE=${生效 profile}` → 有登记 prompt 再注入 `HERMES_PROMPT`。
  强制写 profile 是为了让页面新选的值压过 yaml 里为防漂移写死的旧值。
- `_task_volumes`：登记 volumes 纯透传（2026-11-11 起 jobs.json 挂载改写已移除；
  AI 任务登记里不需要也无法依赖挂载 jobs.json——prompt 走 HERMES_PROMPT）。

## 5. API 与页面

- `GET /api/profiles` → `{profiles: [{name, label, env_file, tasks}]}`（jobs_dir 字段已移除）
- `PUT /api/tasks/{id}/profile`，body `{"profile": "ohyes768"}` 设置 / `{"profile": null}` 清除
- `GET /api/tasks` 每行多返回 `profile_source`：`override` | `registry` | `null`，
  页面据此标注「已覆盖登记值 / 来自 tasks.yaml」

## 6. 质量检查

- `uv run python -m pytest tests/ -v`（含 `tests/test_profile_override.py` 与
  `tests/test_hermes_trigger.py`——后者守护触发脚本契约：无 HERMES_PROMPT → exit 2、
  历史残留 CLI 参数被忽略）
- 改 profile 目录后务必确认 `default`/`ohyes768` 的 env_file 在 task-web 容器内可读
  （compose 把 `~/.hermes` 只读挂到 `/hermes-home`）
- 残留检查：`grep -rn "apply_jobs_mount\|jobs_dir\|HERMES_CRON_JOBS_JSON\|job-id" backend/task-web/src backend/task-web/trigger backend/task-web/tests apps/task-web` 期望 0 命中
