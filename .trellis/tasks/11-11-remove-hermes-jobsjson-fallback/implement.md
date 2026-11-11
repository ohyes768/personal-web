# 实施计划：清理 hermes_trigger jobs.json 回退链路（含 --job-id 移除，2026-11-11 决策）

## 前置状态（已完成，无需重复）

- [x] Hermes ohyes768 profile 3 个手动 job 已删除（CLI remove，备份 jobs.json.bak-del3-20261111-065834）
- [x] 13/13 hermes 任务 prompt 非空已验证（yaml + NAS 生产 DB）
- [x] tasks.yaml 无 .hermes cron 挂载、NAS 生产无 TASK_WEB_HERMES_PROFILES 已确认

## 实施顺序

1. [ ] trigger/hermes_trigger.py：删 DEFAULT_JOBS_JSON/load_job/--jobs-json/回退分支与 --job-id 参数；HERMES_PROMPT 必填（缺失 exit 2，报错信息含"在 task-web 登记里补 prompt"指引）；docstring 重写（CLI 无参数，全部走 env）
2. [ ] trigger/Dockerfile:2 注释同步
3. [ ] src/profiles.py：删 apply_jobs_mount（:88-111）；docstring "三件事"改"两件事"；catalog docstring
4. [ ] src/executor.py：_task_volumes 去 apply_jobs_mount 调用（:123）；:105-107/:114-115 注释同步
5. [ ] src/config.py：_DEFAULT_HERMES_PROFILES 去 jobs_dir（:14-25）；get_hermes_profiles schema/docstring 去 jobs_dir（:68-93，多余键忽略）
6. [ ] src/api/routes.py：/api/profiles 响应去 jobs_dir（:88）
7. [ ] apps/task-web/lib/api.ts：ProfileInfo 去 jobs_dir（:47）
8. [ ] tests/test_profile_override.py：删 test_jobs_mount_follows_profile、test_apply_jobs_mount_ignores_non_jobs_volumes；AI_YAML 去 --jobs-json 行与 .hermes cron 卷（保留 /ack 卷，验证普通卷不受影响）；_catalog 去 jobs_dir 键；test_profiles_endpoint_lists_catalog:45 断言改；模块 docstring 改；新增 trigger 无 HERMES_PROMPT → exit 2 用例（subprocess 跑 trigger/hermes_trigger.py，无网络请求路径）
9. [ ] tasks.yaml：13 条 hermes 命令去 `--job-id <id>`（变 `python hermes_trigger.py`）；description/注释里的 job-id 引用清理（grep -n "job-id\|job [0-9a-f]\{10\}" 定位全部落点，覆盖 :81、:156、:260-262、:313-315、:519-521、:633-635 及 macro 4 条 description）；陈旧表述（"jobs.json 仅作 prompt 单一事实源/pause"）同步更新
10. [ ] 本地验证（见下）
11. [ ] commit + push origin master
12. [ ] NAS：git pull + ./scripts/deploy-nas.sh task-web（重启时 registry sync 自动把新 command 刷进生产 DB，无需手动 SQL）
13. [ ] 生产验证（见下）

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

- [ ] 页面手动触发 hermes-gold-price：run 记录 trigger=scheduled/manual、status=success、exit_code=0
- [ ] 日志含 `[trigger] ... 已提交`（Runs API 路径），不再有 job=<id> 标签
- [ ] 生产 DB 命令已同步：`docker exec task-web-backend python3 -c "import sqlite3; print(sqlite3.connect('/app/data/taskweb.sqlite3').execute(\"select command from tasks where id='hermes-gold-price'\").fetchone())"` → `python hermes_trigger.py`（无 --job-id）
- [ ] `docker inspect <一次性容器>` 确认 Mounts 为空（无 .hermes 卷）
- [ ] `curl -sk https://web.duomi77.cn:9443/tasks/api/profiles`（或经页面）返回无 jobs_dir 字段且切换 profile 正常

## 风险文件与回滚点

- 风险最高：trigger/hermes_trigger.py（执行路径行为变化仅"prompt 缺失"分支，已验证全部任务有 prompt）；
- tasks.yaml：命令/注释改动经 registry upsert 自动同步 DB（registry.py:118），无 schema/数据迁移；
- 回滚：git revert 单 commit → NAS 重新部署。

## task.py start 前检查

- [x] prd.md 收敛（Open Questions 已清空，Q1 决策回填 R1/R5）
- [x] design.md / implement.md 就绪并同步 Q1 决策
- [ ] 用户确认后 task.py start
