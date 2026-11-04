# 股息率 · 基本面资料阅读页前端契约

> 适用范围：`apps/dividend` 的独立基本面报告阅读页（`/quality-reader`，线上 `/dividend/quality-reader`）、
> 主页面阅读入口，以及弹窗与阅读页共享的报告正文组件。
> 触发时机：改动阅读页路由、阅读集合、URL 同步、线上前缀处理，或抽取/修改 `QualityReportContent` 时。
> 评分数据本身的契约见 [`../../backend/dividend-select/backend/quality-rating-contract.md`](../../backend/dividend-select/backend/quality-rating-contract.md)。

## 1. 边界

- 只改 `apps/dividend` 前端；**不新增后端接口**，不改动 `nginx/web.conf`，不改 `basePath`。
- 只读：阅读页不提交分析、不轮询任务、不调用 `/api/dividend/quality/*` 下的写接口（analyze / jobs / queue）。
- 数据源只有一个：`GET /api/dividend/quality` 的 `scores`（全量已落盘结果）。

## 2. 阅读集合与顺序

- 集合 = `scores` 的全部条目，**不受**主页面股息率阈值、筛选结果、收藏状态约束；`per_code` 与 `hermes_configured` 不作为可阅读与否的门槛。
- 排序固定为**六位股票代码升序**；身份用 `score.code`，不用数组下标，也不用 `scores` 的对象键。
- 新增报告会改变序号但不改变当前公司；当前公司被删除后进入「该公司的基本面资料暂不可用」状态，**不擅自跳到邻篇**。

## 3. URL 身份

- `code` query 参数是当前公司的唯一身份；页面不另存「选中下标」。
- 首次加载成功且地址里没有 `code` 时，用 `replaceState` 写入最小代码的首篇（零份结果不写）。
- 主动下拉/上下篇用 `pushState` 同步 `code`，**保留真实 pathname** 与来源参数（`fromTab` / `fromFav`），清掉 hash。
- 浏览器前进后退按 URL 还原公司；不要求恢复每家公司上次的滚动位置。
- 只有主动换篇执行「回顶 + 聚焦标题」；刷新与数据回填不抢焦点、不重置滚动。

## 4. 线上 `/dividend` 前缀

应用 `basePath` 为空，线上由 nginx 剥前缀（`location /dividend/ { proxy_pass http://dividend_frontend/; }`），
因此浏览器地址带 `/dividend` 而应用内路径不带。

- 前缀只能从**浏览器真实 `window.location.pathname`** 判定，正则 `/^\/dividend(?:\/|$)/`；`/dividend-other/` 不算线上。
- 不得硬编码 `/dividend`，也不得把 `Link href="/quality-reader"` 直接当线上入口（会离开 `/dividend/`）。
- 主页面 → 阅读页用普通同源 `<a>` 完整导航（不做 Next 客户端路由）：初始 href 用同目录相对 `./quality-reader`，挂载后按真实 pathname 计算绝对地址。
- 阅读页返回链接同样按真实 pathname 生成，且只在 hydration 后计算真实地址，SSR 阶段用同目录相对 `./` 兜底。
- API 路径始终是 `/api/dividend/quality`，**不随页面前缀拼接**。

## 5. 返回参数白名单

- 只保留 `fromTab`（`all` / `alerts` / `screening`）与 `fromFav`（仅 `all` 生效）。
- 旧书签 `tab=watchlist` 归一为 `all` + fav。
- 忽略任意 `returnUrl`，不允许外部地址。

## 6. 共享报告正文契约

`QualityReportContent`（`variant: 'modal' | 'reader'`）是弹窗与阅读页唯一的正文来源：

- 五维逐项展示，null 维度显示「未评分」；**不渲染 `weighted_score` / `stars` / `boundary`**。
- 不改写历史正文；`report_md` 为空时显示「暂无完整报告正文」，其余字段（摘要、五维、风险、关注点、元信息）仍可读。
- 权重标签只在此处定义一份，不在两个组件里各写一份。
- Markdown 插件沿用 `remarkGfm` + `remarkBreaks`，**不引入 `rehype-raw`**。
- `variant='reader'` 只增加阅读作用域样式（表格局部横滑、代码块横滑、长文本换行），不得改变弹窗的视觉密度与既有可观察行为。

## 7. 状态区分

| 状态 | 表现 |
|------|------|
| 首次加载 | 「正在加载基本面资料…」，返回入口可用 |
| 读取失败 | 错误 + 可读原因 + 重试；**不能伪装成空列表** |
| 合法空结果 | 「暂无基本面资料」+ 返回选股关注 |
| 指定公司不存在 | 「该公司的基本面资料暂不可用」+ 下拉占位「请选择已有资料」，上下篇禁用 |
| 正文为空 | 「暂无完整报告正文」，其余结构可读 |
| 刷新失败 | 非阻断提示 + **保留旧内容** |
| 刷新时新增/删除结果 | 保留所选 `code`；删除则进入不存在状态 |

主页面选股关注（screening）的阅读入口紧接“评级队列”，在结果工具栏同排，不再独占头部行；保持来源查询参数；入口高度与队列按钮一致，窄屏同组局部横向滚动，避免增加独立行。其他视图保留头部入口。

## 8. 手机阅读与可访问性

- 单栏；正文 17px / 行高 1.8；左右 ≥16px 留白（桌面 24px）；控件触摸区域 ≥44px；select 字号 ≥16px（避免手机自动缩放）。
- 底部翻页栏固定并适配 `env(safe-area-inset-bottom)`；正文底部留白与翻页栏高度共用 CSS 变量。
- 宽表格与代码块**局部**横滑，不产生整页横向滚动；长链接与长串用 `overflow-wrap` 换行。
- 桌面正文限宽 48rem，保持可读行长。
- 控件有可读名称（`选择公司` / `刷新资料` / `上一篇` / `下一篇`），有 `focus-visible` 轮廓与 `disabled` 状态；进度提示用 `aria-live="polite"`，避免整篇报告被重复朗读。

## 9. 验证

- 单测：`node --experimental-strip-types --test src/lib/quality-reader.test.ts`（纯函数：排序、code 选择、前缀判定、链接参数白名单）。
- E2E：`npx playwright test e2e/quality-reader.spec.ts e2e/screening.spec.ts`。写接口必须拦截并断言调用数为 0。
- 线上前缀用 Playwright route 模拟 nginx 剥前缀转发（**不能用 `**/dividend/**`，会误伤 `/api/dividend/*`**）；真实容器形态仍需按 `docs/dividend-testing-checklist.md` 做部署 smoke。
- 项目当前**没有 ESLint 配置**，`npm run lint`（`next lint`）会进入交互式向导不可用；`next build` 内建的类型检查可作为替代。
