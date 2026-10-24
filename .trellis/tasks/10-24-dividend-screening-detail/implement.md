# 执行计划

前置核对：Modal 共享组件 size 档位是否够宽（QualityReportModal 用 lg）；useCompare 的参数类型 DividendStock 与 ScreeningItem.stock 兼容。

1. 抽 `useQualityAnalysis` hook（纯重构，行为不变）
   - 验证：ScreeningTab 评级交互不变（首屏加载、分析、3s 轮询、重试失败、hermes 未配置置灰）
2. ScreeningTab 列表精简（R1/R2）
   - eligible 8 列；excluded/insufficient 视图条件渲染原因列（colSpan 同步调整）
   - 评级拆两列：「基本面操作」（无分→分析/待分析，有分→重评）+「评级结果」（weighted_score 1 位小数 + boundary ⚠️，无分→-）
   - 整行点击打开详情（勾选框/基本面操作/评级结果/收藏按钮 stopPropagation）；行业取 stock.sw_level1，缺失显示「—」
   - 验证：三种视图切换、勾选/收藏/批量操作全部可用
3. ScreeningStockDetailModal 骨架：头部条 + 状态与提示块（头部只接基本面评级入口，不接收藏/对比/重评）
4. 股息率块 + 盈利质量块（行内数据即时渲染，不等待网络）
5. 分红明细 + 买点参考 + 筹码块（allSettled 补拉、逐块降级、板块缓存）
6. 评级入口 + 重评接入共享 hook
   - 详情内「基本面评级」入口：先关详情再开 QualityReportModal，两弹框互斥；shared-ui/Modal 不改
   - QualityReportModal 加可选 props：`onReanalyze(code)`、`analyzing`、`progress`；不传时按钮不渲染，行为与现状一致
   - 重评进度显示在评级弹框内；完成后星级与五维就地更新，列表评级列同步
7. 质量检查：`pnpm lint`、`pnpm build`；dev server 手动 QA 对照 prd AC1–AC6
8. spec 更新（screening-watchlist-contract 补 UI 口径；quality-rating-contract 的「加权分不对用户展示」已改）+ commit

回滚点：单 commit 整体 revert。

验证命令：

```bash
cd apps/dividend && pnpm lint && pnpm build
```
