# 设计：夏普榜单数据缺口周口径修正

> 对应 PRD `prd.md`（R1–R6 / AC1–AC9）。后端契约见
> `.trellis/spec/backend/fund-select/backend/contracts.md` §13/§18/§19，前端契约见
> `.trellis/spec/frontend/fund-sharpe-board.md`。

## 1. 边界

只改**只读聚合层**（`aggregate_board`）与其 DTO/前端消费。不动发布侧
（`publish_week_board`）、不动 profile、不动库表结构、不回填历史行。

## 2. 事实来源（全部是库里已有的字段）

| 要回答的问题 | 数据来源 | 备注 |
|---|---|---|
| 这周发榜了吗？ | `sharpe_board_weeks.status` | `complete` / `failed` / `skipped_no_new_data` |
| 这只基金这周样本更新了吗？ | 同周 `diagnostics_json.stale_codes` | 发布时写入：入选谓词通过但样本尾日未前进的基金 |
| 这只基金在榜了吗？ | `sharpe_board_observations` | 现状，不变 |

`stale_codes` 的语义在发布侧是「不写新点、留空断线」的基金（`sharpe_board_service.py`
发布流程第 6 步），本设计把它提升为**统计层的「该基金本周无有效样本」**信号。

实测（生产库 v3，窗口 2025-11-17 ~ 2026-11-09）：除 2026-02-16 外所有周
`stale_codes` 为空 → 该信号是稀疏且精确的，不会把正常周误判成缺口。

## 3. 判定模型

对窗口内每个周一 `w ∈ [window_start, current]`、每只基金 `code`：

```
gap(code, w) =
    对 scope 内每个来源 s：
        week_row(s, w) 缺失                      → 该来源缺口
        week_row(s, w).status != complete        → 该来源缺口
        code ∈ stale_codes(s, w)                → 该来源缺口
        否则                                    → 该来源可评 ⇒ 整个 gap(code, w) = False
    （全部来源都缺口 ⇒ gap = True）
```

- scope：单来源 = `[source]`；`all` = `["stock", "discovery-stock"]`。
- `listed(code, w)`：该周有该基金观测（all 时同周只算一次，stock 优先，沿用现状）。
- `miss(code, w)` = `not listed and not gap`。

三类互斥且完备。

### 3.1 为什么 `all` 用「所有来源都缺口」而不是「任一来源缺口」

`all` 的语义是两条链路的并集：只要**有一条**链路能给这只基金有效样本，它那周就是
可评的（它在别的链路没上榜只说明那条链路没选它，不是数据问题）。只有当所有链路都拿不到
有效样本时，那周才是纯数据缺口。

## 4. 统计

窗口 = `[current - 51 周, current]`（周一网格，52 周；`WINDOW_WEEKS`）。

```
gap_weeks(code)     = {w : gap(code, w)}                       # 窗口内
evaluable_weeks     = 52 - |gap_weeks(code)|                   # 可评周数
listed_weeks        = |{w : listed(code, w)}|                   # 不变
consecutive_weeks   = 从 last_listed_week 逐周 -7 天回退：
                        listed → 记 1，继续
                        gap    → 跳过（不计数、不中断）
                        miss   → 中断
```

`consecutive_weeks` 仍是「在榜周数」的连续段长度：gap 周不在榜，不计入长度，
只是不作为断点。

`miss` 断点保持旧语义（「缺席中断」），只有**数据原因**的缺席被豁免——这是本次口径
变更的全部内容。

## 5. DTO 变更（三处同步，§3a 静默砍字段陷阱）

`src/api/models.py`：

```python
class SharpeBoardItemDTO(BaseModel):
    ...
    listed_weeks: int
    evaluable_weeks: int = 0     # 可评周数（窗口内有有效样本的周数）= 分母
    consecutive_weeks: int
    gap_weeks: list[date] = []   # 该基金的数据缺口周（不计入在榜、不中断连续）
    ...

class SharpeBoardDiagnosticsDTO(BaseModel):
    no_board_weeks: list[date] = []   # 不变：这周没发榜
    gap_weeks: list[date] = []        # 新增：这周数据不可用（没发榜 或 有基金样本未更新）
```

⚠ `aggregate_board` 的 `item_keys` 元组必须同步加 `evaluable_weeks` / `gap_weeks`，
否则被过滤掉（contracts §18.8 记录过的坑）。

前端 `src/lib/sharpe-board.ts`：`SharpeBoardItem` 加同名字段；
`SharpeBoardDiagnostics` 加 `gap_weeks: string[]`。

## 6. 前端呈现

### 6.1 表格

| 列 | 旧 | 新 |
|---|---|---|
| 近52周在榜 | `51` | `51/51`（`listed_weeks/evaluable_weeks`），hover：分母口径 + 缺口周列表 |
| 最近连续周数 | `38` | `51`，hover：「跨过 N 个数据缺口周（2026-02-16 等），数据缺口不打断连续」 |

hover 用仓库已有的 `hover-tip` + `data-tip` 模式（同类分位列同款）。

### 6.2 图表

`buildSharpeChartOption` 新增入参 `gapWeeks: string[]`：

- 在第一条 series 的 `markLine.data` 追加 `{xAxis: <week>}` 竖线，标签「数据缺口周」；
- tooltip formatter：命中缺口周时，文案为「本周为数据缺口周（无榜单 / 样本未更新）」，
  取代「本周无在榜记录」。

`markLine` 已有下限参考线（`{yAxis: minLatestSharpe}`），两者共存于同一 `data` 数组。

`buildSharpeChartOption` 必须保持**零依赖纯函数**（node:test 直跑，不 import echarts/React）。

### 6.3 规则说明卡

`SharpeBoardProfileCard` 在「近 52 周窗口」说明行旁追加一行（仅当
`diagnostics.gap_weeks.length > 0`）：列出缺口周与成因分类（没发榜 / 样本未更新）。

## 7. 兼容与回滚

- 纯展示层口径修正，不改历史行 → 回滚 = revert 代码，数据无损。
- 老版本 `profile_version`（v1/v2）同样适用（聚合层不区分版本规则，只读观测）。
- 排序键仍用 `listed_weeks`（分子）——分母变化不改变排序，避免「口径一改榜单重排」。

## 8. 陷阱

1. **`item_keys` 漏加字段** → 响应里字段消失（§3a）。改 DTO 必同步。
2. **`week_meta` 必须按 (source, week) 建**——`all` 模式下同周两行，不能用 week_start 单键。
3. **`stale_codes` 可能缺失/类型异常** → 解析要容错（`diagnostics_json` 为 NULL、
   非 dict、`stale_codes` 非 list 一律当空集），不能让一条脏数据把整页打挂。
4. **`gap` 只豁免数据原因**，`missing_evidence`（nav 失败）也算数据缺口吗？
   —— **不算**：发布侧 `missing_evidence` 是采集失败（当周 failed），
   已由「该周无 complete 榜」覆盖；若当周 complete 而某基金缺证据，它只是没参评，
   视同 miss（真实缺席口径），保持保守。
5. **`near_12w` 未同步**（PRD Out of Scope）：仍是「最近 12 条观测」，
   缺口周落在最近 12 周内时口径会差 1 周；本次不改，已在 PRD 记录。
