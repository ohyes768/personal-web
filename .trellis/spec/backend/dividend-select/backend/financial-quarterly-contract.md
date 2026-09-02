# 财务指标季度口径契约（最新季度扣非 / 数据季度 / latest_quarter_label）

> 适用范围：`backend/dividend-select` 财务指标链路 + `apps/dividend` 前端展示。
> 建立于 2026-09-02，源于 "2026Q1 写死、数据季度语义错位" 排查（见文末背景）。

---

## 1. Scope / Trigger

跨层契约：CSV 列（`财务指标汇总_*.csv`）→ `FinancialReader` → `routes.py`
`financial_map` → pydantic `DividendStock` → 前端 `DividendStock` 类型 +
`DividendTable` 弹层。任何一层改季度相关字段，全链路必须同步。

## 2. 数据事实（akshare 契约，勿凭直觉）

`stock_financial_analysis_indicator` 的
`扣除非经常性损益后的净利润(元)` 列是**报告期累计值**，不是单季值：

| 报告期行 | 值的含义 |
|---------|---------|
| 03-31 | Q1 单季（累计=单季，唯一不需要还原的行） |
| 06-30 | **上半年累计**（不是 Q2 单季！） |
| 09-30 | **前三季累计**（不是 Q3 单季！） |
| 12-31 | **全年累计** |

日期列可能是 `datetime.date` 或字符串，统一
`pd.to_datetime(df["日期"]).dt.date` 后再比较。

## 3. 契约（Signatures & 字段语义）

### `_calc_quarterly_yoy(df) -> dict`（`src/data/financial_fetcher.py`）

```
最新报告期 R = df 中 max(日期)
单季值 single:
  Q1      → R 本身
  Q2/Q3/Q4 → R − 同年上一报告期累计（03-31 / 06-30 / 09-30，必须 date(R.year, …) 锁同年）
去年同期单季 same: 去年同月报告期累计 − 去年上一报告期累计（Q1 时直接取去年 03-31 行）
返回 {
  "最新季度扣非(元)":     single,            # float | None
  "最新季度扣非同比(%)":  (single-same)/abs(same)*100,  # 任一为 None 或 same==0 → None
  "数据季度":             f"{R.year}Q{q}",   # 如 "2026Q2"
}
```

「最新季度」= **每只股票各自最新已披露报告期**（表内不同股票可跨季度，
这是有意为之，PRD 已确认；不是 bug）。

### 列/字段语义

| 位置 | 字段 | 语义 |
|------|------|------|
| CSV | `数据季度` | **该行扣非数据所属报告期**（如 `2026Q2`）。历史文件曾存"抓取时日历季度"，过渡期混存，以新刷新为准。**禁止再写 `current_quarter()` 进此列**（文件名后缀仍用抓取季度，两回事） |
| API | `DividendStock.latest_quarter_label` | 同 CSV `数据季度`，`Optional[str]` |
| 前端 | `latest_quarter_label` | 弹层标题 `{label} 扣非同比`、副标题 `vs {label年份-1}`；null 时 fallback「最新季度」并省略副标题 |

## 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| 缺同年上一累计期（如只有 06-30 无 03-31） | 单季/同比 → None |
| 缺去年同期报告期行 | 绝对值有、同比 → None |
| same == 0 或 None | 同比 → None（防除零/爆炸） |
| 无任何季报行 | 三字段全 None |

## 5. Wrong vs Correct

### Wrong — 季度切换靠手改（2026-09 前的旧模式，禁止回潮）

```python
# 后端：全市场固定日期常量
QUARTERLY_YOY_REPORT_DATE = date(2026, 3, 31)  # 每季度手改
# 前端：写死文案
<span>2026Q1 扣非同比</span>  {/* 每季度手改 */}
// 数据季度写抓取时的日历季度
result["数据季度"] = current_quarter()
```

问题：每季度改 4+ 处、必漏改；06-30 累计值被当 Q2 单季直接同比（口径错 2 倍量级）。

### Correct — 数据驱动

后端从数据推出报告期与单季值，label 走 `latest_quarter_label` 一路透传，
前端只渲染字段。季度切换**零代码改动**，只需刷新数据。

## 6. Tests Required（`tests/test_financial_fetcher.py::TestCalcQuarterlyYoy`）

断言点（精确值，非 truthy）：Q2 单季还原（H1−Q1）、Q1 回归、Q4 年报还原
（FY−Q3累计）、新股无去年数据、缺同年上一累计期、基数 0、真实 akshare 列名 +
`datetime.date` 回归 guard、`数据季度` 标签字符串。
改算法必须先改这些用例（红→绿）。

## 7. 相关边界

- 年报口径的 `扣非净利润同比` / `3年复合增长率`（12-31 行）**不在本契约内**，算法未动。
- `routes.py` 财务刷新接口的 `current_quarter_date`（missing_count 判定）基于
  `数据日期` 列，独立于此契约。
- `CompareTable.tsx` 展示同两字段但无季度文案，不需要 label。

---

## 背景 case（2026-09-02）

用户发现 CSV 同列混有 `2026Q2`/`2026Q3`，前端弹层却写死 `2026Q1`。根因：
① `数据季度` 写的是 `current_quarter()`（抓取时日历季度），与报表期无关，
   语义误导；② 后端固定 `QUARTERLY_YOY_REPORT_DATE=2026-03-31` + 前端 3 处
   写死 `2026Q1` 文案，构成"每季度手改"模式；③ 已到 9 月（Q2 财报披露完）
   页面仍展示 Q1。

教训：**展示口径类字段必须由数据推导并全链路透传，禁止在前后端各自写死
"当季"字面量**——两处写死一旦只有一处更新，界面与数据就静默错位。
