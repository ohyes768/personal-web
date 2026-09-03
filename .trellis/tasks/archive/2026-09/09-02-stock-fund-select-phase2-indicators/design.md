# phase2-B 设计：risk_service 指标计算

## 模块边界

```
src/services/risk_service.py     # 新建
  ├── compute_risk_metrics(r_p, r_b, r_f) -> MetricsResult   # 纯函数，无 IO
  └── refresh_fund_risks(db, codes) -> list[str]             # 编排
src/data/nav_fetcher.py          # 追加 fetch_nav_accumulated()（累计净值）
src/db/models.py                 # FundRiskMetrics
src/scheduler/tasks.py           # refresh_stock_funds_sync 末尾追加 risk 步骤
src/api/routes.py                # /api/funds/stock 响应加 6 字段
apps/fund-select                 # /funds/stock 表格 6 列
```

依赖：r_b 来自 A 的 `fund_benchmark` 表，r_f 来自 `risk_free_rate` 表（均已落库）。

## 数据流

```
fetch_nav_accumulated(code)          DB: fund_benchmark(code)        DB: risk_free_rate
  累计净值日频 ──pct_change──> R_p     tri ──pct_change──> R_b          rate/252 ──ffill──> R_f(日)
        └──────────── inner join(日期) ──────────┘                └──── reindex 对齐 ────┘
                                      ↓
                        compute_risk_metrics(R_p, R_b, R_f)
                                      ↓
                        FundRiskMetrics upsert（一行一基金）
```

- 窗口：近 3 年（end=today, start=today−3y），与 dd_3y 口径一致
- 对齐：R_p 与 R_b 按日 **inner join**（A 股日历 ∩ 港股日历 自动成立）；R_f reindex 到对齐日 ffill
- 样本 < 250 交易日 → 全指标 NULL（不足 1 年无统计意义）
- **nav 口径用累计净值**（`indicator="累计净值走势"`）：红利类基金分红除权会让单位净值收益严重低估；累计净值含分红再投，与 benchmark TRI（财富口径）同构

## 指标公式（窗口内日频序列）

| 指标 | 公式 | 备注 |
|---|---|---|
| excess_3y | `∏(1+R_p) − ∏(1+R_b)` | 3 年累计超额（小数） |
| sharpe | `mean(R_p−R_f) / std(R_p−R_f, ddof=1) × √252` | |
| ir | `mean(R_p−R_b) / std(R_p−R_b, ddof=1) × √252` | |
| alpha | T-M 截距 × 252（年化） | 见下 |
| gamma | T-M 二次项系数（日频原值） | |
| alpha_ir | `alpha_daily / σ_ε × √252` | σ_ε 为回归残差 std |

**T-M 回归**（numpy，不引 statsmodels）：

```python
y = r_p - r_f
x1 = r_b - r_f
x2 = x1 ** 2
X = np.column_stack([np.ones_like(x1), x1, x2])
coef, *_ = np.linalg.lstsq(X, y, rcond=None)   # coef = [alpha_d, beta, gamma]
resid = y - X @ coef
sigma_e = resid.std(ddof=1)
```

容错：std=0（R_p−R_f 或 R_p−R_b 恒定）→ 对应指标 None；`lstsq` 正常奇异不抛错，但 x1 全 0 时 coef 退化 → 用残差判据（sigma_e 为 NaN 或 x1.std==0 → alpha/gamma/alpha_ir None，sharpe/ir 按各自 std 判）。

## 数据模型

```python
class FundRiskMetrics(Base):
    __tablename__ = "fund_risk_metrics"
    code = Column(String(6), primary_key=True)
    sharpe = Column(Float, nullable=True)
    ir = Column(Float, nullable=True)
    alpha = Column(Float, nullable=True)       # 年化
    gamma = Column(Float, nullable=True)       # 日频二次项
    alpha_ir = Column(Float, nullable=True)
    excess_3y = Column(Float, nullable=True)   # 3年累计超额（小数）
    sample_days = Column(Integer, nullable=True)  # 诊断：实际样本数
    as_of_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, ...)
```

benchmark 不可用（968157 tri=NULL、fallback exhausted）→ 全 NULL + sample_days=0，前端显示 "—"。

## Refresh 接入

`refresh_stock_funds_sync` 主循环 + benchmark 步骤后追加：

```python
def refresh_fund_risks(db, codes) -> list[str]:
    end, start = today, today - 3y
    r_f_all = 读 risk_free_rate → Series
    for code in codes:
        bench = 读 fund_benchmark(code) → r_b（tri NULL/空 → 写全 NULL 行）
        nav = fetch_nav_accumulated(code) → r_p
        m = compute_risk_metrics(...)
        upsert FundRiskMetrics（每只 commit）
```

无新网络源（nav 走东财已有接口）；单只失败记 errors 不阻塞。

## API

`GET /api/funds/stock` 每条记录追加 6 字段：`sharpe / ir / alpha / gamma / alpha_ir / excess_3y`（命名跟随现有 ret_1y / dd_3y 风格），NULL → null。

## 前端

`/funds/stock` 表格追加 6 列（复用现有 FundTable 列定义模式）：

| 列 key | 表头 | 格式 |
|---|---|---|
| sharpe | 夏普 | 2 位小数 |
| ir | IR | 2 位小数 |
| alpha | 选股α | 百分比 2 位（年化超额贡献） |
| gamma | 择时γ | 4 位小数（量级小） |
| alpha_ir | α-IR | 2 位小数 |
| excess_3y | 超额3y | 百分比 2 位 |

排序 + 导出 CSV + 空值 "—"；不动债基页。

## 已知口径差异（surfaced，不在 B 内修）

第一阶段 `FundPerformance.ret_3y / dd_3y` 基于**单位净值**；B 的 `excess_3y` 基于**累计净值**。分红多的基金两者会有差异（单位净值低估）。若需统一口径，后续单独 task 把 nav_fetcher 全部切累计净值并重算 ret/dd —— 涉及第一阶段验收基准，不在本 task 动。

## 测试策略

- `compute_risk_metrics` 纯函数 TDD：构造已知序列（如 R_p 恒 +1%、R_b 恒 0% → sharpe/ir 精确可算）；构造精确 `y = a + b·x + c·x²` 序列 → T-M α/β/γ 精确恢复
- 容错分支：样本不足 / std=0 / benchmark 空 → None 不抛异常
- `fetch_nav_accumulated`：mock akshare 验证列与排序契约
- 集成：143 只全量跑 → 142 只非 NULL、968157 全 NULL
