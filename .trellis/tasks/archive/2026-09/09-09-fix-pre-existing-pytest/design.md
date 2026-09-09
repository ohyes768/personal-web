# Design: Pre-existing pytest 失败修复

## 1. 范围与边界

### 在范围内

| 层 | 改动 |
|---|---|
| 后端测试 | `tests/test_filter_service.py::TestParsePeerRank` 3 case 断言更新 |
| 后端测试 | `tests/test_stock_filter_service.py` 2 case 断言更新 |
| 后端生产 | `src/data/benchmark_fetcher.py` 替换 `ak.bond_index_general_cbond(...)` → `ak.bond_new_composite_index_cbond()` + 注释更新 |
| 后端配置 | `config/benchmarks.yaml` source 字段 + 注释更新 |
| 后端测试 | `tests/test_benchmark_fetcher.py` patch 目标 + 注释 + 关联 case 更新 |
| 文档 | `.trellis/spec/backend/fund-select/backend/contracts.md` B1 段落 |

### 不在范围内

- 其它 akshare API 兼容性
- 实际触发 refresh 验证（仅静态 + 单测验证）
- 前端 / 其它后端 / eslint 配置

## 2. 契约 / 数据流

### 2.1 peer_rank 契约

`_parse_peer_rank` 自 d82928e 起返回：

```python
{"pct": float, "total": int, "rank": int}
```

5 个测试断言需要从 2 键扩到 3 键。每个失败的测试都有确定的 rank 值（从输入 `'<rank>/<total>'` 解析），直接加到断言里即可。

**TestParsePeerRank::test_valid**：输入 `'25/204'` → rank=25
**TestParsePeerRank::test_valid_leading_one**：输入 `'1/5615'` → rank=1
**TestParsePeerRank::test_whitespace_tolerated**：输入 `'  100  /  500  '` → rank=100
**test_screen_stock_dto_has_rank_keys_with_full_data**：输入 `'50/1000'` → rank=50（来自 `_seed_ranks_full` fixture）
**test_screen_stock_dto_rank_partial**：输入 `'100/1000'` → rank=100

### 2.2 cbond 源迁移

**当前路径**（2026-09-09 实测失败）：
```python
# src/data/benchmark_fetcher.py:196
if source == "bond_index_general_cbond":
    raw = ak.bond_index_general_cbond(index_category="综合指数", indicator="财富", period="总值")
```

**新路径**（无参数，akshare 1.18.39 起可用）：
```python
# src/data/benchmark_fetcher.py:196
if source == "bond_new_composite_index_cbond":
    raw = ak.bond_new_composite_index_cbond()
```

**数据等价性验证**（2026-09-09 实跑）：

| 维度 | bond_index_general_cbond（旧，已删） | bond_new_composite_index_cbond（新） |
|---|---|---|
| 列 | `[date, value]` | `[date, value]` ✓ 同 |
| 行数 | 6171（旧 B1 实证） | 6174（新） ✓ 同量级 |
| 2024-10-11（周五） | 保留 | 保留 ✓ |
| 2024-10-12（周六调休） | 保留 | 保留 ✓ |
| 近 3 年 weekday 分布 | Sun=142（错位!）/Sat=11/Fri=9（B1 bug） | Sun=11/Sat=9/Mon-Fri=144-149 ✓ 无错位 |

**结论**：`bond_new_composite_index_cbond` 本身就是「无 B1 bug 的版本」（按行数和 weekday 分布判定），无需 `+1` day hack。

### 2.3 yaml source 字段

`config/benchmarks.yaml` 中 `中债综合财富.source` 当前是 `"bond_index_general_cbond"`。改为 `"bond_new_composite_index_cbond"`。

## 3. 关键实现细节

### 3.1 peer_rank 测试断言改法

最小改动 —— 把 `{"pct": X, "total": Y}` 改成 `{"pct": X, "total": Y, "rank": Z}`。**不**改 `_parse_peer_rank` 实现（已正确）。

### 3.2 benchmark_fetcher.py 改法

```python
# 改前
if source == "bond_index_general_cbond":
    # B1 修复（2026-09-04 实证）：旧源 bond_composite_index_cbond 同一指数但日期整体
    # -1 天（真实周一标成周日、周五标成周四，3 年分布 Sun=142/Sat=11），inner join
    # 丢周末行 → 中债周五收益永久丢失。改用 bond_index_general_cbond(综合指数/财富/总值)：
    # 与旧源全史 6171 行逐值 0 差值（同一指数序列），日期为真实交易日
    # （含债市调休周六日：股市休市、银行间开市，3 年 20 天，属正常交易日非错位）。
    raw = ak.bond_index_general_cbond(index_category="综合指数", indicator="财富", period="总值")
    df = raw.rename(columns={"value": "close"})[["date", "close"]]

# 改后
if source == "bond_new_composite_index_cbond":
    # B1 修复（2026-09-04 实证）：旧源 bond_composite_index_cbond 同一指数但日期整体
    # -1 天（真实周一标成周日、周五标成周四，3 年分布 Sun=142/Sat=11），inner join
    # 丢周末行 → 中债周五收益永久丢失。
    # 09-09-fix-pre-existing-pytest 二次迁移：akshare 1.18.39 移除 bond_index_general_cbond，
    # 改用 bond_new_composite_index_cbond()。该源无 B1 错位 bug：6174 行 / Sun=11 / Sat=9 调休，
    # 周五保留。无需参数。
    raw = ak.bond_new_composite_index_cbond()
    df = raw.rename(columns={"value": "close"})[["date", "close"]]
```

### 3.3 test_benchmark_fetcher.py 改法

两处需要改：

1. **`test_cbond_uses_general_source` 注释 + fixture**（line 45 附近）：
   - `"ak_symbol": "CBA00301", "source": "bond_index_general_cbond"` → `"bond_new_composite_index_cbond"`
   - 注释更新

2. **`test_cbond_source_dates_kept_as_is`**（line 240）：
   - `patch("src.data.benchmark_fetcher.ak.bond_index_general_cbond", return_value=raw)` → `patch("src.data.benchmark_fetcher.ak.bond_new_composite_index_cbond", return_value=raw)`
   - `_fetch_index_daily("CBA00301", "bond_index_general_cbond", ...)` → `_fetch_index_daily("CBA00301", "bond_new_composite_index_cbond", ...)`
   - 注释更新

### 3.4 contracts.md 改法

把 B1 段里的 `bond_index_general_cbond` 全部改为 `bond_new_composite_index_cbond`，并加迁移注记。

## 4. 兼容性 & 回滚

### 兼容性

- peer_rank：API 已支持新契约（d82928e 起），测试跟上即可，无兼容性风险
- cbond：refresh 时不再 AttributeError；TRI 合成结果与原 B1 修复目标一致（同一指数序列，日期正确）

### 回滚

- peer_rank：git revert 即可
- cbond：理论上 akshare 旧版本还能用 `bond_index_general_cbond`，但 venv 已经 1.18.39，回滚会导致 refresh 立刻炸。**不建议回滚**

## 5. 测试策略

- pytest 全量回归，确保不引入新失败
- 重点验证 6 个原失败 case 全部变 PASS
- contracts.md 文档一致性（grep 验证无残留旧 API 名）
