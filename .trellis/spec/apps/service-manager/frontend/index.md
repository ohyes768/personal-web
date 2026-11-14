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
| 证书徽章按原因给准确说法，不笼统说「无效」（=证书坏了） | 自签证书显示「无效」红标 |

文案与配色集中在 `lib/status.ts`（`RUNTIME`/`HEALTH`/`URL_STATE`/`TLS_STATE`/`RELEASE_STATE`/`describeCheck`/
`portText`/`composeFileText`/`tlsInvalidReason`）；**不要在页面里手写状态字符串**。
颜色之外必须同时有文字，状态徽章都带 `title`。

## 3. 交互约束

- 列表**平铺**：不分分组 tab，全部服务直接列出。归属（谁维护哪些）由**标签**表达，
  筛选靠标签筛选栏按需过滤——不要用 tab 把服务藏起来（tab 是「默认只看得见一半」）。
- 台账条目只从 Docker 发现来（发现导入页）：列表页**没有「新增服务」入口**，
  但发现导入页的「（新建服务）」必须保留——从容器认领一组容器时仍要建台账条目。
- 每行要能看到「用途」（`description`），不用点进详情页才知道这条服务是干什么的。
- **标签体系**（形态照搬 skill-manager）：
  - 列表页每行显示自己的标签**药丸** + 一个「＋标签」按钮 → 打开 `TagEditor` 弹窗：
    已有标签点一下勾选/取消，输入框回车新建（重复、空白、超长要有明确提示），保存即整体替换。
  - 工具栏下方是**标签筛选栏**（`TagFilterBar`）：全库标签药丸排，点一下选中/取消，
    **多选是 AND**（同时具备才算命中），选中非空时给「清除标签」。
  - 候选词表取后端 `summary.all_tags`（**全库**），不要从当前列表派生——一搜索词表就缩水。
  - 点行内标签药丸 = 按该标签筛选；详情页点标签 = 回列表并带上 `?tag=xxx`。
  - 弹窗：`role="dialog" aria-modal`，`Esc` 关闭，保存期间禁用输入与按钮。
- **分类（category）与归属（ownership）都已退役**：界面上没有分类入口，也没有归属下拉；
  这两件事统一走标签。列表平铺，不分组 tab。
- **已下线的能力**（后端实现与数据仍在，只是界面不再暴露；要接回见 backend spec §2.10）：
  - **详情页 `/service/[id]`**：整个页面删除，路由 404；列表页不再有指向它的链接。
  - **URL·发布徽章 / 「巡检」按钮**：入口与发布的数据还在库里，但列表只展示**运行**与**健康**
    两个维度（URL/证书另见下条）。
  - ~~入口维护 / 主入口列 / 证书徽章~~ → **已恢复**（2026-11-14）：列表页有「主入口」与「证书」两列，
    URL **行内可编辑**（点「改」/「登记」→ 输入框 → 回车或点「保存」）；类型与是否查证书
    由**后端按 URL 判定**（内网 IP → internal 不查证书，其余 external，`https` 才查证书），
    前端不自己算。证书列显示状态徽章 + 到期天数，无效证书写原因（自签 / 不受信任 / 域名不符 / 链已过期）。
  - **组件明细**（镜像 / 部署路径 / 数据卷）：列表页不给，去 Docker 那边看。
  - **资源总览的域名 / 证书视图**：数据源是入口，只保留**端口**视图。
  - **单条服务的定时与手动检查**：只保留全局「扫描容器」（后台本来每 60 秒自动扫一次）。
  - **解绑 / 换绑组件**：暂不做；发现导入页仍是唯一能改组件归属的地方。
- **列表页是台账的唯一维护面**：名称、用途在**行内编辑**（点「编辑」→ 名称变输入框、
  用途变文本框 → 保存/取消），标签走 `TagEditor` 弹窗，移除台账条目走行内「移除」按钮
  （confirm 写明「只影响台账，容器照常运行」）。
  保存成功后就地更新本地数据，**revision 必须用后端返回值覆盖**，否则下一次 PATCH 会 409。
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

e2e 跑在 NAS 容器栈上（后端也在容器里）时，写操作需要后端放行回环来源：
Next rewrite 会把 `Host` 改写成后端容器地址，后端按 `Origin == Host` 判同源就拒了。
compose 默认已带 `SERVICE_MANAGER_ALLOWED_ORIGINS=http://127.0.0.1:3012,http://localhost:3012`，
所以 `pnpm exec playwright test` 直接可用；也可把 `SM_E2E_BASE_URL` 指到 nginx 入口
（如 `https://web.duomi77.cn:9443`）跑生产拓扑——那条路径 nginx 保留 Host，写操作本来就能过。

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
