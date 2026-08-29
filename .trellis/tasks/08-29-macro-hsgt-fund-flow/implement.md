# 实施计划：南向净买额+北向成交总额接入

依赖顺序：后端取数 → 存储/查询 → API → 前端。每步有独立验证，可分段执行。

## Step 1 后端取数层重写

- [ ] 重写 `backend/macro/src/services/fund_flow_service.py`：东财直调 + 分页 + 单位换算（详见 design.md 契约）
- [ ] 新增 `backend/macro/tests/test_fund_flow_service.py`（全部 monkeypatch requests，禁止真连）：
  - 分页终止（第 2 页空）
  - 百万→亿元换算精确断言（44732.81 → 447.3281）
  - 北向取 DEAL_AMT、南向取 NET/BUY/SELL 三列
  - date 从 TRADE_DATE 截前 10 位
  - 网络错误重试后仍失败 → 抛异常
- 验证：`.venv/Scripts/python.exe -m pytest tests/test_fund_flow_service.py -v`

## Step 2 存储与查询层

- [ ] `data_service.py`：重写 `save_fund_flow`（4 列 outer-join keep=last）；fund_flow 段列映射改 4 键；`TAB_SECTIONS`/`TAB_RESPONSE_FIELDS` 的 market-sentiment 加 fund_flow；`result` 模板同步；`INDICATOR_SECTIONS` 删 north_net 加 north_deal
- [ ] 检查 `append_data`/`_ensure_file_exists` 对既有旧 6 列文件的列不匹配行为；若报错则回补端点先删旧文件再写（记录在 PR 风险项）
- 验证：pytest 全量 `python -m pytest tests/ -v`（关注 data_service 相关既有测试是否引用旧列名）

## Step 3 API 层

- [ ] `models.py`：`FundFlowData`/`FundFlow`/`FundFlowHistoryItem` 等字段改新 4 键
- [ ] `routes.py`：`/fetch/fund-flow/history` 改调 `fetch_history("2014-11-17", 昨天)`；`/update/fund-flow` 改调 `fetch_recent()`（近 10 日）；两处 latest 快照装配同步
- [ ] 启动后端实测：`POST /fetch/fund-flow/history` → 检查 `data/fund_flow.csv` 行数（应 ~2741）、首行 2014-11-17、2026-08-28 北向成交额 2781.2163 亿
- [ ] 实测 `GET /data/market-sentiment` 含新字段；`POST /update/fund-flow` 重跑无重复行
- 验证：AC1 / AC2 / AC3

## Step 4 前端类型与 comparison

- [ ] `economic.ts` fund_flow 类型改 4 键
- [ ] `indicators.ts` 删 north_net 加 north_deal；`normalize.ts` 映射；`types.ts` 同步
- 验证：`pnpm build`（apps/macro）

## Step 5 市场情绪 Tab 新图

- [ ] 新建 `HsgtFundFlowChart.tsx`（双轴：北向成交额左 / 南向净流入右含 zeroline）
- [ ] `MarketSentimentTab.tsx` 挂第二张图；`useFilteredEconomicData` market-sentiment 分支补 fund_flow 切片
- [ ] `api.ts`：`initMarketSentimentHistory` 改 `Promise.all` 加 fund-flow；`updateMarketSentiment` 串行链尾加第 4 步
- 验证：`pnpm build` + 浏览器实测市场情绪 Tab 双图渲染、comparison 选"北向成交额+南向净流入"出曲线（AC4 / AC5）

## 风险点与回滚

- 旧 6 列 fund_flow.csv 若存在于部署环境：Step 2 验证列不匹配行为，必要时回补端点先 unlink
- 东财接口反爬变化：与 akshare 同源同风险，tenacity 重试兜底；失败时 update 返回 failed，调度次日 10 日窗口自愈
- 回滚：git revert 整个提交即可，无迁移无外部副作用

## task.py start 前检查

- [ ] prd.md / design.md / implement.md 三件齐
- [ ] implement.jsonl / check.jsonl 已填真实条目（非 _example）
