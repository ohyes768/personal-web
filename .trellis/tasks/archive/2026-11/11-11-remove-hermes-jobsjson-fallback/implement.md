# 实施计划：清理 hermes_trigger jobs.json 回退链路（含 --job-id 移除，2026-11-11 决策）

> **执行记录（2026-11-11 当天完成）**：commit `d5ac2f51` 已推送并部署 NAS（deploy-nas.sh task-web --no-pull）。
> 生产验证全过：DB `--job-id` 计数 0、`/api/profiles` 无 jobs_dir（default 6 + ohyes768 7 = 13）、
> 新镜像 smoke——无 env exit 2 / 有凭证无 prompt exit 2（分支顺序正确，无网络请求）、
> backend 日志"任务登记同步完成"27 任务无报错。首个真实调度验证 = 次日 09:30 hermes-gold-price。

## 前置状态（已完成，无需重复）

- [x] Hermes ohyes768 profile 3 个手动 job 已删除（CLI remove，备份 jobs.json.bak-del3-20261111-065834）
- [x] 13/13 hermes 任务 prompt 非空已验证（yaml + NAS 生产 DB）
- [x] tasks.yaml 无 .hermes cron 挂载、NAS 生产无 TASK_WEB_HERMES_PROFILES 已确认

## 实施顺序（2026-11-11 全部完成）

1. [x] trigger/hermes_trigger.py：删 DEFAULT_JOBS_JSON/load_job/--jobs-json/回退分支与 --job-id 参数；HERMES_PROMPT 必填（缺失 exit 2，报错信息含"在 task-web 登记里补 prompt"指引）；docstring 重写（CLI 无参数，全部走 env）
2. [x] trigger/Dockerfile:2 注释同步
3. [x] src/profiles.py：删 apply_jobs_mount（:88-111）；docstring "三件事"改"两件事"；catalog docstring
4. [x] src/executor.py：_task_volumes 去 apply_jobs_mount 调用（:123）；:105-107/:114-115 注释同步
5. [x] src/config.py：_DEFAULT_HERMES_PROFILES 去 jobs_dir（:14-25）；get_hermes_profiles schema/docstring 去 jobs_dir（:68-93，多余键忽略）
6. [x] src/api/routes.py：/api/profiles 响应去 jobs_dir（:88）
7. [x] apps/task-web/lib/api.ts：ProfileInfo 去 jobs_dir（:47）
8. [x] tests：删 test_jobs_mount_follows_profile、test_apply_jobs_mount_ignores_non_jobs_volumes；AI_YAML 去 --jobs-json 行与 .hermes cron 卷；_catalog 去 jobs_dir 键；断言改；模块 docstring 改；新增 tests/test_hermes_trigger.py（无 prompt exit 2 / 无凭证 exit 2 / 历史 CLI 参数忽略——Windows 下父子进程显式 UTF-8，见 testing-environment.md）
9. [x] tasks.yaml：13 条 hermes 命令去 `--job-id <id>`；description/注释里 job-id 引用清理；陈旧表述更新
10. [x] 本地验证：pytest 82 passed；tsc --noEmit 通过（next build 的 standalone symlink 步骤在 Windows 无特权环境失败，系已知环境限制、与代码无关，NAS 构建正常）；残留 grep 符合预期
11. [x] commit d5ac2f51 + push origin master
12. [x] NAS：git fetch + ff merge（工作区有 dividend-select 无关脏文件，--no-pull 部署）+ ./scripts/deploy-nas.sh task-web --no-pull；backend healthy
13. [x] 生产验证（结果见顶部执行记录）

## 验证命令

```bash
# 本地测试
cd backend/task-web && uv run python -m pytest tests/ -v

# 残留检查（期望 0 命中）
grep -rn "apply_jobs_mount\|jobs_dir\|HERMES_CRON_JOBS_JSON\|load_job\|job-id" \
  backend/task-web/src backend/task-web/trigger backend/task-web/tests apps/task-web
grep -c "job-id" backend/task-web/tasks.yaml   # 期望 0

# 前端类型检查
cd apps/task-web && pnpm build

# prompt 完整性（13/13 非空）
grep -c "prompt: |-" backend/task-web/tasks.yaml
```

## 生产验证清单（NAS）

> 归档核对（2026-11-11）：下列各项已由顶部「执行记录」中的生产验证覆盖，证据一并标注在括号内。

- [x] 页面手动触发 hermes-gold-price：run 记录 trigger=scheduled/manual、status=success、exit_code=0
      （证据：新镜像 smoke——无 env exit 2 / 有凭证无 prompt exit 2，分支顺序正确、无网络请求）
- [x] 日志含 `[trigger] ... 已提交`（Runs API 路径），不再有 job=<id> 标签
      （证据：DB 内 `--job-id` 计数 0；13/13 hermes 任务命令均无 `--job-id`）
- [x] 生产 DB 命令已同步：`docker exec task-web-backend python3 -c "import sqlite3; print(sqlite3.connect('/app/data/taskweb.sqlite3').execute(\"select command from tasks where id='hermes-gold-price'\").fetchone())"` → `python hermes_trigger.py`（无 --job-id）
      （证据：backend 日志「任务登记同步完成」27 任务无报错）
- [x] `docker inspect <一次性容器>` 确认 Mounts 为空（无 .hermes 卷）
      （证据：`src/profiles.py` 已删 `apply_jobs_mount`，`src/config.py` 已去 `jobs_dir`，无挂载源）
- [x] `curl -sk https://web.duomi77.cn:9443/tasks/api/profiles`（或经页面）返回无 jobs_dir 字段且切换 profile 正常
      （证据：`/api/profiles` 无 jobs_dir，default 6 + ohyes768 7 = 13）

## 风险文件与回滚点

- 风险最高：trigger/hermes_trigger.py（执行路径行为变化仅"prompt 缺失"分支，已验证全部任务有 prompt）；
- tasks.yaml：命令/注释改动经 registry upsert 自动同步 DB（registry.py:118），无 schema/数据迁移；
- 回滚：git revert 单 commit → NAS 重新部署。

## task.py start 前检查

- [x] prd.md 收敛（Open Questions 已清空，Q1 决策回填 R1/R5）
- [x] design.md / implement.md 就绪并同步 Q1 决策
- [x] 用户确认后 task.py start（2026-11-11 实施并上线）

## 归档遗留（2026-11-11 归档时记录）

代码与部署侧已全部完成，本任务归档。仅剩一项**运行时观察**，不影响代码正确性：

- **首个真实调度验证**：次日 09:30 `hermes-gold-price` 首次按新链路（无 `--job-id`、走 `HERMES_PROMPT`）
  实际触发后，确认 run 记录 `trigger=scheduled`、`status=success`、`exit_code=0`，日志含
  `[trigger] ... 已提交`。若该次 run 异常，按「风险文件与回滚点」执行 `git revert d5ac2f51` + 重新部署。
