# PRD：首页门户升级 — nginx 内联 HTML 改静态驾驶舱

## 背景

当前首页是 [nginx/web.conf](../../../nginx/web.conf) `location = /` 里 `return 200` 的一行内联 HTML（8 个应用链接 + emoji，样式写死在字符串里）。零运行时依赖是它的优点，但：改一个链接要改 nginx conf 并 restart 容器；无任何数据（不知道服务死活、看不到关键数字）；一行字符串无法维护。

## 目标

把首页换成仓库内的静态 `index.html`：一个"个人数据驾驶舱"——每张应用卡片带服务状态点 + 关键数据（零点击可见），风格暖白纸感、数据密控件疏。**零新容器**，根路径可用性不回退（不依赖任何 app 容器）。

## 需求

### 1. 首页文件化

- 新增 `nginx/html/index.html`（单文件，内联 CSS/JS，无构建步骤）
- `web.conf` 的 `location = /` 从 `return 200 '<html>...'` 改为 serve 静态文件
- NAS nginx 容器需一次性加 bind mount（`nginx/html/` 目录 → 容器内路径），属 NAS 手动操作，写入部署文档

### 2. 应用卡片：链接 + 状态点 + KPI

8 个应用（dividend / douyin / rss / funds / macro / map / skills / kids），每张卡片：

- 名称 + 链接（点击进入应用，行为与现状一致）
- **状态点**：绿 = 对应后端 health 返回 200；红/灰 = 非 200 或超时（UI 诚实，不装活）
- ~~KPI 实时数据~~（**2026-10-09 用户拍板移除**：NAS 部署后确认不需要股息率/宏观/房价数字，8 张卡统一为「名称 + 状态点 + 一句话简介」；KPI 抓取代码与样式已整体删除）

### 3. nginx 转发补齐（health 可达性）

现状盘点（经 nginx 外部访问）：

| 后端 | health 实际路径 | 经 nginx 现状 |
|------|----------------|---------------|
| dividend | `/api/dividend/health` | ✅ 可达 |
| macro | `/api/macro/health` | ✅ 可达 |
| housing-map | `/api/map/health` | ✅ 可达 |
| fund-select | `/api/funds/health` | ❌ 被 `/api/funds/` rewrite 剥成 `/api/health` → 404 |
| skill-manager | `/api/health` | ❌ nginx 只转 `/api/skills/*` |
| douyin | `/health` | ❌ 无对外路由 |
| kids-catalog | `/health` | ❌ 无对外路由 |

需在 web.conf 补精确匹配 location 修复后四个（health 只返回状态，无敏感信息，可对外）。

### 4. 可用性与回退

- 任一后端挂掉：首页仍可访问，对应卡片显示"离线"（JS fetch 失败按卡片降级，不白屏）
- 回滚 = `git revert` web.conf + nginx restart；HTML 文件本身无副作用

## 约束

- 不新建任何 docker 服务、不新建 Next.js 应用（避开 basePath='' 冲突，dividend 仍独占全局 `/_next/static`）
- UI 风格：暖白纸底、系统字体、卡片网格；数据密控件疏（有主见默认值：卡片按使用频率排序）
- HTML 改动后**无需 restart nginx**（静态文件每请求重新 open）；conf 改动才需要 restart
- 本地预览：浏览器直接打开或 `python -m http.server`，API fetch 失败如实显示离线

## 验收标准

1. NAS 部署后 `curl -k https://web.duomi77.cn:9443/` 返回新静态页，`nginx -t` 通过。
2. 每张卡片有状态点；人为停掉一个后端（或本地预览 fetch 失败）时对应卡片显示离线，其余卡片正常，页面不白屏。
3. ~~至少 3 张卡片显示实时 KPI~~（2026-10-09 需求变更移除，8 卡统一仅状态点 + 简介）。
4. `docker compose -f docker-compose.nas.yml ps` 服务数不变（无新容器）。
5. 4 条补齐的 health 转发逐个 `curl` 验证返回 200。
6. DEPLOYMENT_FILES.md / 相关部署文档更新（NAS 挂载操作 + 新增 location 说明）。

## 不做

- 不做登录/鉴权、不做搜索、不做各应用数据的深钻（卡片点进应用看）
- 不做后端 summary 聚合接口（若现有接口响应过重，记入后续任务，第一版 KPI 挑轻量字段）
- 不改 dividend basePath、不动全局 `/_next/static`
