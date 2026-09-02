# phase2-A 实施清单

## 前置确认

- [ ] PRD.md 已 review（决策 1-6 来自调研 + 用户确认）
- [ ] design.md 已 review（算法 1-4 + refresh 接入 + 回滚策略）
- [ ] `task.py start .trellis/tasks/09-02-stock-fund-select-phase2-infra` 已激活

## 实施步骤（顺序执行）

### Step 1: 指数 yaml 映射表
- [ ] 创建 `backend/fund-select/config/benchmarks.yaml`
- [ ] 包含 ≥30 个常见指数 + aliases 表 + fallback_chain
- [ ] **验证**：`yaml.safe_load(open("config/benchmarks.yaml"))` 不报错；indices 数 ≥ 30

### Step 2: 「活期存款基准利率」常量模块
- [ ] 创建 `src/data/deposit_floor.py`
- [ ] 定义 `PBOC_DEPOSIT_FLOOR_RATE = 0.0035`（固定常量，不做历史分档映射）
- [ ] 注释说明：0.35% 自 2012-07-06 起执行至今（活期档位最后一次调整）；历史档位误差 ~0.02%/年可忽略
- [ ] **验证**：`python -c "from src.data.deposit_floor import PBOC_DEPOSIT_FLOOR_RATE; assert 0.003 < PBOC_DEPOSIT_FLOOR_RATE < 0.004"`

### Step 3: ORM 模型新增
- [ ] `src/db/models.py` 追加 `FundBenchmark` + `RiskFreeRate` 类
- [ ] **验证**：`python -c "from src.db.models import FundBenchmark, RiskFreeRate; print(FundBenchmark.__tablename__, RiskFreeRate.__tablename__)"`

### Step 4: 建表（项目无 alembic，走 create_all 约定）
- [ ] 项目用 `Base.metadata.create_all(engine)` 建表（`src/db/session.py:24`），无 alembic —— 遵循现状，新 model 导入后自动建表
- [ ] **验证**：`.venv/Scripts/python -c "from src.db.session import engine; from src.db import models; from sqlalchemy import inspect; insp = inspect(engine); print([t for t in insp.get_table_names() if 'benchmark' in t or 'risk_free' in t])"` 输出两张新表

### Step 5: 单测先行 - parse_formula 8 类样例
- [ ] 创建 `tests/test_benchmark_fetcher.py`
- [ ] 用 8 类真实公式做 parametrize：
  - 标准三指数
  - 含活期存款
  - 含子指数（中证 800 成长）
  - 经汇率调整（中证港股通综合（使用估值汇率折算））
  - 百分号前置（95%×指数...+5%×存款...）
  - 全角字符（ｘ60%＋40%）
  - 单指数无权重（纳斯达克 100 指数）
  - 纯名称无权重（标普 500 等权重指数）
- [ ] 每个 case 断言：kind / weight / ak_symbol
- [ ] **验证**：`pytest tests/test_benchmark_fetcher.py::test_parse_formula -v` 全过

### Step 6: 实现 parse_formula
- [ ] `src/data/benchmark_fetcher.py` 创建
- [ ] `_FULLWIDTH = str.maketrans("＋ｘ（）", "+*()")`
- [ ] `parse_formula()` 函数（按 design.md 算法 1）
- [ ] `_classify()` 函数（deposit_floor / index / unknown 三分类）
- [ ] `_load_benchmarks_yaml()` 缓存读取
- [ ] **验证**：`pytest tests/test_benchmark_fetcher.py::test_parse_formula -v` 全过

### Step 7: 实现 _fetch_index_daily
- [ ] 同文件实现 `_fetch_index_daily(symbol, source, start, end)`
- [ ] 分发：symbol 前缀 `hk` 走 `stock_hk_index_daily_em`，其他走 `stock_zh_index_daily`
- [ ] 返回 `pd.DataFrame(date, close, return)`
- [ ] **验证**：`python -c "from src.data.benchmark_fetcher import _fetch_index_daily; print(_fetch_index_daily('sh000300', 'stock_zh_index_daily', date(2024,1,1), date.today()).head())"` 能跑出数据

### Step 8: 实现 fetch_benchmark_tri
- [ ] `src/data/benchmark_fetcher.py` 追加 `fetch_benchmark_tri(code, start, end)`
- [ ] 按 design.md 算法 2：拉 info → parse → 拉各指数 → 加权日收益 → 复利累加 → TRI
- [ ] `_fallback_chain_tri()` 处理整体失败
- [ ] `_empty_with_source()` 处理单只基金无字段（968157 等）
- [ ] **验证**：`python -c "from src.data.benchmark_fetcher import fetch_benchmark_tri; df = fetch_benchmark_tri('005827', date(2023,1,1), date.today()); print(df.shape, df.head())"` 输出 ≥ 500 行 TRI 序列

### Step 9: 单测 - TRI 合成形状
- [ ] `tests/test_benchmark_fetcher.py` 追加 `test_fetch_benchmark_tri_shape`
  - 断言：行数 > 200、列名含 `tri`、参考日 tri ≈ 1000、单调性（TRI 变化方向与基准指数方向一致）
- [ ] `test_fetch_benchmark_tri_005827` — 用易方达蓝筹精选做集成测试
- [ ] **验证**：`pytest tests/test_benchmark_fetcher.py -v` 全过

### Step 10: 实现 risk_free_fetcher
- [ ] 创建 `src/data/risk_free_fetcher.py`
- [ ] `fetch_risk_free_rate(start, end)` 按 design.md 算法 4
- [ ] 三级降级：bond_zh_us_rate 2Y → LPR 1Y → 0.025
- [ ] **验证**：`python -c "from src.data.risk_free_fetcher import fetch_risk_free_rate; df = fetch_risk_free_rate(date(2020,1,1), date.today()); print(df.shape, df.head())"` 应 ≥ 1000 行

### Step 11: 单测 - risk_free_fetcher
- [ ] 创建 `tests/test_risk_free_fetcher.py`
- [ ] 覆盖：返回非空、列名正确、单位为年化小数（0.005~0.05 量级）
- [ ] **验证**：`pytest tests/test_risk_free_fetcher.py -v` 全过

### Step 12: Refresh pipeline 接入（实际在 src/scheduler/tasks.py，非 refresh_service）
- [ ] `src/scheduler/tasks.py` 追加：
  - `_refresh_fund_benchmarks(db)` — 跑 funds_stock.yaml 全量，先删后插（仿 `_replace_achievement` 模式）
  - `refresh_risk_free_rate_sync()` — 独立函数，一次拉全历史
- [ ] 在 `refresh_stock_funds_sync` 主循环完成后调用 `_refresh_fund_benchmarks`
- [ ] **不动** `refresh_configured_funds_sync`（债基路径）

### Step 13: 全量回归
- [ ] **不实现** Sharpe / IR / T-M（phase2-B 范围）
- [ ] 跑 refresh pipeline 一次：
  ```bash
  .venv/Scripts/python -c "from src.services.refresh_service import refresh_stock_funds_sync, refresh_risk_free_rate_sync; import uuid; refresh_risk_free_rate_sync(str(uuid.uuid4())); refresh_stock_funds_sync(str(uuid.uuid4()))"
  ```
- [ ] 检查 DB：
  ```bash
  sqlite3 fund_select.db "SELECT COUNT(*) FROM fund_benchmark; SELECT COUNT(*) FROM risk_free_rate; SELECT COUNT(DISTINCT code) FROM fund_benchmark WHERE tri IS NOT NULL"
  ```
  - 预期：fund_benchmark 总行数 ≈ 143 × ~700 ≈ 100,000+
  - 预期：fund_benchmark tri 非 NULL 的 code 数 ≥ 142
  - 预期：risk_free_rate 总行数 ≥ 8000
- [ ] 检查失败基金：
  ```bash
  sqlite3 fund_select.db "SELECT code, COUNT(*) AS rows FROM fund_benchmark WHERE tri IS NULL GROUP BY code"
  ```
  - 预期：只有 968157 一行 tri=NULL

### Step 14: 单测全量回归
- [ ] `pytest tests/ -v` 全过
- [ ] 覆盖率：
  ```bash
  pytest --cov=src --cov-report=term-missing tests/
  ```
  - 目标：`benchmark_fetcher.py` ≥ 80%，`risk_free_fetcher.py` ≥ 80%

### Step 15: 语法 / 编译检查（项目无 ruff/black 工具链，遵循现状）
- [ ] `.venv/Scripts/python -m py_compile` 覆盖所有新增/修改文件
- [ ] `pytest tests/ -q` 全过（存量 2 个 fee 测试失败与本 task 无关，stash 验证过）

## Review Gates

| Gate | 触发时机 | 检查项 |
|---|---|---|
| **G1 算法对齐** | Step 5 后 | parse_formula 8 类样例全过；与 design.md 算法 1 一致 |
| **G2 数据流通** | Step 13 后 | DB 行数与预期一致；968157 唯一 tri=NULL |
| **G3 回归** | Step 14 后 | pytest 全过；覆盖率达标 |
| **G4 Lint** | Step 15 后 | ruff / black / isort 全过 |

## 验收命令（一键）

```bash
cd backend/fund-select
.venv/Scripts/python -m pytest tests/test_benchmark_fetcher.py tests/test_risk_free_fetcher.py -v
.venv/Scripts/python -m pytest tests/ -v
.venv/Scripts/python -m py_compile src/data/benchmark_fetcher.py src/data/risk_free_fetcher.py src/data/deposit_floor.py src/scheduler/tasks.py src/db/models.py
```

## 回滚

新表由 create_all 创建，回滚 = 删表（数据可随时重拉）：

```bash
sqlite3 fund_select.db "DROP TABLE IF EXISTS fund_benchmark; DROP TABLE IF EXISTS risk_free_rate;"
git checkout -- src/ config/    # 代码回滚
```

phase2-B 不会受影响（独立 task）；债基路径完全未触及。

## Notes

- 不要修改债基相关任何代码（`funds.yaml`、债基 refresh、债基 filter 等）
- 不要引新依赖（pyyaml / pandas / numpy / akshare 已够）
- 不要引新 .env 变量
- 不要实现 Sharpe / IR / T-M / α-IR / 超额收益（phase2-B 范围）
- 公式解析的「不可解析」必须走 fallback_chain 而不是抛异常
