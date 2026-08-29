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

API 端点（routes.py）：
- `POST /api/update/volume` / `POST /api/update/turnover` — 日常增量（内部调
  `fetch_today()`，路径与响应模型不变，n8n 调度无感知）
- `POST /api/update/volume-turnover/history?start_date=2010-01-01&end_date=<昨天>`
  — 一次性回补，响应 data 带 `{volume_rows, turnover_rows, start, end}`

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
