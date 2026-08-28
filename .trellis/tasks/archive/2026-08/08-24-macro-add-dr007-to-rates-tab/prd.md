# rates tab 加 DR007 曲线

## Goal

在 `apps/macro` 的「利率利差」Tab 增加 **DR007（中国货币网 7 天质押式回购利率）日频曲线**，与已有的 SOFR / TED 利差形成"短端利率 + 利差"视图。当前 rates tab 只覆盖美国利率水平 + 中长端国债，缺中国短端市场利率这一关键参考。

## 背景

### 当前 rates tab 结构（apps/macro/src/app/modules/economic/components/RatesChart.tsx）

Plotly 单图 4 轴叠加：

| 轴 | 指标 | 量级 |
|----|------|------|
| y（左） | SOFR + 美债 3M | ~4-5% |
| y2（左内） | TED 利差 | ~0-1% |
| y3（右） | 中国 10y | ~1.5-3% |
| y4（右内） | 中国 10y-2y | ~0-1% |

数据从 `EconomicDataResponse` 中 `ted_spread.sofr / ted_spread.ted_spread / china_bond.10y / china_bond.spread_10y_2y` 取。

### 缺失的视角

DR007 是央行观察银行间流动性最常用的市场利率，与 7 天逆回购政策利率（OMO7D，当前 1.5%）对比判断银根松紧。`monetary-policy-skill/scripts/fetch_dr007.py` 已经实现了抓取逻辑（中国货币网 prr-chrt.csv 解析，含最新值 + 月内日均），但该 skill 走 `macro_signal.json` 上传链路，**没有接入 `/api/macro/data` 全量 JSON 响应**，前端拿不到历史日序列。

### macro-page-perf 任务背景

宏观页面性能优化任务（08-24-macro-page-perf，in_progress）正在解决全量 JSON 传输效率问题。本任务在其后端响应中**新增一条日频序列**，会小幅增加响应体积（DR007 单序列 ~6000 点 × 1 字段 vs 当前全量 ~23 万点，可忽略不计），不阻塞 perf 任务进度。

## Requirements

### 1. 后端 fetcher（数据采集）

复用 `monetary-policy-skill/scripts/fetch_dr007.py` 的解析思路，按本项目既有 service 模式落到 `backend/macro`：

- **新建文件** `backend/macro/src/services/dr007_service.py`
  - 类比 `china_bond_service.py` / `hibor_service.py` 的最小骨架（**不引入 `monetary-policy-skill` 作为依赖**，避免跨项目耦合；解析逻辑在本项目内独立维护）
  - 数据源：`https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`（与 skill 一致）
  - 解析：CSV 第 8 列（index 7）为当日 DR007 收盘利率（%）
  - 返回 DataFrame：`columns = ["date", "dr007"]`，date 为 `YYYY-MM-DD`，dr007 为 float
  - 增量更新起点：`_compute_incremental_start(data_service, "dr007", latest_end)`（与现有 5 个 update_* 一致）

- **新增端点**（在 `routes.py` 新增两个）：
  - `POST /api/macro/fetch/dr007/history`，body `{"historical_start_date": "YYYY-MM-DD"}`
  - 默认 start_date 从 `config.py` 新增 `dr007_start_date: str = "2015-01-01"`（DR007 2014 年底才有货币网公开历史，取 2015 起保安全）
  - 落 CSV：`backend/macro/data/dr007.csv`，列 `date,dr007`
  - `POST /api/macro/update/dr007`：增量抓取 + 追加

- **白名单扩列**：`routes.py` 第 1016 行 `_ALLOWED_DATA_TYPES` 加上 `"dr007"`

### 2. 后端响应契约（接入 /api/macro/data）

在 `EconomicDataResponse` 顶层 schema 加：

```json
"dr007": { "value": (number | null)[] }
```

具体动作：
- `models.py`（或等价 schema 文件）增加 `dr007: Optional[Dict[str, List[Optional[float]]]]`
- `data_service.py` 的 `query_data`（或等价聚合函数）按全量日期索引读取 `dr007.csv`，ffill 对齐日期（与 china_bond / hibor 处理一致）
- `routes.py` 的 `GET /api/macro/data` 返回结构加 `dr007` 字段

### 3. 前端类型与渲染

- **types**：`apps/macro/src/lib/types/economic.ts` 在 `EconomicDataResponse` 加 `dr007?: { value: (number | null)[] }`
- **`RatesChart.tsx` 拆为两个 subchart**：
  - **上图（短端利率 + 利差）**：DR007（独立左轴）+ TED spread（独立右轴）。SOFR / 美债 3M 留在原图（仍属短端）。
  - **下图（中长端）**：中国 10y + 中国 10y-2y 期限利差。
- 上下图共享 X 轴（同一时间范围），用 Plotly `subplots` + `specs: [[{"secondary_y": true}], [{"secondary_y": true}]]` 实现
- DR007 默认 1M/3M 视图有意义（短端波动大），无需特殊处理

### 4. 数据接入清单

| 端点 | 用途 |
|------|------|
| `POST /api/macro/fetch/dr007/history` | 历史一次性拉取（初始化） |
| `POST /api/macro/update/dr007` | 每日增量更新（手动 / n8n 调度） |

前端不需要新增按钮——复用现有 `InitButton` / `RefreshButton`，但要确保它们识别 DR007 数据已加载。

### 5. 文档与契约更新

- `backend/macro/docs/数据更新端点规范.md`：在 fetcher 表格加 DR007 一行
- `backend/macro/docs/MACRO_SIGNAL_API.md`（如涉及）：补 release rule
- 后端 `services/release_rules.py`：加 `dr007` 工作日规则（与现有 DR007 macro-signal 规则一致：`workdaily`）

## 约束

- 不引入 `monetary-policy-skill` 作为后端依赖。DR007 解析逻辑在本项目内独立维护，保持可移植但解耦。
- 不改变 `EconomicDataResponse` 现有字段，只新增 `dr007`
- 后端响应体积变化在可接受范围（单序列 ~6KB/6K 点 vs 全量 ~3MB）
- `routes.py` 中 `_ALLOWED_DATA_TYPES` 必须扩到包含 `dr007`，否则 `query_data` 静默丢弃
- DR007 数据源货币网 CSV 偶发 5xx / 限流，fetcher 沿用项目内既有重试模式（如 `china_bond_service` 是否有 retry，没有则至少加重试装饰器）

## 验收标准（Acceptance Criteria）

- [ ] **AC1 后端初始化**：调用 `POST /api/macro/fetch/dr007/history {"historical_start_date": "2015-01-01"}` 后，`backend/macro/data/dr007.csv` 存在，行数 ≥ 2000（2015 至今交易日数），首列日期格式 `YYYY-MM-DD`，第二列 DR007 利率（%）无空值（非交易日不写入）
- [ ] **AC2 后端响应**：`GET /api/macro/data` 返回 JSON 含 `dr007.value` 数组，长度 = `dates.length`，数组中非 null 元素日期对应交易日
- [ ] **AC3 后端更新**：`POST /api/macro/update/dr007` 后 CSV 末尾追加到昨日（含）或最新交易日（无重复日期）
- [ ] **AC4 前端渲染**：rates tab 切到 3M 视图，上图可见 DR007 曲线（颜色与 legend 一致），下图仍展示中国 10y + 10y-2y，X 轴对齐
- [ ] **AC5 时间范围**：切换 1M / 3M / 6M / 1Y / ALL 时两个 subchart 同步缩放
- [ ] **AC6 现有回归**：rates tab 原 4 条曲线（SOFR / 美债3M / TED / 中国10y / 中国10y-2y）仍正常显示，关闭 DR007 数据时（临时把 CSV 清空）其他曲线不断裂
- [ ] **AC7 类型安全**：`pnpm build`（apps/macro）通过，`pnpm lint` 无新增错误
- [ ] **AC8 后端测试**：新增/补齐 `tests/test_dr007.py`，覆盖 CSV 写入、增量更新、null 对齐三路径
- [ ] **AC9 文档**：`docs/数据更新端点规范.md` 已加 DR007 一行；`services/release_rules.py` 已加 `dr007` 规则

## 范围外（明确不做）

- R007（全市场口径）：本任务只做 DR007，R007 数据源货币网不同表（prr-mmrt.csv），独立任务
- DR001 / R001 / 同业存单利率等其它短端利率：本次不做
- DR007 单独 Tab：本次只并入 rates tab，不新增顶层 Tab
- `monetary-policy-skill/scripts/fetch_dr007.py` 的逻辑迁移到本项目：解析思路参考，但不依赖 / 不 import；本项目内独立维护
- 前端 localStorage 缓存迁移：与 macro-page-perf 任务解耦
- 性能优化（gzip / 分层加载 / HTTP 缓存头）：属于 macro-page-perf 任务，本任务不重复做

## 风险与依赖

- **风险**：中国货币网 CSV 偶发限流（HTTP 429），初始化大批量拉取可能被封。缓解：分批 sleep 重试，或退到只初始化最近 3 年。
- **依赖**：与 `08-24-macro-page-perf` 任务并行推进，无代码冲突（修改文件不同：后端 `services/` + `routes.py` 白名单一处；前端 `RatesChart.tsx` + `types/economic.ts`）。冲突点：`routes.py` 第 1016 行白名单——若 perf 任务碰过同一行需协调。
- **未确认点**：`_ALLOWED_DATA_TYPES` 之外的 `query_data` 数据集清单是否还需扩？需要实施时核实 `data_service.py`。

## Notes

- 复用 `monetary-policy-skill/scripts/fetch_dr007.py` 的解析思路是关键加速器——已有现成的 CSV 列含义、重试模式、解析函数可参考
- 选 RatesChart 拆 subchart 而非加 IndicatorSelector 是因为：当前 4 轴已显拥挤（rates tab 在 1Y/ALL 视图上标签密集），再加 1 条线会让 SOFR / TED / DR007 / 中国10y / 中国10y-2y 五个东西挤在一个图里；subplot 拆开后视觉更清晰
- DR007 是日频（工作日），与 SOFR 同频；用 Plotly `connectgaps=false` 即可在缺失段自然断开，无需特殊处理