# implement：B2 价格对齐

## 前置

- [ ] 工作区有另一任务（fix-risk-adjusted-nav）的未提交改动：`nav_fetcher.py` / `risk_service.py` / `models.py` / `tests/test_risk_refresh.py` —— **本任务不 stage、不 revert 这些文件**，commit 只加本任务文件
- [ ] `uv run pytest tests/ -v` 先跑一遍基线（当前应全绿）

## 步骤

1. **TDD：先写失败测试**（`tests/test_benchmark_fetcher.py` 增补，monkeypatch `_resolve`）
   - 双计消除 / 前导裁剪 / 同日历回归 / deposit 混合（见 design.md 测试设计）
   - → verify: 新用例红（旧算法下双计用例失败）
2. **改 `fetch_benchmark_tri`**：收益序列 → 收盘价序列；`reindex→ffill→dropna→pct_change`
   - → verify: 新用例绿，原有用例全绿
3. **定向重刷验证**：python 直跑 `_refresh_fund_benchmarks(db, ['004316','021967'])` + `refresh_fund_risks(db, ['004316','021967'])`
   - → verify: 004316 库中 TRI 3y 涨幅 ≈ +21.8%（容忍 B1 残差 <1pp）、excess_3y ≈ −15.6%；021967（单日历）指标几乎不变
4. **全量重建**：142 只 benchmark + risk
   - → verify: 无异常日志；非 NULL 指标数不降（97 ir）；抽查 2-3 只
5. **trellis-check** 子代理全量检查

## 回滚点

- 步骤 2 后：`git checkout -- src/data/benchmark_fetcher.py`（测试文件单独删）
- 步骤 4 后：重跑旧算法不可行——保留本任务 git revert 路径，数据重建幂等可重入

## Commit

`fix(fund-select): 基准TRI合成改价格对齐,消除混合日历收益双计` —— 只含 `benchmark_fetcher.py` + `tests/test_benchmark_fetcher.py` + 本任务目录
