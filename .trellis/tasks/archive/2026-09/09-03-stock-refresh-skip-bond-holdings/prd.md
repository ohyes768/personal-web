# 股票宇宙刷新跳过债券季报拉取

## Goal

股票宇宙（`funds_stock.yaml`）刷新不再请求东财债券季报（`zqcc` 接口），消除无效请求与「季报持仓拉取失败 xxx: no text parsed from document」日志噪音。债券季报数据只服务债基筛选的持仓分析（利率债/信用债/可转债占比、前五大集中度，`fund_holdings_bond` 表），股票 tab 无任何消费方。

## Background

- `snapshot_fund`（`src/services/refresh_service.py:87-98`）对「非股票型且非 QDII」的基金都拉债券季报；短路按 `fund_type` 字符串判断，**混合型（股票 yaml 里 43 只）全部命中**。
- 混基多数年度无债券持仓披露，东财返回 `content:""`，`pd.read_html` 抛 `no text parsed from document`，被 catch 后仅 warn。失败路径不写缓存，每次刷新重复请求。
- 债基 yaml（31 只）里也含混合/QDII，这些是债基 tab 需要持仓分析的对象，**必须继续拉**。因此不能把「混合型」加进类型短路——宇宙归属才是真相源（与 universe-split 任务决策一致）。

## Requirements

1. `snapshot_fund` 增加显式开关（如 `fetch_holdings: bool = True`），为 False 时完全跳过第 3 步（债券季报拉取 + `fund_holdings_bond` 写入），不发 HTTP 请求。
2. `refresh_stock_funds_sync`（`src/scheduler/tasks.py:131`）调用时传 `fetch_holdings=False`。
3. `refresh_configured_funds_sync`（债基）行为不变：仍按现状拉取。
4. 删除 refresh_service.py:87-95 的 `fund_type` 类型短路判断——宇宙分流后按类型猜的兜底不再需要（债基宇宙内股票型/QDII 也应跳过，因为它们的季报无债券表，属于同样的无效请求 + warn 噪音）。跳过时不再发起请求即可，无需额外日志。

## Constraints

- 不改 `holdings_fetcher.py` 的缓存与解析逻辑（失败缓存优化不在本次范围）。
- 不动 phase2-A/2-B（benchmark / risk）。
- 改动仅限 `refresh_service.py` + `scheduler/tasks.py`（及对应测试）。

## Acceptance Criteria

- [x] `refresh_stock_funds_sync` 刷新全程对任何基金（含混合型）零 `zqcc` 请求、零「季报持仓拉取失败」warn
- [x] 股票宇宙刷新后 `fund_holdings_bond` 中股票 yaml 独有代码的 `updated_at` 不变（不写持仓）
- [x] 债基刷新路径行为与现状一致（测试通过即可证明）
- [x] `pytest tests/ -v` 全过；`snapshot_fund` 新增开关有用例覆盖（跳过时不发请求）

> 验证：113 passed / 2 failed；失败为 `TestFeeContract` 预存环境失败（本机缺 `personal-web/cache/fees_*.json` 夹具，与本次改动无关，干净树同样失败）。
