# 宏观信号 API 文档

> 给后续 agent(数据写入层 + n8n cron)使用。后端实现已就位,本文件说明接口契约、数据源、agent 落地步骤。

## 数据源

后端**只读** macro-fin-skill 仓库产出的 JSON 文件,**不调用 skill 脚本、不重算 score/conclusion**。

```
{数据源根目录}/
├── monetary-policy-skill/macro_signal.json   # 货币政策
├── money-supply-skill/macro_signal.json       # 信用扩张
├── entity-economy-skill/macro_signal.json     # 经济运行
├── inflation-skill/macro_signal.json          # 通胀环境
├── exchange-rate-skill/macro_signal.json      # 外部压力
└── risk-appetite-skill/risk_data.json         # 市场情绪(注意文件名不同!)
```

数据源根目录通过环境变量 `MACRO_SIGNAL_DATA_DIR` 配置:

```bash
# 本地开发(默认，读 macro-fin-skill 仓库产出)
export MACRO_SIGNAL_DATA_DIR=F:/personal-projects/macro-fin-skill/skills

# 生产环境(NAS，由 agent 推送写入，持久卷 macro-data 下)
# docker-compose.nas.yml 已注入：MACRO_SIGNAL_DATA_DIR=/app/data/macro-signals
```

**生产环境数据由 agent 推送写入**(见下方 `POST /api/macro/signal/upload`),不再依赖共享存储 / n8n 同步。本地开发则直接读 macro-fin-skill 仓库目录。

数据源根目录若不存在或子目录缺 JSON 文件,该维度返回空 group,接口整体仍可正常返回 200(除非 6 个维度都无月份匹配 → 返回 404)。

---

## 接口列表

### `GET /api/macro/signal?month=YYYY-MM`

获取指定月份的 6 维度宏观信号快照。

#### 请求

```bash
curl 'http://localhost:8094/api/macro/signal?month=2026-05'
```

#### 响应(200)

```json
{
  "success": true,
  "data": {
    "month": "2026-05",
    "generated_at": null,
    "groups": {
      "monetary_policy": {
        "conclusion": "偏宽松",
        "indicators": [
          { "key": "dr007",  "value": 1.328, "updated_at": "2026-05-21" },
          { "key": "lpr_1y", "value": 3.0,   "updated_at": "2026-05-21" }
        ]
      },
      "money_supply": {
        "conclusion": "信用扩张",
        "indicators": [
          { "key": "m2_yoy",     "value": 8.6, "updated_at": "2026-05-13" },
          { "key": "m1_yoy",     "value": 5.0, "updated_at": "2026-05-13" },
          { "key": "social_yoy", "value": 7.8, "updated_at": "2026-05-13" }
        ]
      },
      "entity_economy": {
        "conclusion": "平稳",
        "indicators": [
          { "key": "electricity_yoy", "value": 3.5, "updated_at": "2026-04-20" },
          { "key": "railway_yoy",     "value": null, "updated_at": null }
        ]
      },
      "inflation":      { "conclusion": "温和",       "indicators": [...] },
      "exchange_rate":  { "conclusion": "外部中性",   "indicators": [...] },
      "risk_appetite":  { "conclusion": "偏热/乐观", "indicators": [...] }
    }
  }
}
```

#### 错误码

| 状态码 | 触发条件 | body |
|---|---|---|
| 404 | 请求月份无任何维度数据(macro-fin-skill 暂无快照) | `{ "detail": "No data for month YYYY-MM" }` |
| 500 | 服务内部异常 | `{ "detail": "错误描述" }` |

#### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `month` | string | 'YYYY-MM' |
| `groups` | object | 6 个 dimension key,固定顺序 |
| `groups[d].conclusion` | string \| null | skill 的定性结论(中文),如「温和」「偏宽松」「外部中性」 |
| `groups[d].indicators` | array | 该维度的所有指标 |
| `indicators[].key` | string | 指标 key,如 `cpi_yoy`、`dr007` |
| `indicators[].value` | number \| null | 指标数值,无数据为 null |
| `indicators[].updated_at` | string \| null | ISO 'YYYY-MM-DD',粒度到指标级 |

**indicator.updated_at 来源**:当前从 dimension `data_date` 派生(所有指标共用同一日期)。后续如果 skill 输出改为 per-indicator 时间戳,服务层不用改、前端自动正确显示。

#### 容错行为

- 单个 skill JSON 缺失或损坏 → 该维度 `{conclusion: null, indicators: []}`,其他维度正常
- 某指标 value 非数值 → 该 indicator 被跳过(不返回),但同维度其他指标正常
- 整组(空 `indicators`)→ 月份匹配检查视为无该月数据,可能返回 404

---

### `GET /api/macro/months`

获取当前可用的月份列表(降序)。

#### 请求

```bash
curl 'http://localhost:8094/api/macro/months'
```

#### 响应(200)

```json
{
  "months": ["2026-05", "2026-04", "2026-03"]
}
```

#### 字段说明

- `months` 数组,按 'YYYY-MM' **降序** 排列
- 来源:扫描 6 个 JSON,提取各 `data_date` 的 'YYYY-MM' 部分,合并去重

---

## 路径说明（nginx 反代）

| 层 | 路径 |
|---|---|
| 对外(浏览器 / agent 经网关) | `/api/macro/signal`、`/api/macro/months`、`/api/macro/signal/upload` |
| 后端内部(router prefix `/api`) | `/api/signal`、`/api/months`、`/api/signal/upload` |

nginx `location /api/macro/` 剥前缀直转后端,故**对外路径保持 `/api/macro/<x>` 不变**;本地直连后端测试用 `/api/<x>`。

---

### `POST /api/macro/signal/upload`

接收 macro-fin-skill agent 推送的 JSON,落盘到 `MACRO_SIGNAL_DATA_DIR`。写后自动清内存缓存,`GET /api/macro/signal` 立即可读新数据。

#### 请求

```bash
curl -X POST 'https://web.duomi77.cn:9443/api/macro/signal/upload' \
  -H "X-Upload-Token: $MACRO_SIGNAL_UPLOAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"skill":"monetary-policy-skill","file":"macro_signal.json","data":{ ...macro_signal.json 内容... }}'
```

#### 入参

| 字段 | 类型 | 说明 |
|---|---|---|
| `skill` | string | 子 skill 目录名,白名单:`monetary-policy-skill` / `money-supply-skill` / `entity-economy-skill` / `inflation-skill` / `exchange-rate-skill` / `risk-appetite-skill` |
| `file` | string | `macro_signal.json` 或 `risk_data.json`(白名单) |
| `data` | object | 该 skill 产出的原始 JSON |

#### 响应(200)

```json
{ "success": true, "skill": "monetary-policy-skill", "file": "macro_signal.json", "path": "/app/data/macro-signals/monetary-policy-skill/macro_signal.json", "bytes": 241 }
```

#### 错误码

| 状态码 | 触发条件 |
|---|---|
| 401 | `X-Upload-Token` 缺失/错误,或服务端未配 `MACRO_SIGNAL_UPLOAD_TOKEN` |
| 400 | `skill`/`file` 不在白名单(防路径穿越),或 `data` 非对象 |

#### 鉴权

`X-Upload-Token` header,constant-time 校验,值来自环境变量 `MACRO_SIGNAL_UPLOAD_TOKEN`(docker-compose.nas.yml 注入,根 `.env` 提供)。未配置则所有推送 401(生产必须配)。

#### agent 对接(macro-fin-skill 侧,跨仓库)

`run_all.py` 跑完 6 个 skill 后,遍历产出 JSON 逐个推送:

```bash
UPLOAD_URL='https://web.duomi77.cn:9443/api/macro/signal/upload'
for pair in "monetary-policy-skill:macro_signal.json" "money-supply-skill:macro_signal.json" \
            "entity-economy-skill:macro_signal.json" "inflation-skill:macro_signal.json" \
            "exchange-rate-skill:macro_signal.json" "risk-appetite-skill:risk_data.json"; do
  skill="${pair%%:*}"; file="${pair##*:}"
  curl -X POST "$UPLOAD_URL" -H "X-Upload-Token: $MACRO_SIGNAL_UPLOAD_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(jq -nc --arg skill "$skill" --arg file "$file" --slurpfile d "skills/$skill/$file" '{skill:$skill,file:$file,data:$d[0]}')"
done
```

---

## 缓存策略

- **5 分钟内存缓存**(进程内)
- 修改 skill JSON 后**不需要重启后端**,5 分钟后自动加载新数据
- 如需立即刷新,重启后端服务即可

---

## 给后续 agent 的实施指南

### 1. 数据写入责任

skill JSON 的更新由 **macro-fin-skill 各子 skill 的脚本**(`scripts/run_all.py`)负责。本服务只读不写。

### 2. 让前端看到最新数据

前端(`apps/macro`)的 NODE_ENV === 'production' 时自动调用本服务接口。数据流:

```
macro-fin-skill 各 skill 脚本
   ↓ 写入 macro_signal.json / risk_data.json
{数据源根目录}/
   ↓ 后端服务读(5 分钟缓存)
GET /api/macro/signal
   ↓ 前端 fetch
MacroSignalTab 渲染卡片
```

### 3. 部署到 NAS

后端部署到 NAS 时,需要确保:

1. NAS 上有 `MACRO_SIGNAL_DATA_DIR` 指向的目录
2. macro-fin-skill 通过某种方式(共享存储 / n8n cron / GitHub Actions)把 JSON 同步到该目录
3. 后端服务环境变量配置 `MACRO_SIGNAL_DATA_DIR`

### 4. 新增维度或指标

**前端契约固定**(`apps/macro/src/lib/modules/macro-signal/types.ts`)。如需新增:

1. 修改 skill 输出的 `details` JSON,加新指标
2. (可选) 修改本服务的 `_convert_dimension_from_macro_signal`,对特殊 key 做格式化
3. 前端 `constants.ts` 的 `INDICATOR_LABELS` 加中文翻译
4. 前端会自动按 `INDICATOR_LABELS` 查询显示 label,查不到 fallback 到原 key

**不需要**改接口路径、字段名、Pydantic 模型,后端服务完全透传。

---

## 接口契约变更原则

- 接口路径、字段名是**公开契约**,改动需同步更新本文档 + 前端类型
- 新增字段向后兼容(前端不解析新字段不报错)
- 删除字段需要前端先废弃再删除

---

## 测试用例

### 本地起后端

```bash
cd backend/macro
./.venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8094
```

### curl 测试

```bash
# 1. 查询当月快照(期望 200 + 6 维度 JSON)
curl http://localhost:8094/api/macro/signal?month=2026-05 | jq

# 2. 查询无数据月份(期望 404)
curl http://localhost:8094/api/macro/signal?month=2024-01

# 3. 查询可用月份(期望 {months: ["2026-05"]} 或更多)
curl http://localhost:8094/api/macro/months | jq
```

### 前端集成验证

```bash
cd apps/macro && pnpm dev  # 端口 3001
# 浏览器 http://localhost:3001/modules/economic
# 切到「宏观信号」Tab
# 预期:卡片数据来自真实接口,NOT mock
```