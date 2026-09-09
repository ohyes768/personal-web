# market tab 接入东方财富 rankhandler 批量业绩接口

## 大白话

之前股基·市场 / 债基·市场两个 tab 只能显示基金的"名字 + market_subtype + 规模/年限/经理"等基础信息，**业绩数据（近 1 年/3 年涨幅）是空的**——因为这部分基金没在现有 yaml 名单里，没有 refresh 过业绩。

原因是逐只拉业绩太慢：4452 只 × 5 个 fetcher × ~3 秒 ≈ **12+ 小时**。

本任务改用**东方财富的批量排行榜接口**（`rankhandler.aspx`）：

- 一次 HTTP 请求拿 50 只基金的完整业绩（近 1 周/1 月/3 月/6 月/1 年/2 年/3 年/今年/成立以来）+ 规模 + 净值日期
- 按 `ft`（gp/hh/zq/zs/qdii 等）筛选类别
- **~40 秒就能拉完全市场 ~4000 只的业绩**（vs 12+ 小时，**降 1000 倍**）

新增独立的 `MarketFundRank` 表（专门存市场 tab 业绩），**不动现有 yaml refresh 路径**——两套数据源彻底分开。

## 背景

### 现状（09-08-market-fund-tabs 已完成）
- `funds.market_subtype` / `funds.market_type` 列：akshare `fund_name_em()` 写入的子类粗分类
- `funds.name`：akshare 简称
- `_screen("discovery-stock")` 返回 4452 只，但 `ret_1y/3y` 等都是 NULL（库内无业绩）
- 用户体验：能看到市场全名单，但看不出哪只基金业绩好

### 东方财富 rankhandler 接口（已实测）
```
URL: http://fund.eastmoney.com/data/rankhandler.aspx
参数: op=ph, dt=kf, ft={gp|hh|zq|zs|qdii|lof|fof|bb},
      sc={zzf|1yzf|3nzf|6yzf|...}, st=desc, sd=YYYY-MM-DD, ed=YYYY-MM-DD,
      pi=页码, pn=每页条数(≤50), dx=1
响应: JSONP var rankData = {datas: ["code,name,...,近1年,...,近3年,...,规模(亿),..."], allRecords, allPages}
请求头: Referer: https://fund.eastmoney.com/data/fundranking.html 必带
```
**关键优势**：单次 HTTP 拿 50 只基金完整业绩（含规模），完全无需逐只 fetch_basic + nav。

### 关键决策：两套实现分开（用户明确要求）
| 维度 | yaml 名单（现有） | market 名单（本任务） |
|---|---|---|
| 数据源 | `fund_individual_basic_info_xq` 逐只 | `rankhandler.aspx` 批量 50/页 |
| 存储 | funds + fund_performance + fund_fees + fund_holdings_bond + fund_risk_metrics + fund_benchmark + fund_achievement_rank | **新增 market_fund_rank**（独立表） |
| 刷新机制 | yaml 名单逐只 snapshot_fund（5 fetcher） | 按 ft 批量 rankhandler |
| 字段 | ret_1y/3y/5y/dd_3y/sharpe/ir/alpha/gamma + achievement_rank | 近 1 周/1 月/3 月/6 月/1 年/2 年/3 年/今年/成立 + 规模 |
| 关联字段 | fund.fund_type（雪球细分类） | fund.market_subtype（akshare 子类） |

## 数据齐全性

**最终展示要求**：股基·市场 4452 只 + 债基·市场 5353 只，**每个基金**的字段：
- ✅ 基础：code / name / market_subtype / size_yi / age_years / mgr_name / mgr_company / mgr_experience_years（来自 funds 表，由 L0 universe + L2 size_yi 写入）
- ✅ 业绩：nav_latest / nav_date / ret_1w / ret_1m / ret_3m / ret_6m / ret_1y / ret_2y / ret_3y / ret_ytd / ret_all（来自 market_fund_rank，L1 写入）

**业绩字段对全 universe 覆盖**：每日 06:30 跑 rankhandler 分页，每 ft 拉 N 页（如 N=20，每页 50 只 = 每 ft 1000 只），4 ft = 4000 只。

**09-09 探索更新**：原 L2 fund_basic 阶段（雪球 `fund_individual_basic_info_xq` 逐只拉 4452 只）发现雪球 schema 残缺，**29 只 C/E 份额全军覆没**。改为 L0 用 akshare 全量接口（fund_name_em + fund_manager_em，35 秒）+ L2 用东财移动端 msm 接口（仅对 L1 预筛后 ~1573 只）。详情见 implement.md「阶段 0 / 阶段 2」。

### 字段对齐

MarketFundRank 字段映射：
| 字段 | 来源字段 | 单位 |
|---|---|---|
| code | `datas[0]` 基金代码 | str |
| nav_date | `datas[3]` 净值日期 | date |
| nav_latest | `datas[4]` 单位净值 | float |
| ret_1w | `datas[7]` 近 1 周 | % (如 1.5) |
| ret_1m | `datas[8]` 近 1 月 | % |
| ret_3m | `datas[9]` 近 3 月 | % |
| ret_6m | `datas[10]` 近 6 月 | % |
| ret_1y | `datas[11]` 近 1 年 | % |
| ret_2y | `datas[12]` 近 2 年 | % |
| ret_3y | `datas[13]` 近 3 年 | % |
| ret_ytd | `datas[14]` 今年以来 | % |
| ret_all | `datas[15]` 成立以来 | % |
| ft_code | URL 参数 ft | str (gp/hh/zq/zs/qdii) |

### 与现有 screen 对齐

`_screen("discovery-*")` 的 DTO 字段名：
- `ret_1y`, `ret_3y` → 来自 `MarketFundRank.ret_1y / ret_3y`
- `size_yi` → 来自 `funds.size_yi`（**L2 阶段 FundMNBasicInformation 写入**；只有 ~1573 只 L1 预筛后基金有，老 yaml 名单基金可能没有）
- `fund_type` → 来自 `funds.fund_type`（**L0 阶段 ak.fund_name_em 写入**；已有数据）

**决策**：funds.size_yi / fund_type 都不被 rankhandler 覆盖（保持入库原值）；rankhandler 拉来的规模仅在 UI 缺数据时使用。

## Requirements

### 后端

#### R1 新增表 `market_fund_rank`

```python
class MarketFundRank(Base):
    __tablename__ = "market_fund_rank"
    code = Column(String(6), primary_key=True)
    nav_date = Column(Date, nullable=True)
    nav_latest = Column(Float, nullable=True)
    ret_1w = Column(Float, nullable=True)
    ret_1m = Column(Float, nullable=True)
    ret_3m = Column(Float, nullable=True)
    ret_6m = Column(Float, nullable=True)
    ret_1y = Column(Float, nullable=True)
    ret_2y = Column(Float, nullable=True)
    ret_3y = Column(Float, nullable=True)
    ret_ytd = Column(Float, nullable=True)
    ret_all = Column(Float, nullable=True)
    ft_code = Column(String(8), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

老库自动 ALTER TABLE（幂等）+ 创建 code 主键索引（已是主键）。

#### R2 新增 fetcher `data/market_rank_fetcher.py`

- `fetch_market_rank_page(ft, sd, ed, pi, pn=50, sc="3nzf", st="desc") -> list[dict]`
  - 单页 rankhandler 调用，Referer 头必带
  - 失败抛异常（外层重试）
- `fetch_market_rank_bulk(fts: list[str], sd, ed, pages_per_ft=20) -> pd.DataFrame`
  - 按 ft 列表分页拉，返回 `[code, name?, nav_date, nav_latest, ret_*, ft_code]`
- 解析 JSONP：`var rankData = {datas: [...], ...}`，正则提取 + 裸 key 加引号

#### R3 新增 refresh service `services/market_rank_refresh.py`

- `refresh(session, df, task_id=None) -> dict`
  - upsert `MarketFundRank`（已有 code 覆盖，新 code 插入）
  - 每 500 行 commit 一次，写入 RefreshRun 进度
- 默认拉取参数：
  - discovery-stock ft 列表：`["gp", "hh", "zs", "qdii"]`
  - discovery-bond ft 列表：`["zq"]`
  - 每类 `pages_per_ft=20`（每页 50 只 = 1000 只/类 → stock 4000 只，bond 1000 只）
  - sd = (今天 - 3 年)，ed = 今天（与 `dd_3y` 对齐）
  - `sc="3nzf" st="desc"`（按近 3 年涨幅降序，优先拉头部业绩好的基金）

#### R4 新增 refresh 端点 + task

- 新增 `tasks.refresh_market_rank_sync(preset_task_id=None)` 函数
- scheduler 加 06:35 cron job（在 06:30 全市场名单之后；07:05 yaml refresh 之前）
- API 路由 `/api/funds/discovery-{bond,stock}/rank/refresh`（新前缀避免与现有 refresh 冲突）
- 复用 `RefreshRun` 进度接口

#### R5 改 `_screen()` discovery-* 路径

```python
elif kind in ("discovery-bond", "discovery-stock"):
    ...
    q = (
        select(Fund, FundPerformance, ..., MarketFundRank)
        .outerjoin(FundPerformance, ...)
        ...
        .outerjoin(MarketFundRank, Fund.code == MarketFundRank.code)
        .where(Fund.is_active == True)
        .where(Fund.market_subtype.in_(types))
    )
```

`_to_dto()` 优先从 `MarketFundRank` 读业绩字段：

```python
ret_1y = market_rank.ret_1y if market_rank else None,
ret_3y = market_rank.ret_3y if market_rank else None,
...
```

#### R6 universe_stats 扩展

```python
def universe_stats(kind, universe_codes=None, market_types=None):
    if kind in ("discovery-bond", "discovery-stock"):
        ...
        with_perf = SELECT count(DISTINCT code) FROM market_fund_rank
                    WHERE code IN (active_codes)
        ...
```

返回的 `with_performance` 统计"有多少基金有 MarketFundRank 数据"。

### 前端

#### R7 `lib/api.ts` 加新方法

```typescript
export const discoveryBondApi = {
  ...
  refreshRank(): Promise<{ task_id; status }> { ... },
};
```

#### R8 `RefreshStatusPopover` 加「拉业绩」按钮

- 顶部两个按钮：「刷新名单」+「拉业绩」
- 调不同的 `refreshUrl`：
  - 名单 → `/api/funds/discovery-{bond,stock}/refresh`（已有）
  - 业绩 → `/api/funds/discovery-{bond,stock}/rank/refresh`（新增）
- 文案动态：业绩场景显示「拉取 ~4000 只基金业绩（rankhandler 批量），约 1 分钟」

### 非功能需求

- **N1 老 yaml refresh 路径完全不动**：funds.fund_type + fund_performance/fees/holdings/risk_metrics 表数据保留
- **N2 funds 表不动**：不覆盖 funds.name / market_subtype / size_yi / 等
- **N3 老接口不变**：`GET /api/funds/discovery-{bond,stock}/screen` 返回结构兼容，老版本客户端不破坏
- **N4 幂等**：MarketFundRank upsert，重复 code 覆盖
- **N5 限频保护**：rankhandler 单页 0.5s 延时（避免被东财限流）

## Out of Scope

- ❌ 历史业绩快照（rankhandler 只返回当前累计涨幅）
- ❌ 单只净值历史曲线（market tab 不展示）
- ❌ 持仓 / 费率 / 风险指标（market tab 不展示）
- ❌ market_fund_rank 表覆盖 funds.size_yi（保留 L2 FundMNBasicInformation 写入的规模）
- ❌ 用雪球 `ak.fund_individual_basic_info_xq` 逐只拉 fund_basic（接口 schema 残缺，29 只 C/E 份额拿不到；改用 L0 akshare 全量 + L2 东财 msm 单只）

## Acceptance Criteria

### 后端

- [ ] **AC1** 新建表 `market_fund_rank`，老库自动 ALTER TABLE 添加（幂等）
- [ ] **AC2** `fetch_market_rank_page('gp', sd, ed, pi=1, pn=50)` 实测返回 50 只 code，每只含 nav_latest / ret_1y / ret_3y / ret_ytd / size_yi* 等字段（size_yi 来自 `datas[18]`）
- [ ] **AC3** `refresh_market_rank_sync()` 默认参数下：
  - 跑完耗时 < 5 分钟
  - market_fund_rank 总行数 ≥ 4000（discovery-stock 4000 + discovery-bond 1000 + 重叠）
- [ ] **AC4** `GET /api/funds/discovery-stock/screen` 返回 items 中至少 80% 有非 NULL 的 ret_3y
- [ ] **AC5** `GET /api/funds/discovery-bond/screen` 返回 items 中至少 80% 有非 NULL 的 ret_3y
- [ ] **AC6** `GET /api/funds/discovery-stock/stats` 的 `with_performance` 字段 ≥ 3000（vs 现状 0/几十）
- [ ] **AC7** 老接口回归：`GET /api/funds/screen` 和 `GET /api/funds/stock/screen` 返回不变，老 yaml 名单基金仍走 FundPerformance 路径
- [ ] **AC8** 老 60 只 yaml 名单的 code 既出现在 `funds.fund_type`（雪球细分类）又出现在 `market_fund_rank`（akshare 业绩）—— 两套数据互补
- [ ] **AC8.1**（L0 阶段）`fund_name_em()` 全量拉取（5 秒）+ `fund_manager_em()` 全量拉取（30 秒）后，stock universe 内 `fund_type / mgr_name / mgr_company / mgr_days / mgr_experience_years` 覆盖率 ≥ 99%（原 36%）
- [ ] **AC8.2**（L2 阶段）`FundMNBasicInformation` 对 L1 预筛后 ~1573 只拉取后，funds 表 `size_yi / age_years / established_date` 覆盖率 ≥ 99%（原 64%）
- [ ] **AC8.3**（L2 阶段）原 29 只「雪球 schema 残缺的 C/E 份额」用 `FundMNBasicInformation` 全字段补齐

### 前端

- [ ] **AC9** FundsHeader 的「刷新」按钮旁新增「拉业绩」按钮（桌面端 + 移动端均显示）
- [ ] **AC10** 点「拉业绩」调 `rank/refresh` 端点，弹窗显示进度（跑 1-5 分钟）
- [ ] **AC11** 业绩跑完后表格自动 reload，ret_3y / ret_1y / size_yi 列显示数值（不再是 -）

### 数据

- [ ] **AC12** 单只基金（如 000001 华夏成长）在 funds 表 + fund_performance 表 + market_fund_rank 表中都有完整字段
- [ ] **AC13** 新增基金（如某只 2026 年成立）首次跑 rankhandler 后入库；老基金 upsert 覆盖业绩字段

### 测试

- [ ] **AC14** `pytest tests/test_market_rank_fetcher.py` 通过（rankhandler mock，JSONP 解析）
- [ ] **AC15** `pytest tests/test_market_rank_refresh.py` 通过（upsert 不破坏 fund_performance）
- [ ] **AC16** `pytest tests/test_discovery_filter_service.py` 全部通过（discovery SQL LEFT JOIN market_fund_rank 后字段来源正确）
- [ ] **AC17** `pytest backend/fund-select/tests/ --ignore=test_benchmark_fetcher.py` 全部通过（无 regression）

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| 东方财富 rankhandler 反爬限流 | 单页 0.5s 延时；总请求 100 页 ≈ 50s；失败重试 3 次后跳过 |
| 字段位置变化（datas 数组下标） | 用 named 字段提取（先 split + named index），并加 unit test 锁定位置 |
| MarketFundRank 与 FundPerformance 字段名冲突 | DTO 字段名按 market_fund_rank 命名（ret_1y/3y），前端无感知 |
| 老 60 只 yaml 基金在 market_fund_rank 也有记录 | 数据冗余但无害；DTO 优先用 market_fund_rank（最新数据） |
| scheduler 跑 3 个 cron（market_universe / market_rank / yaml_refresh）冲突 | 06:30 全市场名单 → 06:35 业绩 → 07:05 yaml refresh（顺序分明） |

## Notes

- 不重写现有 `fund_basic_fetcher / fund_performance / etc.`——老路径完全不动
- MarketFundRank 是只读派生数据（每日重新覆盖），不需要保留历史快照
- 实现顺序建议：R1 schema → R2 fetcher → R3 refresh service → R5 screen SQL → R4 API + scheduler → R7 前端 API → R8 前端 UI → R6 stats
