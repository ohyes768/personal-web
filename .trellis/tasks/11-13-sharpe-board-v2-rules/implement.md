# 执行计划：夏普榜单 v2 入选规则与稳定性统计

## 前置阅读

- `.trellis/spec/backend/fund-select/backend/contracts.md` §13（夏普榜单）、§3a（DTO 三处同步）
- `.trellis/spec/frontend/fund-sharpe-board.md`（前端契约）
- 本任务 `prd.md` / `design.md` / `research/v2-gate-impact.md`

## 测试环境

```bash
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/ -q        # 597 passed 为基线
cd apps/fund-select
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit
```

---

## 阶段 0：基线确认（不改代码）

- [ ] 0.1 跑后端全量测试，记录基线通过数（预期 597）
- [ ] 0.2 跑前端 node --test + tsc，记录基线
- [ ] 0.3 确认生产库 v1 数据快照（行数、哈希），后续验证删除无副作用

**回滚点**：无改动，随时可回。

---

## 阶段 1：谓词与 profile（纯逻辑，先写测试）

### 1.1 `filter_service.entry_predicate` 扩展

- [ ] 加三个可选参数：`min_ir=None` / `min_sample_days=None` / `max_peer_pct=None`
- [ ] NULL 一律不命中（与现有 `min_sharpe` 语义一致）
- [ ] `max_peer_pct` 用 `<=`（含等号）
- [ ] docstring 补语义说明 + 「三个新参数默认 None = v1 行为逐字节不变」

**测试**（`tests/test_filter_service.py` 新增 class `TestV2EntryGates`）：
- [ ] `min_ir=0.5`：0.5 通过、0.49 不通过、None 不通过
- [ ] `min_sample_days=700`：700 通过、699 不通过、None 不通过
- [ ] `max_peer_pct=20`：20.0 通过、20.1 不通过、None 不通过
- [ ] `peer_pct` 为 None（无数据）不通过
- [ ] 三参数全 None 时，对一组 v1 用例的结果与改动前完全一致（回归锁）

### 1.2 v2 profile

- [ ] `sharpe_board_service.py` 新增 `ALGORITHM_VERSION_V2 = "risk-3y-v2"`
- [ ] 新增 `_v1_filters()` 返回 v1 五条件深拷贝
- [ ] 新增 `(stock, v2)` / `(discovery-stock, v2)` 两条 profile
- [ ] **v1 两条 profile 一字不改**

**测试**：
- [ ] `get_profile('stock','v2')['filters']` 含 `min_ir==0.5`、`min_sample_days==700`、`max_peer_pct==20.0`
- [ ] `get_profile('stock','v1')['filters']` 与硬编码的 v1 五条件全等（防污染）
- [ ] `algorithm_version` 两版本不相等

---

## 阶段 2：capture 冻结（含既有缺陷修复）

### 2.1 `BASE_ROW_FIELDS` 加字段（R6 缺陷修复）

- [ ] `sharpe_capture.BASE_ROW_FIELDS` 加 `"mgr_experience_years_max"`

**测试**：
- [ ] `freeze_base_row` 返回值含该键
- [ ] 端到端：发布后 `evidence_json["base"]["mgr_experience_years_max"]` 存在

### 2.2 `freeze_peer_rows` 新增

```python
PEER_PERIOD_KIND = "阶段业绩"
PEER_PERIOD = "近3年"
PEER_STALE_DAYS = 90

def freeze_peer_rows(db: Session, codes: list[str]) -> dict[str, dict]:
    """批量冻结近3年同类排名分位。无记录/格式异常/超90天陈旧 → 不入字典。"""
```

- [ ] 一次批量查询（`code.in_(codes)` + period 条件），**不做 per-code 查询**
- [ ] 解析 `peer_rank`（'278/1951'）→ `rank/total*100`，保留 4 位小数
- [ ] 格式异常（无 `/`、total<=0、rank<=0、rank>total）→ 丢弃
- [ ] `as_of_date` 距今 > 90 天 → 丢弃（用数据自带 as_of，不用今天）
- [ ] 返回 `{code: {"peer_pct": float, "peer_raw": str, "as_of": date.isoformat()}}`

**测试**（`tests/test_sharpe_board_capture.py`）：
- [ ] 正常解析：`278/1951` → 14.25
- [ ] 边界：`1/5` → 20.0（恰好命中前20%）；`2/6` → 33.33
- [ ] 异常：`''` / `'abc'` / `'0/100'` / `'101/100'` → 不入字典
- [ ] 陈旧：as_of = today-91 天 → 不入字典；today-89 天 → 入
- [ ] 不存在的 code → 不入字典
- [ ] **性能断言**：500 codes 的冻结不超过一次 SQL（用 SQLAlchemy event 计数或 mock 验证调用次数）

### 2.3 接线两个调用点

- [ ] `market_full_pipeline.py`：L5 之后 `capture.peer_rows = freeze_peer_rows(db, codes)`
- [ ] `tasks.py`（stock）：主循环后、`benchmark_refresh` 之前冻结
- [ ] `SharpeRunCapture` dataclass 加 `peer_rows: dict[str, dict] = field(default_factory=dict)`

**测试**：
- [ ] stock 链路：mock 后断言 `capture.peer_rows` 非空且含预期 code
- [ ] discovery-stock 链路：断言冻结发生在 L5 之后（用调用顺序 mock）

---

## 阶段 3：发布侧接入三道门

### 3.1 `publish_week_board` 合并 peer 数据

- [ ] 谓词输入改为 `{**base, "sharpe": ...} | risk_fields | peer_fields`
- [ ] risk_fields 取 `ir` / `sample_days`
- [ ] peer_fields 取 `peer_pct`
- [ ] **诊断分类**：新增 `diagnostics["gate_missing"]`，按门槛分桶记录被"数据缺失"挡掉的 code
  （与"不达标"区分；不达标不记诊断）

**测试**：
- [ ] 三道门各自挡住一只，`gate_missing` 只记缺失那种
- [ ] 全部达标 → 正常入选，evidence_json 含 peer 数据
- [ ] 无 peer 数据的 code 被挡且记入 `gate_missing["peer"]`

### 3.2 切换默认版本

- [ ] `weekly_refresh.BOARD_PROFILE_VERSION = "v2"`
- [ ] `api/sharpe_board.py` 的 `profile_version` 默认改 `"v2"`
- [ ] 未知版本仍 404

**测试**：
- [ ] 周刷新后新周 `profile_version == 'v2'`
- [ ] `GET /sharpe-board` 不传版本 → 返回 v2 数据
- [ ] `?profile_version=v9` → 404

---

## 阶段 4：52 周窗口与聚合统计（展示层）

### 4.0 引入 52 周窗口（先做，后续统计依赖它）

- [ ] `sharpe_board_service.py` 新增 `WINDOW_WEEKS = 52` 与 `_window_start(current)`
- [ ] `aggregate_board` 里对每个 code 计算 `eps_in_window = [(w,o) for w,o in eps if w >= window_start]`
- [ ] `listed_weeks = len(eps_in_window)`（**不再是 `len(eps)`**）
- [ ] `consecutive_weeks` 只从窗口内最新周向前数，跨窗口边界截断
- [ ] `range` 语义收窄：`all`/`1y` → 52 周；`6m` → 26 周；`3m` → 13 周；
      起点取 `max(window_start, range_start)`

**测试**（`tests/test_sharpe_board_service.py` 新增 `TestFiftyTwoWeekWindow`）：
- [ ] 构造 100 周历史 → `listed_weeks <= 52`（不是 100）
- [ ] 窗口起点 = 当前周 - 364 天，且 `.weekday() == 0`（周一）
- [ ] 历史不足 52 周（如 20 周）→ `listed_weeks == 20`，`weeks` 长度 20，不补零
- [ ] 窗口外有观测、窗口内无 → `listed_weeks == 0`，被默认 `min_weeks=1` 筛掉
- [ ] `range=1y` 与 `range=all` 返回相同周历（52 周，等价别名）
- [ ] `range=3m` → 13 周；`range=6m` → 26 周
- [ ] 全部 `weeks` 元素 `.weekday() == 0`（周一网格，含裁剪后起点）
- [ ] **数据完整性**：改动前后 `sharpe_board_observations` 总行数不变（窗口不删数据）

### 4.1 近12周达标统计（基于窗口内数据）

- [ ] 取 `eps_in_window[-12:]`（**不是 `eps[-12:]`**——窗口外数据不参与）
- [ ] `qualified = sum(1 for _, o in recent if o.sharpe >= QUALIFIED_SHARPE)`（0.8 常量）
- [ ] `total = len(recent)`
- [ ] 无历史 → 两者都 None（不是 0）

**测试**：
- [ ] 12 周全达标 → `(12, 12)`
- [ ] 12 周中 8 周达标 → `(8, 12)`
- [ ] 只有 6 周历史、4 周达标 → `(4, 6)`
- [ ] 0 周历史 → `(None, None)`
- [ ] 窗口边界：15 周历史但只有 10 周在窗口内 → 分母为 10

### 4.2 peer 分位展示

- [ ] 取窗口内最后一条观测的 `evidence_json["peer"]`
- [ ] 窗口内无观测 → null
- [ ] 旧观测（无 peer 字段）→ null

---

## 阶段 5：DTO 与前端

### 5.1 后端 DTO

- [ ] `SharpeBoardItemDTO` 加 5 字段：`near_12w_qualified` / `near_12w_total` /
      `peer_pct` / `peer_as_of` / （`profile_version` 若需要）
- [ ] **⚠ 确认 `aggregate_board` 的 `item_keys` 元组同步加字段**（否则被过滤掉）

**测试**：API 返回的 item 含全部新字段且非 None（有数据时）

### 5.2 前端

- [ ] `src/lib/sharpe-board.ts`：`SharpeBoardItem` 加对应字段
- [ ] URL 默认 `profileVersion = 'v2'`（省略不写进 URL）
- [ ] 表格新增两列：「近12周达标」`n/m`、「同类分位」`前 X%`
- [ ] 页面顶部显示当前规则版本提示（v2 徽标）
- [ ] 空值渲染为 `—`，不显示 `null`

- [ ] 页面顶部同时显示「近 52 周」口径说明（与 v2 版本徽标相邻，避免歧义）
- [ ] `range` 选择器文案与语义对齐：`all`→「近一年(52周)」、`1y` 隐藏或合并、
      `6m`→「近半年」、`3m`→「近3月」

**测试**：
- [ ] `sharpe-board.test.ts` 补 parse/serialize 默认 v2
- [ ] `tsc --noEmit` 通过

---

## 阶段 6：v1 数据迁移（导出 → 验证 → 删除）

### 6.1 脚本 `scripts/migrate_v1_archive.py`

- [ ] 阶段1 导出：weeks（全 status）+ observations → JSON + SQL + manifest（含 sha256）
- [ ] 阶段2 验证：重读比对行数/哈希；临时库重放 SQL 比对
- [ ] 阶段3 删除：仅 `--apply` 执行；单事务；先删 observations 再删 weeks

**测试**（`tests/test_migrate_v1_archive.py`，用 tmp_path 造小库）：
- [ ] dry-run 不删任何行
- [ ] 导出 → 删除 → 用存档重建，行数与 sha256 一致
- [ ] 删除只影响 v1 行，v2 行与其它表零影响
- [ ] 中途中止 → 整体回滚（无半个状态）

### 6.2 实际执行（人工确认后）

- [ ] 生产库 dry-run，人工核对行数（预期 192 周 / 9264 观测）
- [ ] `--apply` 执行
- [ ] 验证 `SELECT COUNT(*) FROM sharpe_board_weeks WHERE profile_version='v1'` == 0

---

## 阶段 7：验证与收尾

### 7.1 全量测试

- [ ] 后端 `pytest tests/ -q` 全绿（597 + 新增）
- [ ] 前端 `node --test` + `tsc --noEmit`

### 7.2 端到端

- [ ] 手动触发 v2 周刷新（本地或 NAS）
- [ ] `GET /api/funds/sharpe-board` 返回 v2 数据，留存数与调研预期同量级
      （stock ~10、discovery-stock ~33）
- [ ] 浏览器验证：两列渲染、版本徽标、1440/390 无横溢出

### 7.3 文档

- [ ] contracts.md 新增 §17（v2 规则与三道门契约）
- [ ] `frontend/fund-sharpe-board.md` 补两列与版本提示
- [ ] journal 记录

---

## 回滚点

| 阶段 | 回滚方式 |
|---|---|
| 1-5（代码） | `git revert` 或整体回退；v1 数据未动，功能可退回 v1 |
| 6（删数据） | 从 `data/archive/` 存档重放 SQL 恢复 |
| 7.2（切 v2 后发现问题） | 改 `BOARD_PROFILE_VERSION` 回 `"v1"` 一行；但 v1 数据已删需先恢复 |

**关键顺序**：阶段 6 必须在阶段 7.2 之前完成，且阶段 6 执行时
`BOARD_PROFILE_VERSION` 应仍为 v1（避免边删边写新 v1 行）。

---

## 验收命令汇总

```bash
# 后端
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/test_filter_service.py -q
/tmp/fsvenv/bin/python -m pytest tests/test_sharpe_board_service.py -q
/tmp/fsvenv/bin/python -m pytest tests/test_sharpe_board_capture.py -q
/tmp/fsvenv/bin/python -m pytest tests/test_sharpe_board_api.py -q
/tmp/fsvenv/bin/python -m pytest tests/test_migrate_v1_archive.py -q
/tmp/fsvenv/bin/python -m pytest tests/ -q

# 前端
cd apps/fund-select
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit

# 迁移
cd backend/fund-select
/tmp/fsvenv/bin/python scripts/migrate_v1_archive.py            # dry-run
/tmp/fsvenv/bin/python scripts/migrate_v1_archive.py --apply    # 确认后
```
