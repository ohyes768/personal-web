# hermes 任务统一触发

来源：2026-11-06 用户决策——定时任务统一由 task-web 管理，Hermes 只作为被调用执行器（"到点给 hermes 发消息"）。

## Goal

把 Hermes 内置 cron 的任务迁到 task-web 统一调度：task-web 到点 → 经 Hermes Runs API 提交 run（即"发消息"）→ 轮询终态 → 记录/日志。Hermes 侧旧 cron job 逐个禁用，保留定义回滚。

## Confirmed Facts（2026-11-06 NAS 实测）

- Hermes gateway（API server）监听宿主机 `172.27.0.1:8643`（profile ohyes768）；`HERMES_BASE_URL/API_KEY/PROFILE` 已在 stock-info-dingding `.env` 配置并被生产使用。
- Runs API 契约（hermes_client.py 实证）：`POST {base}/p/{profile}/v1/runs`（Bearer 鉴权 + Idempotency-Key 防重）→ `GET /v1/runs/{run_id}` 轮询，终态 completed/failed/cancelled/interrupted。
- Hermes 内置 cron 共 6 个 job（`~/.hermes/cron/jobs.json`）：港股IPO每日研究（deliver: origin）、港股IPO回测审计、A债宏观周报×2、WaytoAGI 追踪、杭州PM2.5 播报（deliver: weixin，prompt 自带推送步骤）。
- 系统 crontab 1 条：CSI300 简报 `cron_daily.sh`，`35 8 * * 1-5`（**UTC**）= 北京 16:35。
- `cron_daily.sh` 恒 `exit 0`（brief.py 失败也报成功）——迁移必须直跑 `brief.py`，不经包装脚本。
- `brief.py` 纯标准库（urllib），无第三方依赖；skill 脚本位于 `/home/ohyes768/skills/`。
- PM2.5 job 的 prompt 显式含"推送到微信"步骤，agent 自行完成投递 → API 触发不依赖 gateway 的 deliver 路由。

## Requirements

1. **通用触发器 `hermes_trigger.py`**：按 job id 读 jobs.json 取 prompt → Runs API 提交（Idempotency-Key=run_id）→ 轮询至终态 → stdout 打印产出摘要；completed→退出 0，其余→非 0。复用 stock-info 镜像（已含 hermes_client.py 同款依赖）。
2. **docker 引擎任务级 volumes**：tasks.yaml 支持 `volumes: ["src:dst:ro"]`，executor 传给 containers.run（skill 类任务需要原路径挂载，如 `/home/ohyes768/skills`）。
3. **两个试点登记**（默认禁用，逐个启用）：
   - `csi300-brief`：docker 引擎，command 直跑 brief.py，cron `35 16 * * 1-5`（北京），挂载 skills 目录 ro
   - `pm25-broadcast`：docker 引擎，command=hermes_trigger.py --job-id <PM2.5 job>，挂载 jobs.json 所在目录 ro
4. compose：task-web-backend 增可选 skills 目录挂载（env var，默认 `/home/ohyes768/skills`）+ jobs.json 只读挂载（env var）。
5. 试点验证后，Hermes 侧对应旧 job 置 enabled=false（保留定义回滚）；后续其余 4 个 job 迁移不在本任务范围。

## Acceptance Criteria

- [ ] hermes_trigger.py 干跑（无 API key 指向无效地址）有明确报错与非 0 退出，不误报成功。
- [ ] pm25-broadcast 手动执行一次成功：run 记录 completed、微信收到播报、日志含产出摘要。
- [ ] csi300-brief 手动执行一次：钉钉收到简报；brief.py 失败时 run 状态=failed（不再被 cron_daily.sh 掩盖）。
- [ ] 启用正式计划前，Hermes 侧两个旧触发已禁用，无双触发。
- [ ] volumes 挂载在 fake client 测试中验证参数传递；env/密钥不回显不落日志（既有红线延续）。

## Out of Scope

- ~~其余 4 个 Hermes job 的迁移~~ 已扩展：2026-11-07 用户要求 Hermes 两 profile 全量登记（10 job 全进 tasks.yaml hermes 组，默认禁用）；交付核实结论：全部 5 个非试点 job 的 prompt/SKILL.md 内置 RSS 中转推送（push_rss.py 为必经步骤，推 macro 频道 + 看板；WaytoAGI 双通道 RSS+钉钉），无需改 prompt。
- deliver: origin 任务的会话回复副本（仅飞书聊天层，任务产出已走 RSS，不影响业务）。
- task-web 页面展示 Hermes run 内部进度（只落终态与摘要）。
- 时区事实：Hermes cron 存 UTC，登记 task-web（Asia/Shanghai）时已逐个换算。

## Open Questions

1. ~~触发器代码位置~~ 已决策（2026-11-07）：放 stock-info-dingding 仓库根，进现有 stock-info 镜像，零新增构建。
2. ~~jobs.json 读取方式~~ 已决策（2026-11-07）：只读挂载 `~/.hermes/cron/` 目录（compose env var `HERMES_CRON_HOST_PATH`，默认 `/home/ohyes768/.hermes/cron`），触发器按 job id 现场取 prompt，单一事实源不漂移。
