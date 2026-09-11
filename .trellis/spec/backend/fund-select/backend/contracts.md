# fund-select 契约（API / DB / 缓存 / 前后端链路）

## 1. Scope / Trigger

- 任务 09-01-fund-select-v1-bond：新增跨层契约（FastAPI ↔ Next.js 代理 ↔ 前端表格/对比），且补回了预研缺失的费率 fetcher 契约。
- 任务 09-09-fund-select-pagination：分页契约（server 端排序-切片、total/limit 不变量）。
- 任务 09-09-fund-list-rank：同类排名 DTO（RankPercentile 三字段 + Pydantic 静默砍字段陷阱）。
- 任务 09-10-qdii-reits-coarse-mapping / 09-10-subtype-coverage-fix / 09-10-fund-table-type-chip：粗类别映射契约的完整化与边界。
- 任务 09-11-bond-market-type-fix（本次）：粗类别映射契约的**前端一致性**强化（chip 文案 derive + 死选项清理 + 跨 tab 透传），沉淀于 §8a–§8d。

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

**⚠️ 隐式契约：`src/api/models.py:FundListItem` 必须同步声明新字段**

`/screen` 端点的 `response_model=ScreenResponse → items: list[FundListItem]` 用 Pydantic v2 严格序列化——`_to_dto` 返回 dict 里**任何不在 `FundListItem` 模型里定义的字段都会被静默丢弃**（不报错、不警告）。所以后端在 `_to_dto` 加新字段时，**必须同时**给 `models.FundListItem` 补 Optional 字段，否则前端永远拿不到。

09-09 实战踩坑：`mr_*`（L1 业绩 11 字段）+ `rank_ytd/1y/3y/5y`（4 字段）=_to_dto 早就有，response 一律不见。原因就是 `models.FundListItem` 没补。修复 = 在 `models.py` 加 `RankPercentileDTO` 嵌套 + 14 个 Optional 字段。

**新增 list-item 字段 checklist**（加字段时 3 处必须同步）：
1. `services/filter_service.py:_to_dto` — 加进 return dict（**ranks 走 `**ranks` 展开**）
2. `api/models.py:FundListItem` — Pydantic 字段声明（**否则被静默砍掉**）
3. `apps/fund-select/src/lib/types.ts:FundListItem` — TS 接口同步

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

## 8. discovery-* tab「基金类型」粗类别映射契约（09-10-qdii-reits-coarse-mapping）

### 两层过滤模式

前端 UI 暴露**粗类别**（5 个：`股票型 / 混合型 / 指数型 / QDII / REITs`），用户勾选的也是粗类别；后端 SQL 只认**精确 subtype**（akshare 子类枚举，如 `QDII-普通股票`）。

```typescript
// apps/fund-select/src/lib/types.ts — 前端做粗→精展开
'QDII': ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活', 'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs'],
'REITs': ['Reits', 'REITs'],
// 展开后写入 ?market_type=QDII-普通股票,... 后端 IN (...) 过滤
```

后端 `_parse_market_types` 仅做 `split(',')`，不做粗→精展开（设计决策 D3：粗类别的语义归前端）。后端写单测时**必须模拟前端展开后的精确列表**，不要直接传 `["QDII"]` 给 `screen_discovery_stock(market_types=...)`——会得到空集（因为 `market_subtype` 字段值是 `QDII-普通股票` 等，没有 "QDII" 这个值）。

### 跨界 subtype 归类（QDII-REITs 边界 case）

`market_subtype` 字段值中部分 subtype 同时归属两个语义类别（如 `QDII-REITs` 既是 QDII 又是 REITs）。归类决策按**用户心智模型**而非纯语义——「QDII」粗类别包含所有 QDII 系列，与标的无关：

| 精确 subtype | SUBCLASS_TO_CATEGORY（后端） | COARSE_TO_SUBTYPES_STOCK 粗类别（前端） |
|---|---|---|
| `QDII-REITs` | `stock`（与 Reits/REITs 同组，避免落 `other`） | **`QDII`**（不是 `REITs`） |

**为什么 QDII-REITs 归 QDII 粗类别**：不勾「QDII」时用户期望"无任何 QDII 基金"，若归 REITs 则会出现名字带「(QDII)」的海外 REIT（鹏华美国房地产、嘉实全球房地产、诺安全球收益不动产等）——前端语义必须与用户直觉对齐。代价：勾 QDII 但不勾 REITs 时也能看到 QDII-REITs，但这与「QDII 大类」的语义一致。

### Common Mistake: 后端单测传粗类别而非精确 subtype

**Symptom**: `screen_discovery_stock(market_types=["QDII"])` 返回空集；测试失败。

**Cause**: 后端 `market_subtype` 字段没有值为 "QDII" 的记录，只有 `QDII-普通股票 / QDII-混合偏股 / ...` 等子串。粗→精展开由前端 `COARSE_TO_SUBTYPES_STOCK` 完成。

**Fix**: 单测里手写展开后的精确列表：
```python
qdii_subtypes = ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活',
                 'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs']
FilterService(db).screen_discovery_stock(market_types=qdii_subtypes)
```

### Tests Required（09-10 新增）

`tests/test_discovery_filter_service.py::TestScreenDiscoveryStock::test_qdii_reits_excluded_when_qdii_coarse_unchecked`：
- 断言 1：不勾 QDII（仅勾 REITs 展开 `["Reits", "REITs"]`）→ QDII-REITs 不命中
- 断言 2：勾 QDII（展开 6 个精确 subtype）→ QDII-REITs 命中
- 断言 3：勾 QDII + REITs → 两者都命中（QDII-REITs 只出现 1 次，靠精确列表去重）

### Gotcha: UI 5 粗类别 = universe 全集

`DISCOVERY_STOCK_SUBTYPES` 14 个 subtype 全部分配在 5 个粗类别里（无 "other"）。`DISCOVERY_BOND_SUBTYPES` 10 个同理。修改 `COARSE_TO_SUBTYPES_STOCK` 时**必须保证 universe 全集仍被 5 粗类别覆盖**——漏掉的 subtype 默认 `market_types=null` 走 `DISCOVERY_STOCK_SUBTYPES` 全集时会重新出现，与 UI 行为脱节。

## 8a. 前端粗类别 UI 一致性契约（09-11-bond-market-type-fix）

> 大白话：用户在筛选器看到的钮 = 用户在表格里看到的 chip = 实际能筛出来的基金。三者必须严格对齐，错一个就是用户被骗。债基 5 个钮里 REITs 钮点了等于没点（09-11 实战），就是这个契约破了。

### 三处必须对齐的真相源

| 真相源 | 类型 | 位置 |
|---|---|---|
| `*_MARKET_TYPE_OPTIONS` | UI 筛选器可选项（value + label） | `apps/fund-select/src/lib/types.ts:182-208` |
| `COARSE_TO_SUBTYPES_*` | 粗类别 value → 精确 subtype 列表（前端 → 后端 IN 过滤） | `apps/fund-select/src/lib/types.ts:214-228` |
| `SUBCLASS_TO_CATEGORY`（后端） | 精确 subtype → universe 成员判定（bond / stock / other） | `backend/fund-select/src/data/market_subtype_map.py` |

**三者一一对应**，任何一边改了必须三边同步，否则出现：钮能点 / 表格能看 / 筛选结果对不上的三角错位。

### Convention: 死选项三处同步清理

`COARSE_TO_SUBTYPES_*['某粗类别'] = []` 是**死选项征兆**——后端 universe 不含此粗类别任何 subtype，前端钮点了展开为空 array → `api.ts:33` 静默不传参 → 后端 `_parse_market_types(None)` → 走默认 universe 返回全部基金。

清理死选项必须**同时**删三处（不是一处）：
1. `*_MARKET_TYPE_OPTIONS` 删该粗类别选项
2. `COARSE_TO_SUBTYPES_*` 删该死键
3. `DISCOVERY_*_DEFAULT_FILTERS.market_types` 删该粗类别引用（否则 `FilterChipBar` 会渲染出无法从 `FilterPanel` 重新加入的死 chip）

09-11 实战：债基侧 REITs 死选项，先删 1 + 2 → 仍然在 3 留死引用 → commit 后自修（commit `dd08321` 包含 default filters 数组同步清理）。

### Convention: chip 文案 = OPTIONS label 唯一真相源

表格类型列 `<TypeCell>` 显示两层：上行 chip（粗类别）+ 下行小字（精确 subtype）。chip 文案**必须**从 `*_MARKET_TYPE_OPTIONS` 的 `label` 字段 derive，禁止硬编码第二份文案。

实现位置：`apps/fund-select/src/lib/types.ts` 导出 `STOCK_OPTION_LABELS` / `BOND_OPTION_LABELS`，由 `buildOptionLabelMap(*_MARKET_TYPE_OPTIONS)` 生成。

```typescript
// Wrong — 硬编码两份文案，第二份必漂
export const SUBTYPE_TO_LABEL: Record<string, string> = {
  '混合型-偏债': '混合债基',
  '指数型-固收': '指数债',
  // ... 改 OPTIONS 时忘改这里 → 用户看到 chip「混合型」, 筛选器显示「混合债基」
};

// Correct — 唯一真相源
function buildOptionLabelMap(opts: { value: string; label: string }[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const o of opts) out[o.value] = o.label;
  return out;
}
export const BOND_OPTION_LABELS = buildOptionLabelMap(BOND_MARKET_TYPE_OPTIONS);
```

### Convention: 跨 tab 渲染 FundTable 必须显式传 `marketKind`

`resolveCoarseLabel(subtype, kind?)` 是粗类别 → label 的解析器，`kind` 决定走 stock 还是 bond 的 label map：

- `kind === undefined` → 走 `STOCK ?? BOND` fallback（**仅**老 `/bond`、`/stock` tab 用，不区分 context）
- `kind === 'stock' | 'bond'` → 按指定 tab 解析 chip label

`FundTable.tsx` props 加 `marketKind?: 'stock' | 'bond'`（**optional，老 tab 不传**）。`discovery-bond/page.tsx` 传 `marketKind="bond"`，`discovery-stock/page.tsx` 传 `marketKind="stock"`。

不传 `marketKind` 的代码路径（老 `/bond`、`/stock` tab）**逐字节保持原行为**——不允许"为了统一让老 tab 也传"。

### Common Mistake: 改 OPTIONS 文案不查仓库里所有引用

**Symptom**: 改了 `BOND_MARKET_TYPE_OPTIONS` 里某项 label，单元测试过、生产跑通，但上线后用户报告"表格 chip 文案和筛选器对不上"。

**Cause**: 仓库里**至少 4 处**可能引用到 label 或粗类别名（按命中优先级排查）：
1. `DISCOVERY_*_DEFAULT_FILTERS.market_types`（数组元素是 OPTIONS 的 value）
2. `discovery-{bond,stock}/page.tsx` 顶部注释（文档漂移主灾区）
3. `api/routes.py` docstring（"10 个债券相关子类" 这种描述，**09-11 实战：补完混合型-偏债后是 11 个，注释没改**）
4. `tests/test_discovery_filter_service.py` 断言字符串

**Prevention**:
- 改 `*_MARKET_TYPE_OPTIONS` / `COARSE_TO_SUBTYPES_*` 后，**必须** grep `apps/fund-select` 与 `backend/fund-select` 全部相关引用（不止上面 4 处）
- 优先靠「唯一真相源」设计消除漂移（OPTIONS label derive），而不是靠"搜得全"

### Gotcha: 跨界 subtype 同时归属两个粗类别时归类决策按用户心智模型

见 §8「跨界 subtype 归类（QDII-REITs 边界 case）」。09-10 决策：QDII-REITs 归 QDII 粗类别（不勾 QDII 时不出现），代价是勾 QDII 但不勾 REITs 仍能看到 QDII-REITs。

**新增陷阱**：跨界 subtype 在 chip 展示时也要按归类决策走，不能按 `market_subtype` 字符串前缀匹配。`SUBTYPE_TO_COARSE_*` 反向 map 的值必须与 §8 表格里的归类决策**逐字一致**。

### Tests Required（09-11 新增）

`apps/fund-select` 无单测框架（仅 backend pytest）。契约靠 `pnpm build` + `next dev` 手动验证，09-11 实证：

- 改完 `BOND_MARKET_TYPE_OPTIONS` 删 REITs → `pnpm build` 通过 + 手动 `discovery-bond` 页面确认筛选器只 4 选项
- chip 文案与筛选器 label 逐字一致 → 手动 `discovery-bond` 表格确认 `混合型-偏债` 行 chip =「混合债基」
- 老 `/bond`、`/stock` tab 渲染逐字节不变 → 手动切换老 tab 确认（**重点**：老 tab 不传 `marketKind`，走 STOCK ?? BOND fallback）
- `DISCOVERY_BOND_DEFAULT_FILTERS` 不含 REITs → `FilterChipBar` 不渲染死 chip

### Wrong vs Correct

#### Wrong
```typescript
// ❌ 死选项单边清理 — 只删 OPTIONS 不删 COARSE_TO_SUBTYPES
BOND_MARKET_TYPE_OPTIONS = [{ value: '纯债型', ... }, { value: '混合型', ... }];  // 删了 REITs
COARSE_TO_SUBTYPES_BOND = { ..., 'REITs': [] };  // 忘了删 — 仓库里留不可达死数组

// ❌ chip 文案硬编码第二份真相源
function resolveCoarseLabel(s: string) {
  if (s === '混合型-偏债') return '混合债基';  // 改 OPTIONS 时必漂
  return SUBTYPE_TO_COARSE_STOCK[s] ?? SUBTYPE_TO_COARSE_BOND[s];
}

// ❌ 老 /bond tab 传 marketKind='bond'
<FundTable items={items} marketKind="bond" />  // 老 tab 数据走老 path, marketKind='bond' 会让老股票基金 chip 显示债基 label
```

#### Correct
```typescript
// ✅ 死选项三处同步清理
BOND_MARKET_TYPE_OPTIONS = [{ value: '纯债型', ... }, { value: '混合型', ... }, { value: '指数型', ... }, { value: 'QDII', ... }];
COARSE_TO_SUBTYPES_BOND = { '纯债型': [...], '混合型': [...], '指数型': [...], 'QDII': [...] };  // 无 REITs 键
DISCOVERY_BOND_DEFAULT_FILTERS = { market_types: ['纯债型', '混合型', '指数型', 'QDII'], ... };  // 数组同步

// ✅ chip 文案 derive
export const BOND_OPTION_LABELS = buildOptionLabelMap(BOND_MARKET_TYPE_OPTIONS);
function resolveCoarseLabel(s: string, kind?: 'stock' | 'bond') {
  if (kind === undefined) return SUBTYPE_TO_COARSE_STOCK[s] ?? SUBTYPE_TO_COARSE_BOND[s] ?? null;
  const coarse = (kind === 'stock' ? SUBTYPE_TO_COARSE_STOCK : SUBTYPE_TO_COARSE_BOND)[s];
  return coarse ? (kind === 'stock' ? STOCK_OPTION_LABELS : BOND_OPTION_LABELS)[coarse] : null;
}

// ✅ 老 tab 不传 marketKind，老 path 走 STOCK ?? BOND fallback
<FundTable items={items} />  // 老 /bond、/stock 用
<FundTable items={items} marketKind="bond" />  // discovery-bond 用
<FundTable items={items} marketKind="stock" />  // discovery-stock 用
```

## 9. SUBCLASS_TO_CATEGORY 完整枚举契约（09-10-subtype-coverage-fix）

`SUBCLASS_TO_CATEGORY` 是 akshare 27+ 个精确 subtype → 4 类 universe（stock / bond / other / 未声明）的**显式白名单**。**未知 subtype 降级 "other"**（不出现在 universe 中）——这是有意为之，让运维在数据新增/异常时显式补映射，避免静默错归。

### 当前完整映射（stock universe 16 个 / bond universe 11 个）

| universe | 精确 subtype 列表 |
|---|---|
| **stock** | 股票型 / 指数型-海外股票 / 指数型-其他 / 指数型-股票 / 混合型-平衡 / 混合型-绝对收益 / 混合型-灵活 / 混合型-偏股 / QDII-普通股票 / QDII-混合偏股 / QDII-混合灵活 / QDII-混合平衡 / QDII-FOF / QDII-REITs / Reits / REITs |
| **bond** | 债券型-中短债 / 债券型-混合一级 / 债券型-混合二级 / 债券型-混合债 / 债券型-利率债 / 债券型-信用债 / 债券型-长期纯债 / 指数型-固收 / QDII-纯债 / QDII-混合债 / 混合型-偏债 |
| **other**（不进 universe） | FOF-稳健型 / FOF-均衡型 / FOF-进取型 / 货币型-普通货币 / 货币型-浮动净值 / QDII-商品 / 商品 / 其他 |

### Convention: 修改 SUBCLASS_TO_CATEGORY 必须同步改前端 COARSE_TO_SUBTYPES_STOCK/BOND

`SUBCLASS_TO_CATEGORY` 控制"是否进 universe"；`COARSE_TO_SUBTYPES_STOCK` / `COARSE_TO_SUBTYPES_BOND` 控制"在 UI 上被哪个粗类别命中"。两者一一对应：

- 加 subtype 进 `SUBCLASS_TO_CATEGORY` 时，**必须**同时加进对应粗类别数组，否则用户勾不到
- 删 subtype 时同理两端都删，避免前端展开列表包含 universe 外的值（`market_types=[...]` 命中空集但用户不知道为啥）

### Convention: 跨界 subtype 必须显式归 stock 或 bond，不允许 "other"

09-10 实战踩坑：修复前 `指数型-股票` (5677 只) / `混合型-偏股` (5726 只) / `混合型-偏债` (1464 只) 漏在 SUBCLASS_TO_CATEGORY 之外，默认归 other，**前端 UI 完全搜不到**。这三类是 A 股 ETF/指数增强主流、偏股混合主流、偏债混合主流，规模巨大。

判定原则：
- `指数型-股票`：A 股 ETF / 指数增强（华夏沪深 300ETF 联接A 等）→ 投资标的是股 → **stock**
- `混合型-偏股`：偏股混合基金（股票仓位 ≥60%）→ **stock**
- `混合型-偏债`：偏债混合基金（股票仓位 ≤40%）→ **bond**

### 暂时保持 other 的 subtype

- `QDII-商品` / `商品`（黄金、原油等大宗商品基金）：不属于股基/债基范畴，避免污染 universe。等有需要再加第 6 粗类别「商品型」。

### Tests Required（09-10 新增）

`tests/test_discovery_filter_service.py`：
- `TestScreenDiscoveryStock::test_index_stock_included_when_index_coarse_selected` — 勾「指数型」粗类别展开（含 `指数型-股票`）→ 命中 `指数型-股票 / 指数型-海外股票 / 指数型-其他` 三种
- `TestScreenDiscoveryStock::test_partial_stock_included_when_mixed_coarse_selected` — 勾「混合型」（股基侧，含 `混合型-偏股`）→ 命中 `混合型-偏股`，**不**含 `混合型-偏债`
- `TestScreenDiscoveryStock::test_qdii_commodity_still_excluded_from_stock_universe` — `QDII-商品 / 商品` 默认不进 stock universe
- `TestScreenDiscoveryBond::test_partial_bond_included_when_mixed_coarse_selected` — 勾「混合型」（债基侧，含 `混合型-偏债`）→ 命中 `混合型-偏债 + 债券型-混合债`

### Gotcha: 修改 SUBCLASS_TO_CATEGORY 后 universe 规模会变

修复后 universe 实际规模（活跃基金）：
- stock: ~11.6k → ~17.3k（+5677 指数型-股票 +5726 混合型-偏股 - 重复？→ 单算）
- bond: ~7.3k → ~8.8k（+1464 混合型-偏债）

走默认 universe 的接口（`screen_discovery_stock/bond`、`universe_stats`、全量 refresh `universe_filter`）行为都会变化。前端首屏 P95 可能受影响（5 粗类别默认全选时结果集变大），本次不优化，留后续观察。

## 10. 全量 refresh pipeline profile 契约（09-11-bond-full-pipeline-trim）

### 两套独立的 refresh pipeline（不要混淆）

fund-select 实际有 **两套独立**的全量 refresh pipeline，不是同一套接不同 universe：

| 维度 | 市场 tab 全量（`market_full_pipeline`） | 债基/股基三分法（`scheduler.tasks`） |
|---|---|---|
| 入口函数 | `refresh_market_full_sync` | `refresh_configured_funds_sync` / `refresh_stock_funds_sync` |
| Universe 来源 | `ak.fund_name_em()` 全市场 ~2.8 万只 | `config/funds.yaml` / `funds_stock.yaml` 手工名单 |
| 循环模式 | 阶段化流水线 + 分阶段重算 codes | `for code: snapshot_fund(code)` 单只 IO |
| 主要写表 | `market_fund_rank` / `market_nav` / `fund_risk_metrics` / `fund_achievement_rank` | `funds` / `FundFees` / `FundHoldingsBond` / `FundPerformance` |
| 触发方式 | 手动（`/full/refresh` 端点） | daily scheduler + 手动 |
| 适用页面 | `/funds/discovery-bond` / `/funds/discovery-stock` | `/funds/bond` / `/funds/stock` |

**两者之间没有共享 universe、没有共享 fetcher、没有共享进度回调**。老债基三分法不跑 L4/L5（`snapshot_fund` 默认 `fetch_ranking=False`，`refresh_configured_funds_sync` 不调 `benchmark_refresh.refresh`）—— 本任务的"精简"只对市场 tab pipeline 有效。

### pipeline_profile 参数（市场 tab pipeline 内部切换）

`refresh_market_full_sync` 新增 `pipeline_profile: str = "stock"` 参数：

- `"stock"`（默认）：6 阶段全跑 — L0 universe → L1 rank → L2 size → L3 nav → L4 risk → L5 achievement
- `"bond"`：4 阶段，跳 L4 + L5 — 保留 L0/L1/L2/L3

非法值在函数顶部抛 `ValueError`，不写 `RefreshRun`。

### 债基详情页不消费的数据（L4/L5 跳过理由）

- **`fund_risk_metrics`** 6 指标（sharpe / ir / alpha / gamma / alpha_ir / excess_3y）：只有 `RowDetailDrawer.tsx`（股基详情页）import `RiskMetricsGrid`，`RowDetailDrawerBond.tsx` 完全没 import → 债基详情页不展示这 6 个指标
- **`fund_achievement_rank`** 同类排名：只有 `RowDetailDrawer.tsx` 消费 `detail.achievement_ranks`，债基详情页 / 列表页 / 筛选器均不消费

保留 L3 nav 是因为 `max_dd_3y` 是债基筛选维度（`discovery-bond/page.tsx:77`），且 nav 数据是 1y/3y 涨幅计算基础。

### main_run.total 按 profile 动态算

- stock: `len(codes) * 6`
- bond: `len(codes) * 4`

`RefreshRun.total` 在两处写入：初始化时（line 192，原"占位"）和 L2 后（line 273）。两处都用 `stages_per_code` 动态算。前端 `discoveryBondApi.getFullRefreshStatus` 拿到的 total/completed 比例与实际跑的阶段数匹配。

### 路由层接入

- `routes.py:444 discovery_bond_full_refresh` 显式传 `pipeline_profile="bond"`
- `routes.py:505 discovery_stock_full_refresh` 不传 profile → 默认 `"stock"`，行为不变
- `scheduler/tasks.py` 若有调用 `refresh_market_full_sync` 的入口需手动加 profile 参数（`pipeline_profile` 默认 `"stock"` 保证向后兼容）

### Tests Required（09-11 新增）

`tests/test_market_full_pipeline.py::TestPipelineProfile` 覆盖：

- `test_bond_profile_skips_l4_and_l5` — profile="bond" 时 L4/L5 sentinel 函数被设但 flag 仍为 False；`stage_results.keys()` 只含 L0/L1/L2/L3
- `test_default_profile_runs_all_six_stages` — 不传 profile → 6 阶段全跑（回归保护）
- `test_invalid_profile_raises_value_error` — `pipeline_profile="etf"` 抛 `ValueError` 且不写 `RefreshRun`
- `test_main_run_total_reflects_stages_per_code` — bond profile total = universe × 4；stock profile total = universe × 6

### Common Mistake: 把"债基市场刷新"当成"债基三分法刷新"

两者是独立 pipeline：
- 想精简债基市场刷新 → 改 `refresh_market_full_sync` + `discovery_bond_full_refresh`（本次范围）
- 想精简债基三分法 → 改 `refresh_configured_funds_sync`（独立任务，且老路径无 L4/L5 可精简）

### Gotcha: pipeline 跳过阶段后 `stage_results` 不造假

`stage_results` dict 在 profile="bond" 时**不写** `L4_risk` / `L5_achievement` key（不写占位如 `{"skipped": "..."}`）。前端轮询拿到的 `RefreshRun.total/completed/failed` 自然反映 4 阶段进度。日志里通过 `logger.info("跳过 L4/L5 阶段")` 留痕。

### 后续：合并两套 pipeline（不在本任务范围）

把"市场 tab 全量"和"债基三分法"合并成一个 profile-driven 的统一刷新系统，是更大的架构重构（涉及 universe 来源 IO、单只 vs 阶段化循环、字段映射、schema 差异）。本次不动。
