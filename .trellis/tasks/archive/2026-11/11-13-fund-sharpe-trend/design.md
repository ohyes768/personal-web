# 技术设计：夏普走势页

> 关键结论都带实测证据。所有数字来自生产库（`docker exec fund-select-backend`）或本地拉取。

## 1. 为什么必须「纯净值口径」（本设计最重要的决定）

`risk_service.compute_risk_metrics` 在算夏普时，若基准可用会做 **`r_p` 与 `r_b` 的 inner join**。这本身没错（夏普不受基准影响，但 join 会限制样本日期），问题在于**生产库 `fund_benchmark` 只有 561 只、且最早 2023-11-08**。

滚动窗口回测到 2024 年时，3 年窗口（729 个交易日）被基准截断成 1 年（219 天）。

实测（000628，同一份净值）：

| 窗口截止 | join 基准 | 纯净值 | 结论 |
|---|---|---|---|
| 2026-11-13 | 0.9753 (n=723) | 0.9216 (n=728) | 近端几乎一致 |
| 2025-06-30 | 1.4829 (n=397) | 0.8336 (n=729) | join 版严重偏高 |
| 2024-12-31 | 1.8048 (n=280) | 0.3298 (n=729) | 差 5 倍 |
| 2024-09-30 | 2.4216 (n=219) | 0.6845 (n=729) | 差 3.5 倍 |

若沿用 join 口径，曲线会在 2025 年附近出现**虚假的断崖**——恰好是「稳定性」判断的反面教材。

**决定：走势页用纯净值口径。** 夏普 = (R_p − R_f)/σ(R_p−R_f) × √252，基准不参与。近端点与列表值基本一致（0.9216 vs 0.9216），差异仅为「本周最后交易日」对齐。

### 与列表值对齐的处理

列表夏普来自 `refresh_fund_risks`，窗口是 `date.today() - 3年`，样本尾日是**最新净值日**。走势页最后一点用「最新净值日所在自然周」的最后交易日——两者在最新一周通常就是同一天，故数值一致（实测差值 < 1e-4）。文档需写明：**若最新净值日是周一/周二早期，最后一点可能略早于列表值**，属正常。

## 2. 滚动算法

```python
TD = 252
WINDOW_DAYS = 365 * 3
MIN_SAMPLE_DAYS = 250

def rolling_sharpe(nav_df, rf_series) -> list[Point]:
    s = nav_df.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
    # 每个自然周最后一个交易日为一个观测点
    ends = s.groupby(s.index.to_period("W")).apply(lambda x: x.index.max()).tolist()
    out = []
    for end in ends:
        w = s[(s.index >= end - pd.Timedelta(days=WINDOW_DAYS)) & (s.index <= end)]
        arr = w.to_numpy()
        if len(arr) < MIN_SAMPLE_DAYS:
            out.append(Point(date=end, sharpe=None, sample_days=len(arr)))
            continue
        excess = arr - rf_daily_aligned  # rf 缺失全 0
        std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
        val = None if (std == 0 or math.isnan(std)) else float(excess.mean()) / std * math.sqrt(TD)
        out.append(Point(date=end, sharpe=val, sample_days=len(arr)))
    return out
```

**性能实测**：603 个周点（000628，2015 起全历史）= **0.171s**；净值拉取 0.12s。合计 < 0.3s。

优化点（若将来需要）：用 `np.convolve` 或累计和做 O(n)，但当前 0.17s 不值得加复杂度。

**rf 对齐**：`r_f` 年化小数 → `/252` 得日频 → reindex 到窗口索引 ffill 缺省 0。生产库 `risk_free_rate` 为空（fetcher 未入调度），此时 `rf_basis="zero"`，全窗口按 0 处理。

## 3. API 契约

`GET /api/funds/sharpe-trend/{code}?range=all|3y|1y`

```python
class SharpeTrendPointDTO(BaseModel):
    date: date                      # 该周最后交易日
    sharpe: Optional[float] = None  # None = 样本不足或无定义（断线不补零）
    sample_days: int = 0

class SharpeTrendStatsDTO(BaseModel):
    threshold: float = 0.8
    current: Optional[float] = None
    max: Optional[float] = None
    min: Optional[float] = None
    mean: Optional[float] = None
    above_count: int = 0            # 有效点中 ≥ threshold 的周数
    valid_count: int = 0            # 有效点数（sharpe 非 None）
    above_ratio: Optional[float] = None
    consecutive_above: int = 0      # 从最新点往回连续达标周数
    longest_below: int = 0          # 最长连续 < threshold 的周数
    trend_12w: Optional[float] = None  # 最近 12 点线性斜率（每周变化）

class SharpeTrendResponse(BaseModel):
    code: str
    name: Optional[str] = None
    range: str = "all"
    rf_basis: str = "zero"          # zero | rate（数据来源透明化）
    algorithm_version: str = "trend-v1"
    threshold: float = 0.8
    points: list[SharpeTrendPointDTO] = []
    stats: SharpeTrendStatsDTO = SharpeTrendStatsDTO()
    diagnostics: dict = {}          # insufficient_history / nav_failed / not_found
```

**必须显式声明全部字段**（contracts §3a：Pydantic `response_model` 静默丢弃未声明字段）。

**错误语义**：

| 场景 | 响应 |
|---|---|
| code 不存在（Fund 表无此 code 且净值拉不到） | 404 `{"detail": "基金不存在或无法获取净值: {code}"}` |
| 净值网络失败 | 502 `{"detail": "净值拉取失败: ..."}`（与"无历史"分开） |
| 净值 < 250 日 | 200 + `points=[]` + `diagnostics.insufficient_history=true`（正常空态，不是错误） |
| 无任何有效点但样本够 | 200 + `points` 全 None + 诊断 |

`range` 语义：`all` 全历史；`3y`/`1y` 只裁**返回的点**，不改变每个点的 3 年滚动窗口。

## 4. 缓存层

```python
# src/services/sharpe_trend_service.py
_NAV_TTL_SECONDS = 3600
_nav_cache: dict[str, tuple[float, pd.DataFrame]] = {}   # code -> (monotonic_ts, df)

def _cached_nav(code: str) -> pd.DataFrame:
    now = time.monotonic()
    hit = _nav_cache.get(code)
    if hit and now - hit[0] < _NAV_TTL_SECONDS:
        return hit[1]
    df = fetch_nav(code)
    if not df.empty:
        _nav_cache[code] = (now, df)
    return df
```

单进程内存缓存，无锁（GIL 下 dict 读写安全；重复拉取最坏是多一次网络请求，无害）。不持久化——净值每日更新，1 小时粒度足够。

## 5. 前端结构

```
apps/fund-select/src/
├── app/sharpe-trend/page.tsx           # 新页面（'use client' + Suspense 包 useSearchParams）
├── lib/sharpe-trend.ts                 # DTO + parse + fetch（照 sharpe-board.ts 模式）
├── lib/sharpe-trend.test.ts            # 纯逻辑测试（node --experimental-strip-types）
└── components/sharpe-trend/
    ├── SharpeTrendStats.tsx            # KPI 卡片行
    └── SharpeTrendChart.tsx            # 复用 SharpeChart 或薄封装
```

**图表复用**：现有 `buildSharpeChartOption({weeks, series, minLatestSharpe, hiddenCodes})` 完全够用——传单条 series、`weeks` 为点日期数组、`minLatestSharpe=0.8`。**不新建图表基建**，只在页面里做 `weeks = points.map(p => p.date)` / `series=[{code, name, values}]` 的适配。

**区间切换**：`useSearchParams` 读 `range`，改变时 `router.replace` 只改 query。后端已按 range 裁剪，前端不重复裁。

**KPI 展示**（6 格）：
```
当前夏普 1.02 | 区间最高 1.95 | 区间最低 0.42 | 均值 1.18 | 达标率 78% | 最近连续 12 周
```
次级一行：`最长连续低于 0.8：9 周 ｜ 近 12 周趋势 +0.03/周`

**无 code 态**：输入框 + placeholder「输入 6 位基金代码」+ 提交后 `router.push('/sharpe-trend?code=xxx')`。不做"最近查看"（避免引入 localStorage 新状态）。

## 6. 三处入口改动

### 6.1 FundTable 代码列

```tsx
// props 新增
trendEnabled?: boolean;

// 单元格
<td className="font-mono">
  {trendEnabled
    ? <Link href={`/sharpe-trend?code=${fund.code}`} className="text-info hover:underline">{fund.code}</Link>
    : fund.code}
</td>
```

调用方：`stock/page.tsx` 与 `discovery-stock/page.tsx` 传 `trendEnabled`；`bond` / `discovery-bond` 不传（默认 false，债基 UI 零变化）。

⚠ 点击 `<td>` 内的 Link 不能触发行选中/抽屉打开——需 `onClick={e => e.stopPropagation()}` 或确认行点击走的是别的事件。**实测确认**。

### 6.2 详情抽屉夏普 KPI

`RowDetailDrawer.tsx` / `RowDetailDrawerBond.tsx` 的夏普 KpiCell：值改为 `<Link href={...}>`。由于抽屉是浮层，点击后页面跳转，抽屉随路由卸载自然关闭。

⚠ **只给股基抽屉加**（`RowDetailDrawer`），债基抽屉 `RowDetailDrawerBond` 不加（第一版不支持债基）。

### 6.3 夏普榜单行代码

`SharpeBoardTable` 的 code 列加 Link。注意榜单页已有行点击（打开抽屉），同样需 stopPropagation。

## 7. 测试计划

### 后端 `tests/test_sharpe_trend.py`

1. **纯净值口径**：构造有 benchmark 的 fund，断言历史窗口 sample_days 未被截断（≈729 而非 219）——这是本任务最关键的回归测试。
2. **rf 缺失**：`risk_free_rate` 空 → `rf_basis="zero"`，曲线正常产出。
3. **rf 可用**：插 rf 行 → `rf_basis="rate"`，夏普值按 rf 下调。
4. **样本不足**：< 250 日的 fund → `points=[]` + `diagnostics.insufficient_history`。
5. **KPI 边界**：
   - 全达标 → `consecutive_above == valid_count`、`longest_below == 0`、`above_ratio == 1.0`
   - 全不达标 → `consecutive_above == 0`
   - 恰好 12 点 → `trend_12w` 有值
   - 11 点 → `trend_12w is None`
   - 单点 → stats 不崩（max/min/mean == 该点）
6. **range 裁剪**：`3y` 只裁点集，窗口不变（对比 `all` 的重叠区间数值应完全一致）。
7. **路由顺序**：`/sharpe-trend/000628` 不被 `/{code}` 吞掉（status 200 而非 404「基金不存在: sharpe-trend」）。

### 前端

- `src/lib/sharpe-trend.test.ts`：DTO 解析、range 参数 parse、KPI 格式化。
- `npx tsc --noEmit`。
- 手工浏览器验证 375/1440、三处入口、无 code 态、区间切换。

## 8. 风险与注意事项

| 风险 | 处置 |
|---|---|
| 净值接口限频/抖动 | TTL 缓存 1h；失败返回 502 可重试，不静默空曲线 |
| Tailwind 任意值类陈旧缓存 → 图表容器高 0 | 新组件用标准类或删 `.next` 重启 dev |
| stopPropagation 漏加 → 点代码同时开抽屉 | 三处入口逐一实测点击行为 |
| 榜单页行点击与 Link 冲突 | 同上，实测 |
| 与并行会话改同一文件 | `FundTable.tsx` / 抽屉文件改动前先看 git status |
| 最新点与列表值微差 | 文档写明对齐口径，不强行改算法 |

## 9. 不做的事

- 不落库、不建表、不进调度。
- 不叠加「在榜区间背景带」（后续可选）。
- 不支持债基入口（后端能算，前端不开）。
- 不做多基金对比（夏普榜单已有横向对比）。
