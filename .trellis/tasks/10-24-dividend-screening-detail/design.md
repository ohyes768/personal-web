# 技术设计

## 视觉稿

`prototype.html`（同目录）：单文件交互原型，含三个列表视图（符合条件 / 未符合 / 待补数据）、个股详情弹层、独立评级弹层三态。配色与间距沿用 `apps/dividend/src/app/globals.css` 的纸感 token（paper / ink / rule / accent）。

## 改动边界

只动 `apps/dividend/src`：

- `lib/hooks/useQualityAnalysis.ts`（新）：从 ScreeningTab 抽出评级分数加载/分析/轮询。
- `components/ScreeningTab.tsx`：列表精简、详情入口、改用共享 hook。
- `components/ScreeningStockDetailModal.tsx`（新）：个股详情弹层。
- `components/QualityReportModal.tsx`：加「重评」入口与进度条（`onReanalyze` / `analyzing` / `progress` 新增可选 props，不传时行为与现在一致）。

`app/page.tsx` 不改（详情弹框不做收藏/对比，无需传入 compare 子集）。后端与 `lib/api.ts` 不改（所需方法已齐）。

## 组件与数据流

### useQualityAnalysis

把 ScreeningTab 现有内联逻辑原样抽出（行为不变的重构）：qualityScores、qualityConfigured、analyzing、qualityJob、qualityMessage、analyze(codes)、refreshScores；保留 requestId 自增、3s 轮询、卸载清理。实例留在 ScreeningTab，弹层经 props 复用同一实例——轮询状态单一来源，弹层关闭不中断 job。

### ScreeningStockDetailModal

props：`{ item: ScreeningItem | null, price: PriceItem | undefined, quality, onClose }`。打开与否由 `item != null` 决定，关闭置 null 即丢弹层状态。详情不做收藏/对比/重评，故不接 `watchlist` / `compare` / `onAnalyze`。

- 首屏渲染直接用行内 stock（DividendStock 已含 roe_history、年度 yield/dividend/avg_price、payout_ratio、eps、CAGR、shareholder_*、季度扣非字段）——打开不白屏。
- 打开时 `Promise.allSettled` 并行补拉，逐块独立降级：
  - `getStockDetail(code)` → dividend_history（分红明细）
  - `getBoardInfo({code})` → 行业/概念板块；localStorage 24h 缓存，key 前缀 `dividend-screen-board-info-`（模式同 DetailModal，前缀区分互不污染）
  - `getM120Data()` → 该股 M120，再 `getRealtimePrice({code, m120})` → 偏离度；现价/PE/PB 优先用列表已拉的 priceMap，缺失则该字段待补
- 每块独立 try/catch，失败显示「加载失败/待补」，不阻塞其他块。
- 评级弹框由 `ScreeningTab` 持有（`qualityModalCode` 状态不变）。列表点星级、详情内点「基本面评级」都走同一个入口；详情内入口先 `setDetailItem(null)` 再 `setQualityModalCode(code)`，实现两弹框互斥。
- 「重评」只存在于评级弹框：`QualityReportModal` 接收 `onReanalyze(code)`、`analyzing`、`progress`（可选，缺省时按钮不渲染，组件行为与现状一致）。点击后由 `useQualityAnalysis.analyze([code])` 提交，轮询状态在弹框内展示，完成后 `refreshScores` 更新 `qualityScores` → 弹框内星级/五维与列表评级列同步刷新。

### 区块 → 数据映射

| 区块 | 来源 |
|---|---|
| 状态与提示 | item.status / reasons / warnings（契约语义：reason=失败事实，warning=单季下滑） |
| 股息率年度序列 | stock.yield_2023/24/25、dividend_*、dividend_count_*、avg_price_*（窗口固定 2023–2025，不展示 2022/滚动年） |
| 三年均值 vs TTM | stock.avg_yield_3y + price.yield_ttm |
| 分红明细 | getStockDetail().data.dividend_history（明细表口径同 DetailModal 现有实现） |
| 盈利质量 | stock.roe_history、annual_net_profit_ex_non_recurring、net_profit_ex_non_recurring_yoy、net_profit_cagr_3y、eps、payout_ratio、previous/latest_quarter_* |
| 买点参考 | price.close/pe/pb、M120+偏离度、stock.high_price_2025 / low_price_2025 / 涨跌幅 |
| 筹码 | stock.shareholder_count / shareholder_change_pct / per_share_holding |
| 基本面操作列 | qualityScores[code] 是否存在 → 存在则「重评」，否则「分析」（非 eligible 行无分时为「待分析」文字） |
| 评级结果列 | qualityScores[code].weighted_score（1 位小数）+ .boundary（⚠️）；无分显示「-」 |

## 权衡

- 弹层 vs 路由页：弹层保留「扫 → 看 → 下一只」工作流，列表状态不丢；项目无详情路由先例。
- 详情入口 = 整行点击（勾选框、基本面操作、评级结果、收藏按钮除外）：扫视时不必精确命中文字。
- 评级拆成「基本面操作」+「评级结果」两列：操作（分析/重评）与结果（分数）是两种信息，混在一列会既看不清分数又堆控件。代价是列表从 7 列变 8 列。
- 列表「评级结果」列展示加权分（3.4），评级弹框内仍用星级+维度：列表是扫视/排序视角，需要可比数字；弹框是报告视角，星级+维度+markdown 更易读。**这推翻了 quality-rating-contract 原来的「加权分不对用户展示」禁令，契约已同步更新。**
- 详情头部只留「基本面评级」：收藏走列表第 7 列，避免同一动作两处入口；对比本轮不接，故详情不提供「加入对比」。
- 「重评」放进评级弹框而不是详情弹框：重评的对象是评级结果，入口与被操作对象同处一个弹框最自然；也顺带让详情头部只剩一个动作。
- 评级：用户拍板独立弹窗；详情页只放入口按钮与重评；契约禁止向用户展示加权分。
- 评级弹框与详情弹框**互斥**（详情内点「基本面评级」→ 关详情 → 开评级）：现有 `shared-ui/Modal` 每实例各持一份 `document.body.style.overflow` 与 Esc 监听，并存时关内层会提前解锁外层的滚动锁，Esc 也会一次关两层；z-index 固定 50 时层级还取决于渲染顺序。改为互斥后不需要改 `shared-ui/Modal`，行为与现在单独打开评级弹窗一致。
- 重评入口从列表移入详情页：降低列表控件密度；轮询提升到共享 hook 后与列表互不干扰。
- PE 不单调 `/pe` 接口：getPrices 的 PriceItem 已含 pe/pb，复用列表同源数据，避免第二次请求。

## 兼容与回滚

- DetailModal、shared-ui/Modal 不改行为（弹层宽度用现有 size 档位，必要时 className 放宽，同 DetailModal 先例）。
- QualityReportModal 只做加法：新增可选 props（不传时按钮不渲染，行为与现在完全一致），已有调用方无需改。
- 纯前端、单 commit，可整体 revert；无数据迁移、无新环境变量。
