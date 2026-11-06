# 抖音文字稿定时任务页面化：调度可见与执行记录

## Goal

给 douyin-processor 的定时任务（09:45 / 17:15 转写 + 03:07 清理）补上「页面可管理 + 执行有记录」，对齐仓库里 dividend / macro 已验证的内建调度管理模式，替代现在"只能翻容器日志"的黑盒状态。

## Background（已确认事实，代码取证）

### 现状

- 调度在 `backend/douyin-processor/src/server/main.py:140-176` lifespan 内：`AsyncIOScheduler` 注册 3 个 job
  - `process_pending_morning`（45 9 * * *）→ 处理 status=pending 视频（阿里 FunASR → unread）
  - `process_pending_evening`（15 17 * * *）
  - `cleanup_old_records`（7 3 * * *）→ 清理 45 天前 wav + status 记录
- cron 配置在 `config/app.yaml` 的 `app.process_pending` / `app.cleanup`（只读挂载进容器，改后需 restart，recreate 不丢）
- **没有任何管理 API、没有执行历史、没有 UI**；执行痕迹只在容器日志
- 已有手动入口：前端「待处理(N)」按钮 → POST `/api/process/pending`，与定时共用 `endpoints._process_lock`（endpoints.py:28,169-212）防重入
- task-web（/tasks）预登记清单里没有 douyin 任务；douyin 调度是进程内组件调用，套 task-web 需拆命令行 + 新登记，与其他服务形态不一致 → 不走 task-web
- n8n 已被 dividend/macro/douyin 三家先后淘汰为触发方，不回头

### 参照模式（详见 research/scheduler-pattern-survey.md）

dividend-select 与 macro 是同一套内建调度管理模式：

- 后端 `src/scheduler/` 包：SchedulerManager + 4 个管理 API（jobs 列表 / PATCH 启停 / run 立即执行 / runs 历史）+ JSONL 执行历史（5MB 滚动归档）+ cron_human
- 前端：dividend 主页弹框 / macro 独立页，展示 cron 人话、下次触发、启停开关、立即执行、最近 20 条历史
- dividend 先例决策：「cron 由配置文件固定，UI 仅开放启用/禁用与立即执行」；scheduler-lifecycle spec（`.trellis/spec/backend/dividend-select/backend/scheduler-lifecycle.md`）沉淀了 shutdown drain 契约

### 部署形态（约束）

- `douyin-backend` 挂 `douyin-data`(→/app/data)、`douyin-logs`、`config`（只读）
- nginx `/api/douyin/*` → 后端 8093；前端 Next 代理 route.ts 只有 GET/POST/DELETE（无 PATCH）
- douyin-processor 无 tests/ 目录，pytest 基建从零加

## 已决决策（用户确认）

| # | 决策 | 选择 |
|---|---|---|
| D1 | 前端形态 | **主页弹框**（dividend/fund-select 先例，2026-11-06 确认） |
| D2 | 管理范围 | **全部定时任务都纳入**（转写 + cleanup 清理，cleanup 失败也要页面可见，2026-11-06 确认） |

> 设计层面注记：design.md 将 09:45/17:15 两个时刻合并为一个逻辑 job（`process_pending`，双 CronTrigger，卡片显示「每天 09:45 / 17:15」），管理能力不减（启停=两时刻一起停、立即执行、历史同卡）。D2 的意图是「cleanup 也要管」，该意图不受影响；审阅时若要恢复 3 卡形态，实现成本几乎相同。

## Requirements

### R1 后端：内建调度管理 API（照 dividend/macro 模式，douyin 适配）

- 新增 `src/scheduler/` 包：SchedulerManager + 4 个管理 API，挂 `/api/scheduler/*`
- 全部定时任务（转写 2 个时刻 + cleanup）纳入管理；行为不变（时间、逻辑、时区 Asia/Shanghai 均不变）
- 启用/禁用持久化（douyin-data 卷 `data/scheduler/enabled.json`，重启/recreate 均保持）；cron 不进 UI，改配置走 app.yaml + restart（沿 dividend 先例）
- cron/手动执行共用 `_process_lock` 互斥防重入
- 执行历史落 JSONL（`data/scheduler/history.jsonl`），记录 trigger（scheduled/manual）、start/end/status/count/reason/error，5MB 滚动归档
- 现有手动按钮 POST `/api/process/pending` 保持响应结构兼容，执行同样记入历史（trigger=manual）

### R2 前端：主页弹框

- 抖音页面头部新增定时任务管理入口（齿轮按钮）+ 弹框
- 展示：job 卡片（名称、cron 人话、下次触发时间、启用开关、立即执行、可展开最近 20 条历史，含手动/定时标记）

### R3 生命周期与测试

- shutdown drain 遵循 scheduler-lifecycle spec；单 worker 断言
- 新增 pytest（douyin-processor 无测试基建，从零加）：启停持久化、互斥、历史 schema、双 cron trigger、drain 契约

## Acceptance Criteria

- [ ] GET /api/scheduler/jobs 返回全部定时任务，含 cron_human / next_run_time / last_run
- [ ] PATCH 启停立即生效；重启容器后状态保持；禁用的 job 不再触发
- [ ] 立即执行后历史出现 trigger=manual 记录；与 cron 运行互斥（撞锁不双跑）
- [ ] 定时触发后历史出现 trigger=scheduled 记录；页面可见最近 20 条
- [ ] 前端弹框可查看全部 job 状态并操作启停/立即执行；cleanup 的失败可在页面看到
- [ ] 现有「待处理(N)」按钮行为与响应结构不变，且执行也落历史
- [ ] 后端 `uv run python -m pytest tests/ -v` 通过；前端 `pnpm lint` / `pnpm build` 通过

## Out of Scope

- task-web 接入 / n8n 回归
- UI 编辑 cron（改时间走 app.yaml + restart，与 dividend「cron 固定」先例一致）
- 历史分页查询、多用户权限、跨服务统一调度台

## Notes

- 复杂任务：`design.md`（技术设计）与 `implement.md`（执行清单）已就绪，待用户审阅后 `task.py start`
