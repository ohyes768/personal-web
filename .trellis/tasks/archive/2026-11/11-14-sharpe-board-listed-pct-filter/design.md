# 设计：夏普榜单在榜占比筛选 + 精简时间范围

## 1. 后端改动

### 1.1 `src/services/sharpe_board_service.py`

`aggregate_board` 的 `min_weeks: int = 1` → `min_listed_pct: float = 60.0`。
展示筛选（第 2 段）改为：

```python
matched = [
    s for s in stats.values()
    if s["listed_weeks"] >= 1                      # 硬门槛：窗口内曾在榜
    and s["listed_weeks"] * 100 >= min_listed_pct * s["evaluable_weeks"]
    and (min_latest_sharpe is None or ...)
    and (not latest_only or ...)
]
```

- 整数左乘避免浮点比较误差（51×100 ≥ 60×51）。
- `evaluable_weeks` 为 0 的基金 `listed_weeks` 必为 0 → 被硬门槛挡掉，不会出现除零。
- `min_listed_pct=0` → 恒真 → 等价旧 `min_weeks=1`。

### 1.2 `src/api/sharpe_board.py`

`min_weeks: int = Query(1, ge=1, ...)` → 
`min_listed_pct: float = Query(60, ge=0, le=100, description="在榜占比下限（%，在榜周数 ÷ 可评周数，含等于）")`。

旧 `min_weeks` 参数**删除**（422 由 Query 校验负责越界；未知参数 FastAPI 忽略 → 旧链接落默认）。

## 2. 前端改动

### 2.1 `src/lib/sharpe-board.ts`

- `SharpeBoardFilters.minWeeks: number` → `minListedPct: number`；
  `DEFAULT_SHARPE_FILTERS.minListedPct = 60`。
- URL 参数：`min_weeks` → `min_listed_pct`（默认值不写进 URL）。
  `parseSharpeFiltersFromSearch` 读 `min_listed_pct`，非法值回落 60。
- `SharpeRange` 去掉 `'1y'`；`RANGE_OPTIONS` 去掉「近 1 年」并按时长升序：
  `3m 近 3 个月` / `6m 近 6 个月` / `all 近一年(52周)`。
- `sharpeFiltersActive`：`minListedPct !== DEFAULT.minListedPct` 才算筛选激活。

### 2.2 `src/components/sharpe-board/SharpeBoardFilters.tsx`

「至少上榜 [N] %」：

```tsx
<label className={labelCls}>
  至少上榜
  <input type="number" min={0} max={100} step={1} value={filters.minListedPct}
         onChange={onMinListedPctChange} aria-label="在榜占比下限（%，在榜周数 ÷ 可评周数）"
         className={`${control} w-16 tnum`} />
  %
</label>
```

- 输入变化：非数字/越界 → 回落到 60；空串 → 0（= 不限）。
- `title` 说明分母口径（在榜周数 ÷ 可评周数）。

### 2.3 `src/app/sharpe-board/page.tsx`

- `pageAffecting` 判定里的 `'minWeeks'` → `'minListedPct'`；
- `clearDisplayFilters` 里 `minWeeks: 1` → `minListedPct: 60`。

## 3. 测试

- 后端：`test_sharpe_board_api.py`（`min_weeks` → `min_listed_pct`；越界 422）、
  `test_sharpe_board_service.py`（窗口外基金任何下限都看不到）。
- 前端：`sharpe-board.test.ts`（URL 往返、默认值省略、非法值回落、筛选激活判定、
  RANGE_OPTIONS 不含 1y）。

## 4. 陷阱

1. **`sharpeFiltersActive` 忘了改默认**：非默认值比较用 60，否则「筛选已激活」永远为 false。
2. **URL 默认值省略**：`min_listed_pct` 等于 60 时不写进 URL（保持链接短、可分享）。
3. **`range=1y` 旧链接**：从白名单移除后回落默认 `all`（同样 52 周）→ 行为不变 ✓。
4. **空输入框**：`Number('') = 0` → 会把上限写成 0（= 不限）→ 用显式空串判断避免误触。
