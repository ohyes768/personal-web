# 设计：基金经理维度评价（股票基金）

对应 PRD：`.trellis/tasks/11-10-fund-manager-evaluation/prd.md`

## 1. 架构与边界

在 `backend/fund-select` 内新增经理维度，不新建服务。

```
东财 dt=14 经理表 ──┐
东财经理档案页 ─────┼──> manager_fetcher(扩展) ──> managers 表 ──┐
东财 pingzhongdata ─┘                                          │
                                                               ├─> ManagerService
现有 funds 表（mgr_name）──> 姓名→ID 映射 ─────────────────────┘       │
                                                                     ├─> /api/funds/managers/screen
                                                                     └─> 前端经理 tab
```

**边界**：
- 不碰 `index-trends`。
- 不改现有四 tab 的筛选行为（`min_mgr_exp` 语义保持）。
- 债基经理不入 `managers` 表。

## 2. 数据模型

### 2.1 新增 `managers` 表

```python
class Manager(Base):
    __tablename__ = "managers"
    manager_id = Column(String(16), primary_key=True)   # 东财经理 ID，如 30189744
    name = Column(String(64), nullable=False, index=True)
    company = Column(String(128), nullable=True)

    # 从业（来自 dt=14「累计从业时间」，单位天）
    career_days = Column(Integer, nullable=True)
    career_years = Column(Float, nullable=True)

    # 在管规模（dt=14「现任基金资产总规模」，亿元）
    current_scale_yi = Column(Float, nullable=True)
    current_fund_count = Column(Integer, nullable=True)
    managed_fund_count = Column(Integer, nullable=True)  # 累计管理过（含离任）

    # 经理口径业绩（本任务计算）
    tenure_weighted_annual = Column(Float, nullable=True)  # 管理时长加权年化 %
    longest_tenure_annual = Column(Float, nullable=True)   # 最长任期单只年化 %
    longest_tenure_years = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)            # 代表基金最大回撤 %
    sharpe = Column(Float, nullable=True)
    calmar = Column(Float, nullable=True)
    representative_fund = Column(String(6), nullable=True) # 代表基金代码

    scope = Column(String(16), nullable=False, default="stock_active")  # 首版恒为主动权益
    updated_at = Column(DateTime, ...)
```

### 2.2 新增 `manager_tenures` 表（历任明细）

```python
class ManagerTenure(Base):
    __tablename__ = "manager_tenures"
    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_id = Column(String(16), ForeignKey("managers.manager_id"), index=True)
    fund_code = Column(String(6), index=True)
    fund_name = Column(String(128))
    fund_type = Column(String(64))          # 「股票型」「混合型-偏股」
    size_yi = Column(Float)
    start_date = Column(Date)
    end_date = Column(Date, nullable=True)  # NULL = 至今
    tenure_days = Column(Integer)
    tenure_return = Column(Float)           # 任职回报 %
    annual_return = Column(Float)           # 任职年化 %
    is_current = Column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("manager_id", "fund_code", "start_date"),)
```

**为什么单独建 tenure 表**：一名经理可能在同一只基金上有两段任期（离任后回归），`(manager_id, fund_code)` 不唯一，必须带 `start_date`。

## 3. 数据采集

### 3.1 复用与扩展

现有 [manager_fetcher.py](../../../backend/fund-select/src/data/manager_fetcher.py) 用 `ak.fund_manager_em()`，但它**丢弃了经理 ID**。改为直接请求原始接口：

```
GET https://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx
    ?dt=14&mc=returnjson&ft=all&pn=500&pi=<页>&sc=abbname&st=asc
```

返回 `var returnjson= {data:[[...]], record:4384, pages:9, ...}`，需 `akshare.utils.demjson.decode`。

**字段映射**（12 列，实测确认）：

| 索引 | 字段 | 用途 |
|---|---|---|
| 0 | 经理 ID | **主键**（akshare 丢弃，本次必取）|
| 1 | 姓名 | |
| 3 | 所属公司 | |
| 4 | 现任基金代码（逗号分隔）| 建映射 |
| 6 | 累计从业时间（天）| career_days |
| 7 | 现任基金最佳回报 | 参考 |
| 10 | 现任基金资产总规模 | current_scale_yi |

### 3.2 档案页解析

```
GET https://fund.eastmoney.com/manager/<manager_id>.html
```

**必须显式 `content.decode("utf-8")`**——响应带 BOM，`requests.text` 默认按 ISO-8859-1 解码会把「年/天」变乱码，导致任职天数解析为 0、年化全为 n/a（实测踩过）。

历任基金表是**第 2 个 `<table>`**（`<body>` 之后），列序：
`基金代码 | 基金名称 | 相关链接 | 基金类型 | 规模（亿元）| 任职时间 | 任职天数 | 任职回报`

- `任职时间` 形如 `2019-09-17 ~ 至今` 或 `2023-11-27 ~ 2026-01-30`
- `任职天数` 形如 `7年又56天` / `82天` → 解析为天数
- 单次请求即返回全部历任（实测 53 条也不分页）

### 3.3 复权净值

**不能用** `ak.fund_open_fund_info_em(code, "累计净值走势")` 算收益/回撤（不复权，富国天惠实测：462.6% vs 真实 1500%）。

用 `https://fund.eastmoney.com/pingzhongdata/<code>.js`：
- `Data_netWorthTrend[].equityReturn` = 当日复权增长率（%）
- 连乘重建复权曲线：`nav[i] = nav[i-1] * (1 + equityReturn/100)`（实测 161005 → 1498.6%，与官方 1500.33% 吻合）
- 单请求 ~690KB，仅对代表基金取

### 3.4 采集编排

```
阶段 M0：拉经理表（9 次请求，~3s）→ 建 managers 骨架 + 姓名映射
阶段 M1：库内主动权益基金 → 经理名 → 经理 ID（多对多）
阶段 M2：对每人拉档案页（~0.3s/人，1799 人 ≈ 9 分钟）→ manager_tenures
阶段 M3：每人选代表基金（最长任期 + 主动权益类型）→ pingzhongdata → 风险指标
阶段 M4：聚合出 manager 表指标
```

**限速**：0.25–0.35s 间隔 + 失败重试 3 次（指数退避）。断点续采：`managers.fetched_at IS NULL` 的经理优先。

## 4. 关键算法

### 4.1 任职年化

```python
def annual(tenure_return_pct: float, tenure_days: int) -> float | None:
    if not tenure_days or tenure_return_pct <= -100:
        return None
    return ((1 + tenure_return_pct / 100) ** (365.0 / tenure_days) - 1) * 100
```

### 4.2 管理时长加权年化

```python
def weighted_annual(tenures: list) -> float | None:
    # 只用主动权益段，按管理天数加权
    segs = [t for t in tenures if t.annual_return is not None]
    total = sum(t.tenure_days for t in segs)
    if not total:
        return None
    return sum(t.annual_return * t.tenure_days for t in segs) / total
```

**为什么必须加权**：只看最长任期单只 = 让经理自选代表作。实测张坤最长任期 10.53% / 全段加权 6.78%（早期手写 5.15% 漏掉了灵活配置与 QDII 段；精确定义 = 排除债券型/货币型/FOF 后按管理天数加权，偏股 QDII 计入——张坤任期最长的 110011 就是 QDII-混合）。

### 4.3 代表基金选择

优先级：① 主动权益类型（股票型/混合型-偏股）② 任期最长 ③ 在管优先。用于算回撤/夏普。

### 4.4 风险指标（基于复权曲线）

```python
# equityReturn 连乘 → nav
peak = np.maximum.accumulate(nav)
max_dd = ((nav - peak) / peak).min() * 100
rets = np.diff(nav) / nav[:-1]
vol = rets.std(ddof=1) * np.sqrt(252) * 100
sharpe = (cagr - 2.0) / vol
calmar = cagr / abs(max_dd)
```

口径版本号：`mgr-3y-v1`，变更须升版本（对齐现有 `ALGORITHM_VERSION` 惯例）。

## 5. API 契约

```
GET /api/funds/managers/screen
    min_career_years     float?  从业年限 ≥
    min_weighted_annual  float?  加权年化 ≥ %
    max_drawdown         float?  最大回撤 ≤ %（绝对值）
    min_scale_yi         float?  在管规模 ≥ 亿
    sort   str   (career_years|weighted_annual|max_drawdown|current_scale_yi|sharpe)
    order  str   (asc|desc)
    page   int = 1
    limit  int = 50 (1..200)
  → {total, items: [ManagerListItem]}

GET /api/funds/managers/{manager_id}
  → {manager, tenures: [...]}   # 含已离任
```

沿用现有分页不变量：`total` = 筛后总数，与 page/limit 无关。

## 6. 兼容与迁移

| 项 | 处理 |
|---|---|
| 现有 `funds.mgr_*` | 不动。`mgr_experience_years`(min) / `mgr_experience_years_max`(max) 保持现状 |
| 现有四 tab | 不改行为 |
| 新增表 | `Base.metadata.create_all` 自动建；无需 ALTER |
| 测试 | 516 项必须全绿 |

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 东财限流/封 IP | 限速 + 退避重试 + 断点续采；失败不阻断已有数据 |
| 页面结构变更 | 解析层隔离在 `manager_fetcher`，失败记 diagnostics 不写脏数据 |
| 复权口径算错 | 用 161005 做断言基准（≈1500%）写入测试 |
| 经理改名/换公司 | 以 ID 为主键，姓名/公司可更新 |
| 重名串号 | 主键是 ID 不是姓名，天然隔离 |

**回滚**：新增表独立，删表 + 下线路由即可，不影响现有功能。

## 8. 关键陷阱（实测记录）

1. 档案页 UTF-8 带 BOM，必须 `content.decode("utf-8")`，否则天数解析全 0。
2. `累计净值走势` 不复权，收益会被低估约 3 倍（分红型）。
3. `从业年限`≠`任职年限`，评价单只必须用档案页任职天数。
4. `dt=14` 最佳回报只统计在管，已离任差战绩被隐藏 → 必须用档案页完整列表。
5. 同基金多经理共管，`funds` 层取 min 会误伤老将（已修，新增 max）。
