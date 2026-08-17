# 宏观信号 API 文档

> 给后续 agent(数据写入层 + n8n cron)使用。后端实现已就位,本文件说明接口契约、数据源、agent 落地步骤。

## 数据源

后端**只读** macro-fin-skill 仓库产出的 JSON 文件,**不调用 skill 脚本、不重算 score/conclusion**。

```
{数据源根目录}/
├── monetary-policy-skill/macro_signal.json   # 最新快照:货币政策
├── money-supply-skill/macro_signal.json       # 最新快照:信用扩张
├── entity-economy-skill/macro_signal.json     # 最新快照:经济运行
├── inflation-skill/macro_signal.json          # 最新快照:通胀环境
├── exchange-rate-skill/macro_signal.json      # 最新快照:外部压力
├── risk-appetite-skill/risk_data.json         # 最新快照:市场情绪(注意文件名不同!)
└── archive/                                   # 按月归档(生产真源,upload 自动写入)
    ├── 2026-05/
    │   ├── monetary-policy-skill.json
    │   ├── ...                               # 每个 skill 一个 <skill目录名>.json
    │   └── risk-appetite-skill.json
    └── 2026-06/
        └── ...
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

### 按月留存(归档)

- **写入**:`POST /api/macro/signal/upload` 落盘时执行三步——①旧最新文件按其数据月份**抢救归档**(跨月推送自动留存历史;部署后首次推送自动迁移存量) ②覆盖平铺最新文件 ③本次数据按其数据月份归档。同月重复推送幂等(归档被最新一次覆盖)。
- **归档月份提取**:`macro_signal.json` 取顶层 `data_date` 前 7 位;`risk_data.json` 取 `data.{volume,turnover,margin}.date` 最大值的前 7 位;格式必须为 `YYYY-MM`,提取失败仅跳过归档(平铺最新文件仍写入)。
- **读取**:`GET /api/macro/signal?month=` 优先读 `archive/<month>/`(生产真源,部分 skill 缺失 → 该维度空 group);归档无该月再兜底读平铺最新文件并做月份匹配(本地开发直读 skill 仓库场景)。`month` 参数严格校验 `^\d{4}-\d{2}$`(防路径穿越),非法返回 404。
- **容量**:每 skill JSON 数 KB,每月 6 个文件,默认永久保留。

> 详细设计见[宏观信号按月留存设计.md](./宏观信号按月留存设计.md)。

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
    "generated_at": "2026-05-22T07:59:22Z",
    "groups": {
      "monetary_policy": {
        "conclusion": "偏宽松",
        "score": 67.44,
        "indicators": [
          {
            "key": "dr007", "value": 1.328,
            "updated_at": "2026-05-21", "data_date": "2026-05-21",
            "analyzed_at": "2026-05-22T07:59:22Z",
            "next_release_at": "2026-05-25", "next_release_note": "DR007 每个工作日随银行间市场更新",
            "frequency": "daily"
          },
          {
            "key": "lpr_1y", "value": 3.0,
            "updated_at": "2026-05-20", "data_date": "2026-05-20",
            "analyzed_at": "2026-05-22T07:59:22Z",
            "next_release_at": "2026-06-22", "next_release_note": "LPR 每月20日发布(节假日顺延)",
            "frequency": "monthly"
          }
        ]
      },
      "money_supply": {
        "conclusion": "信用扩张",
        "indicators": [
          { "key": "m2_yoy", "value": 8.6, "updated_at": "2026-05-13", "data_date": "2026-05-13", "analyzed_at": "2026-05-22T07:59:22Z", "next_release_at": "2026-06-12", "next_release_note": "金融统计数据(M2/社融)约每月13日发布" }
        ]
      },
      "entity_economy": {
        "conclusion": "平稳",
        "indicators": [
          { "key": "electricity_yoy", "value": 3.5, "updated_at": "2026-04-20", "data_date": "2026-04-20", "analyzed_at": "2026-05-22T07:59:22Z", "next_release_at": "2026-05-20", "next_release_note": "工业用电量约每月20日发布" },
          { "key": "railway_yoy", "value": null, "updated_at": null, "data_date": null, "analyzed_at": null, "next_release_at": null, "next_release_note": null }
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
| 404 | 请求月份无任何维度数据(macro-fin-skill 暂无快照),或 month 格式非法(非 `YYYY-MM`,防路径穿越) | `{ "detail": "No data for month YYYY-MM" }` |
| 500 | 服务内部异常 | `{ "detail": "错误描述" }` |

#### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `month` | string | 'YYYY-MM' |
| `generated_at` | string \| null | 全页最新分析时间 = 所有指标 `analyzed_at` 的最大值 |
| `groups` | object | 6 个 dimension key,固定顺序 |
| `groups[d].conclusion` | string \| null | skill 的定性结论(中文),如「温和」「偏宽松」「外部中性」 |
| `groups[d].indicators` | array | 该维度的所有指标(三时间都是指标级) |
| `indicators[].key` | string | 指标 key,如 `cpi_yoy`、`dr007` |
| `indicators[].value` | number \| null | 指标数值,无数据为 null |
| `indicators[].data_date` | string \| null | **数据时间** 'YYYY-MM-DD',指标数值所属/发布日期 |
| `indicators[].analyzed_at` | string \| null | **分析时间** ISO timestamp,skill 生成/推送该值的时间(自报缺失时用文件 mtime 兜底) |
| `indicators[].next_release_at` | string \| null | **下个周期预期发布日** 'YYYY-MM-DD',自报优先、后端规则兜底 |
| `indicators[].next_release_note` | string \| null | 预期口径说明,如「CPI/PPI 约每月9日发布上月数据」 |
| `indicators[].frequency` | 'daily' \| 'monthly' \| null | **发布频率**(自报优先、规则表推导);日频前端不渲染「下次」段,只显示「日频」标记 |
| `indicators[].updated_at` | string \| null | **兼容别名** = `data_date`,后端双写过渡,前端迁移完成后删除 |

#### 指标级三时间的来源优先级

| API 字段 | macro_signal.json 自报 | 兜底(当前默认) |
|---|---|---|
| `data_date` | `indicator_meta[key].data_date` | 组级 `data_date` 前 10 位 |
| `analyzed_at` | `indicator_meta[key].analyzed_at` | 组级 `generated_at`(risk_data 用子块 `fetched_at` → 顶层 `data.fetched_at`) → **文件 mtime(推送时间)** |
| `next_release_at/note` | `indicator_meta[key].next_release` | 后端 `release_rules.py` 按指标规则推算 |
| `frequency` | `indicator_meta[key].frequency`('daily'/'monthly') | 规则表 kind 推导(workdaily→daily,monthly/month_end→monthly) |

risk_data.json 天然指标级:子块 `date` → `data_date`,子块 `fetched_at` → `analyzed_at`,子块 `next_release`/`frequency` → 自报下期预期与频率。

#### skill 自报契约(可选,向后兼容)

macro_signal.json 可选新增 `indicator_meta`,不新增也不影响现有兼容逻辑:

```json
{
  "dimension": "inflation",
  "conclusion": "温和",
  "data_date": "2026-05-11",
  "generated_at": "2026-05-22T07:59:22Z",
  "details": { "cpi_yoy": 1.2 },
  "indicator_meta": {
    "cpi_yoy": {
      "data_date": "2026-05-11",
      "analyzed_at": "2026-05-22T07:59:22Z",
      "next_release": { "date": "2026-06-09", "note": "CPI/PPI 约每月9日发布上月数据" },
      "frequency": "monthly"
    }
  }
}
```

risk_data.json 子块自报:`data.volume.next_release = { "date": ..., "note": ... }`、`data.volume.frequency = "daily"`(turnover/margin 同理)。

#### 后端兜底规则表(`src/services/release_rules.py`)

规则来源:各 skill SKILL.md「数据发布时间」,工作日=周一~周五(不含法定节假日,note 用「约」表达误差)。
基准日 = max(指标 `data_date`, 今天),保证「下次」一定在未来。
频率划分:**日频**(每工作日更新,前端不显示「下次」只显示「日频」标记)与**月频**(显示「下次 ≈MM-DD」);API 层两类都返回 `next_release_at`,是否展示由前端按 `frequency` 决定。

**日频(daily)**:

| indicator key | 规则 |
|---|---|
| `dr007` / `dollar_index` / `usd_cny` / `ted_spread` / `total_amount_yi` / `turnover_rate` / `margin_balance_yi` | 每工作日 → 下一个工作日 |

**月频(monthly)**:

| indicator key | 规则 | 周末校正 |
|---|---|---|
| `lpr_1y` | 每月20日 | 顺延(央行惯例) |
| `mlf_1y` | 每月15日 | 顺延 |
| `m2_yoy` / `m1_yoy` / `social_yoy` | 每月13日 | 前移 |
| `industrial_yoy` / `fai_yoy` / `retail_yoy` | 每月13日 | 前移(统计局惯例提前) |
| `electricity_yoy` | 每月20日 | 前移 |
| `railway_yoy` | 每月7日 | 前移 |
| `cpi_yoy` / `ppi_yoy` / `core_cpi_yoy` | 每月9日 | 前移 |
| `pmi_manufacturing` | 每月最后一日发布当月数据 | 不校正 |
| 其他未知 key | 无规则 → `next_release_at`/`frequency` 均为 null,前端不渲染「下次」段 | — |

> 注:货币政策组是混合频率(DR007 日频 + LPR/MLF 月频),因此 frequency 做在指标级而非维度级。前端 `release-rules.ts` 的 inflation 规则(10日)与 SKILL.md(9日)不一致,以后端本表(9日)为准;前端发布日历后续可改为消费本 API。

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
- 来源:`archive/` 归档月目录 ∪ 平铺最新 6 个 JSON 的 `data_date` 'YYYY-MM',合并去重

---

## 路径说明（nginx 反代）

| 层 | 路径 |
|---|---|
| 对外(浏览器 / agent 经网关) | `/api/macro/signal`、`/api/macro/months`、`/api/macro/signal/upload` |
| 后端内部(router prefix `/api`) | `/api/signal`、`/api/months`、`/api/signal/upload` |

nginx `location /api/macro/` 剥前缀直转后端,故**对外路径保持 `/api/macro/<x>` 不变**;本地直连后端测试用 `/api/<x>`。

---

### `POST /api/macro/signal/upload`

接收 macro-fin-skill agent 推送的 JSON,落盘到 `MACRO_SIGNAL_DATA_DIR` 并**按月归档**(见上方「按月留存」)。写后自动清内存缓存,`GET /api/macro/signal` 立即可读新数据,历史月通过 `?month=` 可查。

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
{ "success": true, "skill": "monetary-policy-skill", "file": "macro_signal.json", "path": "/app/data/macro-signals/monetary-policy-skill/macro_signal.json", "bytes": 241, "archived_month": "2026-08" }
```

#### 响应字段

| 字段 | 说明 |
|---|---|
| `archived_month` | 本次数据归档到的月份 'YYYY-MM';data 提取不到合法月份时为 `null`(此时仅写平铺最新文件,历史留存降级) |

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