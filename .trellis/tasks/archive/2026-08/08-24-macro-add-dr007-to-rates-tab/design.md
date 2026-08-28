# rates tab 加 DR007 曲线 — 技术设计

> 与 [prd.md](./prd.md) 配套。技术设计：模块边界、契约、数据流、向后兼容、风险与 rollback。

## 1. 模块边界与新文件清单

### 后端 — 新建

| 文件 | 角色 |
|------|------|
| `backend/macro/src/services/dr007_service.py` | DR007 fetcher，参考 `hibor_service.py` 模式 |
| `backend/macro/tests/test_dr007.py` | 单测 |

### 后端 — 修改

| 文件 | 改动 |
|------|------|
| `backend/macro/src/config.py` | 新增 `dr007_start_date: str = "2015-01-01"`（注意：DR007 在中国货币网公开历史数据自 2014-12 起，2015 起保留 1 年缓冲） |
| `backend/macro/src/api/routes.py` | (a) 第 1016 行 `_ALLOWED_DATA_TYPES` 加 `"dr007"`；(b) 新增 `POST /api/macro/fetch/dr007/history` + `POST /api/macro/update/dr007` 端点 |
| `backend/macro/src/services/data_service.py` | `query_data` 或等价聚合函数读取 `dr007.csv` 并按全量日期索引 ffill |
| `backend/macro/src/models.py` | `EconomicDataResponse` 加 `dr007: Optional[Dict[str, List[Optional[float]]]]` |
| `backend/macro/src/services/release_rules.py` | DR007 已在表中（line 34），无需新增（仅核对） |
| `backend/macro/docs/数据更新端点规范.md` | fetcher 表格加一行 |

### 前端 — 修改

| 文件 | 改动 |
|------|------|
| `apps/macro/src/lib/types/economic.ts` | `EconomicDataResponse` 加 `dr007?: { value: (number | null)[] }` |
| `apps/macro/src/app/modules/economic/components/RatesChart.tsx` | Plotly 单图 → 2 个 subchart（row 布局，shared xaxis） |
| `apps/macro/src/lib/hooks/useFilteredEconomicData.ts` | 若该 hook 对 `rates` tab 硬编码了字段，需扩到含 `dr007.value` |

## 2. 数据契约

### 2.1 后端响应新增字段

```jsonc
// GET /api/macro/data 响应新增顶层字段
{
  // ... 既有字段不变 ...
  "dr007": {
    "value": [null, null, 1.62, 1.61, ..., 1.68, 1.69]  // length == dates.length
  }
}
```

**对齐规则**（参考 china_bond / hibor）：
- 日期索引与顶层 `dates` 完全对齐
- 非交易日 / 缺失值为 `null`（前端 Plotly `connectgaps=false` 自动断开）
- 不允许用 0 填充（避免绘图误判为有效读数）

### 2.2 错误处理

- **HTTP 5xx / 429**：fetcher 走 `@async_retry(max_retries=3, delay=1.0)` 装饰器（沿用 `hibor_service` 模式）；重试失败抛异常，由 routes 层捕获并返回 `UpdateResponse(success=False, ...)`
- **CSV 解析失败（schema 变动）**：返回 `success=False, message="DR007 CSV 解析失败: <reason>"`，**不抛 500**，便于 n8n 重试
- **CSV 缺失 / 空文件**：`query_data` 返回空数组，前端拿到的是空 series，UI 不渲染该曲线但不报错

## 3. 复用与不复用清单

### 复用（按代码模式）

| 复用对象 | 复用方式 |
|----------|---------|
| `hibor_service.py` | fetcher 骨架（Session、async_retry 装饰器、返回 Series 的模式） |
| `routes.py` `fetch_vix_history` / `update_vix` | history + update 端点的结构模板 |
| `data_service.save_hibor_data` / `append_hibor_data` | CSV 落库 + 增量追加 |
| `release_rules.py` 的 `dr007` 项 | 已有 workdaily 规则，**无需新增**（macro-signal 那条） |
| `buildMultiAxisLayout` / `BASE_PLOT_CONFIG` | Plotly 主题封装（前端 subchart 拆后仍复用） |
| `monetary-policy-skill/scripts/fetch_dr007.py` 的解析思路 | CSV 列含义、解析函数（**仅参考，不 import**） |

### 不复用（明确）

| 对象 | 原因 |
|------|------|
| `monetary-policy-skill` 整个包 | 跨项目耦合，部署链路不同 |
| `fetch_common.py` | skill 私有 utils，依赖 skill 目录 .env |
| `china_bond_service.py` | 数据源是中国国债，非货币市场利率，CSV schema 不同 |

## 4. 数据流

### 4.1 初始化（一次性）

```
n8n / 手动 POST /api/macro/fetch/dr007/history
       { "historical_start_date": "2015-01-01" }
              ↓
       routes.fetch_dr007_history()
              ↓
       dr007_service.fetch_dr007_history(start, end)
              ↓
       fetch_text(CSV) → parse → DataFrame
              ↓
       data_service.save_dr007_data(df) → backend/macro/data/dr007.csv
```

### 4.2 日常更新（每日）

```
n8n / 手动 POST /api/macro/update/dr007
              ↓
       routes.update_dr007()
              ↓
       _compute_incremental_start(data_service, "dr007", latest_end)
              ↓
       dr007_service.fetch_latest(latest_end → today)
              ↓
       data_service.append_dr007_data(new_df) → 追加到 dr007.csv 末尾
```

### 4.3 前端消费

```
useFullEconomicData (顶层 hook)
   ↓ GET /api/macro/data
EconomicDataResponse（含 dr007.value）
   ↓ props 透传
RatesTab.useFilteredEconomicData(fullData, timeRange, 'rates')
   ↓
RatesChart 拆 2 subchart
   ├─ subplot 1 (上): DR007 | SOFR | 美债 3M | TED spread
   └─ subplot 2 (下): 中国 10y | 中国 10y-2y
   共享 xaxis
```

## 5. 关键技术决策

### 5.1 DR007 数据来源选型

| 候选 | 评价 |
|------|------|
| 中国货币网 prr-chrt.csv | **采用**。URL `https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`，列含义：`[日期, 加权利率(%), 加权平均(%), 成交笔数, 成交量(亿), 卖开利率, 买开利率, 加权平均(%)]`。**monetary-policy-skill 已验证可用**。 |
| akshare `bond_repo` | 备用。返回字段更丰富但限流更严，且 akshare 不一定在 `backend/macro` pyproject 里 |

**结论**：复用 skill 的 URL，按 `hibor_service.py` 模式写独立 fetcher，**不 import skill**（避免跨项目耦合）。

### 5.2 CSV 落库格式

参考 `hibor` 既有 CSV（用 grep 找一份样本）——大概率是 `date, value` 两列。无 schema 的话照 `hibor` 沿用即可。

### 5.3 RatesChart 拆 subchart 的实现路径

```ts
// Plotly multi-subplot 配置（伪代码）
const layout = {
  grid: { rows: 2, columns: 1, pattern: 'independent', roworder: 'top to bottom' },
  xaxis:  { /* subplot 1 的 x */ anchor: 'y2' },
  xaxis2: { /* subplot 2 的 x */ anchor: 'y' },
  yaxis:  { /* subplot 1 的左轴（DR007 + SOFR + 美债3M）*/ title: '短端利率 (%)' },
  yaxis2: { /* subplot 1 的右轴（TED spread）*/ overlaying: 'y', side: 'right' },
  yaxis3: { /* subplot 2 的左轴（中国 10y）*/ title: '中长端利率 (%)' },
  yaxis4: { /* subplot 2 的右轴（中国 10y-2y）*/ overlaying: 'y3', side: 'right' },
  height: 900,  // 拆 subchart 后整体高度上调（原 700px 单图 → 上下各 380px + 间距）
};
```

**关键**：
- `shared xaxes` 让两个 subchart 在切换时间范围时联动
- 复用现有 `buildMultiAxisLayout` / `BASE_PLOT_CONFIG`（不重写主题）
- Plotly `connectgaps=false` 处理节假日缺失段

### 5.4 不引入 skill 作为依赖

理由：
- `monetary-policy-skill/scripts/fetch_dr007.py` 的解析函数依赖 `fetch_common.py`，进而依赖 skill 目录的 `.env` 加载逻辑
- `backend/macro` pyproject 不应反向依赖 `F:/personal-projects/skills/finance-macro/`
- skill 与后端的部署链路不同：skill 输出到 `finance-macro/output/`，后端读 `backend/macro/data/`

## 6. 向后兼容性

### 6.1 API 兼容

- `EconomicDataResponse` 是**新增字段**（`dr007`），非破坏性。前端不读 `dr007` 时忽略即可。
- `_ALLOWED_DATA_TYPES` 加 `"dr007"` 不影响已有调用方。

### 6.2 前端类型兼容

- `EconomicDataResponse.dr007?` 为可选字段——旧前端版本（还没升级）会忽略此字段，UI 行为不变。

### 6.3 初始化安全

- **空 CSV / 缺数据**：前端 RatesChart 检测 `dr007.value` 全是 null 时静默不渲染该曲线（与 hibor / china_bond 缺失段处理一致），不抛错。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|------|------|------|
| 货币网 CSV 大批量初始化被限流（429） | 限速到每次 1 年窗口；3 次重试；首次失败可手动重试 | 删除 `data/dr007.csv`，回滚到 `EconomicDataResponse` 无 dr007 字段状态 |
| `routes.py` 第 1016 行白名单与 perf 任务冲突 | 先 `git fetch` 看 perf 任务分支是否改过，未改再合；若有冲突手动 rebase | 该行加 `"dr007"` 是单字符改动，revert 即可 |
| Plotly subchart 拆后视觉拥挤 / 高度不够 | 保持 700px → 900px 高度；若仍拥挤考虑 `roworder: 'top to bottom'` 配合 `vertical_spacing: 0.15` | 回滚 RatesChart 到单图（git revert） |
| `_ALLOWED_DATA_TYPES` 加了但 `query_data` 漏读 | 实施后跑 `pytest backend/macro/tests/test_dr007.py` + `curl /api/macro/data \| jq .dr007` 双重验证 | 删 `"dr007"` + 回滚 models.py |

## 8. 与 macro-page-perf 任务的边界

- **本任务不碰**：nginx gzip / FastAPI GZipMiddleware / `Cache-Control` 头 / 前端分层加载 / localStorage 缓存
- **本任务会小增响应体积**：DR007 单序列约 6KB（6000 个交易日 × 1 float），相对全量 3MB 可忽略（+0.2%）
- **本任务完成后可能影响 perf 任务的 gzip 收益基准**：在 AC 复核时让 perf 任务再跑一次 `curl --compressed -w '%{size_download}'` 对比 gzip 后体积

## 9. 不在范围（明确）

- R007（全市场 7 天回购）：URL `prr-mmrt.csv`，独立任务
- DR001 / R001 / 同业存单利率：独立任务
- DR007 单独 Tab：明确不做
- monetary-policy-skill 脚本迁移：解耦，不 import
- perf 优化（gzip / HTTP 缓存 / 分层加载）：属 macro-page-perf，不重复