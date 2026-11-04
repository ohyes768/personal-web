# 基本面阅读页技术设计

## 边界与总体方案

独立 App Router 路由 `/quality-reader`，线上浏览器地址为 `/dividend/quality-reader`。沿用现有暖白纸面、墨色正文和暖橘强调色，以长文阅读为主。只改 apps/dividend 前端和相关文档，不增加后端 API 或改变 nginx/basePath。

页面首次请求全量已保存 QualityScore；之后翻篇均使用本地结果。主页面到阅读页采用同源完整导航，将阅读与主页面的行情请求、筛选状态、对比抽屉及队列轮询隔离。

## 页面结构

```text
← 返回股息率                         刷新资料
基本面资料阅读
[000001 公司名称                     ▾]
第 1 / 24 篇
─────────────────────────────────────────
公司名称 000001
数据日期 · 评分时间 · 分析耗时
Skill 版本 / 需重评提示

摘要
五维评分（维度 / 权重 / 得分）
主要风险
关注点
完整报告（Markdown）

─────────────────────────────────────────
[上一篇]             第 1 / 24 篇 [下一篇]
               手机底部安全区
```

- 页头不固定，避免占用手机阅读高度。底部导航固定，正文底部 padding 与导航总高度共用 CSS 变量，加 env(safe-area-inset-bottom)。
- 正文容器最大 48rem，手机水平 padding 16px，桌面 24px；正文 17px/1.8，辅助元信息至少 12px。选择框字号 16px 避免手机输入自动缩放。
- 顶部选择标签为「选择公司」，原生 select，名称长时不撑宽父级；进度表示当前序号，不当作已读记录。
- 按钮至少 44px 高，有 focus-visible 轮廓，disabled 状态同时保留文字对比；翻页使用普通 button，主导航使用 a。
- 切换后标题可程序聚焦（tabIndex=-1）并滚回顶部；刷新资料不抢焦点、不重置滚动。标题焦点传达新公司，状态提示用 aria-live=polite，避免整篇报告被重复朗读。

## 文件及职责

| 文件 | 操作 | 职责 |
| --- | --- | --- |
| `apps/dividend/src/app/quality-reader/page.tsx` | 新增 | 页面 metadata、Suspense、挂载阅读组件，不加载主页面组件。 |
| `apps/dividend/src/components/QualityReader.tsx` | 新增 | 选择、阅读状态、进度、翻页、query 同步、返回与刷新。 |
| `apps/dividend/src/components/QualityReaderEntry.tsx` | 新增 | 主页面两种首屏分支共用的入口，生成带返回视图的链接。 |
| `apps/dividend/src/components/QualityReportContent.tsx` | 新增 | 从原弹窗抽取纯报告内容，variant=modal/reader；不包含重评工具条。 |
| `apps/dividend/src/components/QualityReportModal.tsx` | 修改 | 保留 Modal、重评行为；内容改用共享组件。 |
| `apps/dividend/src/lib/hooks/useQualityReports.ts` | 新增 | 只读快照加载、刷新和错误状态，不发现/轮询分析任务。 |
| `apps/dividend/src/lib/quality-reader.ts` | 新增 | 稳定排序、代码选择、受控返回参数和页面链接的纯函数。 |
| `apps/dividend/src/app/page.tsx` | 修改 | 正常头部与加载骨架中加入入口，不改其业务 hook。 |
| `apps/dividend/src/app/globals.css` | 修改 | 仅增加 reader 作用域样式，不修改原弹窗视觉密度。 |
| `apps/dividend/e2e/quality-reader.spec.ts` | 新增 | 读取、导航、错误、响应式与前缀兼容测试。 |
| `apps/dividend/src/lib/quality-reader.test.ts` | 新增 | 代码排序、缺失选择与路径/返回参数规则单测。 |

## 共享内容契约

```ts
interface QualityReportContentProps {
  score: QualityScore;
  currentSkillVersion?: string | null;
  variant?: 'modal' | 'reader';
}
```

复用 QUALITY_DIMENSION_ORDER、QUALITY_DIMENSION_LABELS、formatAnalysisDuration、QualitySkillVersion。权重标签从原弹窗移到共享内容，避免两个来源。无论总评级是否完整，都展示五个维度，null 显示未评分；不渲染 weighted_score/stars/boundary。

ReactMarkdown + remarkGfm + remarkBreaks 沿用原配置，不添加 raw HTML 插件。阅读模式为表格提供独立 overflow-x:auto 容器；代码块可局部横滑，长文本 overflow-wrap:anywhere。新样式仅作用于 reader 变体，原弹窗的文本、元数据、重评状态和选择器可观察语义保持兼容。空 report_md 显示明确提示，其余结构仍可阅读。

## 数据和刷新状态

```ts
interface QualityReportsState {
  snapshot: QualityScoresResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}
```

- 首次 loading=true，成功后 snapshot 保存完整响应；空 scores 为合法空状态。
- 失败且 snapshot=null：整页错误 + 重试 + 返回；不能把失败当作空结果。
- 手动刷新期间保留 snapshot，禁用刷新按钮，翻篇仍可用；失败显示非阻断错误并保留快照。
- 使用请求序号/卸载标记防止迟到响应覆盖新请求，不更改共享 ApiClient。
- 只从 scores 生成列表；per_code 和 hermes_configured 不作为可阅读与否的门槛。
- 排序每次按 code 升序；以 code 而非数组 index 作为身份。新增结果会改变序号但不会改变当前公司。
- 刷新后当前 code 已删除则展示不存在提示，允许从下拉选择其他公司，不擅自跳到邻篇。
- 不自动轮询或前台恢复自动刷新；用户主动刷新才更新快照，避免长文阅读被异步替换。

## URL 与浏览器历史

| 场景 | 本地 | 线上 |
| --- | --- | --- |
| 默认阅读 | `/quality-reader` | `/dividend/quality-reader` |
| 指定公司 | `/quality-reader?code=000001` | `/dividend/quality-reader?code=000001` |
| 从选股进入 | `/quality-reader?fromTab=screening` | `/dividend/quality-reader?fromTab=screening` |
| 返回选股 | `/?tab=screening` | `/dividend/?tab=screening` |

1. 入口挂载时读取 window.location.pathname，只将 `/dividend` 或以 `/dividend/` 开头识别为线上前缀，其余为本地根。服务端/水合前入口使用同目录相对 href `./quality-reader`，不硬编码线上前缀。
2. 主页面保留的返回信息为 fromTab=all/alerts/screening 和 fromFav=1；旧 watchlist 规范化成 all+fav。忽略任意 returnUrl，不允许外部地址。只在 tab=all 时保留 fav。
3. 阅读页首次成功加载且没有 code 参数时选第一篇，并 replaceState 写入规范 code，保持 pathname/fromTab/fromFav；零结果不写 code。有 code 但非法或不存在时保持参数并显示缺失状态。
4. 主动下拉/上下篇时 pushState 同步 code，删除旧 hash，并保留真实 pathname。使用 useSearchParams 派生选中 code，History API 与当前 Next 版本同步需测试；若不能同步，改为页面内独立 popstate 订阅，不能双存索引与 code。
5. 浏览器前进后退按 URL 恢复公司。不要求恢复每家公司旧滚动位置；只有主动选篇执行回顶，不因刷新触发回顶。
6. 阅读页返回链接仅在 hydration 后根据真实 pathname 生成，以免服务器看到剥前缀地址造成错误链接；加载中也应渲染安全的同目录返回 href `./`。不依赖 history.back，保证直接打开也能返回。
7. 非空但不存在 code 的状态下，下拉显示「请选择已有资料」占位，底部导航禁用，直到用户明确选择。

## 错误与边界文案

| 状态 | 提示与行为 |
| --- | --- |
| 首次加载 | 正在加载基本面资料…；返回入口可用。 |
| 请求失败 | 基本面资料加载失败 + 可读错误原因 + 重试。 |
| 合法空结果 | 暂无基本面资料；请在选股关注完成分析后再来阅读 + 返回选股关注。 |
| 指定公司不存在 | 该公司的基本面资料暂不可用 + 选择已有资料；总集合为空时仍解释指定报告缺失。 |
| 正文为空 | 暂无完整报告正文；保留其余字段。 |
| 后续刷新失败 | 刷新失败，继续显示上次加载的资料 + 重试。 |
| 未知版本/耗时 | 复用现有「版本未知」「未记录」展示，不推算补值。 |

## 兼容、风险和回滚

- 无数据迁移、后台任务或新增依赖；不调用分析、取消、调序等写接口。
- 最大风险是无 basePath 应用的线上路径导航，其次是抽取内容导致旧弹窗变化。分别由前缀代理浏览器测试与完整 screening 回归覆盖。
- 全量 Markdown 响应可能变大，但现有接口已经返回全量；首版不顺手做分页存储改造。执行时记录实际响应体积作为后续性能依据，不在无证据时引入复杂缓存。
- 回滚只撤销阅读入口、独立页、专用 hook/工具、局部样式和共享内容抽取，恢复原弹窗即可；后端结果与分析任务均无需变动。
- 规划采用独立页优先，若实施发现现有代理下 Next 客户端路由问题，先保留跨页完整导航及 query 内历史，不扩展到全站路由迁移。
