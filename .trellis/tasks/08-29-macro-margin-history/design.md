# 融资余额历史回补 — 技术设计

## 边界

| 层 | 改 | 不改 |
|----|----|------|
| `margin_service.py` | 新增 `fetch_history()`；抽出按日对齐合计 | `fetch_today()` 行为与响应 |
| `routes.py` | 新增 `POST /fetch/margin/history` | `POST /update/margin`、调度路径 |
| `models.py` | 新增 history 响应 model | `MarginData` / `MarginUpdateData` |
| `data_service.save_margin_data` | 复用 | 合并写 keep=last 逻辑 |
| `economicApi.initMarketSentimentHistory` | 串行两条 history | `updateMarketSentiment`、InitButton 组件 |
| 规范 / `data-sources.md` | 补端点与初始化契约 | `scheduler.json` |

## 数据流

```
InitButton
  → POST /api/macro/fetch/volume-turnover/history   （已有，BaoStock）
  → POST /api/macro/fetch/margin/history            （本任务）
       → MarginService.fetch_history()
            akshare 沪全表 + 深全表
            列名检测（复用 _detect_margin_columns）
            按 date outer join，缺侧 0
            元 ÷ 1e8 → 亿元
       → DataService.save_margin_data（keep=last）
  → onSuccess → refreshKey++ → GET /api/macro/data/market-sentiment
```

akshare 一次调用即全量，不按日期分页，不需要 `start_date`/`end_date` query。落盘前丢掉早于 `settings.historical_start_date` 的行（规范禁止硬编码日期；数据源实际从 2010-03-31 起，过滤是空操作）。

## 合约

### `MarginService.fetch_history() -> dict`

```python
{
  "status": "ok" | "failed",
  "error": str | None,
  "data": DataFrame,   # columns: date, margin_balance_yi；status=failed 时为空
}
```

- 列名、单位与 `fetch_today` 同一套：`_detect_margin_columns` + 元÷1e8。
- 沪、深各自按日期去重 keep=last，再 `outer` merge，`fillna(0)` 后相加，`round(..., 2)`。
- 禁止按 `iloc` 行号对齐（沪约 3983 行 / 深约 3785 行）。
- 解析失败或任一侧空表 → `status=failed`，不抛给调用方以外的异常；route 再转成 `UPDATE_FAILED`。

### `POST /api/fetch/margin/history`

- 前缀：后端 router 是 `/api`，前端 rewrite 后写 `/api/macro/fetch/margin/history`。
- 9 步骨架：锁检查 → acquire → fetch_history → 空则失败 → `save_margin_data` → 成功响应 → finally 释放。
- 响应 `data`：

```python
MarginHistoryData(rows: int, start: str, end: str)
MarginHistoryUpdateData(history: MarginHistoryData)
```

与 volume-turnover history 同形（行数 + 实际起止），InitButton 只看 `success`。

### 前端

```typescript
initMarketSentimentHistory: async () => {
  const vt = await post('/api/macro/fetch/volume-turnover/history');
  if (!vt.success) return vt;
  return post('/api/macro/fetch/margin/history');
}
```

与 `updateMarketSentiment` 同一串行模式，避开 `_is_updating`。

## 取舍

| 方案 | 结论 |
|------|------|
| 独立 `/fetch/margin/history` vs 并进 volume-turnover | 独立。规范禁止两套命名，且数据源不同（akshare vs BaoStock）。 |
| outer join 填 0 vs inner join | outer。单边交易日不丢行；「两市合计」缺侧按 0，避免把单边当成两市。 |
| query 日期窗 vs 全表 | 全表。akshare 无日期参数；过滤只用 `historical_start_date`。 |
| hasData / storageKey 迁移 | 不做。操作员删三份 CSV + 清 localStorage 后重点初始化。 |

## 兼容与回滚

- 已有 `margin.csv` 日更点：history 同日 keep=last 覆盖，更早日期追加。
- 调度仍只打 `/update/margin`。
- 回滚：还原 `margin_service.py` / `routes.py` / `models.py` / `api.ts`；CSV 若已被全量覆盖，需从备份恢复或重新跑 history。
- 前端第一步成功、第二步失败：成交额/换手率已写入，融资余额未全量；按钮不置灰，可再点（第一步幂等）。

## 测试

`tests/test_margin.py` 增补（全部 mock akshare）：

- 沪深日期不完全重合：outer 合计，缺侧 0，不按行号错位。
- 单位：元÷1e8，与现有 `test_extract_latest_margin_sums_sh_and_sz` 一致。
- 两侧空 / 列名失败 → `status=failed`。
- `save_margin_data` 对 history 形状 DataFrame 幂等 keep=last（可复用现有 merge 测试）。
