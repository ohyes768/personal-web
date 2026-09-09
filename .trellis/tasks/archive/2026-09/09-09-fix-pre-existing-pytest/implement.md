# Implement: Pre-existing pytest 失败修复

按依赖顺序执行，每步独立可验证。

## 1. peer_rank 测试断言更新（5 case）

### 1.1 `backend/fund-select/tests/test_filter_service.py`

`TestParsePeerRank` 类下 3 个 case，把 2 键断言改成 3 键：

- `test_valid`：`_parse_peer_rank("25/204") == {"pct": 12.3, "total": 204}` → `... {"pct": 12.3, "total": 204, "rank": 25}`
- `test_valid_leading_one`：`_parse_peer_rank("1/5615") == {"pct": 0.0, "total": 5615}` → `... {"pct": 0.0, "total": 5615, "rank": 1}`
- `test_whitespace_tolerated`：`_parse_peer_rank("  100  /  500  ") == {"pct": 20.0, "total": 500}` → `... {"pct": 20.0, "total": 500, "rank": 100}`

### 1.2 `backend/fund-select/tests/test_stock_filter_service.py`

2 个 case：

- `test_screen_stock_dto_has_rank_keys_with_full_data`（line 174 附近）：
  `by_code["600001"]["rank_ytd"] == {"pct": 5.0, "total": 1000}` → `... {"pct": 5.0, "total": 1000, "rank": 50}`
- `test_screen_stock_dto_rank_partial`（line 205 附近）：
  `items["600001"]["rank_1y"] == {"pct": 10.0, "total": 1000}` → `... {"pct": 10.0, "total": 1000, "rank": 100}`

### 1.3 验证

```bash
cd backend/fund-select && python -m pytest tests/test_filter_service.py::TestParsePeerRank tests/test_stock_filter_service.py -v
```

5 个失败全 PASS，无新增失败。

## 2. cbond 源迁移

### 2.1 `backend/fund-select/src/data/benchmark_fetcher.py`

line 196-203：

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
    # 改用 bond_new_composite_index_cbond()。该源无 B1 错位 bug：6174 行 / Sun=11 / Sat=9
    # 调休 / 周五保留。无需参数（默认全序列，返回列 [date, value]）。
    raw = ak.bond_new_composite_index_cbond()
    df = raw.rename(columns={"value": "close"})[["date", "close"]]
```

### 2.2 `backend/fund-select/config/benchmarks.yaml`

找到 `source: "bond_index_general_cbond"` 那行（带 CBA00301 ak_symbol 的「中债综合财富」条目）：

- `source: "bond_index_general_cbond"` → `source: "bond_new_composite_index_cbond"`
- 同时更新文件顶部注释里描述此源的段落（line 注释里「bond_index_general_cbond 中债网，中债-综合指数（财富/总值口径）」+ B1 修复注释）

### 2.3 `backend/fund-select/tests/test_benchmark_fetcher.py`

两处：

1. `test_cbond_uses_general_source`（line 45）：
   - fixture 里 `"source": "bond_index_general_cbond"` → `"bond_new_composite_index_cbond"`
   - 测试方法名是否要改名？暂不改（方法名描述行为「用通用源」，与具体 API 名解耦）

2. `test_cbond_source_dates_kept_as_is`（line 240）：
   ```python
   # 改前
   with patch("src.data.benchmark_fetcher.ak.bond_index_general_cbond",
              return_value=raw) as mock:
       df = _fetch_index_daily("CBA00301", "bond_index_general_cbond",
                               date(2024, 1, 1), date(2024, 10, 14))
   # 改后
   with patch("src.data.benchmark_fetcher.ak.bond_new_composite_index_cbond",
              return_value=raw) as mock:
       df = _fetch_index_daily("CBA00301", "bond_new_composite_index_cbond",
                               date(2024, 1, 1), date(2024, 10, 14))
   ```
   + 更新注释说明迁移

### 2.4 验证

```bash
cd backend/fund-select && python -m pytest tests/test_benchmark_fetcher.py -v
```

`TestFetchIndexDaily::test_cbond_source_dates_kept_as_is` 等全 PASS。

## 3. contracts.md 更新

### 3.1 `.trellis/spec/backend/fund-select/backend/contracts.md`

B1 段（line 76 附近）：

```md
# 改前
- **B1（已修复，09-04-fix-bond-index-date-shift）**：... 改源：换源非 shift：`bond_index_general_cbond(index_category="综合指数", indicator="财富", period="总值")` 与旧源全史 6171 行逐值 0 差值（同一指数序列），日期正确 ...

# 改后
- **B1（已修复，09-04-fix-bond-index-date-shift）**：... 二次迁移（09-09-fix-pre-existing-pytest）：akshare 1.18.39 移除 `bond_index_general_cbond`，改用 `bond_new_composite_index_cbond()`。该源本身无 B1 错位 bug：6174 行 / 近 3 年 weekday 分布 Sun=11 / Sat=9 调休 / Mon-Fri=144-149（与 B1 bug 实证的 Sun=142/Sat=11 分布截然不同）。无需参数 ...
```

## 4. 全量回归

### 4.1 后端全量

```bash
cd backend/fund-select && python -m pytest tests/ -v
```

应：之前 6 个失败全部变 PASS，无新增失败。

### 4.2 grep 残留验证

```bash
# 不应有 ak.bond_index_general_cbond 残留
cd backend/fund-select && grep -rn "bond_index_general_cbond" src/ tests/ config/ --include="*.py" --include="*.yaml" 2>&1

# yaml source 字段全部更新
cd backend/fund-select && grep -rn "source:" config/benchmarks.yaml | grep -i cbond 2>&1
```

应：第一个命令 0 结果；第二个命令显示 `bond_new_composite_index_cbond`。

## 5. 提交

### 5.1 文件清单

- `backend/fund-select/tests/test_filter_service.py`
- `backend/fund-select/tests/test_stock_filter_service.py`
- `backend/fund-select/src/data/benchmark_fetcher.py`
- `backend/fund-select/config/benchmarks.yaml`
- `backend/fund-select/tests/test_benchmark_fetcher.py`
- `.trellis/spec/backend/fund-select/backend/contracts.md`

### 5.2 commit message

```
fix(fund-select): peer_rank 测试断言补 rank 键；cbond 源迁移 bond_index_general_cbond → bond_new_composite_index_cbond
```

Body 要点：
- 5 个 peer_rank 失败：d82928e 加了 rank 键但测试未跟；断言更新即可
- 1 个 cbond 测试失败：akshare 1.18.39 移除 bond_index_general_cbond API；
  生产代码 refresh 路径已迁到 bond_new_composite_index_cbond；
  实证该源无 B1 错位 bug（6174 行 / Sun=11 / Sat=9 调休 / 周五保留）；
  yaml config source 字段同步更新；
  contracts.md B1 段落更新

### 5.3 跑 git status 确认

```bash
git status -s
```

仅 6 个目标文件改动，无意外文件。
