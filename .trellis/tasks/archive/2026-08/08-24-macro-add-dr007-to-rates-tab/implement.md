# rates tab 加 DR007 曲线 — 执行计划

> 与 [prd.md](./prd.md) + [design.md](./design.md) 配套。Phase 2 Execute 阶段的清单 + 验证 + 回滚。

## Phase 顺序

```
Step 1 (后端 fetcher + 单测)  ─┐
                                ├─ 串行：Step 2 依赖 Step 1 的接口
Step 2 (后端接入 /data 接口)  ─┤
                                ├─ 串行：Step 3 依赖 Step 2 的响应字段
Step 3 (前端类型 + RatesChart) ─┘
```

整体**后端先到位、前端再动**，避免前端拿到空字段调试。

## Step 1 — 后端 fetcher + 单测（TDD：先测试再实现）

### 1.1 写测试（RED）

**新增** `backend/macro/tests/test_dr007.py`：

```python
import pandas as pd
import pytest
from src.services.dr007_service import DR007Service
from src.services.data_service import DataService


@pytest.mark.unit
def test_parse_prr_csv_extracts_dr007_column():
    """第 8 列（index 7）为当日 DR007 利率（%）"""
    csv_text = (
        "2026-08-22,1.6500,1.6500,1234,567.89,1.7000,1.6000,1.6500\n"
        "2026-08-21,1.6300,1.6300,1100,500.00,1.6800,1.5800,1.6300\n"
    )
    df = DR007Service.parse_csv(csv_text)
    assert list(df.columns) == ["date", "dr007"]
    assert df.iloc[0]["date"] == pd.Timestamp("2026-08-22")
    assert df.iloc[0]["dr007"] == 1.6500


@pytest.mark.unit
def test_parse_csv_skips_invalid_rows():
    csv_text = "2026-08-22,bad,1.6500\n2026-08-21,1.6300,1.6300,1234,500,1.7,1.6,1.63\n"
    df = DR007Service.parse_csv(csv_text)
    assert len(df) == 1
    assert df.iloc[0]["date"] == pd.Timestamp("2026-08-21")


@pytest.mark.integration
def test_save_and_read_dr007_roundtrip(tmp_path):
    """CSV 写入磁盘 → DataService 读取回 DataFrame"""
    csv_path = tmp_path / "dr007.csv"
    rows = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-22"]),
        "dr007": [1.62, 1.63, 1.65],
    })
    DataService.save_dr007_data(rows, csv_path)

    loaded = DataService.load_dr007(csv_path)
    assert len(loaded) == 3
    assert loaded.iloc[-1]["dr007"] == 1.65
```

**verify**: `cd backend/macro && python -m pytest tests/test_dr007.py -v` — 必须失败（fetch + save 函数尚未实现）

### 1.2 实现 fetcher（GREEN）

**新增** `backend/macro/src/services/dr007_service.py`：

- 参考 `hibor_service.py` 的 Session + `@async_retry` 模式
- 数据源 URL：`https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`
- 提供：
  - `class DR007Service` 单例 `get_dr007_service()`
  - `parse_csv(csv_text: str) -> pd.DataFrame` — 解析函数（提为静态方法便于测试）
  - `async def fetch_history(start_date, end_date) -> pd.DataFrame`
  - `async def fetch_latest(end_date) -> pd.DataFrame`
- 错误：重试失败抛 `requests.HTTPError`，routes 层捕获

**verify**: 再跑 `pytest tests/test_dr007.py -v` — 必须全绿

## Step 2 — 后端接入 /api/macro/data

### 2.1 config.py

**修改** `backend/macro/src/config.py`：

```python
dr007_start_date: str = "2015-01-01"
```

### 2.2 models.py

**修改** `backend/macro/src/models.py`：

```python
class EconomicDataResponse(BaseModel):
    # ... 既有字段 ...
    dr007: Optional[Dict[str, List[Optional[float]]]] = None
```

### 2.3 data_service.py

**修改** `backend/macro/src/services/data_service.py`：

- 新增 `save_dr007_data(df, path)` 与 `load_dr007(path)`
- 修改 `query_data`（或等价聚合函数）按 `dates` 全量索引读取 `dr007.csv`，ffill 对齐

### 2.4 routes.py

**修改** `backend/macro/src/api/routes.py`：

- 第 1016 行 `_ALLOWED_DATA_TYPES` 加 `"dr007"`
- 新增 `POST /api/macro/fetch/dr007/history`（参考 `fetch_vix_history` 模板）
- 新增 `POST /api/macro/update/dr007`（参考 `update_china_bonds` 模板）
- 新增 `update_lock` / `acquire_update_lock` 的 `dr007` 处理（与 hibor 一致）

### 2.5 验证命令

```bash
# 1) 启服务
cd backend/macro && ./.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8094 &

# 2) 初始化（小窗口验证，避免一次性拉 11 年触发限流）
curl -X POST http://localhost:8094/api/macro/fetch/dr007/history \
  -H "Content-Type: application/json" \
  -d '{"historical_start_date": "2026-01-01"}'

# 3) 检查 CSV
ls -la backend/macro/data/dr007.csv
head -5 backend/macro/data/dr007.csv
wc -l backend/macro/data/dr007.csv  # 应 ≥ 200（2026 至今交易日）

# 4) 检查 /data 响应
curl http://localhost:8094/api/macro/data | jq '.data.dr007.value | length'
# 应输出与 dates.length 相等

# 5) 增量更新
curl -X POST http://localhost:8094/api/macro/update/dr007
wc -l backend/macro/data/dr007.csv  # 至少 + 1 行
```

### 2.6 后端全测

```bash
cd backend/macro && python -m pytest tests/ -v
# 必须不出现新的 FAIL；旧的 test 不变
```

## Step 3 — 前端类型 + RatesChart 拆 subchart

### 3.1 types

**修改** `apps/macro/src/lib/types/economic.ts`：

```ts
export interface EconomicDataResponse {
  // ... 既有字段 ...
  dr007?: {
    value: (number | null)[];
  };
}
```

### 3.2 useFilteredEconomicData（如果需要）

先用 `grep` 确认 `useFilteredEconomicData.ts` 在 rates tabType 下过滤了哪些字段——若已透传所有字段则不动；若是白名单过滤则把 `dr007.value` 加进白名单。

### 3.3 RatesChart 拆 subchart

**修改** `apps/macro/src/app/modules/economic/components/RatesChart.tsx`：

- 布局：Plotly `grid: { rows: 2, columns: 1, roworder: 'top to bottom' }`
- 共享 xaxis：subplot 1 的 `xaxis` 与 subplot 2 的 `xaxis2` 通过 `matches` / `scaleanchor` 联动
- 配色：DR007 用与"中国"语义区分配色，建议 `#dc2626`（深红，区别于现有 `#f87171` / `#fb7185`）
- subplot 1（左轴）: SOFR + 美债3M + **DR007**
- subplot 1（右轴）: TED spread
- subplot 2（左轴）: 中国 10y
- subplot 2（右轴）: 中国 10y-2y

### 3.4 验证

```bash
# 类型检查
cd apps/macro && pnpm build

# lint
cd apps/macro && pnpm lint
```

### 3.5 浏览器手动验证（必做）

1. 启 dev server：`cd apps/macro && pnpm dev`
2. 访问 `http://localhost:3003/macro`，切到「利率利差」tab
3. 默认 3M 视图：上图应可见 DR007 曲线（红色），下图应可见中国 10y + 10y-2y
4. 切换 1M / 3M / 6M / 1Y / ALL：两个 subchart 同步缩放
5. 切到「刷新」按钮后数据正常
6. DevTools Network 看 `/api/macro/data` 响应大小变化（应略增）

## Review Gate（必须全绿）

- [ ] `backend/macro`：`pytest tests/` 全绿，无新增 FAIL
- [ ] `apps/macro`：`pnpm build` 成功，`pnpm lint` 无新增错误
- [ ] 浏览器手动验证：rates tab 切 5 个时间范围均正常，DR007 曲线可见
- [ ] `curl /api/macro/data | jq '.data.dr007.value | length'` 输出 = `.data.dates | length`

## Rollback Point（每步可独立回滚）

| 步骤 | 回滚动作 |
|------|---------|
| Step 1 | `git revert` fetcher + test 即可 |
| Step 2 | `git revert` config/models/routes/data_service，回滚后 `/api/macro/data` 不含 dr007 |
| Step 3 | `git revert` types/RatesChart，前端不会读 dr007 字段 |

**整体回滚**：3 次 `git revert` 即可回到 master 当前状态。

## 执行顺序与子代理

**默认主线程顺序执行**（步骤之间有强依赖）。如果时间允许**并行**的场景：

- Step 1 的 `parse_csv` 静态方法可与 Step 2 的 `models.py` / `config.py` 改动并行（无依赖）
- 但需要 dispatch sub-agent 的意义不大——文件小、上下文集中，主线程按顺序跑更快

**建议**：不分 sub-agent，主线程顺序跑 1 → 2 → 3，每步带 verify。

## Commit 策略

按现有仓库 conventional commits：

```
feat(macro): 后端接入 DR007 日频数据（fetcher + /data 接口）
feat(macro): 前端 rates tab 加 DR007 曲线 + 拆 subchart
test(macro): DR007 fetcher 单元测试
docs(macro): 数据更新端点规范补 DR007 行
```

4 个 commit（或合并为 2 个）：后端 / 前端 / 测试 / 文档。

## 不要做的事（提醒）

- ❌ 不要 import `monetary-policy-skill/scripts/fetch_common.py`
- ❌ 不要改 `_ALLOWED_DATA_TYPES` 之外的其他 routes 逻辑
- ❌ 不要碰 nginx / GZipMiddleware / Cache-Control（属 perf 任务）
- ❌ 不要碰 localStorage 缓存 / 分层加载（属 perf 任务）
- ❌ 不要新增 R007 / DR001 / 同业存单（范围外）
- ❌ 不要新增独立 Tab（明确不做）