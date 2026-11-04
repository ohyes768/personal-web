# 源文件签名快照缓存契约

> 建立于 2026-11-04（11-02-dividend-page-load-speed）。适用 `backend/dividend-select`
> 全部"读 CSV → 派生数据"链路；前端按 Tab 按需加载的请求边界约束一并记录。

## 1. Scope / Trigger

- 任何给读取类接口（stocks/m120/prices/*status）加缓存、加查询参数、或把同步
  Pandas 计算移出事件循环的改动。
- 新增派生快照（按代码索引的 map、合并结果等）时必读。

## 2. 契约

### 签名与失效

- 缓存 key 是源文件的**签名 = (实际路径, mtime_ns, size)**（`versioned_snapshot.file_signature`）。
  禁止固定 TTL 作为唯一失效手段：文件替换、切换季度文件（`find_latest_aux_file`
  按 mtime 选最新）、删除后补齐，都必须在下一次读取自动生效。
- 源不可用时签名为 None，**None 不发布缓存**：每次重新探测，补齐后自然恢复。
- 构建抛异常时不发布任何缓存（坏文件不会变成永久空快照），下一次请求重试。
- 构建前后各探测一次签名，源在构建期间被替换则有界重试（`VersionedSnapshot`，
  默认 3 轮）。
- 快照对象是共享只读的：消费者不得修改返回的 DataFrame/dict。

### 各链路现状

| 快照 | 缓存对象 | 失效依据 |
|---|---|---|
| `ShareholderReader._snapshot / _map_snapshot` | df / 按代码索引 map | 股东户数汇总 CSV 签名 |
| `FinancialReader._snapshot / _map_snapshot` | df / row_to_data map | 财务指标汇总 CSV 签名（strict 读语义保留） |
| `StockInfoService._sw_snapshot` | 申万映射 df | 个股申万行业映射 CSV 签名（修复了旧版加载一次永不更新的问题） |
| `M120Service._snapshot_cache` | 选中周快照 df | **当前周写路径 + 当前周文件签名 + 选中快照签名**（三者任一变化失效；当前周文件从无效被 refresh 修复时必须切换到新快照） |
| `M120Service._price_cache` | 价格 dict | 实时价格 CSV 签名 |
| `M120Service._deviation_cache` | 合并 dict | (快照签名, 价格签名) |
| `DataReader` | 主 CSV df | 既有 30s TTL + mtime；已加双检锁（并发 miss 只读一次文件） |

### 线程隔离

- uvicorn 单 worker 是前提，不靠加 worker 解决阻塞。
- 读取类 async 路由的同步 Pandas 组装放 `asyncio.to_thread`：`health`、
  `get_stocks`（`_build_stock_list`）、`get_m120_stocks`（`_build_m120_list`）、
  `get_prices`（`_build_price_list`）、`get_m120_status`、`get_financial_status`。
- 被内部直接调用的路由新增查询参数时，用 `Annotated[..., Query(...)] = None` 等普通 Python 默认值；FastAPI `Query(None)` 默认对象不会在 Python 调用中自动解析。必须测试真实路由调用链，不能只 mock `get_stocks`（2026-11-04：screen/quality analyze 曾因此触发 `Query.strip` 异常）。
- 内部 `await get_stocks(...)` 的调用方（screen、quality analyze）保持不变，
  隔离在 get_stocks 内部完成。
- 刷新任务互斥、调度器生命周期、原子发布语义不受影响（refresh 的写路径经
  `os.replace`/`atomic_csv` 原子替换，签名变化自动失效）。

### /stocks codes 精确过滤

- `GET /stocks?codes=90,600000`：逗号分隔，读入口 `zfill(6)` 归一，非六位数字
  返回 422（与 batch favorites 同口径）；空/None 保持原行为。
- 与筛选参数取**交集**：`codes` 先过滤，`min_yield>0` 等筛选继续生效；
  前端收藏资料请求用 `min_yield=0&codes=…`（阈值外收藏保留，缺资料前端占位）。

### 前端请求边界（apps/dividend）

- 主列表（`useDividendData`）与全量 M120（`useTechnicalData`）仅"全部"Tab 启用；
  Tab 切换由 enabled 驱动重拉，响应带序号防旧响应覆盖新筛选。
- 挡位监控首屏链路：favorites/alerts-status → 挡位代码 → `/prices?codes=`（现价
  不等资料/M120）；资料走 `/stocks?min_yield=0&codes=`，缺失时用挡位 item 名称
  占位，条目不消失。
- 挡位设置弹框在无全量 M120 的 Tab 打开时，用 `priceToTechnical`（/prices）补
  close/realtime/PE/PB/yield_ttm，M120/偏离度保持空。
- 初始化只请求一次 `/financial/status`（由 checkAuxStatus 一并提供 missing_codes）。

## 3. Tests Required

`tests/test_snapshot_cache.py`：同签名复用、签名变化重建、None 不缓存（补齐恢复）、
坏文件不发布、并发构建去重、reader 的原地更新/新季度文件/删除重建、M120 当前周
修复失效、价格更新失效、跨周失效、codes 过滤（前导零/交集/无匹配/422/None 原行为）、
to_thread 并发冒烟。

## 4. Wrong vs Correct

Wrong：给读取接口加固定 TTL 缓存；缓存住空结果；在 async def 里直接跑重 Pandas
以为"已经是 async 了"；用新增 worker 解决阻塞。
Correct：签名失效 + 失败不发布 + 消费者只读；同步组装进 `asyncio.to_thread`；
单 worker 保持任务互斥与原子发布。
