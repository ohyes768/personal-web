# Data Source Contracts（数据源契约）

> backend/macro 外部数据源的取数契约。状态: Filled 2026-08-29

---

## Scenario: BaoStock 两市成交额/换手率

### 1. Scope / Trigger

- 触发：`volume` / `turnover` 两指标的历史回补与日常增量取数（2026-08-29 起生效）
- 背景：原沪深交易所官方 API 方案（已删除的 volume_service.py / turnover_service.py）
  只能取当日点、历史日期不可查，且口径与通用"两市成交额"存在偏差
  （官方口径沪市 ≈ 2× 指数口径，疑混入非股票品种）

### 2. Signatures

```python
# src/services/baostock_service.py
class BaostockService:
    _SH_CODE = "sh.000001"   # 上证指数（全沪市样本）
    _SZ_CODE = "sz.399106"   # 深证综指（全深市样本）

    def fetch_index_daily(code: str, start: str, end: str) -> pd.DataFrame
        # columns: date, close, volume, amount(元), turn(%)

    def fetch_history(start: str, end: str) -> dict
        # {"volume": df, "turnover": df, "status": "ok"|"failed", "error": str|None}
        # 一次 bs.login()/logout() 会话拉两指数；inner-join on date；dropna

    def fetch_today() -> dict
        # start=今天-10自然日（覆盖节假日缺口），end=今天；结构同 fetch_history

get_baostock_service() -> BaostockService  # 模块级单例
```

API 端点（routes.py）。后端 `APIRouter(prefix="/api")`，前端 Next rewrite
`/api/macro/:path*` → `/api/:path*`，所以页面里写 `/api/macro/...`：

| 用途 | 后端路径 | 前端 `economicApi` |
|------|----------|-------------------|
| 全量回补成交额+换手率 | `POST /api/fetch/volume-turnover/history` | `initMarketSentimentHistory` 第 1 步 |
| 全量回补融资余额 | `POST /api/fetch/margin/history` | `initMarketSentimentHistory` 第 2 步 |
| 增量成交额 | `POST /api/update/volume` | `updateMarketSentiment` 第 1 步 |
| 增量换手率 | `POST /api/update/turnover` | `updateMarketSentiment` 第 2 步 |
| 增量融资余额 | `POST /api/update/margin` | `updateMarketSentiment` 第 3 步 |

- 历史必须走 `/fetch/{xxx}/history`，禁止 `/update/.../history`（规范见 `backend/macro/docs/数据更新端点规范.md`）。
- volume-turnover 的 `start_date` 默认 `2010-01-01`，`end_date` 默认昨天；前端 POST 空 body 即可。
- 回补响应 `data` 带 `{volume_rows, turnover_rows, start, end}`（成交额/换手率）或 `{rows, start, end}`（融资余额）。
- `routes.py` 全局 `_is_updating`：**同一时刻只能跑一个 fetch/update**。市场情绪初始化必须 **await 串行** volume-turnover → margin → fund-flow history；增量同样串行。不要 `Promise.all`。

### 3. Contracts

- CSV 落盘（经 `DataService._save_market_sentiment_data`，合并写 keep=last）：
  - `data/volume.csv`：`date,total_amount_yi`（亿元）
  - `data/turnover.csv`：`date,turnover_rate`（%）
- 合成公式：
  - 两市成交额 = (sh.amount + sz.amount) / 1e8
  - 两市换手率 = (sh_amt×sh_turn + sz_amt×sz_turn) / (sh_amt + sz_amt)
- 单位：BaoStock `amount` 单位**元**、`turn` 单位 **%**；`get_row_data()` 返回
  字符串列表，空串必须 `pd.to_numeric(errors="coerce")` 转 NaN
- 依赖：`baostock>=0.9.0`（pyproject.toml）

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| bs.login 失败 / query error_code != 0 | 返回 `status="failed"` + error 消息，**不抛异常** |
| 某日仅一指数有值 | inner-join 剔除该日 |
| amount/turn 空串 | → NaN → dropna 剔除该行该指标 |
| fetch_today 窗口无新数据 | status=ok + 空批，保存为 no-op（幂等） |
| 同日重复写 | keep=last 覆盖（幂等，回补端点可重入） |

### 5. Good/Base/Bad Cases

- Good: 回补 2010-01-01~今 → 4045 行，2026-08-28 成交额 21017.15 亿，
  换手率 1.8669%（落在沪 1.0431 与深 2.5735 之间 = 加权正确）
- Base: 盘后调度 fetch_today → 近 10 日窗口重写，行数不变、0 重复
- Bad: 调度期间 BaoStock 服务不可用 → failed 返回，调度次日自然补上
  （近 10 日窗口保证缺口自愈）

### 6. Tests Required

`tests/test_baostock_service.py`（全部 monkeypatch bs.*，禁止真连）：
- 合成手算 fixture：amount 求和/1e8 与加权 turn 精确断言（能失败）
- inner-join 剔除单边日期
- 空串 → NaN → dropna
- login 失败 / error_code != 0 不抛异常
- keep=last 幂等 roundtrip（baostock 输出形状重复写无重复行）

### 7. Wrong vs Correct

#### Wrong

```python
# 直接 float(row[4]) — 空串 "" 会 ValueError 或悄悄变 0
amt = float(row_data[4])
```

```python
# 模块级 import — baostock 拖慢启动，且部分环境不可用
import baostock as bs
```

```python
# 用官方交易所 API 做历史回补 — SSE 仅近一两年、SZSE 历史返回空
requests.get(SSE_URL, params={"SEARCH_DATE": "2015-06-12"})
```

```python
# 全量初始化挂在 /update/ 下 — 违反「fetch=历史、update=增量」
@router.post("/update/volume-turnover/history")
```

```typescript
// 并发三个 update — 撞 _is_updating，后两个 UPDATE_IN_PROGRESS
await Promise.all([updateVolume(), updateTurnover(), updateMargin()]);
```

#### Correct

```python
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")  # 空串→NaN→dropna
```

```python
def _get_bs(self):  # 方法内按需 import，对齐 margin_service 处理 akshare
    if self._bs is None:
        import baostock as bs
        self._bs = bs
    return self._bs
```

```python
# 历史回补/增量统一走 BaoStock；logout 必须放 finally（query 抛错也要登出）
bs.login()
try:
    ...
finally:
    bs.logout()
```

```python
@router.post("/fetch/volume-turnover/history")
```

```typescript
const volume = await post("/api/macro/update/volume");
if (!volume.success) return volume;
const turnover = await post("/api/macro/update/turnover");
if (!turnover.success) return turnover;
return post("/api/macro/update/margin");
```

前端数据 Tab（中美利差 / 流动性 / 利率 / 商品 / 股指 / 市场情绪）复用 `InitButton` +
`RefreshButton`：文案「初始化历史数据」/「更新数据」；两者成功都要 `onSuccess` 刷图。
信号首页与对比不加写数按钮。各 Tab 独立 `storageKey`。

多端点必须 **串行** 且 **全部成功** 才置灰（`postSerial`）。禁止 `Promise.all`。

| Tab | 初始化 | 更新 |
|-----|--------|------|
| 中美利差/汇率 | us-treasuries → exchange-rates → china-bonds history | 同序 `/update/*` |
| 利率利差 | china-bonds → ted-spread → dr007 → us-treasuries history | 同序 `/update/*` |
| 流动性/风险 | vix → tga → hibor history | 同序 `/update/*` |
| 商品 / 股指 | 单端点 history | 单端点 update |
| 市场情绪 | volume-turnover → margin → fund-flow history | volume → turnover → margin → fund-flow |

日度增量：外部 API 成功但区间无观测、CSV `last_date` 存在且落后 ≤ 5 个日历天 → `success`「已是最新」（覆盖周末 + FRED/TGA T+1~T+2）。`last_date` 为空，或落后超过 5 天仍无观测 → `UPDATE_FAILED`，message 带底库日期与落后天数。FRED 单系列失败必须上抛，不能吞成空 Series。

商品/股指/汇率走阿里云 `comkm`（倒序，最新在前）。`fetch_all(start, end)` 把 `start` 传给翻页 `since`：当前页最旧一根 ≤ since 即停，日常增量通常 1 页（500 根 ≈ 2 年）。`Code=-100`（最多 10 年内）是翻页结束，打 INFO 不是 ERROR。全量 history 的 start 很早，仍会翻到上限。实现：`src/services/aliyun_comkm.py`。

---

## Scenario: 阿里云 comkm 汇率 / ICE DXY（切源）

### 1. Scope / Trigger

- 触发：`POST /api/fetch/exchange-rates/history` 全量回补与 `POST /api/update/exchange-rates` 日度增量（2026-08-31 起生效）
- 背景：FRED H.10（`DEXCHUS` 等）常滞后 7–10 个日历天；`DTWEXBGS` 是贸易加权广义指数（量级约 118），不是 ICE DXY（约 99）。同一套 `ALIYUN_API_APPCODE` 的 comkm 可查 `DXY/USDCNY/USDJPY/EURUSD`，最新约 T+1。
- API 字段名不变：`dollar_index` / `usd_cny` / `usd_jpy` / `usd_eur`。CSV 列名仍是 `美元指数,美元人民币,美元日元,美元欧元`。

### 2. Signatures

```python
# src/services/exchange_rate_service.py
class ExchangeRateService:
    async def fetch_all(start_date: date, end_date: date) -> dict[str, pd.Series]
        # keys: dollar_index, usd_cny, usd_jpy, usd_eur
        # usd_eur = 1 / EURUSD（与旧 FRED 倒数列同向：外币/1 美元）

DataService.save_fred_data(data, key="exchange_rates", *, replace=False)
DataService.exchange_rates_need_aliyun_rebuild() -> bool
    # 底库最后一根「美元指数」>= 115 → 仍是 FRED DTWEXBGS，禁止增量
```

| 用途 | 后端路径 |
|------|----------|
| 全量回补（整表覆盖） | `POST /api/fetch/exchange-rates/history` |
| 日度增量 | `POST /api/update/exchange-rates` |

全量窗口 `settings.exchange_history_years`（默认 10 年，对齐 comkm 上限）。symbol 映射在 `settings.exchange_rate_symbols`。

### 3. Contracts

- 认证：`ALIYUN_API_APPCODE`；未配置 `fetch_all` 返回 `{}`，路由 `UPDATE_FAILED`
- 全量 history **必须 `replace=True` 整表覆盖**，禁止 append 到 FRED 历史（DXY≈99 接到 DTWEXBGS≈118 会在图上断裂）
- 增量：若 `exchange_rates_need_aliyun_rebuild()` 为 True，**不调阿里云**，直接 `UPDATE_FAILED`，message 含 `/fetch/exchange-rates/history`
- `usd_cny`/`usd_jpy` 与 FRED 同向（外币/1 美元）但报价口径不同，仍不得混写
- 不要用 `FXINDEX`（comkm `SYMBOL未找到`）；不要把 DXY 当 DTWEXBGS 补洞

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| AppCode 未配置 / comkm 全空 | history/update `UPDATE_FAILED` |
| 底库美元指数 ≥ 115 | 增量拒绝，提示先跑 history |
| 底库已是 DXY（约 99） | 增量 append，keep=last |
| 空窗且 last_date 落后 ≤ 5 天 | 与其它日度源相同，「已是最新」 |
| 单 symbol 失败 | 该 series 空，其它继续（与商品/股指一致） |

### 5. Good/Base/Bad Cases

- Good: NAS 先跑 history → `exchange_rates.csv` 从约 10 年前起、最新 DXY≈99.7、USDCNY≈6.73（2026-08-28）
- Base: 次日 `update/exchange-rates` 只翻 1 页，append 新行
- Bad: 不跑 history 直接增量 → 拒绝，避免 118 后面接 99

### 6. Tests Required

`tests/test_exchange_rate_service.py`（mock `fetch_comkm_klines`，禁止真连）：
- DXY/USDCNY/USDJPY/EURUSD 映射到四个 API key；`usd_eur == 1/EURUSD`
- 无 AppCode 返回 `{}`
- `replace=True` 丢掉 FRED 118.x 历史；之后 `need_aliyun_rebuild` 为 False
- 增量在 FRED 口径底库上不调用 fetch，message 含 `history`

### 7. Wrong vs Correct

#### Wrong

```python
# 把 Aliyun DXY append 进 FRED DTWEXBGS CSV
data_service.save_fred_data(dxy_batch, key="exchange_rates")
```

```python
# 把 EURUSD 原值当 usd_eur 落盘（旧列是 1/EURUSD）
series = eur_usd_close
```

#### Correct

```python
data_service.save_fred_data(aliyun_fx, key="exchange_rates", replace=True)
```

```python
if name == "usd_eur":
    series = 1.0 / series
```

部署：NAS 升级后必须先点「中美利差/汇率」初始化（或手动 POST history），再依赖 `global_daily` 增量。

---

## Scenario: akshare 融资余额历史

### 1. Scope / Trigger

- 触发：`margin` 全量回补（`POST /api/fetch/margin/history`）与当日增量（已有 `POST /api/update/margin`）
- 背景：`macro_china_market_margin_sh/sz` 一次调用即 2010-03-31 起全表；`fetch_today()` 只取末行。沪约 3983 行 / 深约 3785 行，必须按日期对齐，禁止 iloc 行号对齐。

### 2. Signatures

```python
class MarginService:
    def fetch_today() -> dict   # 沪+深最新一行合计，亿元
    def fetch_history() -> dict
        # {"status": "ok"|"failed", "error": str|None,
        #  "data": DataFrame[date, margin_balance_yi]}
        # outer join on date，缺侧 0；元 ÷ 1e8；过滤 < historical_start_date
```

- 前端初始化第 2 步：`POST /api/macro/fetch/margin/history`（空 body）
- 响应 `data.history`: `{rows, start, end}`
- CSV：`data/margin.csv` 列 `date,margin_balance_yi`，`save_margin_data` keep=last

### 3. Contracts

- 请求：POST 空 body；不接受日期 query（akshare 一次返回全表，落盘前丢掉 `< historical_start_date` 的行）。
- 成功：`success=true`，`data.history.rows/start/end` 为写入后的行数与实际起止日期。
- 失败：`success=false`，`error_code` 为 `UPDATE_IN_PROGRESS`（全局锁占用）或 `UPDATE_FAILED`（解析空、akshare 异常）。
- 单位：akshare 列是**元**，写入亿元（÷1e8，2 位小数）。注释里的「万元」是错的。
- 幂等：同日 `keep=last`。日常增量仍是 `POST /api/update/margin`。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| `_is_updating` 已占用 | `UPDATE_IN_PROGRESS`，不调 akshare |
| 列名识别失败 / 沪或深空表 | `fetch_history` 返回 `status=failed`，路由 `UPDATE_FAILED` |
| 过滤 `historical_start_date` 后为空 | 同上 |
| 沪深日期不完全重合 | outer join，缺侧 0，不丢行 |
| akshare 抛异常 | `status=failed` + error 字符串，不把异常漏出锁外 |

### 5. Good/Base/Bad Cases

- Good: 回补后 `margin.csv` 从 2010-03-31 起约数千行，无重复日期；单位与 `update/margin` 当日点同量级（亿元）。
- Base: 已有几天日更点时再跑 history，同日覆盖、更早日期追加。
- Bad: 按 `iloc` 把深市第 i 行加到沪市第 i 行（行数 3983 vs 3785）→ 错位相加。

### 6. Tests Required

`tests/test_margin.py`（mock akshare，禁止真连）：
- outer join 缺侧 0，日期列表与手算亿元一致
- 行数不同时 8-18 只有沪市，合计不是「沪[0]+深[0]」
- 列名无法识别 → `_merge_margin_history` 返回 None
- `fetch_history` 空表 → `status=failed`
- `save_margin_data` keep=last 幂等（已有 roundtrip 测试）

### 7. Wrong vs Correct

#### Wrong

```python
# 按行号对齐 — 沪深交易日不完全重合，会错位相加
for i in range(min(len(sh), len(sz))):
    total = sh.iloc[-(i+1)]["融资余额"] + sz.iloc[-(i+1)]["融资余额"]
```

```typescript
await Promise.all([fetchVtHistory(), fetchMarginHistory()]); // 撞 _is_updating
```

#### Correct

```python
aligned = pd.concat([sh_s, sz_s], axis=1).fillna(0)  # outer join，缺侧 0
```

```typescript
const vt = await post("/api/macro/fetch/volume-turnover/history");
if (!vt.success) return vt;
const margin = await post("/api/macro/fetch/margin/history");
if (!margin.success) return margin;
return post("/api/macro/fetch/fund-flow/history");
```

---

## 数据源选型备忘（A 股日频历史）

| 数据源 | 结论 |
|---|---|
| BaoStock `query_history_k_data_plus` | ✅ 采用。指数 amount/turn 全历史（1990 起），免费无反爬 |
| 交易所官方 API（SSE/SZSE） | ❌ 仅当日/近一两年；SZSE `txtQueryDate` 历史返回空 |
| 新浪 `stock_zh_index_daily` | ❌ 只有 volume（股数），无成交额 |
| 腾讯 `stock_zh_index_daily_tx` | ❌ `amount` 列实为成交量（手） |
| akshare `index_zh_a_hist`（东财） | ❌ 本机 ConnectionError（被断连），不稳定 |
| akshare `macro_china_market_margin_sh/sz` | ✅ 融资余额专用：本身就返回 2010-03-31 起全量历史（单位**元**） |
