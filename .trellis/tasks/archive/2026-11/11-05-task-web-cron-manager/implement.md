# task-web 实施计划

前置：prd.md 四项决策已定，design.md 已评审。

## 实施顺序

### Phase 1 后端骨架
1. `backend/task-web/` 脚手架：pyproject/uv、FastAPI 入口、SQLite 迁移（tasks、task_schedules、runs、scheduler_heartbeat）。
2. tasks.yaml 预登记格式定义 + 加载校验（启动时登记缺失任务、不覆盖已有 schedule）。
3. executor.py：Popen 进程组执行、超时 killpg、互斥 skipped、日志文件写入。
4. scheduler.py：APScheduler 集成、心跳、漏执行补记（interrupted + missed_schedule_at）、重启恢复（running→interrupted）。

### Phase 2 API
5. 任务列表/调度修改/手动执行（密码校验 TASK_WEB_ADMIN_PASSWORD）/runs 筛选/详情/日志 tail 六个路由。
6. 保留策略：日志按天清理（可配置，默认 30 天）。

### Phase 3 前端
7. `apps/task-web/` Next.js 脚手架（basePath /tasks，端口 3011），任务列表页 + 运行记录页 + 详情页（运行中 3s 轮询日志）。
8. 手动执行密码弹窗、结果含义提示文案。

### Phase 4 部署与验证
9. docker-compose.nas.yml 增加 task-web 后端+前端服务（bind mount stock-info-dingding、TZ=Asia/Shanghai、named volume）；本地 docker compose 构建验证。
10. 无外发测试脚本四场景验证：成功、失败（非 0 退出）、长运行（超时 killpg 生效）、并发触发（skipped 记录）。
11. 重启恢复验证：容器重启后旧 running→interrupted、心跳恢复、下次计划时间正确。
12. A 股新股接入：登记 enabled=false → 容器内 import 核对并补 requirements → dry-run 验证 → 用户确认后启用，停用旧入口。

## 验证命令

- 后端：`cd backend/task-web && uv sync && uv run python -m pytest tests/ -v`
- 前端：`cd apps/task-web && pnpm lint && npx tsc --noEmit && npm run build`
- 编排：`docker compose -f docker-compose.nas.yml config`（本地校验），NAS 上 `up -d --build` 后 `ps` + 页面走查。

## 风险文件与回滚点

- `docker-compose.nas.yml`（唯一触碰的既有文件）：改动独立 commit，回滚即还原该文件并 down task-web 服务。
- Phase 每层独立可 review；任何单步失败先修复该层。
- 不修改 NAS 既有 cron、脚本与 hooks.json。

## task.py start 前检查

- [x] prd.md 收敛完成（4 个 Open Questions 已全部决策并折叠进正文）
- [x] design.md、implement.md 就绪
- [ ] implement.jsonl / check.jsonl 若走子代理派发需补真实条目；本任务按 inline 工作流可跳过 JSONL 门禁
