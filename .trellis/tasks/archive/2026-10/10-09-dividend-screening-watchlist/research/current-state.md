# Repository evidence — 2026-10-09

- apps/dividend/src/app/page.tsx:328：当前筛选只有交易所、3.5% 股息率输入；约 524 行维护 all/alerts、fav=1 和旧 watchlist 链接。
- apps/dividend/src/lib/hooks.ts:49：默认 min_yield=3.5，avg_yield_3y 降序。
- backend/dividend-select/src/api/routes.py:392：/stocks 默认 min_yield=5，与页面不同；新增页须显式使用自己的条件，不依赖 API 默认值。
- backend/dividend-select/src/services/filter_service.py:170：三年分红规则当前固定 2023/2024/2025，页面必须明确实际窗口，不能假定随日期自动滚动。
- backend/dividend-select/src/data/financial_fetcher.py:49：ROE 取最新 12-31 年报加权净资产收益率，源数据中有历史年报但目前只输出一个年度值；需验证三年历史完整性。
- backend/dividend-select/src/data/financial_fetcher.py:203：目前仅计算最新季度单季扣非同比。前一季度需要基于相邻报告期计算，遵守季度契约。
- backend/dividend-select/src/services/shareholder_financial_reader.py:133：财务 Reader 目前仅返回 roe 和最新季度同比/标签，无三年 ROE、前一季度同比。
- apps/dividend/src/app/page.tsx:557：只看收藏是当前 stocksWithTechnical 的子集，阈值外收藏股会消失；应独立加载。
- apps/dividend/src/lib/watchlist.ts:41：已有单只幂等收藏接口；后端 /favorites/alerts/batch 是监控批量接口，不是批量收藏接口。
- backend/dividend-select/src/api/models.py:425：收藏包含 added_at、note、alerts，新流程须保留。
- 适用规范：financial-quarterly-contract.md（累计转单季/各股实际报告期）、code-type-guidelines.md（股票代码字符串保留前导零）。

本轮仅仓库取证与产品规划，不涉及外部行情或财务阈值有效性研究。

## ROE 决策更新
用户已确认三年平均 ROE 与最近年度 ROE 同时达标；现有持久化与 API 仅提供最近年度单值，需扩展保存历史、平均值和报告年度。历史数据源完整性尚未通过实时请求验证。
