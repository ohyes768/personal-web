# skill-manager GitHub 克隆后台任务化

## Goal

把 GitHub 仓库扫描、登记、Clone 缓存三个入口的 clone 操作改为后台任务 + 前端轮询，
使大仓库/慢速网络（实测 FastGithub 出口 ~51 KiB/s、十几 MB 仓库需 5-15 分钟）不再被
300 秒同步超时切断，且用户能看到真实下载进度。

背景：2026-09-24 排查确认扫描失败根因是"慢速传输 + 300s 超时"（不是网络挂死）。
第一阶段（已合入 master，PR #3）补了阶段日志、可达性预检（unreachable）与
download_timeout 错误码、前端计时器；本任务是第二阶段，治本。

## Requirements

- R1 `POST /api/skills/github/scan`：同步完成 ≤30s 的 ls-remote 可达性预检
  （不可达仍同步返回 400 `unreachable`），可达则启动后台扫描任务并立即返回
  202 `{task_id}`。
- R2 `POST /api/skills/github`（登记）：密码校验与可达性预检同步完成，clone
  后台执行，返回 202 `{task_id}`；密码绝不写入任务状态。
- R3 `POST /api/skills/github/{skill_id}/clone`：同 R2。
- R4 新增 `GET /api/skills/github/tasks/{task_id}`：返回任务快照
  `{kind, state, stage, progress{percent,speed,received,total}, error{code,message}}`，
  三种任务共用；完结任务保留 30 分钟后回收；查询不存在/已回收任务返回
  `task_not_found`（服务重启导致任务丢失时同样落到此错误）。
- R5 进度真实可见：解析 `git clone --progress` 的 stderr（含 `\r` 分隔行），
  暴露阶段（negotiating/receiving/resolving）与百分比、速度；无进度时前端
  退回已用时计时。
- R6 后台 clone 的 git 超时提升为 1800 秒；nginx 配置零改动（轮询请求本身
  毫秒级）。
- R7 根治半成品缓存：首次 clone 先落 `GITHUB_SKILL_CACHE_ROOT/.tmp/<随机>`，
  成功后原子 rename 进 `<skill_id>`；失败不留半成品。fetch 更新路径不变。
- R8 启动时清理 `SKILL_MANAGER_STATE_DIR/scan/*` 残留工作区（进程重启孤儿）。
- R9 前端：扫描对话框、登记确认框、Clone 缓存确认框改为发起任务 + 2s 轮询；
  有进度显示"克隆中 45% · 51 KiB/s"，无进度显示已用时；错误码沿用第一阶段
  文案；关闭对话框停止轮询（服务端任务继续跑完自清）。不做服务端取消、
  不做卡片常驻进度徽章、不做断线恢复轮询。

## Constraints

- 单容器个人工具：任务为进程内内存态（线程执行 + 锁保护快照），不引入
  Celery/Redis/任务持久化；容器重启丢任务可接受（由 R4 的 task_not_found 兜底）。
- 密码只在同步请求体内校验，任务状态与日志中禁止出现。
- 错误契约与第一阶段一致（unreachable/download_timeout/scan_failed/
  cache_failed/registry_conflict/invalid_repository），前端已按 message 展示。
- nginx 与 docker-compose 不改；仅后端镜像与前端需要重新部署。

## Acceptance Criteria

- [ ] AC1 对不存在仓库扫描：同步快速返回 `unreachable`（≤30s），行为与第一阶段一致。
- [ ] AC2 对真实可达仓库扫描：立即得到 202 `{task_id}`；轮询可见进度爬升；
       完成后快照 `state=done` 且候选目录与同步版一致（fixture 对照）。
- [ ] AC3 模拟 clone 超时（fixture 控制耗时）：任务 `state=error`、
       `error.code=download_timeout`；前端展示"下载超时：……可稍后重试"。
- [ ] AC4 后端测试全量通过（除既有 test_deployment_files 2 项漂移，另行任务处理）；
       新增代码（task_manager、流式执行器、临时目录 rename）有对应单测且通过。
- [ ] AC5 任务快照与日志中不出现密码（新增断言）。
- [ ] AC6 clone 中断（kill 模拟）后缓存目录无半成品：`.tmp` 被清理，
       正式目录要么不存在要么完整含 `SKILL.md`。
- [ ] AC7 前端 tsc/lint 通过；preview 真实 E2E：扫描 ohyes768/skills 全流程
       （202 → 轮询进度 → 候选列表）；后端日志生命周期完整
       （start → receiving 进度 → done）。
- [ ] AC8 `state/scan` 启动清理有单测：预置残留目录后触发清理函数，目录被清空。
