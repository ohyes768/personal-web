# global-macro-fin 后端新增宏观信号 API + 接口文档

## Goal

在 `backend/global-macro-fin` 子模块后端新增 2 个 REST 接口:
- `GET /api/macro/signal?month=YYYY-MM` — 返回该月 6 个维度的宏观信号快照(对齐 macro-fin-skill 的输出契约)
- `GET /api/macro/months` — 返回当前可用的月份列表

数据源直接读取 macro-fin-skill 各子 skill 产出的 `macro_signal.json`,**不重新实现 skill 计算逻辑**(避免重复)。

并产出 `MACRO_SIGNAL_API.md` 接口文档供后续 agent 实现数据写入逻辑时参考。

## Background

### 数据源结构(`F:\personal-projects\macro-fin-skill\skills\`)

```
monetary-policy-skill/macro_signal.json   # 货币
money-supply-skill/macro_signal.json       # 信用
entity-economy-skill/macro_signal.json     # 经济
inflation-skill/macro_signal.json          # 通胀
exchange-rate-skill/macro_signal.json      # 外部压力
risk-appetite-skill/risk_data.json         # 市场情绪(注意这个文件名为 risk_data.json)
```

每个 skill 的 `macro_signal.json` 结构:
```json
{
  "dimension": "monetary_policy",
  "score": 67.44,
  "conclusion": "偏宽松",
  "data_date": "2026-05-21",
  "errors": [],
  "details": { "dr007": 1.328, "lpr_1y": 3.0 },
  "generated_at": "2026-05-22T07:59:22Z"
}
```

`risk_appetite` 比较特殊:输出在 `risk_data.json`,结构嵌套(`data.volume.total_amount_yi` 等),需要单独适配。

### 前端已实现的契约(`apps/economic/src/lib/modules/macro-signal/types.ts`)

```typescript
interface MacroIndicator { key, value: number|null, updated_at: string|null }
interface MacroSignalGroup { conclusion: string|null, indicators: MacroIndicator[] }
interface MacroSignalSnapshot {
  month: 'YYYY-MM',
  groups: Record<DimensionKey, MacroSignalGroup>,  // 6 个维度
  generated_at?: string
}
```

后端返回 shape 必须严格对齐此契约,前端**已写好**(`useMock` 仅 dev 时使用,prod 走真实接口)。

### 配置

后端 `config.py` 当前只有 `data_dir: str = "./data"`,需要新增 `macro_signal_data_dir` 指向 skill 仓库。

## Requirements

### 功能需求

- **R1 `GET /api/macro/signal?month=YYYY-MM`**:
  - 返回该月 6 个维度的快照
  - 数据从 macro-fin-skill 各 JSON 文件读取
  - 字段对齐前端 `MacroSignalSnapshot` shape
  - 每个 indicator 带 updated_at(粒度到指标级,从 skill details 的 data_date 派生,因为 skill JSON 当前只有维度级 data_date)
  - 找不到该月数据时返回 404,body 为 `{ "detail": "No data for month YYYY-MM" }`
  - 整体响应 < 200ms(纯读文件,无网络)

- **R2 `GET /api/macro/months`**:
  - 扫描 macro-fin-skill 各 JSON,推断可用月份
  - 推断方法:取各 JSON `data_date` 的 `YYYY-MM` 部分,合并去重,降序排序
  - 返回 `{ "months": ["2026-05", "2026-04", ...] }`

- **R3 macro_signal_service.py**: 单一职责的 service 模块
  - 读 skill 各 JSON,聚合成前端需要的 shape
  - 处理 risk_appetite 特殊结构
  - 缓存:5 分钟内存缓存(可选优化,P0 不强制)

- **R4 接口文档 `backend/global-macro-fin/docs/MACRO_SIGNAL_API.md`**:
  - 完整列出 2 个接口的请求/响应示例、字段说明、错误码
  - 给后续 agent 的实施指南:如何更新 `macro_signal.json` 让前端拿到最新数据

### 非功能需求

- **N1 不重新实现 skill 计算逻辑**:后端只读 JSON,不调用 skill 脚本,不重算 score/conclusion
- **N2 不破坏现有接口**:新接口路径不冲突(`/api/macro/signal` 与 `/api/macro/[...path]` 前端 BFF catch-all 不冲突,因为这个后端是 `localhost:8094`,而 BFF 是 `/api/macro/*` → `localhost:8094/api/*`)
- **N3 不引入新依赖**:沿用 FastAPI + pydantic,JSON 读写用 stdlib `json`
- **N4 容错**:某个 skill 的 JSON 缺失或损坏时,该维度 `indicators: []`、`conclusion: null`,不阻塞其他维度

## Out of Scope

- ❌ 调用 skill 脚本实时计算(留给 n8n / cron)
- ❌ 数据写入(agent 后续做)
- ❌ 历史月份数据回填(macro-fin-skill 当前只有 2026-05 一个月快照,接口先支持单月查询,后续 agent 回填历史)
- ❌ 缓存层(Redis / 文件缓存)— P0 不做
- ❌ 评分 / 综合指数计算(前端不需要)
- ❌ 单元测试(P0 阶段接口契约清晰,后续 agent 加测试)

## Acceptance Criteria

- [ ] AC1 `GET /api/macro/signal?month=2026-05` 返回完整 6 维度快照,字段对齐前端 `MacroSignalSnapshot`
- [ ] AC2 `GET /api/macro/signal?month=2024-01` 返回 404(因为 skill 当前没该月数据)
- [ ] AC3 `GET /api/macro/months` 返回降序月份数组(至少 `["2026-05"]`)
- [ ] AC4 `risk_appetite` 维度数据正确从 `risk_data.json` 的 `data.volume` / `data.turnover` / `data.margin` 提取(转成 `total_amount_yi` / `turnover_rate` / `margin_balance_yi`)
- [ ] AC5 indicator 的 `updated_at` 是 ISO 'YYYY-MM-DD'(从 dimension `data_date` 派生,因为 skill 的 details 内没有 per-indicator 时间戳)
- [ ] AC6 某 skill JSON 缺失时,该维度返回 `{ conclusion: null, indicators: [] }`,其他维度正常返回
- [ ] AC7 接口文档 `MACRO_SIGNAL_API.md` 包含 2 个接口的完整示例、字段表、agent 实施指南
- [ ] AC8 `python -m pytest backend/global-macro-fin/tests/` 通过(若存在测试)

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| skill 的 details 没有 per-indicator 时间戳 | 从 dimension `data_date` 派生 indicator `updated_at`(所有指标用同一日期)— 后续 agent 接入时可改为带 per-indicator 时间戳的 skill 输出 |
| macro-fin-skill 路径配置错误 | 用 `config.py` 配置项 + 环境变量,默认值指向 `F:\personal-projects\macro-fin-skill\skills`(本地开发),生产环境用环境变量覆盖 |
| risk_data.json 结构特殊 | service 内单独处理 risk_appetite 维度,与其他 5 个维度分支处理 |
| 前端契约变更 | Phase 3 文档化:接口路径 + 字段在 `MACRO_SIGNAL_API.md` 锁定,前端若有变更需要同步更新文档 |

## Notes

- 数据源路径在生产环境通过环境变量 `MACRO_SIGNAL_DATA_DIR` 配置
- 子模块独立 commit + push,主仓库更新 gitlink
- 接口文档位置:`backend/global-macro-fin/docs/MACRO_SIGNAL_API.md`(已存在的 docs 目录)