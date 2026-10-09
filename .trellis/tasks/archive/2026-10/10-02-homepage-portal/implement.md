# Implement：首页门户升级

前置：PRD / design 已评审；NAS 挂载操作需要用户在 NAS 上执行（步骤 5）。

## 步骤

1. **写 `nginx/html/index.html`**
   - 按 design §3：APPS 注册表 + 暖白纸卡片网格 + 状态点 + KPI
   - 无 JS 时卡片和链接仍可用（渐进增强）
   - → 验证：浏览器直接打开 `nginx/html/index.html`，8 张卡渲染正常、fetch 失败全部显示离线不报错（console 仅预期的 fetch 错误）

2. **确认 KPI 字段**（实现中随时做，不单列）
   - dividend `/api/dividend/stocks` 排序方向与字段名（本地起后端或看 `StockListResponse` 模型）
   - macro `/daily-snapshot` 字段；map `/market-reference` 字段

3. **改 `nginx/web.conf`**
   - `location = /` 替换为 root 方案（design §2.1）
   - 补 4 条 health 精确匹配（design §2.2）
   - → 验证：`docker run --rm -v .../web.conf:/etc/nginx/conf.d/web.conf nginx nginx -t` 或 NAS 上 `docker exec nginx nginx -t`（本地无 nginx 容器则只在 NAS 验证）

4. **本地集成验证**（可选，若本地 docker 可用）
   - `docker compose up -d` 起部分后端 + 临时 nginx 挂 web.conf/html，curl `/` 与 4 条 health
   - 本地不具备时跳过，直接走 NAS 验证（步骤 6 覆盖）

5. **NAS 一次性操作**（用户手动或远程执行，先于新 conf 部署）
   - nginx 容器 compose 加挂载 `<仓库>/nginx/html:/var/www/personal:ro`
   - `docker compose -f ~/-/nginx/docker-compose.yml up -d nginx`（重建容器挂载生效；旧 conf 仍在用，无影响）

6. **NAS 部署与验证**
   - `./scripts/deploy-nas.sh nginx`
   - → 验证清单：
     - `curl -k https://web.duomi77.cn:9443/` 返回新 HTML（标题/卡片关键词）
     - `curl -k .../api/{funds,skills,douyin,kids}/health` 各返回 200（新加 4 条）
     - `curl -k .../api/{dividend,macro,map}/health` 仍 200（未破坏旧路由）
     - `curl -k .../dividend/` 等 8 个应用入口各返回 200（未破坏应用路由）
     - 浏览器打开首页：状态点全绿、3 张 KPI 卡有数值
     - 停一个后端（如 `docker stop kids-catalog-backend`）→ 对应卡变红，其余正常；验证后 `docker compose up -d` 恢复

7. **文档更新**
   - `DEPLOYMENT_FILES.md`：nginx 小节补 html 挂载与新 location
   - `CLAUDE.md` 或 `docs/`：首页改静态文件的说明（一句话级别）

8. **收尾**
   - `python ./.trellis/scripts/task.py` 走 Phase 3（spec 更新按需、commit、archive）

## 回滚点

- 步骤 3 后：`git checkout nginx/web.conf`（未部署即无影响）
- 部署后：`git revert` web.conf commit + `./scripts/deploy-nas.sh nginx`
- `nginx/html/` 目录任何时候留着都无害

## 明确不做（防蔓延）

- 不改任何 app 代码 / basePath
- 不新增 docker 服务
- 不做 rss/douyin/funds/skills/kids 的 KPI（后续任务）
