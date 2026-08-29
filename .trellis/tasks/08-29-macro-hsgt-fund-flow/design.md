# 技术设计：南向净买额+北向成交总额接入

## 架构与边界

改动集中在三个层面，全部为替换式改造（旧 fund_flow 链路整条换掉），无跨服务影响：

```
东财 datacenter-web API (RPT_MUTUAL_DEAL_HISTORY)
  ↓ fund_flow_service.py（重写：requests 直调 + tenacity 重试 + 分页）
  ↓ data_service.py（save_fund_flow 新 4 列；market-sentiment 段加入 fund_flow）
  ↓ routes.py（/fetch/fund-flow/history 全量、/update/fund-flow 增量；models.py 字段）
  ↓ 前端 economic.ts 类型 + MarketSentimentTab 新图 + api.ts 初始化/更新链
```

## 数据流与契约

### 取数层（fund_flow_service.py）

```python
class FundFlowService:
    EASTMONEY_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    # MUTUAL_TYPE: "005"=北向合计, "006"=南向合计
    def _fetch_page(mutual_type: str, page: int, page_size: int = 500) -> list[dict]
        # params: reportName=RPT_MUTUAL_DEAL_HISTORY, columns=ALL,
        #         filter=(MUTUAL_TYPE="005"), sortColumns=TRADE_DATE, sortTypes=1
        # 返回 data 列表；空页 = 翻页终止
    def fetch_history(start_date, end_date) -> Dict[str, pd.DataFrame]
        # 005 取 DEAL_AMT → north["北向成交额"]
        # 006 取 NET_DEAL_AMT/BUY_AMT/SELL_AMT → south[三列]
        # 单位: 原始百万元 ÷ 100 → 亿元；date 从 TRADE_DATE 截取前 10 位
    def fetch_recent(days=10) -> Dict[str, pd.DataFrame]  # 增量窗口，复用 fetch_history
```

- 空值处理：北向 NET/BUY/SELL 为 null 属预期（不取）；南向三列理论上全量有值，若 null 保留 NaN 由 dropna 剔除
- 复用现有 `akshare_retry`（tenacity，requests 传输层错误 3 次指数退避），改名或直接复用均可
- 对齐 baostock_service 模式：方法内按需 requests，失败不抛异常的地方在 service 层返回数据；网络层错误重试后仍失败则抛，由路由层兜底

### 存储层（data_service.py）

- `data/fund_flow.csv` 新 4 列：`北向成交额, 南向净流入, 南向买入, 南向卖出`（亿元）
- `save_fund_flow(data: Dict[str, pd.DataFrame])` 重写：north df 1 列 + south df 3 列，按 date outer-join，keep=last 幂等（复用 `append_data` 现有语义）
- 旧 CSV 不存在，无需迁移；若部署环境存在旧 6 列文件，`_ensure_file_exists` 对不匹配列的处理需检查（列不同会怎样——实现时验证，必要时删除重建，见 implement.md 风险点）

### 查询层（data_service.py）

- fund_flow 段读取映射改：`{"北向成交额": "north_deal_amount", "南向净流入": "south_net_flow", "南向买入": "south_buy", "南向卖出": "south_sell"}`
- `TAB_SECTIONS`/`TAB_RESPONSE_FIELDS` 的 `"market-sentiment"` 加入 `"fund_flow"`
- `result` 初始化模板里 `fund_flow` 字段结构同步为 4 键
- `INDICATOR_SECTIONS`：删 `"north_net"`，加 `"north_deal": "fund_flow"`；`south_net` 映射不变（仍指 fund_flow 段）

### API 层（routes.py / models.py）

- `FundFlowData` 字段改为新 4 键；`FundFlow` 装配处同步
- `/fetch/fund-flow/history`（routes.py:1532）：调 `fetch_history("2014-11-17", 昨天)`，`data_service.save_fund_flow`，响应 message 带行数
- `/update/fund-flow`（routes.py:1620）：增量逻辑改调 `fetch_recent()`（近 10 自然日窗口，缺口自愈），其余锁/日志结构保持
- scheduler.json 不动（`/update/fund-flow` 路径未变）

### 前端（apps/macro）

- `economic.ts`：`fund_flow` 类型改 4 键；`FundFlowHistoryItem` 等历史模型若仅后端用则同步检查
- 新组件 `HsgtFundFlowChart.tsx`（放 economic/components/，复制 MarketSentimentChart 双轴模式）：
  - trace1 北向成交额 → y 左（金额亿元）
  - trace2 南向净流入 → y2 右（金额亿元，shape 属性加 0 线用 `zeroline: true`）
- `MarketSentimentTab.tsx`：现有图下方加第二张图卡片；`useFilteredEconomicData` market-sentiment 分支补 fund_flow 切片透传
- `api.ts`：`initMarketSentimentHistory` 改为 `Promise.all([volume-turnover, fund-flow])`（两个 /fetch 端点各自独立锁，可并行；与 updateMarketSentiment 的"必须串行"不同——那是 update 全局锁）；`updateMarketSentiment` 串行链尾加 `/update/fund-flow`
- comparison：`indicators.ts` 删 `north_net` 加 `north_deal`（label"北向成交额"）；`normalize.ts` `north_deal → data.fund_flow?.north_deal_amount`；`types.ts` 同步

## 权衡记录

- **直调东财原始 API 而非等 akshare 修复**：akshare 与东财同源同 reportName，我们只补它漏映射的字段；风险等价，收益是立刻可用
- **北向成交笔数 DEAL_NUM 不落库**：当前无消费方，将来要时 API 还在（YAGNI）
- **增量窗口 10 自然日而非 1 日**：对齐 baostock fetch_today 自愈模式，节假日/断连缺口次日自动补上
- **删 north_net 不做兼容期**：该指标 2024-08 后本来就全空，图表早已断线，无真实用户依赖

## 回滚

- 代码回滚后旧服务恢复原状（写入死数据源），CSV 多出的 4 列文件不影响旧代码读旧列——但旧代码 `_ensure_file_exists` 若按旧 6 列校验会写旧列并存，无害
- 无数据库迁移、无外部副作用，纯文件+代码改动，git revert 即可
