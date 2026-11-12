# service-manager 前端契约（NAS 服务管理台）

> 来源：11-11-nas-service-manager（V1）。改 `apps/service-manager` 时读本文。
> 通用前端约定见 `.trellis/spec/frontend/index.md`；新服务接入见 `.trellis/spec/guides/new-service-onboarding.md`。

## 1. 接入形态

- basePath `/services`，端口 3012；**纯前端无 BFF**：`fetch('/api/services/*')`，dev 由 `next.config.mjs`
  的 rewrite 代理到后端 `/api/*`（`basePath: false` 必须保留，否则 source 会被拼成 `/services/api/...`），
  生产由 nginx 剥前缀直转。
- 返回首页用原生 `<a href="/">`（Next `Link` 会带 basePath 指到 `/services`）。
  `eslint.config.mjs` 里按此契约关掉了 `@next/next/no-html-link-for-pages`，改回 Link 会让首页入口 404。
- 会话 cookie 是 `HttpOnly`：前端**不读、不存**口令或 Token；未登录只渲染 `SessionGate` 的登录表单。

## 2. 状态展示铁律

| 规则 | 反例 |
|---|---|
| 五个维度各自出徽章，不用一个绿灯抹平 | 服务行只显示一个「正常」 |
| Docker health 未配置显示「-」（该维度不适用），**不显示「健康」** | 把 `not_configured` 映射成 ok |
| 界面不写只有内行懂的缩写：列头写「证书」不写「TLS」 | 表头出现 `TLS`/`IP`/`SLA` 等术语 |
| 失败但保留旧结果时，必须写出「上次成功 X 分钟前」 | 只显示红色「失败」，不标旧值时间 |
| `stale` 数据要显式标「数据已陈旧」 | 旧值当当前值用 |
| 端口页永久显示「不包含宿主进程全部监听，不能据此证明端口空闲」 | 省略这句提示 |
| 证书 `invalid` 要写原因（自签/域名不符/链过期/不受信） | 只显示「无效」 |

文案与配色集中在 `lib/status.ts`（`RUNTIME`/`HEALTH`/`URL_STATE`/`TLS_STATE`/`RELEASE_STATE`/`describeCheck`/
`portText`/`composeFileText`/`tlsInvalidReason`）；**不要在页面里手写状态字符串**。
颜色之外必须同时有文字，状态徽章都带 `title`。

## 3. 交互约束

- 列表按「自己开发的 / 其他」分两个 tab（`role="tablist"` + `role="tab"`）：
  归属由后端 `summary.own_projects` 与每项的 `projects` 判定，
  **前端不硬编码项目名**（改了 `SERVICE_MANAGER_OWN_PROJECTS` 就生效）。
  还没关联容器的服务（人工登记）归第一组；搜索 / 分类 / 只看异常在 tab 内照常生效，tab 上带各自的数量。
- 所有用户录入/展示的 URL 走 `SafeLink`：只有 `http(s)` 才渲染成可点链接，其余退化成纯文本。
  发布正文用 `white-space: pre-wrap` 的 `<div>` 显示原文（不注入 HTML）。
- `PATCH` 409（revision 冲突）要提示「请刷新后重试」并重新拉取；不要静默覆盖。
- 删除服务/解绑组件都要 `window.confirm` 并写明「只影响台账，容器照常运行」。
- 复制用 `CopyButton`，成功即时反馈；复制失败也要说话（不能静默）。
- 表格列多时套 `class="table-scroll"` + `table.cols-fit` + `col-*` 宽度类，
  否则长容器名会把表格撑到必须横向滚动。

## 4. 可访问性与响应式

- 375px 下五个页面**不得出现横向滚动**（e2e 逐页断言 `scrollWidth - clientWidth <= 1`）。
- 导航、按钮、输入都要键盘可达，`:focus-visible` 有 2px 外框（全局 CSS 已有，别在页面里覆盖掉）。
- 空状态要区分：没数据 / 未配置 / 未检查 / 检查失败，四种文案不同。

## 5. 验证命令

```bash
cd apps/service-manager
pnpm exec eslint .          # 0 problems
pnpm exec tsc --noEmit      # 0 error
pnpm build                  # standalone 产物
pnpm exec playwright test   # 16 用例（desktop + 375px）
```

e2e 前置：后端 8102（`SERVICE_MANAGER_ADMIN_PASSWORD=devpass`）+ 前端 3012 已启动；
`SM_E2E_PASSWORD` 可覆盖口令。本机无法下载 Playwright 自带 Chromium，`playwright.config.ts` 用
`channel: "chrome"` 复用宿主机 Chrome。

## 6. Wrong vs Correct

```tsx
// Wrong：把 auth_required 也当成失败，或把未配置 health 当健康
{status.url === "reachable" ? "正常" : "异常"}
{status.health === "not_configured" ? <span className="badge ok">健康</span> : ...}

// Correct：分维度语义，未配置就说未配置
<StateBadge tone={URL_STATE[status.url]} title={describeCheck(status.url_check)} />
<StateBadge tone={HEALTH[status.health]} title="Docker health 未配置时会显示「未配置检查」" />
```

```ts
// Wrong：探测地址填 localhost（容器内指管理台自身）
probe_url: "http://localhost:3003/"

// Correct：填 NAS 可达地址或同网络容器名；后端会 400 拒绝 localhost
probe_url: "http://dividend-backend:8092/api/health"
```
