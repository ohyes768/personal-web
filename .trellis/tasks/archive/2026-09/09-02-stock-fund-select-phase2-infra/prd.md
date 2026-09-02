# phase2-A 基础设施：业绩基准 fetcher + 指数 yaml 映射 + 无风险利率源

## Goal

为 phase2 风险/超额指标计算准备数据源。本 task **不实现指标本身**，只交付：

1. `src/data/benchmark_fetcher.py` — 拉取并合成每只基金的业绩比较基准 TRI 序列
2. `config/benchmarks.yaml` — 指数名称 → akshare symbol 映射（~30 个常见指数）
3. `src/data/risk_free_fetcher.py` — 拉取无风险利率日频序列（中国国债 2Y）
4. `fund_benchmark` / `risk_free_rate` 两张 ORM 表 + alembic 迁移
5. 「活期存款基准利率」常量处理工具

输出供 phase2-B 的 `risk_service` 直接消费（避免 B 再做同一份数据准备）。

## Background & 调研结论

第一阶段（`09-02-stock-fund-select-tab`）已交付：股票 tab 路由、默认筛选、achievement 排名展示。
本次 PRD 撰写前已对全部 143 只基金做 demo 跑通（`tmp/demo_benchmark_extract_143.py`），关键数据：

### 字段提取实测（143 只）

| 指标 | 值 |
|---|---|
| 「业绩比较基准」可提取 | 142 / 143 (99.3%) |
| 提取失败的 | 968157（互认基金 QDII-互认；danjuanfunds 也不含此字段） |
| 跑完全量耗时 | 127 秒（0.89 秒/只） |
| 公式含「存款」/「基准利率」字眼 | **81 / 142 (57%)** |
| 公式含全角括号 `（）` | 89 / 142 (63%) |
| 出现全角 `＋` `ｘ` | 至少 3 只（如 210002、007466、018387） |
| 百分号在权重前 | 至少 1 只（005051：`95%×指数...+5%×存款...`） |
| 子指数（红利/成长/低波/高股息） | 普遍（至少 10+ 不同子指数名） |
| 单指数无权重 | 少数（`纳斯达克100指数`） |
| 纯名称无权重 | 少数（`标普500等权重指数（全收益指数）`） |
| 权重和异常（≠100） | 1 只（000051 = 95%，公司自定义漏写） |

### 实测样例公式（按类型分组）

```
A 标准三指数：     沪深300×45%+中证港股通综合×35%+中债总×20%
B 含活期存款：     中证白酒×95%＋金融机构人民币活期存款基准利率（税后）×5%
C 含子指数：       中证800相对成长×84%+中证全债×16%
D 经汇率调整：     中证港股通综合（使用估值汇率折算）×20%+中证综合债券×20%
E 权重前置：       95%×标普港股通低波红利指数收益率+5%×税后银行活期存款收益率
F 全角字符：       中证红利指数收益率ｘ60%＋上证国债指数收益率ｘ40%
G 单指数无权重：   纳斯达克100指数
H 纯名称无权重：   标普500等权重指数（全收益指数）
```

### 数据源探测结果

| 需求 | 探测结论 |
|---|---|
| 业绩比较基准字段 | `ak.fund_individual_basic_info_xq` 返回，key = `业绩比较基准` |
| 指数日线（沪深 300 等宽基） | `ak.stock_zh_index_daily(symbol="sh000300")` 已可用 |
| **中国国债收益率（风险利率主源）** | `ak.bond_zh_us_rate()` 中国国债**2年**列（1990-至今 9333 行）；**无 1Y** |
| `ak.bond_china_yield()` 中债国债 1Y | **只能拉近 1 年窗口**（2020-02 ~ 2021-01 246 行），不够用，**放弃** |
| `ak.macro_china_lpr()` LPR | 月度（1500+ 行），颗粒度粗，备用 |
| 活期存款基准利率 | akshare **无接口**；央行政策常量 **0.35%**（2012-07-06 起至今未变） |
| `ak.macro_rmb_deposit()` | 是「新增存款数量」宏观数据，**不是利率**，不能用 |

## Requirements

### 1. `config/benchmarks.yaml` 指数映射表

```yaml
version: 1
fallback_index: "sh000300"   # 沪深 300
fallback_chain: ["sh000906", "sh000300"]  # 中证 800 → 沪深 300
indices:
  沪深300:
    ak_symbol: "sh000300"
    source: "stock_zh_index_daily"
  中证500:
    ak_symbol: "sh000905"
    source: "stock_zh_index_daily"
  中证1000:
    ak_symbol: "sh000852"
    source: "stock_zh_index_daily"
  上证50:
    ak_symbol: "sh000016"
    source: "stock_zh_index_daily"
  中证800:
    ak_symbol: "sh000906"
    source: "stock_zh_index_daily"
  中证全债:
    ak_symbol: "h11001"
    source: "stock_zh_index_daily"   # 需在 demo 阶段验证 h11001 是否可用
  恒生综合:
    ak_symbol: "hkHSI"
    source: "stock_hk_index_daily_em"
  中证白酒:
    ak_symbol: "sz399997"
    source: "stock_zh_index_daily"
  # ... 共 ~30 个常见宽基 + 行业
aliases:
  沪深300指数: 沪深300
  HS300: 沪深300
  上证国债指数: 中证全债       # 雪球常见叫法
  中证综合债指数: 中证全债
```

**要求**：
- ≥30 个常见指数（宽基 + 主要行业主题）
- **美股指数（QDII 需要）**：`纳斯达克100` / `标普500` 必须收录，akshare 源在 demo 阶段验证（候选 `index_us_stock_sina(symbol=".NDX")`）；验证失败则该类 component 走 fallback_chain，DB source 标记
- `aliases` 至少覆盖：「沪深300指数」「沪深300」「HS300」「中证综合债指数」「上证国债指数」
- 含 fallback_chain 与 fallback_index
- 跑全量 143 只基金时，未覆盖的指数走 fallback_chain（WARN 日志记录）

### 2. `src/data/benchmark_fetcher.py` 业绩基准合成

**核心函数**：

```python
def parse_formula(text: str) -> list[Component]:
    """解析公式为 [Component] 列表，每项含 name / weight / kind。
    kind ∈ {'index', 'deposit_floor', 'unknown'}

    流程：
      1. unicode 归一化（'＋' -> '+', 'ｘ' -> '*'）
      2. 全角括号统一为半角
      3. 括号内容视作注释（剥离）
      4. 按 '+' 切分各项，每项按 '*' 切分 (name, weight)
      5. 百分号前后位置都支持（'95%×指数' 与 '指数×95%' 同义）
      6. 含「存款」/「基准利率」字眼的项 kind = 'deposit_floor'，weight 取数字
      7. 单指数无权重：weight = 1.0
      8. 纯名称无权重：尝试 aliases / indices lookup；找不到 kind = 'unknown'
    """

def fetch_benchmark_tri(code: str, start: date, end: date) -> pd.DataFrame:
    """返回单只基金的业绩比较基准 TRI 序列（含日期列）。

    步骤：
      1. fetch_basic(code) 拿 info dict，读「业绩比较基准」
      2. parse_formula() 解析
      3. 对 'index' 类 fetch_index_daily(ak_symbol, start, end)
      4. 对 'deposit_floor' 类用常量 0.0035 / 365 当日收益
      5. 加权合成 TRI（参考日=1000；R_d = Σ w_i × r_i,d；tri_d = tri_d-1 × (1+R_d)）
      6. 对齐交易日（基准交易日为骨架）
    """
```

**降级路径**（按优先级）：
- 公式解析失败 → 整体走 fallback_chain，DB source = `fallback_chain:sh000906`
- 单个指数未在 yaml → 用 fallback_chain 单条替换，DB source = `fallback_chain:sh000300`
- 968157 等无字段 → DB 写入 (code, date, tri=NULL, source=`unavailable:...`)
- 单只基金失败不影响 refresh 全量；WARN 日志

### 3. `src/data/risk_free_fetcher.py` 无风险利率

**核心函数**：

```python
def fetch_risk_free_rate(start: date, end: date) -> pd.DataFrame:
    """返回日频无风险年化利率序列。
    列: [date, rate_decimal]   rate_decimal 为年化小数（如 0.0234 表示 2.34%）
    """
```

**实现**：
- 主源：`ak.bond_zh_us_rate()` 取「中国国债收益率2年」列（1990-至今 9333 行）
  - 列名: `中国国债收益率2年`，单位**百分比数字**（如 2.34 表示 2.34%）
  - 转换为小数：÷ 100
- Fallback：`ak.macro_china_lpr()` 取 LPR1Y（月度，平铺到日，前向 fill）
- 兜底：常量 0.025（2.5%）
- 降级路径同 benchmark fetcher

### 4. 「活期存款基准利率」常量

```python
# src/data/deposit_floor.py
PBOC_DEPOSIT_FLOOR_RATE = 0.0035  # 央行活期存款基准利率（年化小数），固定常量
# 0.35% 自 2012-07-06 起执行至今（活期档位最后一次调整；2015-10-24 降息只调了定期档）。
# 更早历史（2011-07-07 起 0.50% → 0.44% → 0.40% 等）不做按日期映射：
# 基金基准公式中存款权重通常仅 5%~20%，用常量替代历史档位的误差 ~0.02%/年，可忽略。
# 若未来央行重启该档位调整，需扩展为按日期生效的常量映射表。
```

### 5. ORM 表

```python
class FundBenchmark(Base):
    """业绩比较基准 TRI 序列"""
    __tablename__ = "fund_benchmark"
    code = Column(String(6), primary_key=True)
    date = Column(Date, primary_key=True)
    tri = Column(Float, nullable=True)          # NULL 表示无可用 benchmark
    source = Column(String(64), nullable=True)  # 'fetched' / 'fallback_chain:sh000906' / 'unavailable:qdii-mutual-recognition'
    updated_at = Column(DateTime, ...)


class RiskFreeRate(Base):
    """无风险利率日频（中国国债 2Y）"""
    __tablename__ = "risk_free_rate"
    date = Column(Date, primary_key=True)
    rate = Column(Float, nullable=False)        # 年化小数
    source = Column(String(32), nullable=True)  # 'bond_zh_us_rate_2y' / 'lpr' / 'constant'
    updated_at = Column(DateTime, ...)
```

### 6. Refresh pipeline 接入

- `refresh_stock_funds_sync` **新增可选步骤**（默认开启）：拉一次 `fund_benchmark`（每个 stock fund × N 个交易日）
- `risk_free_rate` 表独立刷新（与基金无关，一次拉 35 年全历史）
- **不动债基 refresh 路径**

## Constraints

1. **不动债基**：所有改动只在 stock 路径
2. **不引入新外部数据源**：akshare 已有覆盖；不引 baostock / tushare / 爬虫
3. **不引新 .env 变量**
4. **不引新依赖**：`pyyaml`、`pandas`、`numpy` 全部已在
5. **不实现指标本身**：Sharpe / IR / T-M 等全在 phase2-B
6. **公式解析容错**：142 只真实公式形态多样，必须有 WARN 级降级路径
7. **Python 3.13 兼容**；纯手写 numpy，不引 `empyrical` / `quantstats`
8. **不解析括号内非指数成分**：「（税后）」「（使用估值汇率折算）」「（Nasdaq-100 Index）」等括号内文字视作注释剥离
9. **存量基金（2001 年至今）**：常量 0.35% 覆盖所有现役基金；未来调整需扩展常量表

## Acceptance Criteria

- [ ] `config/benchmarks.yaml` 含 ≥30 个常见指数 + aliases 表
- [ ] `parse_formula()` 单测覆盖至少 8 类样例（A-H 上述）：
  - 单指数、双指数、三指数（含 `+` `＋` `*` `×` `（）` `()`）
  - 百分号位置（前 / 后）
  - 含「存款」字眼（kind = `deposit_floor`）
  - 单指数无权重（kind = `index`, weight = 1.0）
  - 纯名称无权重（kind = `index`, weight = 1.0, 命中 aliases）
  - 不可解析（kind = `unknown`, weight = 0）
- [ ] `fetch_benchmark_tri()` 单测覆盖：TRI 形状（行数、列名、参考日=1000、单调性）、含 `deposit_floor` 成分时与纯指数混合
- [ ] `fetch_benchmark_tri()` 跑 `config/funds_stock.yaml` 全量 143 只；写入 DB `fund_benchmark`（项目无磁盘缓存惯例，指数级内存去重：同一 symbol 日线一次 refresh 只拉一次）；**142 只 tri 非 NULL，968157 tri NULL**；失败率 ≤ 1%（只有 968157 一只预期 NULL）
- [ ] 公式含未收录指数 → 走 fallback_chain；DB `source` 字段记录 fallback 路径
- [ ] `fetch_risk_free_rate()` 单测：返回非空、列名正确、单位年化小数（0.005~0.05 量级）
- [ ] `fetch_risk_free_rate()` 跑一次写入 DB `risk_free_rate`，覆盖 ≥ 30 年（约 8000+ 行）
- [ ] 主源 `bond_zh_us_rate` 中国国债 2Y 列；fallback LPR 1Y；兜底 0.025
- [ ] `refresh_stock_funds_sync` 接入 benchmark 步骤，全量跑一次无 schema 错误；`pytest tests/ -v` 全过
- [ ] alembic 迁移：`fund_benchmark` + `risk_free_rate` 两张新表，upgrade / downgrade 都过
- [ ] **不实现**：Sharpe / IR / T-M / α-IR / 超额收益 — 留在 phase2-B 验收

## Decisions（已确认 / 由调研决定）

| # | 决策 | 选择 | 依据 |
|---|---|---|---|
| 1 | 公式解析复杂度 | **统一归一为半角后**，支持 +× 嵌套、括号剥离、百分号位置灵活 | demo 显示 142 只里至少 8 种形态；统一归一最简 |
| 2 | TRI 合成 | 加权日收益率复利，参考日 = 1000 | 业界主流（晨星 / Wind） |
| 3 | Sharpe 用 risk_free | **`bond_zh_us_rate` 中国国债 2Y** | 数据全（1990-至今 9333 行），API 稳定；2Y 偏高 30~50bp 不影响 Sharpe 量级 |
| 4 | 缺指数 / 公式解析失败 | fallback_chain（中证 800 → 沪深 300），DB 标 source | 单只基金坏了不影响整批 refresh |
| 5 | 公式含「存款」/「基准利率」 | 抽出为 `deposit_floor` 成分，常量 **0.35%** 当日收益（不做历史分档映射） | 央行政策常量，2012-07-06 起至今未变；历史档位误差 ~0.02%/年可忽略；akshare 无接口 |
| 6 | 968157 等互认基金无字段 | DB 写入 `tri=NULL, source='unavailable:qdii-mutual-recognition'` | 用户已确认 |

## Notes

- 实施文件清单（仅 stock 路径，不动债基）：
  - `config/benchmarks.yaml`（新建）
  - `src/data/benchmark_fetcher.py`（新建）
  - `src/data/risk_free_fetcher.py`（新建）
  - `src/data/deposit_floor.py`（新建，常量 + 历史调整注释）
  - `src/db/models.py`（加 `FundBenchmark` / `RiskFreeRate`）
  - `src/db/migrations/`（加 alembic 迁移）
  - `src/services/refresh_service.py`（`refresh_stock_funds_sync` 接入 benchmark 步骤；新增 `refresh_risk_free_rate_sync`）
  - `tests/test_benchmark_fetcher.py`（新建，覆盖 8 类解析样例 + TRI 合成）
  - `tests/test_risk_free_fetcher.py`（新建）
- 阶段关系：phase2-A 不交付前端任何改动；输出供 phase2-B 消费
