# daily-review：每日工作回顾服务 · 设计文档

> 状态：设计定稿（2026-11-27 与用户拷问式评审后共识），未开始实施。
> Hindsight initiative: kp-16ab45a72e5b463da12a8d5938e26400

## 目标

汇聚 **Windows** 与 **NAS** 两台机器上的 DSH（DeepSeek Harness）工作及各项目活动，提供：

1. 界面浏览（今日总览 / 日报周报 / 项目聚合）
2. LLM 生成的日报（每日 09:00）与周报（每周一 09:00），钉钉推送

前身 `F:\personal-projects\daily-review`（纯 Python 标准库，Windows PyTaskSched 每天 09:00 收集 Claude Code / Codex 会话 + git commit，LLM 日报推钉钉）只覆盖 Windows 本机，不采集 DSH，不覆盖 NAS。新服务替代并扩展它。

## 架构（方案 C：NAS 服务 + Windows 采集器）

```
Windows 本机                          NAS (Docker, monorepo 部署链)
┌─────────────────────┐              ┌──────────────────────────────┐
│ 采集器（Python）      │  HTTP ingest │ backend/daily-review          │
│  ~/.dsh/sessions/**  │ ──token──▶  │  FastAPI + SQLite, 端口 8103  │
│  ~/.dsh/task-board   │  结构化记录   │  只读挂载 NAS ~/.dsh 自行解析  │
│  git commits (F盘)   │              │  LLM 总结 (DeepSeek)          │
└─────────────────────┘              │  apps/daily-review  /review   │
                                     └──────────────────────────────┘
```

### NAS 后端 `backend/daily-review`

- FastAPI + SQLite，沿 monorepo 惯例，端口 **8103**，uv 同步，pytest。
- Docker 挂载 `~/.dsh:/data/dsh:ro`，直接解析 NAS 本机 DSH 数据（格式与 Windows 一致，解析器共用一份）。
- 提供 ingest HTTP API（**token 鉴权**）接收 Windows 上送的结构化记录；幂等，失败可重试，记录采集状态。
- LLM 总结基于**两机全量结构化记录**在 NAS 侧生成，DeepSeek key 放 NAS。

### Windows 采集器

- 解析本机 `~\.dsh\sessions\<cwd编码>\<uuid>\session.v4.jsonl.zstd`（zstd 帧无内容大小头，须 `zstandard` stream_reader 流式读；每行 JSON 事件：`session/user message/assistant message/tool call|result/turn|step/subagent descriptor/session title`）。
- 另采 `~\.dsh\task-board\ledger-v2.json`（整文件一次读，勿增量读）与各项目 git commit。
- **源头解析为结构化记录**再上送：项目、会话标题、时间、做了什么、完成/进行中/待办信号。**原文不出本机**，LLM 总结只用结构化记录（脱敏在源头）。
- 节奏：每小时增量采集上送；上线时回填近 **30 天**。

### 前端 `apps/daily-review`

- basePath `/review`，nginx basic auth（沿 service-manager 模式，无应用内登录）。
- 三视图（遵循「让布局解释」，不堆说明文字）：
  1. **今日总览**：两机 DSH + 各项目活动时间线
  2. **日报/周报**：列表 + 详情（LLM 总结 + 原始结构化记录）
  3. **项目维度**：按仓库聚合最近工作

## 数据源口径

| 采 | 不采 |
|---|---|
| 主会话（session JSONL） | 子代理对话原文（体量大、与主会话重叠） |
| task board 状态（ledger-v2.json） | goal / 后台 job（无持久化文件，仅会话流内） |
| git commit / 未提交未推送状态 | 浏览器上网行为 |
| NAS 侧 `~/.dsh/sessions`（含 `--home-ohyes768-personal-web--` 等桶） | |

## 迁移与处置

- 旧 daily-review 的 `reports/` 历史 Markdown 导入新库（新服务支持该格式导入，参考其 legacy_import）。
- 新服务稳定后停掉 Windows 侧旧 09:00 定时任务，避免双份推送。
- 钉钉推送沿用旧 daily-review 的钉钉 relay 通道（已验证）。

## 安全红线

- 勿动：`*.lock`、`*.json.dpapi`、`.credentials.yaml`、`profiles\`（运行中进程持有）、synapse `.bak/.corrupt`。
- NAS 挂载只读；ledger/schedule JSON 可能被运行中的 Host 随时写，一次 open 整读。
- 会话原文不离开 Windows；凭据不入库、不入日志。

## 已确认的事实基础（探查结论 2026-11-27）

- Windows `~\.dsh\sessions\` 201MB，NAS `~\.dsh\sessions\` 93MB，格式完全一致（`session.v4.jsonl.zstd`）。
- NAS 经 tailscale 别名 `nas_tailscare`（100.111.184.19）可达；LAN 直连 192.168.31.73 在本会话被出站拦截，部署用现有 deploy-nas.sh 链路。
- NAS personal-web 仓库位于 `~/personal-web`。
