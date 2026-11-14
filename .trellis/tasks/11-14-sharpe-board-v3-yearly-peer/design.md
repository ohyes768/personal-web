# 技术设计：夏普榜单 v3 年度同类排名 + 历史回溯

## 1. 边界

| 层 | 文件 | 改动 |
|---|---|---|
| 谓词 | `services/filter_service.py` | 加 `min_yearly_top_pct` / `min_yearly_years` |
| 冻结 | `services/sharpe_capture.py` | 新增 `freeze_yearly_peer_rows`（替代滚动版） |
| profile | `services/sharpe_board_service.py` | 新增 `(source, v3)`；默认切 v3 |
| 发布 | `services/sharpe_board_service.py` | 谓词输入合并年度达标信息 |
| 接线 | `tasks.py` / `market_full_pipeline.py` | 调新冻结函数 |
| 聚合 | `services/sharpe_board_service.py` | 展示字段改年度口径 |
| DTO | `api/models.py` | `peer_*` 字段语义调整 |
| 前端 | `lib/sharpe-board.ts` + 表格 | 列展示与文案 |
| 回溯 | `scripts/backfill_v3_yearly_peer.py`（新） | 复用 ext 脚本骨架 |

### 不变量

1. v1 / v2 profile 字典**一字不改**（历史周行 profile_json 是冻结快照）。
2. v2 已有的 2 周数据**保留不改写**（版本隔离）。
3. 谓词仍只有一份实现，实时与冻结共用。
4. 回溯脚本默认 dry-run，写库前备份。
5. 冻结数据必含「当年可复现的证据」，发布不回读被覆盖的共享表。

---

## 2. 年度窗口计算（核心纯函数）

```python
MIN_YEARLY_TOP_PCT = 25.0   # 前 25%
MIN_YEARLY_YEARS = 2        # 3 年中至少 2 年
YEARLY_WINDOW = 3           # 完整年度数

def yearly_window(ref_year: int) -> list[str]:
    """最近 YEARLY_WINDOW 个「已完成」年度。

    今年未结束 → 从 ref_year-1 往前数。
    ref_year=2026 → ["2023", "2024", "2025"]
    ref_year=2027 → ["2024", "2025", "2026"]
    """
    return [str(y) for y in range(ref_year - YEARLY_WINDOW, ref_year)]
```

**为什么排除当年**：2026 年只过了 10 个多月，年度排名是「今年以来」的
不完整排名，直接用会与完整年度不可比。用户明确要求「除开今年往前三年」。

`ref_year` 可注入（测试用），默认 `date.today().year`。

---

## 3. 冻结：`freeze_yearly_peer_rows`

```python
def freeze_yearly_peer_rows(
    db: Session, codes: list[str], *, ref_year: int | None = None,
) -> dict[str, dict]:
    """批量冻结最近 3 个完整年度的同类排名分位与达标与否。

    返回 {code: {
        "years": {"2023": 8.2, "2024": 12.5, "2025": None},  # 分位或 None
        "qualified_years": 2,          # 达标年数（分位 ≤ 阈值）
        "yearly_top_pct": 25.0,        # 本轮阈值快照
        "qualified": True,             # qualified_years >= 达标年数门槛
        "window": ["2023","2024","2025"],
    }}
    """
```

- 一次批量 `in_` 查询（500 分块），按 `(code, period)` 聚合。
- **不做陈旧判断**：年度排名是历史事实，`PEER_STALE_DAYS` 对本口径无效。
- 缺失年份保留 `None`（展示用），不计入达标年数。
- 谓词只需 `qualified` 布尔 + `qualified_years`（诊断用）。

**关键**：`qualified` 在冻结时算好（用本轮阈值快照），而不是在谓词里算。
理由：谓词是纯函数、只做数值比较；阈值随 profile 版本可能变，
冻结时把「当时用什么阈值、算出了什么」一并存下来，符合证据冻结原则。

---

## 4. 谓词扩展

```python
def entry_predicate(
    ..., min_yearly_top_pct=None, min_yearly_years=None,
): ...
```

- 新参数默认 `None` → 不判断（v1/v2 行为不变）。
- 判定：`qualified_years >= min_yearly_years`（含等号）。
- `qualified_years` 为 None（无任何年度数据）→ 不命中。

**为什么不复用 `max_peer_pct`**：滚动口径是「单个分位 ≤ X」，
年度口径是「N 年中 M 年达标」，两者语义不同，混用会让同一个参数名
在不同版本表示不同含义——排查问题时极易出错。

---

## 5. 展示字段（前端语义变更）

v2 的 `peer_pct` 是单值（近3年滚动分位）。v3 改为年度集合：

```python
# DTO 变更
peer_years: Optional[dict[str, Optional[float]]] = None  # {"2023": 8.2, ...}
peer_qualified_years: Optional[int] = None               # 达标年数
peer_window: Optional[list[str]] = None                  # ["2023","2024","2025"]
peer_pct: Optional[float] = None   # 保留：最近一个完整年度的分位（向后兼容）
```

前端「同类分位」列渲染：`2/3 年` + hover 显示各年分位明细。

---

## 6. 历史回溯

### 复用现有脚本

`scripts/backfill_sharpe_board_ext.py` 已实现：
- 按周取「当周往前 3 年」净值窗口算夏普（`compute_risk_metrics`）
- 现场合成扩展 TRI（不写库，避免与周六刷新竞争）
- 净值/基准 pickle 缓存
- 复用 `entry_predicate` + `publish_week_board`（冻结语义）

**v3 回溯 = 该脚本换 profile 版本 + 换门参数**。

### 新脚本 `scripts/backfill_v3_yearly_peer.py`

基于 ext 脚本，差异：

| 项 | ext 脚本 | v3 脚本 |
|---|---|---|
| PROFILE_VERSION | v1 | v3 |
| 谓词参数 | 五条件 | 五条件 + 年度门槛 |
| peer 数据 | 无 | `freeze_yearly_peer_rows`（年度排名，全周共享一份） |
| 周范围 | 2025-01-06 ~ 2026-08-31 | 2025-01-06 ~ 最新完整周 |
| 幂等 | complete 周跳过 | 同样跳过（v3 是全新版本，首跑全补） |

**年度排名全周共享**：它是历史固定值，不随周变化，拉一次即可
（与 ext 脚本「净值按周算、基准拉一次」的区别）。

### 夏普与 IR 的时间真实性

每周用**当周往前 3 年**的净值窗口算，这是 ext 脚本已实现的逻辑
（`compute_risk_metrics` + 周截止日切片）。不能用今天的值冒充历史——
那正是我们在 v2 里拒绝的「前视偏差」。

**注意**：年度排名是历史事实，用它做每周判定不构成前视偏差；
但夏普/IR 必须按周算。

### 代价

- 需拉取 universe（约 500 只）的**全量净值历史** + 合成 TRI
- ext 脚本注释里提过：561 只 TRI 合成 + 净值拉取，耗时可能数十分钟
- 提供 pickle 缓存，dry-run 与正式跑共享一次网络请求

---

## 7. 版本与默认切换

```
week 任务：BOARD_PROFILE_VERSION = "v3"
API 默认：profile_version = "v3"
聚合默认：aggregate_board(profile_version="v3")
```

v2 的 2 周数据保留，`?profile_version=v2` 仍可查（对照用）。

---

## 8. 兼容性与回滚

| 场景 | 处置 |
|---|---|
| 回滚到 v2 口径 | 改 `BOARD_PROFILE_VERSION="v2"` 一行 |
| 回溯结果不对 | `DELETE FROM sharpe_board_* WHERE profile_version='v3'` 重跑 |
| v2 数据 | 完全不碰 |
| 年度排名接口变更 | 冻结时存原始 `peer_rank` 字符串，可追溯 |

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 回溯耗时长（数百只基金拉净值） | 运维等待 | pickle 缓存；分批跑；先 dry-run 看范围 |
| akshare 限流 | 部分基金拉取失败 | 重试 + 失败按「无数据不达标」处理；记录到诊断 |
| 年度排名缺失（新基金无 2023 数据） | 不入选 | 符合预期（成立不满 3 年本就该被其他门挡住） |
| 回溯写入大量行（45 周 × 数十只） | 库体积 | 约几千行，可接受 |
| ext 脚本的 TRI 合成依赖库内 `fund_benchmark` | 覆盖不全的基金 IR 缺失 | 该 code 走无基准路径（ext 脚本已有此逻辑） |

---

## 10. Tests Required

- `yearly_window`：2026→2023-2025；2027→2024-2026；边界年份
- `freeze_yearly_peer_rows`：三年齐全/缺年/格式异常/批量分块/阈值边界
- `entry_predicate`：新参数默认 None 不改变 v1/v2 行为；`qualified_years` 边界
- profile：v3 存在、v1/v2 未污染、默认切换
- 回溯脚本：幂等、周键周一、v2 数据不受影响
- 前端：列渲染年度口径、默认版本 v3
