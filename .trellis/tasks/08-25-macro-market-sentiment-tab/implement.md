# 市场情绪 Tab — 执行计划

> 与 [prd.md](./prd.md) + [design.md](./design.md) 配套。Phase 2 Execute 阶段的清单 + 验证 + 回滚。

## Phase 顺序

```
Step 1 (后端 utils + 3 个 fetcher + 单测)  ─┐
                                              ├─ 串行：Step 2 依赖 Step 1
Step 2 (data_service + routes)              ─┤
                                              ├─ 串行：Step 3 依赖 Step 2
Step 3 (前端 types + MarketSentimentTab/Chart) ─┘
```

整体**后端先到位、前端再动**。

## Step 1 — 后端 fetcher + 单测（TDD：先测试再实现）

### 1.1 写 `utils/trade_date.py`（先于 fetcher）

**新增** `backend/macro/src/utils/trade_date.py`：照搬 skill `fetch_volume_exchange.py:33-61` 的 `get_trade_date()` 逻辑。

**单测** `tests/test_trade_date.py`：4 个 case
- 周末 → 返回最近周五
- 周一盘中（< 16:00）→ 返回上周五
- 周一盘后（≥ 16:00）→ 返回周一
- 节假日（待手动 mock）→ 期望逻辑正确（不强求识别法定节假日，仅周末）

**verify**: `pytest tests/test_trade_date.py -v` 全绿

### 1.2 写 `volume_service.py`（TDD）

**新增** `backend/macro/tests/test_volume.py`：

```python
@pytest.mark unit
def test_volume_service_combines_sse_and_szse(monkeypatch):
    """mock SSE 返回 + SZSE 返回 → total_amount_yi = sum / 1e8"""
    # fake sse {"total_amount_yi": 1000.0} + szse {"total_amount_yi": 1500.0}
    # expected: 2500.0 (亿元)

@pytest.mark unit
def test_volume_service_handles_one_side_failed():
    """单边失败（status != 'ok'）→ 返回 status='partial' 或 'failed'"""

@pytest.mark integration
def test_save_volume_roundtrip(tmp_path):
    """save_volume_data → load_volume 读回"""

@pytest.mark integration
def test_save_volume_merges_existing(tmp_path):
    """save_volume_data 合并现有 CSV（同 date 覆盖）"""
```

**新增** `backend/macro/src/services/volume_service.py`：
- 类比 `dr007_service.py` 的 Session + 单例模式
- 内部方法：`async def fetch_sse_volume(date)` / `async def fetch_szse_volume(date)` / `async def fetch_both_today() -> dict`
- 公开：`async def fetch_today() -> dict[date, total_amount_yi]`
- 调用 `src.utils.trade_date.get_trade_date()` 取日期
- `@async_retry(max_retries=3, delay=1.0)` 装饰 fetch_today

**verify**: `pytest tests/test_volume.py -v` 全绿

### 1.3 写 `turnover_service.py`（TDD）

**新增** `backend/macro/tests/test_turnover.py`：
- 合成公式：`(sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)`
- 4 个 case 与 volume 类似

**新增** `backend/macro/src/services/turnover_service.py`：
- 内部：`async def fetch_sse_turnover(date)` / `async def fetch_szse_turnover(date)` / `async def fetch_today()`
- 公式：与 skill `fetch_turnover_rate()` 一致

**verify**: `pytest tests/test_turnover.py -v` 全绿

### 1.4 写 `margin_service.py`（TDD）

**新增** `backend/macro/tests/test_margin.py`：
- mock `akshare.macro_china_market_margin_sh / sz` 返回带 `融资余额` 列的 DataFrame
- 单位换算：万元 → 亿元（÷100000000）
- 合并沪市 + 深市最新一行

**新增** `backend/macro/src/services/margin_service.py`：
- `async def fetch_today() -> dict[date, margin_balance_yi]`
- try/except akshare 异常，包装为 `{"status": "failed", "error": str(e)}`

**verify**: `pytest tests/test_margin.py -v` 全绿

### 1.5 全测回归

```bash
cd backend/macro && FRED_API_KEY=test_dummy_key ./.venv/Scripts/python.exe -m pytest tests/ -v
# 必须不出现新的 FAIL；旧的 test 不变
```

## Step 2 — 后端接入 /api/macro/data + update 端点

### 2.1 models.py

**修改** `backend/macro/src/models.py`：加 3 个 update data 类（参考 `DR007Data / DR007UpdateData`）：

```python
class VolumeData(BaseModel):
    date: date
    value: Optional[float] = None  # 两市成交额 (亿元)

class VolumeUpdateData(BaseModel):
    volume: VolumeData

class TurnoverData(BaseModel):
    date: date
    value: Optional[float] = None  # 换手率 (%)

class TurnoverUpdateData(BaseModel):
    turnover: TurnoverData

class MarginData(BaseModel):
    date: date
    value: Optional[float] = None  # 融资余额 (亿元)

class MarginUpdateData(BaseModel):
    margin: MarginData
```

并加到 `UpdateResponse.data` 的 union。

### 2.2 data_service.py

**修改** `backend/macro/src/services/data_service.py`：

1. `files` 加：
```python
"volume": self.data_dir / "volume.csv",
"turnover": self.data_dir / "turnover.csv",
"margin": self.data_dir / "margin.csv",
```

2. `result` dict（`_query_data_impl`）加：`"volume": [], "turnover": [], "margin": []`

3. `save_volume_data / load_volume` 等 3 对函数（参考 `save_dr007_data` 合并写模式）：
```python
def save_volume_data(self, df: pd.DataFrame, path=None) -> None:
    """append + 合并 + 按 date 去重"""
    # ... 抄 save_dr007_data 改字段名
```

4. `_query_data_impl` 末尾 hibor 处理之后追加 3 段（参考 hibor 模板）：
```python
volume_data = self.load_volume()
if not volume_data.empty:
    volume_data = volume_data.ffill()
    volume_filtered = volume_data[(volume_data.index >= start_date) & (volume_data.index <= end_date)]
    if "total_amount_yi" in volume_filtered.columns and not volume_filtered.empty:
        target_index = us_data.index if not us_data.empty else pd.date_range(start_date, end_date)
        volume_full = volume_data.reindex(target_index, method="ffill")
        volume_aligned = volume_full[(volume_full.index >= start_date) & (volume_full.index <= end_date)]
        result["volume"] = volume_aligned["total_amount_yi"].tolist()
```

### 2.3 routes.py

**修改** `backend/macro/src/api/routes.py`：

1. import 加：
```python
from src.services.volume_service import get_volume_service
from src.services.turnover_service import get_turnover_service
from src.services.margin_service import get_margin_service
```

models import 加 `VolumeData, VolumeUpdateData, TurnoverData, TurnoverUpdateData, MarginData, MarginUpdateData`

2. 第 1019 行 `_ALLOWED_DATA_TYPES` 加 `"volume", "turnover", "margin"`

3. 文件末尾追加 3 个 update 端点（参考 `update_dr007` 模板）：

```python
@router.post("/update/volume", response_model=UpdateResponse)
async def update_volume():
    """增量更新两市成交额 - 当日点（交易所官方 API）"""
    # ... 抄 update_dr007 改字段名 + fetch_today
```

类似 `update_turnover` / `update_margin`。

**不做 history 端点**。

### 2.4 验证命令

```bash
# 1) 启服务
cd backend/macro && FRED_API_KEY=test_dummy_key ./.venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8094 --reload &

# 2) 测 update/volume
curl -X POST http://127.0.0.1:8094/api/update/volume | head -c 300
# 期望：success=True 或 success=False（盘后才有数据），不抛 500

# 3) 检查 CSV
ls -la backend/macro/data/volume.csv
head -3 backend/macro/data/volume.csv

# 4) 检查 /data 响应
curl http://127.0.0.1:8094/api/data?start_date=2026-08-15 | python -c "
import json, sys
d = json.load(sys.stdin)
print('volume present:', 'volume' in d['data'])
print('volume len:', len(d['data'].get('volume', [])))
"

# 5) update/turnover + update/margin 同样
```

### 2.5 后端全测

```bash
cd backend/macro && FRED_API_KEY=test_dummy_key ./.venv/Scripts/python.exe -m pytest tests/ -v
# 必须不出现新的 FAIL
```

## Step 3 — 前端 Tab + Chart

### 3.1 types

**修改** `apps/macro/src/lib/types/economic.ts`：

```ts
export type TabType = 'treasury-exchange' | 'bonds' | 'fund-flow' | 'comparison' | 'commodities' | 'stock-indices' | 'liquidity-risk' | 'rates' | 'macro-signal' | 'market-sentiment';

export interface EconomicDataResponse {
  // ... 既有 ...
  volume?: (number | null)[];   // 两市合计成交额 (亿元)
  turnover?: (number | null)[]; // 加权换手率 (%)
  margin?: (number | null)[];   // 融资余额 (亿元)
}
```

### 3.2 useFilteredEconomicData

**修改** `apps/macro/src/lib/hooks/useFilteredEconomicData.ts`：

1. `getDefaultEconomicData()` 加：`volume: [], turnover: [], margin: []`
2. `timeFiltered` 构造末尾加：
```ts
volume: processedData.volume?.slice(startIndex, endIndex) ?? [],
turnover: processedData.turnover?.slice(startIndex, endIndex) ?? [],
margin: processedData.margin?.slice(startIndex, endIndex) ?? [],
```

### 3.3 MarketSentimentTab / Chart

**新建** `apps/macro/src/app/modules/economic/components/MarketSentimentTab.tsx`：参考 `RatesTab.tsx` 简化版
- 仅渲染 `MarketSentimentChart`，无 InitButton / RefreshButton（CSV 每日自动追加，无需前端触发）

**新建** `apps/macro/src/app/modules/economic/components/MarketSentimentChart.tsx`：参考 `RatesChart.tsx` 单图版本
- 3 条 trace：
  - volume（y 轴，亿元，橙色 `#f97316`）
  - turnover（y2 轴，%，黄色 `#eab308`）
  - margin（y3 轴或左内轴，亿元，绿色 `#22c55e`）
- `connectgaps: false` 缺失段断开

### 3.4 page.tsx

**修改** `apps/macro/src/app/modules/economic/page.tsx`：

1. 顶部 tabs 数组加：
```ts
{
  id: 'market-sentiment',
  label: '市场情绪',
  description: '两市成交额 + 换手率 + 融资余额（日级）'
}
```

2. 动态导入加：
```ts
const MarketSentimentTab = dynamic(() => import('./components/MarketSentimentTab').then(mod => ({ default: mod.MarketSentimentTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载市场情绪...</div>
});
```

3. `handleTabChange` 加 market-sentiment 默认 6M 分支
4. 渲染分支加 `<MarketSentimentTab ... />`

### 3.5 api.ts

**修改** `apps/macro/src/lib/modules/economic/api.ts`：
- 加 `updateVolume / updateTurnover / updateMargin` 三个方法（参考现有 `update*` 方法）

### 3.6 验证

```bash
# 类型检查 + 构建
cd apps/macro && pnpm build

# lint（next lint 弃用，跳过引导模式，详见 dr007 任务记录）
```

### 3.7 浏览器手动验证

1. 启 dev：`cd apps/macro && pnpm dev`
2. 访问 `http://localhost:3003/macro`
3. 切到「市场情绪」tab
4. 默认 6M 视图：3 条曲线可见（成交量曲线随调度天数延展）
5. 切换时间范围 1M/3M/6M/1Y/ALL：3 条曲线同步缩放

## Review Gate（必须全绿）

- [ ] `backend/macro`：`pytest tests/` 全绿，无新增 FAIL
- [ ] `apps/macro`：`pnpm build` 成功
- [ ] 浏览器手动验证：市场情绪 tab 切 5 个时间范围均正常
- [ ] `curl /api/data` 含 volume / turnover / margin 三个数组

## Rollback Point（每步可独立回滚）

| 步骤 | 回滚动作 |
|------|---------|
| Step 1 | `git revert` fetcher + test 即可 |
| Step 2 | `git revert` models/routes/data_service；3 个 update 端点不再注册 |
| Step 3 | `git revert` types/MarketSentimentTab/Chart；前端不会读 volume 等字段 |

**整体回滚**：3 次 `git revert` 即可回到 master 当前状态。

## 执行顺序与子代理

**默认主线程顺序执行**（步骤之间有强依赖）。

**建议**：不分 sub-agent，主线程按顺序跑 1 → 2 → 3，每步带 verify。

## Commit 策略

按现有仓库 conventional commits：

```
feat(macro): 后端新增两市成交额/换手率/融资余额 3 个 update 端点
feat(macro): 前端新增「市场情绪」tab（volume/turnover/margin 三曲线）
test(macro): volume/turnover/margin fetcher 单元测试
docs(macro): 数据更新端点规范补 3 行
```

4 个 commit（后端 / 前端 / 测试 / 文档）。

## 不要做的事（提醒）

- ❌ 不要 import `risk-appetite-skill` 任何模块
- ❌ 不要写 history 端点（不补历史）
- ❌ 不要碰 akshare 成交额/换手率接口（实测不稳）
- ❌ 不要改 `_ALLOWED_DATA_TYPES` 之外的其他 routes 逻辑
- ❌ 不要碰 nginx / GZipMiddleware / Cache-Control（属 perf 任务）
- ❌ 不要碰 localStorage 缓存 / 分层加载（属 perf 任务）