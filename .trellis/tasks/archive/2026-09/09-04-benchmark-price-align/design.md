# design：fetch_benchmark_tri 价格对齐

## 现状与缺陷

`src/data/benchmark_fetcher.py` `fetch_benchmark_tri`：

```python
series[key] = df.set_index("date")["return"]        # 存日收益
all_dates = 并集(各成分日期)
ret_df[key] = s                                       # 对齐到并集 → 缺日 NaN
ret_df = ret_df.sort_index().ffill().fillna(0)        # ← 缺陷：对收益 ffill = 复制前日收益
weighted = Σ ret_df[key] × w；tri = (1+weighted).cumprod() × 1000
```

成分 B 缺席日（另一市场开市）→ B 前一日收益被再计一次。混合日历 3 年累积 +13.5pp（004316 实测）。

## 目标算法

```python
series[key] = df.set_index("date")["close"]          # 改存收盘价（deposit 仍 None 占位）
all_dates = 并集(各成分日期)                          # 不变
px = DataFrame({key: s.reindex(all_dates)}).sort_index().ffill()
px = px.dropna()                                      # 裁掉最晚成分上市前的行（前导 NaN 无法 ffill）
rets = px.pct_change().fillna(0)                      # 缺席日价格不变 → 收益 0 ✓
weighted = Σ rets[key] × (w/total_w)（deposit 项仍常数日收益）
tri = (1 + weighted).cumprod() × 1000
```

语义：并集日历上每日固定权重再平衡的组合收益——与现设计意图一致，只是缺席日贡献 0 而非复制。

## 行为变化点（需测试锁定）

| 场景 | 现算法 | 新算法 |
|---|---|---|
| 成分缺席日 | 前日收益复制（双计） | 收益 0（价格 held） |
| 成分晚于窗口起点上市 | 缺席期收益按 0（fillna(0) 兜底）参与合成 | 并集起点裁到该成分首个交易日（`dropna`） |
| 全成分同日历 | 正常 | 数值不变（reindex 恒等） |
| deposit 成分 | 常数日收益铺全并集 | 不变 |

## 不动的部分

- `_fetch_index_daily`（仍返回 close + return 列；return 列保留给 `_fallback_chain_tri`）
- `_resolve` / fallback 链 / stale 检测 / `parse_formula` / `source` 标记
- `risk_service`、DB 模型、API、前端

## 测试设计（tests/test_benchmark_fetcher.py 增补）

monkeypatch `_resolve` 返回手工构造的日线 DataFrame（不联网）：

1. **双计消除**：A=[d1,d2,d3]、B=[d1,d3]。旧算法 d2 会复制 B 的 d1→d3 段收益；新算法 d2 的 B 收益=0。断言 tri 逐日等于手工期望序列。
2. **前导裁剪**：A 从 d1 有价、B 从 d2 才有价 → 输出首行日期 = d2。
3. **回归**：A、B 同日历 → 新 TRI 与直接用收益序列 cumprod 的结果一致（数值容差 1e-9）。
4. **deposit 混合**：指数 + 存款成分，权重归一不变（现已有类似用例则沿用扩展）。

## 数据重建

代码合入后：`_refresh_fund_benchmarks(db, 全部 142 codes)` + `refresh_fund_risks(db, codes)`（定向脚本，不动债基宇宙）。指数级缓存使基准步 ~5-8 分钟，risk ~10 分钟。

## 风险与回滚

- 影响面：所有非 QDII 且基准含 ≥2 个不同源成分的基金（约 40+ 只）；单成分基准数值不变。
- 回滚：revert 单文件 `benchmark_fetcher.py` + 测试，再重建一次数据即可。
- 已知残留：B1 中债日期错位仍在（独立任务），004316 复验值与 +21.77% 的残差来自 B1。
