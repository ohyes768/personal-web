# 技术设计：夏普榜单 v2 入选规则与稳定性统计

## 1. 边界与不变量

### 改动范围

| 层 | 文件 | 改动性质 |
|---|---|---|
| 规则定义 | `src/services/sharpe_board_service.py` | 新增 v2 profile 常量 + 版本 |
| 谓词 | `src/services/filter_service.py` | `entry_predicate` 加三个可选参数 |
| 冻结 | `src/services/sharpe_capture.py` | `BASE_ROW_FIELDS` 加 `mgr_experience_years_max`；新增 peer 数据冻结 |
| 发布 | `src/services/sharpe_board_service.py` | 发布前批量预取 peer 数据、诊断分类 |
| 聚合 | `src/services/sharpe_board_service.py` | 新增 `near_12w_qualified` / peer 分位统计 |
| DTO | `src/api/models.py` | `SharpeBoardItemDTO` 加两字段 |
| API | `src/api/sharpe_board.py` | 默认 `profile_version=v2` |
| 前端 | `src/lib/sharpe-board.ts` + 页面 | 两列 + 版本提示 |
| 迁移 | `scripts/`（新） | 导出存档 + 删除 v1 |
| 接线 | `src/scheduler/weekly_refresh.py` | `BOARD_PROFILE_VERSION = "v2"` |

### 不变量（违反即回归）

1. **v1 profile 字典内容零变更**——只许新增 `(source, "v2")` 条目，不许改 v1 的值。
2. **v1 历史行整行删除，不做字段改写**——存档是纯读，删除是 `DELETE`，绝不 `UPDATE`。
3. **实时筛选与 capture 谓词共用同一份 `entry_predicate`**——禁止在发布侧另写一套判断。
4. **`min_sharpe`（记录）与 `min_latest_sharpe`（展示）永不合并**。
5. **不 JOIN 实时 `Fund` 表做聚合**（清盘/改名基金历史必须存活）——peer 分位是唯一例外，
   且必须在发布时预取冻结进 evidence，不在聚合时实时 JOIN。
6. **旧路径零行为变更**：`capture=None` 的调用链逐字节不受影响。

---

## 2. 三道门槛的数据流

```
┌─ 采集阶段（周任务）─────────────────────────────────────┐
│  stock 链路            discovery-stock 链路             │
│    ↓                        ↓                           │
│  refresh_fund_risks     market_full_pipeline L4         │
│    ↓ sharpe/ir/sample_days                              │
│  capture.risk_rows[code] = {sharpe, ir, sample_days,...}│
│                                                          │
│  freeze_base_rows → base_rows（+ mgr_experience_years_max）│
│  freeze_dd_rows   → base_rows["dd_3y"]                   │
│  【新增】freeze_peer_rows → peer_rows[code] = {pct, as_of}│
└──────────────────────────────────────────────────────────┘
                     ↓ 发布
┌─ 发布阶段（publish_week_board）──────────────────────────┐
│  predicate_input = base_rows[code]                       │
│                  | risk_rows[code]      (sharpe/ir/sample)│
│                  | peer_rows[code]      (peer_pct)       │
│  entry_predicate(**filters)(predicate_input)             │
│    ↓ 通过 → 写 observation（evidence_json 存全部输入）    │
└──────────────────────────────────────────────────────────┘
```

### 关键点：peer 数据必须冻结，不能聚合时实时查

原因（与 `dd_3y` 同一个坑）：`fund_achievement_rank` 会被市场链路 L5 阶段覆盖重写。
若发布时回读该表，拿到的可能是**下一轮**的数据，而非本轮入选时的证据。

**实现**：发布时一次批量查询（≤ batch 500 codes），构造 `peer_rows` 冻结字典：

```python
def freeze_peer_rows(db: Session, codes: list[str], *, as_of: date) -> dict[str, dict]:
    """批量冻结近3年同类排名分位（发布侧唯一 peer 数据来源）。

    返回 {code: {"peer_pct": 14.2, "peer_raw": "278/1951", "as_of": date}}；
    无记录/格式异常/超过陈旧容忍 → 该 code 不入字典（= 无数据，不命中）。
    """
```

不要写成 per-code 查询（420 只 × 单查 = 发布拖慢数秒）。

---

## 3. 谓词扩展（向后兼容）

```python
def entry_predicate(
    *, min_age=None, min_size_yi=None, max_dd_3y=None, min_mgr_exp=None,
    min_sharpe=None, exclude_qdii=False,
    min_ir=None,            # 新增：IR ≥ X，NULL 不命中
    min_sample_days=None,   # 新增：样本交易日数 ≥ X，NULL 不命中
    max_peer_pct=None,      # 新增：同类分位 ≤ X%（即前 X%），无数据不命中
): ...
```

**向后兼容铁律**：三个新参数默认 `None` = 不参与判断。v1 profile 的 filters 不含这三个键，
`entry_predicate(**v1_filters)` 的行为必须与改动前逐字节一致（由现有测试锁定）。

**分位比较语义**：
- `peer_pct = rank / total * 100`
- 命中条件：`peer_pct <= max_peer_pct`（含等号，与现有 `>=`/`<=` 惯例一致）
- 前 20% ↔ `max_peer_pct = 20.0`
- `rank > total` 或 `total <= 0` 或 `rank <= 0` → 格式异常 → 不命中
- `as_of_date` 距今 > 90 天 → 不命中（陈旧容忍，常量 `PEER_STALE_DAYS = 90`）

**90 天为什么不放在谓词里**：谓词是纯函数、不该依赖 `date.today()`（否则测试不可重现）。
陈旧过滤放在 `freeze_peer_rows` 的取值阶段完成——冻结时就把陈旧记录丢掉，
谓词只做纯数值比较。这是本设计对「谓词等价性测试」的关键让步。

---

## 4. profile 定义

```python
ALGORITHM_VERSION_V2 = "risk-3y-v2"   # 口径变更必须升版本（沿用既有惯例）

# v1 保持原样，一字不改
SHARPE_BOARD_PROFILES = {
    ("stock", "v1"): {...},
    ("discovery-stock", "v1"): {...},
    # 新增
    ("stock", "v2"): {
        "source": "stock", "version": "v2",
        "filters": {**_v1_filters(), "min_ir": 0.5, "min_sample_days": 700, "max_peer_pct": 20.0},
        "collection_prefilters": {},
        "market_subtypes": None,
        "algorithm_version": ALGORITHM_VERSION_V2,
    },
    ("discovery-stock", "v2"): {..., "collection_prefilters": dict(_MARKET_PREFILTERS), ...},
}
```

`_v1_filters()` 返回 v1 五个条件的深拷贝，保证 v2 是「v1 + 三道门」而非另起一套。

---

## 5. 稳定性统计与 52 周窗口（展示层）

### 5.0 52 周窗口（本设计的核心口径变更）

用户要求「榜单只展示最近 52 周，刚好一年」。窗口同时作用于**统计**与**图表**。

```python
WINDOW_WEEKS = 52

def _window_start(current: date) -> date:
    """当前周周一往前数 51 个周一（含当前周共 52 周）。"""
    return current - timedelta(weeks=WINDOW_WEEKS - 1)
```

**为什么 52 周比现有的 365 天好**：364 = 52×7，恰好是 7 的整数倍，
起点必然落在周一网格上。现有 `_RANGE_DAYS["1y"] = 365` 会产生「365 = 52 周 + 1 天」
→ 起点落到周日 → 周历整体脱离周一观测键 → series 全 null。契约 §13 记录的那个
真实回归（2026-11-05 实锤）就是它。改用 52 周后，对齐修正代码可以保留但不再触发，
属于**顺手治好的既有缺陷**。

**实现要点**：

1. `listed_weeks` / `consecutive_weeks` 改为**窗口内**计算：
   ```python
   window_start = _window_start(_current_week())
   eps_in_window = [(w, o) for w, o in eps if w >= window_start]
   listed_weeks = len(eps_in_window)
   ```
2. 窗口外无观测的基金 `listed_weeks == 0` → 被 `min_weeks=1` 默认筛掉
   （PRD R5 已声明这是符合预期的连带后果）。
3. 图表 `weeks` 恒为窗口内周一序列（历史不足则从首周起）。
4. **不删除任何观测行**：窗口只作用于聚合，原始数据完整保留。

### 5.1 与现有 `range` 参数的关系（必须处理）

现有 API 有 `range=3m|6m|1y|all`，其中 `all` 表示"从首次观测周到现在"。
引入 52 周窗口后：
- `all` 的语义变为"最近 52 周"？还是保持"全历史"？
- 两者会造成用户困惑。

**决策**：`range` 参数保留，但**语义收窄为窗口内的缩放**：
- `all`（默认）→ 52 周全窗口（不再是从首次观测起）
- `1y` → 与 `all` 等价（52 周 ≈ 1 年），保留为兼容别名
- `6m` / `3m` → 52 周窗口内的尾部 26 / 13 周
- 周历起点仍受 52 周窗口上限约束（`max(window_start, range_start)`）

这样 `range` 不会让用户看到超出 52 周的数据，语义一致。

**兼容性**：`range=1y` 原先返回约 52 周（365 天裁到周一），改后返回 52 周整——
数值差异最多 1 周，可视作修正而非破坏。已有测试断言「range=1y 周历终点==当前周且全周一网格」，
改后仍满足且更强（起点也精确落在网格上）。

### 5.2 近12周达标周数

在窗口内聚合的基础上，取尾部 12 个：

```python
recent = eps_in_window[-12:]          # 注意：用窗口内切片，不是全历史
qualified = sum(1 for _, o in recent if o.sharpe >= QUALIFIED_SHARPE)  # 0.8
stats[code]["near_12w"] = {"qualified": qualified, "total": len(recent)}
```

- **不足12周按实际计**：新基金只有 6 周 → `4/6`，不补零不冒充。
- **无历史 → null**，不是 `0/0`（0 表示"有历史但全不达标"，语义不同）。
- 常量 `QUALIFIED_SHARPE = 0.8` 与 v1 门槛对齐；即使 v2 调整 `min_sharpe`，
  「达标」语义仍是 0.8（展示用绝对参考线，与入选规则解耦）。

### 5.3 同类分位展示

从最新一条**窗口内**观测的 `evidence_json["peer"]` 读取（发布时已冻结），不在聚合时查表。
若最新观测在窗口外，则用窗口内最后一条；窗口内无观测 → null。

---

## 6. DTO 变更（三处同步）

后端 `src/api/models.py` 的 `SharpeBoardItemDTO` 新增：

```python
near_12w_qualified: Optional[int] = None   # 近12周达标周数
near_12w_total: Optional[int] = None       # 近12周总周数（分母，不足12时为实际数）
peer_pct: Optional[float] = None           # 同类排名分位（%，如 14.2）
peer_as_of: Optional[date] = None          # 同类排名数据日期
```

**⚠ 陷阱**（契约 §3a）：Pydantic `response_model` 会静默丢弃未声明字段。
三处必须同步：`src/api/models.py` ↔ `apps/fund-select/src/lib/sharpe-board.ts` ↔ 页面消费。

---

## 7. v1 历史处置：导出 → 验证 → 删除

### 脚本：`backend/fund-select/scripts/migrate_v1_archive.py`

```
阶段1 导出
  - 读 sharpe_board_weeks WHERE profile_version='v1'（含所有 status）
  - 读关联的全部 observations
  - 写 data/archive/sharpe_board_v1_<timestamp>.json（完整可恢复）
  - 写 data/archive/sharpe_board_v1_<timestamp>.sql（INSERT 语句，可 sqlite3 < 重放）
  - 写 manifest.json：{weeks: N, observations: M, sha256_payload, exported_at}
阶段2 验证（不做破坏性操作）
  - 重新读存档，比对行数与 sha256
  - 在临时 SQLite 库里重放 SQL，比对行数
阶段3 删除（需显式 --apply 才执行）
  - DELETE FROM sharpe_board_observations WHERE week_id IN (v1 weeks)
  - DELETE FROM sharpe_board_weeks WHERE profile_version='v1'
  - 单事务，失败整体回滚
```

**默认 dry-run**：不带 `--apply` 只做阶段 1+2，打印将要删除的行数。防止误删。

### 目录策略

`data/archive/` 不入 git（在 `.gitignore` 加一行）；存档文件命名带时间戳，多次执行不覆盖。

---

## 8. 历史不回溯的论证（写进代码注释，防后人重提）

PRD R4 已列数据证据。设计层的结论：

- 若强行回填，必须伪造 peer 的历史值 → 前视偏差（look-ahead bias），
  统计出来的"在榜周数"会系统性偏乐观（今天的赢家被投影到过去）。
- 部分回填（夏普/IR 补、peer 不补）会造成**混合口径**：同一份榜单里，
  老周的入选只用了两道门、新周用了三道门，`listed_weeks` 失去可比性。
- 因此 v2 从上线周开始干净积累。代价是初期榜单薄（需数周才会显示有意义的在榜周数），
  这是**诚实的数据**换取的成本，必须接受。

**唯一例外**：走势页（另一任务）的滚动夏普曲线是独立的实时计算，不受此限制——
它本来就不依赖榜单历史。

---

## 9. 兼容性与回滚

| 关注点 | 处置 |
|---|---|
| v1 数据被删后能否恢复 | 存档 JSON/SQL 可完整重建（AC6 验证） |
| 回滚到 v1 规则 | 改 `BOARD_PROFILE_VERSION = "v1"` 一行 + 前端默认版本；无需改代码逻辑 |
| 三道门导致空榜 | 实测 97→43 不会空榜；若未来市场极端导致空榜，`complete` 空榜是合法状态（契约 §4） |
| 前端旧版本缓存 | 前端本地无需迁移，`profile_version` 是 URL 参数 |
| 已有测试 | v1 相关测试全部保留（v1 profile 未被改）；新增测试只覆盖 v2 与 display 统计 |

### 部署顺序

1. 后端代码上线（v2 profile + 谓词 + 冻结 + 聚合），**此时 `BOARD_PROFILE_VERSION` 仍为 v1**
2. 跑迁移脚本 dry-run → 人工确认 → `--apply` 删除 v1
3. 切 `BOARD_PROFILE_VERSION = "v2"`，重启后端
4. 前端上线（默认 v2 + 两列）
5. 触发一次手动周刷新，验证 v2 榜首次发布

第 1 步与第 3 步分开，是为了让迁移脚本能在 v1 仍在发布的稳定状态下运行（否则可能
边删边写）。实际可合并部署，但脚本执行必须在切换前。

---

## 10. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 三道门叠加后长期榜单过薄 | 用户觉得"没东西看" | 实测 43 只；若实际低于 20 只，调 `min_ir` 到 0.3 或 `max_peer_pct` 到 30（改配置不改代码） |
| peer 数据陈旧（42 只超 30 天） | 这些基金被排除，可能误伤 | 90 天容忍期；且 L5 每周重拉会自然更新 |
| `fund_achievement_rank` 被 L5 全量 delete+insert | 发布时读到下一轮数据 | **冻结进 peer_rows**，发布只读冻结 |
| stock 链路 achievement 在 snapshot 内写入 | 冻结时机不对会读到旧值 | 主循环后批量冻结（已查实 `snapshot_fund(fetch_ranking=True)` 会写）；见 §11 |
| 52 周窗口让老基金"资历"归零 | 用户以为榜单出 bug（明明在榜过却显示 0 周） | 页面标注「近 52 周」口径；PRD R5 已声明此连带后果 |
| `range` 语义收窄（all 不再是全历史） | 依赖旧语义的调用方看到更少数据 | 已知唯一调用方是本页；`1y` 保留为等价别名；契约 §17 写明变更 |
| capture 加字段改变 evidence_json 内容 | 已有测试断言 evidence 结构会挂 | 测试改为断言「包含」关键字段，非全等 |

---

## 11. peer 冻结的调用位置（已查实，两条链路不同）

两条链路**都会**更新 `fund_achievement_rank`，但写入时机完全不同，
`freeze_peer_rows` 的调用点必须分别放置。

### stock（雪球三分法）—— 已确认会更新

`refresh_stock_funds_sync` 主循环内调
`snapshot_fund(fetch_ranking=True)` → `persist_snapshot`
→ `_replace_achievement`（delete+insert，`refresh_service.py:162`）
→ `db.commit()` → `freeze_base_row`。

**调用点**：主循环**之后**统一批量冻结（此时全部 code 的 achievement 已落库）。
与 `freeze_dd_rows` 同一位置。

### discovery-stock（股基·市场）—— 阶段靠后

`market_full_pipeline` 阶段顺序：L2 size → `freeze_base_rows` → L3 nav →
`freeze_dd_rows` → L4 risk → **L5 achievement**。

**调用点**：必须在 **L5 之后**。若放在 L3 后（与 `freeze_dd_rows` 同处），
L5 还没跑，读到的是上一轮陈旧排名，冻结的就是过期证据。

### 实现约束

```python
# market_full_pipeline.py —— L5 完成后追加
if capture is not None:
    capture.peer_rows = freeze_peer_rows(db, codes)

# tasks.py (stock) —— 主循环后、benchmark_refresh 之前
if capture is not None:
    freeze_dd_rows(db, capture.base_rows)
    capture.peer_rows = freeze_peer_rows(db, codes)
```

### 附带发现：as_of_date 不是「今天」

`refresh_service.py:115` 用 `out["achievement_as_of_date"] = ref.date()`
（`ref` 是取数参考日），不是 `date.today()`。这解释了生产库里 6 个不同
as_of 取值的来源。**90 天陈旧判定必须以数据自带的 `as_of_date` 为准**，
不能用发布日减写入时间——否则数据刚写入却被判陈旧，或早已陈旧却看着很新。
