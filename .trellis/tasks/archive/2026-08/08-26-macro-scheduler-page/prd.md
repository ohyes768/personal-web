# 宏观定时任务与独立管理页面

## Goal

宏观后端(backend/macro)目前没有任何定时调度:约 16 个数据源只能靠前端手动点刷新,
或靠 n8n 外部调度调 `/update`(仅覆盖美债+OECD+汇率)。本任务为宏观后端引入内建定时任务,
自动更新全部数据源,并提供一个**独立的管理页面**(区别于股息率的弹框)。

## Background(调研结论)

- 股息率后端已有成熟的 scheduler 模块(`backend/dividend-select/src/scheduler/`):
  APScheduler 内建、`scheduler.json` 预设、JSONL 运行历史、HTTP self-call 复用现有 API、
  4 个管理 API(列表/启停/立即执行/历史)。前端是 Modal 弹框,只支持启停+立即执行。
- 宏观后端现状:无 scheduler;已有 16 个 `POST /api/update/*` 端点可直接复用
  (us-treasuries / exchange-rates / eu-bonds / jp-bonds / china-bonds / vix / tga /
  hibor / ted-spread / fund-flow / commodities / indices / dr007 / volume / turnover / margin);
  存在 n8n 调用的 `POST /api/update` 老端点(美债+OECD+汇率)。

## Requirements

### R1 后端内建定时任务(按频率分组)

- 移植股息率的 scheduler 模式到 `backend/macro/src/scheduler/`
- 任务粒度:**按频率分组**——一个 job 顺序执行一组 update 端点(用户已确认)
- 预设分组:
  - **A 股组**(需判 A 股交易日,收盘后跑):china-bonds、dr007、fund-flow、volume、turnover、margin
  - **全球组**(工作日跑,不判 A 股交易日):us-treasuries、exchange-rates、eu-bonds、jp-bonds、vix、tga、hibor、ted-spread、commodities、indices
- 单个数据源失败不中断组内后续数据源的执行,运行历史需记录**每个数据源的子结果**
- 非交易日 A 股组跳过并记 `skipped`

### R2 scheduler 管理 API

与股息率一致(用户已确认不在线改 cron):
- `GET /api/scheduler/jobs` 任务列表(含 cron 中文可读、下次运行、上次结果)
- `PATCH /api/scheduler/jobs/{id}` 启用/禁用(写回配置文件)
- `POST /api/scheduler/jobs/{id}/run` 立即执行
- `GET /api/scheduler/jobs/{id}/runs` 运行历史(含数据源子明细)

### R3 独立管理页面(前端 apps/macro)

- 新路由页( basePath 下 `/macro/scheduler` ),**不是弹框**
- 任务卡片:名称/描述/cron 中文/下次运行时间/上次运行状态/启停开关/立即执行
- 运行历史:展开看最近 N 条,每条可看数据源级子明细(状态/条数/耗时/错误)
- 主页面增加**悬浮设置按钮**入口跳转到该页(用户已确认)
- 兼容现有深色模式

### 约束

- n8n 老链路不破坏:`POST /api/update` 保留不动,是否退役 n8n 由用户在 n8n 侧自行决定
- 单 worker 模式(scheduler 要求,启动时校验)
- 不硬编码端口,self-call 端口来自后端配置
- 股息率 scheduler 行为保持不变(只移植/复制,不重构共享)

## Acceptance Criteria

- [ ] 后端启动时 scheduler 注册 2 个分组任务,日志显示 cron 与启用状态
- [ ] A 股组在非交易日触发返回 `skipped`(单测覆盖);交易日手动触发顺序执行 6 个端点并落历史
- [ ] 某一数据源失败时,组内后续数据源继续执行,job 记 `partial` 状态及失败子项明细
- [ ] 4 个 scheduler API 可用(curl 验证);启停立即生效并持久化到 scheduler.json
- [ ] 前端 `/macro/scheduler` 页面可访问:启停(乐观更新+失败回滚)、立即执行、历史+子明细展示正常
- [ ] 主页右下角悬浮按钮可跳转到管理页
- [ ] 后端新增单测通过;`pnpm build` 前端构建通过
- [ ] 股息率前后端行为无变化(纯新增,不改其代码)
