# 挡位 batch API + token 校验

## Goal

为外部 agent 服务提供一条 batch 接口，一次调用补多只股票的 4 档监控信息（heavy / add / reduce / full），简化 agent 的写入路径，避免循环调用单只接口。

## Background

- 现有 `PUT /favorites/{code}/alerts` 是单只覆盖式接口，前端 `AlertSettingsModal` 在用，不适合 agent 批量写
- agent 是**外部服务**（跨网络调用），需要鉴权
- 现有接口对未收藏股票返回 404，agent 调用前要先 `PUT /favorites/{code}` 加收藏再设挡位——双倍调用次数
- agent 数据形态：4 档价格必有，pe/pb 可选（每档可独立），enabled 可选

## Requirements

### 功能性

- **R1**：新增 `POST /api/dividend/favorites/alerts/batch` 接口
- **R2**：入参 `AlertBatchRequest`：
  ```json
  {
    "updates": [
      {
        "code": "600000",
        "levels": {
          "heavy_position":  {"price": 10.0, "pe": 8.5, "pb": 1.2},
          "add_position":    {"price": 12.0},
          "reduce_position": {"price": 15.0},
          "full_exit":       {"price": 18.0}
        },
        "enabled": true
      }
    ]
  }
  ```
  - `code`：必填，6 位股票代码（非数字/超 6 位 → 该条 400）
  - `levels.*.price`：必填，>0
  - `levels.*.pe` / `levels.*.pb`：可选，默认 null
  - `enabled`：可选，默认 `true`
- **R3**：每条 update 独立处理；任意一条失败不影响其他条（per-stock 隔离）
- **R4**：未收藏的 code 自动加入 favorites（`FavoritesService.add`）再设挡位；不要求 agent 预先加收藏
- **R5**：响应 `AlertBatchResponse`：
  ```json
  {
    "results": [
      {"code": "600000", "ok": true},
      {"code": "xxx",    "ok": false, "error": "股票代码格式错误: xxx"}
    ],
    "success_count": 1,
    "fail_count": 1
  }
  ```
- **R6**：token 校验：请求必须带 `X-API-Token: <token>` header；缺失或不匹配 → 整批 401；token 来源 `AGENT_API_TOKEN` 环境变量

### 非功能性

- **N1**：单次 batch 上限 100 条（防滥用）；超过 → 整批 400
- **N2**：token 比较用 `secrets.compare_digest` 防 timing attack
- **N3**：服务端未配置 `AGENT_API_TOKEN`（环境变量空）→ 整批 503，提示运维补配置
- **N4**：不修改现有 `PUT /favorites/{code}/alerts` 行为（前端在用，零回归）

### 范围内/外

- ✅ 在：新 batch 路由 + token 依赖 + Pydantic 模型 + 自动加收藏 + 单测 + .env.example
- ❌ 外：现有 PUT/DELETE 路由改造、其他接口加 token、前端 agent 调用代码、MCP server 包装

## Acceptance Criteria

- [ ] `POST /api/dividend/favorites/alerts/batch` 可用，OpenAPI 文档自动生成
- [ ] 4 档全设 + 已收藏 + 正确 token → `{ok: true}`，挡位写入 `data/favorites.json`
- [ ] 未收藏的 code → 自动加入 favorites + 设挡位，仍返回 `{ok: true}`
- [ ] code 非法（非数字/超 6 位）→ 该条 `{ok: false, error: ...}`，其他条不受影响
- [ ] 缺 token / 错 token → HTTP 401
- [ ] 服务端未配 `AGENT_API_TOKEN` → HTTP 503
- [ ] updates 数组 > 100 → HTTP 400
- [ ] 4 档 price ≤ 0 → 该条 `{ok: false}`（Pydantic 校验）
- [ ] 单测覆盖：happy path / 未收藏自动加 / 部分失败 / token 缺失 / token 错 / 超限
- [ ] `.env.example` 添加 `AGENT_API_TOKEN=` 注释
- [ ] 子模块 `backend/dividend-select` commit + push 后，主仓库 bump gitlink

## Risks

- **R-1**：自动加收藏可能让 favorites 列表无意扩张。缓解：响应里返回新增与否（可选）；本期不做，后续可加 `added` 字段
- **R-2**：token 泄露后任何外部服务可写挡位。缓解：token 仅写入 `.env.local`（已 .gitignore），不进仓库
- **R-3**：batch 部分成功时 favorites.json 已被改写。接受：覆盖式语义下，每条独立 `update_alerts` 调用，原子性足够；不做事务回滚

## Open Questions

- 无（设计阶段已澄清）
