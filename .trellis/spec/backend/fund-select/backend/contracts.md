# fund-select 契约（API / DB / 缓存 / 前后端链路）

## 1. Scope / Trigger

任务 09-01-fund-select-v1-bond 新增跨层契约（FastAPI ↔ Next.js 代理 ↔ 前端表格/对比），且补回了预研缺失的费率 fetcher 契约。记录于此防止后续 session 漂移。

## 2. Signatures

### API（前缀 /api/funds，全部 GET）

| 路由 | 参数 | 返回 | 错误 |
|---|---|---|---|
| /health | - | `{status:"ok"}` | - |
| /screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp（均可空）; sort; order; exclude_qdii（默认 false）; **page**（默认 1, ≥1）; **limit**（默认 50, 1-200） | `{total, items:[FundListItem]}` **total=筛后总数；items=当页** | sort 不在白名单→422；page<1 / limit<1 / limit>200 → 422 |
| /stock/screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp, min_sharpe（股票独有）; sort; order; exclude_qdii; **page, limit** | 同 /screen | 同 /screen |
| /discovery-bond/screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp, min_sharpe, min_ret_1y, min_ret_3y, max_nav_stale_days; market_types（akshare 粗类别，可空）; sort; order; exclude_qdii; **page, limit** | 同 /screen | 同 /screen |
| /discovery-stock/screen | 同 /discovery-bond/screen | 同 /screen | 同 /screen |
| /{code} | - | FundDetail（业绩+fees+holdings） | 404 |
| /refresh | limit 可空 | `{task_id, status:"started"}`（BackgroundTasks） | - |
| /refresh/status | task_id 可空（空=最近一次） | `{task_id,status,total,completed,failed,errors[]}` | 404 无记录 |
| /export/csv | 同 screen | text/csv + UTF-8 BOM + `filename=funds_YYYYMMDD.csv` | - |
| /stats | - | `{total,with_performance,with_fees,with_holdings,last_refresh_at}` | - |

### 分页契约（09-09-fund-select-pagination）

**核心不变量**：

- `total` 永远是**筛后命中总数**，与 page / limit 无关。前端用它算总页数 `Math.ceil(total/limit)`。
- `items` 长度 ≤ `limit`，可能为空（`page` 越界时）。
- `total` 与 `items` 的关系：`items ⊂ 全量items；total = len(全量items)`。多页之间无重叠、无遗漏（按当前 sort 排序后切片）。

**服务端排序-切片顺序（关键）**：

```python
# 1. SQL JOIN 取全量 rows
rows = self.db.execute(q).all()
# 2. ach_map 仍按全量 codes 查（保证排序前数据完整，rank 字段不丢）
codes = [f.code for f, *_ in rows]
ach_rows = self.db.execute(select(...).where(FundAchievementRank.code.in_(codes))).all()
# 3. 组装全量 items
items = [_to_dto(f, p, fee, hold, risk, market_rank, ach_map.get(f.code)) for f, p, fee, hold, risk, market_rank in rows]
total = len(items)
# 4. Python in-memory 排序（None 永远排末位）
valued = [it for it in items if getter(it) is not None]
valued.sort(key=getter, reverse=descending)
empty = [it for it in items if getter(it) is None]
ordered = valued + empty
# 5. ★ 切片在排序之后
offset = (page - 1) * limit
items_page = ordered[offset : offset + limit]
return {"total": total, "items": items_page}
```

**为什么不在 SQL 层 ORDER BY + LIMIT/OFFSET**：

- 现状：discovery-stock universe ~4500 只 → Python `list.sort` < 100ms，深页 offset 切片 O(N) 但仍 < 1s
- 风险：5000→5w+ 时再切 SQL。当前不做是为避免 SQL 注入白名单、LEFT JOIN 多表、ach_map 二次查询的复杂改造
- 触发再切的条件：universe > 5w 或 P95 > 1s

**与 FundAchievementRank 的关系**：

`ach_map` 查询用 `codes = [f.code for f, *_ in rows]`，是**排序前**的全量 codes。排序-切片不会影响 rank 字段正确性（每页 DTO 内 rank_* 都来自同一份 ach_map）。

**前端 URL 同步**（`useFilters` / `parseFiltersFromSearch` / `filtersToSearch`）：

| URL 参数 | 写入条件 | 默认 |
|---|---|---|
| `page` | `page > 1` | 1 |
| `limit` | `limit !== 50` | 50 |

**筛选 vs 排序 对 page 的影响**：

| 触发 | page 重置？ |
|---|---|
| numeric 维度 / exclude_qdii / market_types 变化 | ✅ 重置 page=1 |
| sort 字段 / order 变化 | ❌ 保持 page |
| setLimit | ✅ 重置 page=1 |
| clearAll | ✅ 重置 page=1（合理：清空筛选后命中集变了，原 page 没意义） |

**前端状态归属**：`page` / `limit` 是 `FundFilters` 的字段，跟其它 numeric 维度一起序列化/反序列化、一起触发 useEffect 重拉。不另起 state，避免 URL / 状态双源。

**`LIMIT_OPTIONS = [25, 50, 100] as const`** 导出在 `apps/fund-select/src/lib/types.ts`，Pagination 组件直接复用，不硬编码。

**Performance budget**：discovery-bond 全 universe（~500 只）page=1, limit=50 → 后端 P95 < 800ms（含 DB JOIN × 5 + Python sort + 4 周期排名查询）；前端首屏 < 1.5s。

### 关键语义

- **dd_3y 库内为负值**（如 -4.47）。用户阈值 `max_dd_3y=5` 按**绝对值**比较：SQL 用 `dd_3y >= -abs(max_dd_3y)`。前端展示原值（负号保留）。
- **fee_annual 是计算字段**：`fee_mgmt + fee_custody + (fee_service or 0)`；任一主字段缺失返回 null（不是 0）。
- **筛选宇宙按 yaml 切分**，再 ∩ `is_active==True`：
  - `/screen`、`/export/csv`、`/stats` → `config/funds.yaml`
  - `/stock/screen`、`/stock/export/csv`、`/stock/stats` → `config/funds_stock.yaml`
  - **yaml 名单阶段不要用 `fund_type LIKE` 当成员判定**（名单已分宇宙；`fund_type` 只展示）。
  - **全市场扫描（未做）** 再启用 `fund_type` 收口（股票型 / QDII / 混合型 vs 债券型）。
  - 详情 `/{code}`、`/stock/{code}` 仍按 code 查库，不按宇宙 404。
- **排除 QDII 是用户筛选 overlay**（`exclude_qdii=true`）：丢掉 `fund_type LIKE 'QDII%'` 或 `fund_type == '互认基金'`；`fund_type` 为 NULL 的保留。默认关闭，yaml 里的 QDII 仍显示。债基 `/screen`、`/export/csv` 与股票 `/stock/screen`、`/stock/export/csv` 都支持。
- 不按债券类型过滤（31 只含混合/QDII 照常展示）。
- FundPerformance 用 **LEFT JOIN**：无业绩记录的基金保留在筛选结果（业绩列显示 null → 前端 "-"）。
- **min_sharpe 仅股票 tab（09-04-stock-fund-sharpe-filter）**：`/stock/screen?min_sharpe=X` → `sharpe >= X`；sharpe 为 NULL（benchmark 不可用/样本不足，见 fund_risk_metrics 语义）的基金被一并排除，与 dd_3y 筛选惯例一致。前端 `STOCK_DEFAULT_FILTERS.min_sharpe = 0.8`（股票宇宙分布：中位 0.73 / p75 0.90，默认结果 142→53 只；叠加四维默认〔回撤 30〕后 25 只）；债基 `DEFAULT_FILTERS.min_sharpe = null` 且侧栏不渲染该项（`FilterPanel dimensions` prop 默认四维，股票页传 `STOCK_DIMENSIONS` 五维）。

### ORM（src/db/models.py）

- `funds`：code PK；age_years/size_yi/mgr_experience_years（Float 可空）；is_active 默认 True
- `fund_performance`：code PK；ret_1m/6m/1y/3y/5y + **dd_1y/3y/5y**（只有这三档回撤，无 dd_1m/dd_6m——performance_service 显式过滤）
- `fund_fees`：8 字段对齐预研 `cache/fees_{code}.json` 契约
- `fund_holdings_bond`：(code, report_date) 复合 PK。**只由债基 refresh 写入**：`snapshot_fund(fetch_holdings=True)`（债基路径默认）；股票 refresh 传 `fetch_holdings=False` 完全跳过季报拉取，不发 zqcc 请求。跳过逻辑按宇宙开关，不按 `fund_type` 猜（fund_type 短路已删）。

### 风险指标口径（fund_risk_metrics，risk_service.py）

- r_p 用 `fetch_nav` 的**日增长率/100**（东财复权口径，分红日已调整）。**陷阱**：不要用「累计净值」pct_change——它是 `单位净值+历史分红` 的简单加总（非复权），历史有分红的基金（库内 11/143 只）全序列被稀释：673010 实证 3 年 cum_p 63.4%（稀释）vs 98.8%（真复权），超额3y 46% → 81%。`fetch_nav_accumulated` 已因此删除。
- r_b = benchmark TRI pct_change（tri=NULL 的 QDII/互认基金：sharpe 有值、基准相关 4 指标 None）；r_f = risk_free_rate 表年化小数 /252 折日频。
- 窗口 = 近 3 年自然日；r_p∩r_b inner join，实际窗口尾日受 TRI 尾日约束（可能比净值尾日早一天，`as_of_date` 存的是刷新日）。样本下限 250 天。
- α = T-M 回归截距 ×252 简单年化；γ = 日频二次项系数（不年化、无量纲）；α-IR = α_d/σ_e×√252；夏普/IR = 日均超额/std×√252；excess_3y = 连乘累计算术差。
- `refresh_runs`：task_id PK，进度轮询数据源

### 基准 TRI 合成契约（fetch_benchmark_tri，benchmark_fetcher.py）

多成分基准（公式 N 个指数 + 存款）**必须按价格对齐，禁止对日收益 ffill**（任务 09-04-benchmark-price-align）：

```
成分存 close（index 与 unknown→fallback 分支都是）
→ 并集日历 reindex → ffill 价格 → dropna()（裁掉最晚成分上市前的前导行）
→ pct_change().fillna(0)   # 缺席交易日价格不变 → 收益 0，不复制前日收益
→ weighted = Σ ret×(w/total_w)；deposit 成分 = PBOC_DEPOSIT_FLOOR_RATE/252 常数铺满
→ tri = (1+weighted).cumprod() × 1000；source 标记不变
```

**source 枚举**（`fund_benchmark.source`，同 models.py 注释）：`fetched` / `partial:fallback:<sym>` / `fallback_chain:<sym>` / `unavailable:no_field` / `unavailable:basic_failed` / `unavailable:exhausted` / `unavailable:unknown_majority` / `skipped:qdii`。

**parse_formula 语义**（09-04-benchmark-yaml-coverage 扩充）：

- 乘号归一：`×`/`＊` translate；半角 `x` **仅在后跟数字时**视为乘号（`x(?=\d)`）——「收益率x60%」是乘号、「Index」内 x 是字母，一律 translate 会把英文名拆碎成 weight=0 的 unknown。
- 裸 `N%` 成分（公式末尾 `＋1%` 无指数名）→ `Component(name='存款加成', kind='deposit_floor')` 常数日收益 N%/252，不打「无法解析权重」warning。
- 剥离嵌套括号后残留的孤立 `(`/`)` 一并清除（非贪婪 `\(.*?\)` 只能剥一层）。
- `_PREFIXES` 含「人民币计价的」「经汇率调整的（后）」等实测语料前缀。

**高权重 unknown 置 NULL（R4，宁缺毋错）**：unknown 成分 weight ≥ 0.5 时**不**用 fallback 指数顶替，返回空 TRI + `source=unavailable:unknown_majority`（risk_service 对 tri=NULL 行取不到 r_b → 4 指标 None，不抛错）；weight < 0.5 维持 fallback 顶替 + `partial:fallback` 标记。

**Why**：A/HK/美/中债交易日历互不重合（港股佛诞、美股感恩节等）。对收益 ffill 会把成分缺席日的前一日收益**再计一次**，混合日历 3 年虚高 13.5pp（004316：真 +21.8% 算成 +35.3%），excess/IR/α 全歪。单成分基准两算法等价（回归测试锁定）。

**B1（已修复，09-04-fix-bond-index-date-shift）**：旧源 `bond_composite_index_cbond`（中债综合指数 财富/总值）返回日期整体 **−1 天**（真实周一标成周日、周五标成周四；2026-09-04 复测 3 年分布 Sun=142/Sat=11/Fri=9，与 A 股日历重叠 580/746；+1 天后 725/746，剩余 20 个周末行全部是债市调休交易日——股市休市、银行间开市，属正常）。中债成分收益落在错位日期上，inner join 丢周末行 → 中债周五收益永久丢失。**修复 = 换源非 shift**：`bond_index_general_cbond(index_category="综合指数", indicator="财富", period="总值")` 与旧源全史 6171 行逐值 **0 差值**（同一指数序列）、日期正确、还多最新一天；不做 +1 天 hack（源若日后自行修正会反向错位）。yaml `中债综合财富.source` 已改，ak_symbol 仍为 CBA00301。注意：中债日历含约 20 天/3 年的调休周六日，与 A 股指数并集合成时这些行股指数贡献 0、债指数贡献真实收益，是正确行为。
- **B1.2（已迁移，09-09-fix-pre-existing-pytest）**：akshare 1.18.39 移除 `bond_index_general_cbond` API（refresh 命中即 AttributeError）。迁到 `bond_new_composite_index_cbond()`（无需参数，默认全序列，返回 `[date, value]`）。该源**本身无 B1 错位 bug**：2026-09-09 实证 6174 行 / 近 3 年 weekday 分布 Sun=11 / Sat=9 调休 / Mon-Fri=144-149（与 B1 bug 实证的 Sun=142/Sat=11/Fri=9 截然不同）。yaml `中债综合财富.source` 同步更新为 `bond_new_composite_index_cbond`，生产 refresh 路径不再 AttributeError。
- **B3（已修复，09-04-benchmark-yaml-coverage）**：unknown 成分被 fallback 指数（中证800）**静默替换**、指标照算（006373 85% 权重被换，excess_3y=+146% 失真）→ 已按上方「高权重 unknown 置 NULL」语义修复，并补录 20 个 yaml 指数（中证官网 `stock_zh_index_hist_csindex` / 申万 `index_hist_sw` / 国证 `index_hist_cni`，收录标准=拉到日线且末条距今 ≤10 天）+ curated aliases。重刷实证：unknown 主成分被顶替 45→14 只（剩余均为确认无源无替代的海外指数，走置 NULL）、`partial:fallback` 9→0 行。

**Tests**（test_benchmark_fetcher.py）：mixed_calendar_no_return_duplication（双计消除）/ leading_dates_trimmed（前导裁剪）/ same_calendar_matches_return_compound（回归）/ deposit_weight_normalization / major_unknown_component_returns_null（R4 置 NULL，断言完全不发起指数拉取）/ bare_percent_addon_compounds_as_deposit（裸 N% 加成）/ half_width_x_is_mul_only_before_digit（乘号规则）/ cbond_uses_general_source + cbond_source_dates_kept_as_is（B1 换源后日期原样透传，周五行保留、无周日错位行）。

```python
# Wrong: 对收益 ffill —— B 缺席日复制前日收益（3年 +13.5pp）
ret_df = pd.DataFrame({k: s_return for ...}).sort_index().ffill().fillna(0)
# Correct: 对价格 ffill 后统一重算
px = pd.DataFrame({k: s_close for ...}).sort_index().ffill().dropna()
rets = px.pct_change().fillna(0)
```

## 3. 费率缓存契约（补回的 fetcher）

```
cache/fees_{code}.json = {
  "fee_buy_small": "0.8",       # 申购小额档（%）
  "fee_redeem_lt7d": "1.5",     # <7天
  "fee_redeem_7d_1y": "0.1",    # 7天~1年
  "fee_redeem_ge1y": "0.0",     # ≥1年
  "fee_mgmt": "0.3",            # 管理费/年
  "fee_custody": "0.1",         # 托管费/年
  "fee_service": 缺省           # C 类才有
}
```
- 值是**字符串数字**，fetch_fees 读时转 float；缺字段=无该项
- 联网重拉走东财 `fundf10.eastmoney.com/jjfl_{code}.html` 正则解析，31 份预研缓存优先命中

## 3a. 同类排名契约（fund_achievement_rank → FundListItem.rank_*）

`_parse_peer_rank(value: str | None) -> dict | None` 把数据库 `fund_achievement_rank.peer_rank`（格式 `'<rank>/<total>'`，如 `'25/204'`）解析成 DTO 字段：

```python
{"pct": round(rank / total * 100, 1), "total": total, "rank": rank}
```

**字段语义**（09-08-stock-fund-list-rank 引入 `rank` 字段，向后兼容）：
- `pct`：当前排名 ÷ 同类总数 × 100，保留 1 位小数（**前 X.X%** 展示用）
- `total`：同类总数（**分母**）
- `rank`：当前排名（**分子**，新增；旧后端不返回时前端 `rank=null` 不渲染分子段）

**边界行为**（验证过）：
| 输入 | 返回 |
|---|---|
| `'25/204'` | `{'pct': 12.3, 'total': 204, 'rank': 25}` |
| `'1694/5606'` | `{'pct': 30.2, 'total': 5606, 'rank': 1694}` |
| `'invalid'` / `''` / `None` | `None` |
| `'25'`（无斜杠） | `None` |
| `'0/100'` | `None`（rank ≤ 0） |
| `'200/100'` | `None`（rank > total） |
| 任何 ValueError/TypeError | `None`（不抛异常） |

**4 个排名口径**（`filter_service.RANK_PERIODS`）：
- `(年度业绩, 今年以来)` → `rank_ytd`
- `(阶段业绩, 近1年)` → `rank_1y`
- `(阶段业绩, 近3年)` → `rank_3y`
- `(阶段业绩, 近5年)` → `rank_5y`

**债基 tab 永远返回 `None`**（无入库数据）；`_screen("bond"/"discovery-bond")` 路径不查 `fund_achievement_rank`，DTO 字段是 null。

**DTO 字段类型**（前后端契约，`apps/fund-select/src/lib/types.ts`）：
```ts
export interface RankPercentile {
  pct: number | null;
  total: number | null;
  rank: number | null;  // 09-08-stock-fund-list-rank 新增
}
```

**前端消费模式**（双行列表展示）：
```tsx
{fund.rank_1y?.pct != null && <span>前 {fund.rank_1y.pct.toFixed(1)}%</span>}
{fund.rank_1y?.rank != null && fund.rank_1y?.total != null && (
  <span>· {fund.rank_1y.rank}/{fund.rank_1y.total}</span>
)}
```
`rank === null` 时仅显示"前 X.X%"，分子段不渲染——向后兼容旧后端。

## 4. 前后端链路（basePath 陷阱）

```
浏览器 → http://localhost:3005/funds            (Next.js, basePath=/funds)
       → /funds/api/funds/*                     (app/api/funds/[...path]/route.ts 代理)
       → http://localhost:8095/api/funds/*      (FastAPI)
```

### Common Mistake: basePath 双前缀

**Symptom**: URL 变成 `/funds/funds`
**Cause**: page 放在 `app/funds/page.tsx` 且 basePath 也是 `/funds` → 实际路由 = basePath + 目录 = 双前缀；且 `redirect('/funds')` 会再叠一层
**Fix**:
- page 放 `app/page.tsx` 根（basePath 承担前缀）
- `router.push` / `<Link href>` 用**相对 basePath 的路径**（`/` → `/funds`，`/stock` → `/funds/stock`）；写 `href="/funds"` 会被拼成 `/funds/funds`
- 同步筛选 URL 只用 `?qs`，不要拼 `location.pathname`（浏览器 pathname 已含 `/funds`，`router.push('/funds?cleared=1')` 同样会变成 `/funds/funds?cleared=1`）
- 原生 `fetch('/funds/api/...')` **必须写全路径**——fetch 不吃 basePath

### Gotcha: 代理剥 BOM

代理 route 用 `res.text()` 会吞掉 CSV 的 UTF-8 BOM（TextDecoder 默认去 BOM）。**用 `res.arrayBuffer()` 二进制透传**。

## 5. Good/Base/Bad Cases

- Good: `GET /screen?max_dd_3y=5` 返回 dd_3y∈[-5,0] 的基金
- Good: `GET /discovery-stock/screen?page=2&limit=50&sort=ret_3y&order=desc` 返回 `items[50..99]`；`total` = 全量筛后命中数；与 page=1 无重叠
- Good: `GET /bond/screen?page=1&limit=50` 返回 31 只全量（total=31，items 长度=31，债基 tab 不显示分页器）
- Base: `GET /screen` 无参 → `funds.yaml` ∩ is_active（约 31 只）；分页默认 page=1, limit=50
- Base: `GET /screen?page=1`（URL 不带 limit）→ limit=50
- Bad: `GET /screen?sort=name` → 422（白名单外）；`GET /999999` → 404
- Bad: `GET /screen?page=0` / `?limit=0` / `?limit=1000` → 422
- Bad: `GET /screen?page=999` 越界 → 200 + `items=[]`，`total` 不变（前端分页器下一页按钮 disabled）
- Bad: 假设 `len(items) == total` —— 那是改造前的契约，引入分页后 `len(items) == min(limit, total - offset)`

## 6. Tests Required

`backend/tests/`（含交叉泄漏回归）：
- `test_filter_service.py`：四维组合/边界/排序/LEFT JOIN 保留/is_active 排除 + **TestPagination**（默认/单页/跨页不重叠/越界空/total 不受 page 影响/None 排序尾部）
- `test_stock_filter_service.py`：股票 tab 测试 + **TestStockPagination**
- `test_discovery_filter_service.py`：discovery 路径 SQL LEFT JOIN market_fund_rank + 业绩字段来源 + `_parse_peer_rank` 解析边界（25/204 / invalid / 0/100 / 200/100 全返 None）+ **TestDiscoveryPagination**（discovery-bond + discovery-stock）
- `test_universe_isolation.py`：债基/股票 yaml 宇宙互不泄漏；`fund_type` 不是成员谓词
- `test_performance_service.py`：回撤算法（1.0→1.2→0.9 = -25%）/收益窗口/None 语义
- `test_api.py`：TestClient + in-memory 覆盖依赖；422/404/BOM；stats 按宇宙计数 + **TestScreenPagination422**（page=0/limit=0/limit=1000/page=-1/limit=-1 全 422）
- `test_data_fetchers.py`：31 份费率夹具契约、债券分类关键词、yaml 宇宙

**分页测试夹具**：filter_service 用 `monkeypatch.setattr("src.data.fund_universe.load_fund_codes", ...)` 让 universe 包含 seed codes（避免依赖 yaml 实际 31 只名单）；discovery 测试 seed 同 `market_subtype` 让默认 universe 自动选中。

**测试夹具注意**：in-memory SQLite + TestClient 必须用 `StaticPool`（单连接共享），否则 TestClient 线程看不到建表。

## 7. Wrong vs Correct

### Wrong
```python
q.filter(FundPerformance.dd_3y <= max_dd_3y)   # 库内负值，-4.47 <= 5 恒真，筛不掉
q.where(Fund.is_active == True)                # 债基 tab 会看到股票 refresh 写入的全部活跃基金
Fund.fund_type.like("股票型-%")                # 股票 tab 会吃到债基名单里的混合/QDII
init_db()  # 测试里对全局 engine 建表，但请求走 override session（另一 engine）

# 分页相关
items.sort(...); items = items[:limit]         # 切片在排序之前——多页之间会错位、重叠
total = len(items_page)                        # total 当成页长度——前端分页器总页数算错
ach_map = {c: ... for c in codes_after_slice}  # 按切片后 codes 查 ach——DTO 内 rank_* 字段大量丢
```
### Correct
```python
q.filter(FundPerformance.dd_3y >= -abs(max_dd_3y))  # 绝对值语义
q.where(Fund.is_active == True, Fund.code.in_(resolve_universe_codes("bond")))
# conftest: create_engine("sqlite:///:memory:", poolclass=StaticPool)

# 分页相关
total = len(items)                          # total 在切片前算
ordered = valued_sort + empty_tail
items_page = ordered[offset : offset+limit]  # 切片在排序之后
return {"total": total, "items": items_page}
```
