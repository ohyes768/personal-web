# NAS 服务管理台上线清单

> 目标：在 NAS 上按现有 monorepo 方式部署 `service-manager`（前端 3012 / 后端 8102 / socket-proxy），
> 上线后能在 `/services` 记录服务台账、读取容器元数据、检查 URL 与证书、浏览上游 Release。
> 设计权威见 `.trellis/tasks/11-11-nas-service-manager/design.md`。

## 1. 前置检查

```bash
# 端口未被占用（应为空输出）
ss -lntH | grep -E ':(3012|8102)\b'

# 镜像可获取（实施时锁 digest；这里先确认能拉）
docker pull tecnativa/docker-socket-proxy:0.2.0

# Docker 版本（客户端要能协商；NAS 实测 29.1.3）
docker version --format '{{.Server.APIVersion}}'
```

## 2. 仓库根 `.env` 补齐三项

```bash
# 管理口令（前端登录用；建议 16 位以上随机串）
SERVICE_MANAGER_ADMIN_PASSWORD=

# 会话签名密钥（随机串；轮换即撤销全部会话）
SERVICE_MANAGER_SESSION_SECRET=

# 公网入口（写请求的 Origin allowlist；按实际对外地址填写）
SERVICE_MANAGER_PUBLIC_ORIGIN=https://web.duomi77.cn:9443

# 可选：GitHub Token（公开仓库不需要；配了限流上限从 60/h 提到 5000/h）
SERVICE_MANAGER_GITHUB_TOKEN=

# 可选：哪些 compose 项目算「我自己开发的」（列表里单独一个 tab）；默认 personal-web
SERVICE_MANAGER_OWN_PROJECTS=personal-web
```

前两项缺失时 `docker compose config` 就会因为 `${VAR:?}` 直接报错，不会起一个没有认证的管理台。

> **不必手工填**：`deploy-nas.sh service-manager both`（以及 `all`）在构建前会检查这两项，
> 缺失时自动生成随机值写进根 `.env`（并把 `.env` 权限收到 600），
> 同时把**登录口令打印在终端**。2026-11-12 首次上线就是这么走的。
> 报 `required variable SERVICE_MANAGER_ADMIN_PASSWORD is missing` 就是这个检查没覆盖到的场景，
> 手动补上即可。

## 3. 部署

```bash
./scripts/deploy-nas.sh service-manager both
# 只改后端：./scripts/deploy-nas.sh service-manager backend
# 只改前端：./scripts/deploy-nas.sh service-manager frontend
```

脚本会：buildx 构建前端 → compose 构建后端 → `up -d --force-recreate --no-build` 三个容器
（frontend / backend / socket-proxy）。**不会**重启任何被管理的容器。

nginx 侧（`nginx/web.conf` 已含 upstream 与 location）：

```bash
./scripts/deploy-nas.sh nginx
```

## 4. 冒烟验收

```bash
# 4.1 页面与静态资源（9443 是现有 https 入口）
curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1:9443/services
curl -sk -o /dev/null -w '%{http_code}\n' "https://127.0.0.1:9443/services/_next/static/css/app/layout.css"

# 4.2 后端健康（公开端点，不泄漏台账）
curl -sk https://127.0.0.1:9443/api/services/health          # {"status":"ok"}

# 4.3 未登录台账必须 401
curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1:9443/api/services/services   # 401

# 4.4 登录拿 cookie（Path=/api，HttpOnly，Secure）
curl -sk -c /tmp/sm.ck -X POST https://127.0.0.1:9443/api/services/auth/login \
  -H 'Content-Type: application/json' -H 'Origin: https://web.duomi77.cn:9443' \
  -d '{"password":"<第 2 步的口令>"}'
grep -o 'sm_session.*' /tmp/sm.ck | head -1

# 4.5 汇总与发现（Docker 读取是否可用）
curl -sk -b /tmp/sm.ck https://127.0.0.1:9443/api/services/summary
curl -sk -b /tmp/sm.ck 'https://127.0.0.1:9443/api/services/discovery?include_ephemeral=false' | head -c 400
```

浏览器里再走一遍：登录 → 发现导入（选 personal-web 的 dividend 前后端 → 建「股息率分析」）→
加一条入口 `https://web.duomi77.cn:9443/dividend` → 点「检查 URL」「检查证书」→ 资源总览三个标签可切换。

## 5. socket-proxy 只读边界验证

proxy 只开 `CONTAINERS/PING/VERSION` 且 `POST=0`，因此**写操作必须在这一层被拒绝**。
用无副作用的目标试探（不要拿真实业务容器试写）：

```bash
# 从后端容器内访问 proxy（它只连了 sm-docker-net 和 app-net）
docker exec service-manager-backend sh -c '
  echo -n "GET  list      → "; curl -s -o /dev/null -w "%{http_code}\n" http://service-manager-socket-proxy:2375/containers/json
  echo -n "POST create    → "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://service-manager-socket-proxy:2375/containers/create
  echo -n "POST kill      → "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://service-manager-socket-proxy:2375/containers/nonexistent/kill
  echo -n "GET  images    → "; curl -s -o /dev/null -w "%{http_code}\n" http://service-manager-socket-proxy:2375/images/json
  echo -n "GET  networks  → "; curl -s -o /dev/null -w "%{http_code}\n" http://service-manager-socket-proxy:2375/networks
  echo -n "POST exec      → "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://service-manager-socket-proxy:2375/containers/nonexistent/exec
'
```

期望：`GET list` 200；其余 403（`POST=0` 与类别关闭）。

再确认 proxy 没有对外暴露端口，后端没有挂 socket：

```bash
docker inspect service-manager-socket-proxy --format '{{json .HostConfig.PortBindings}}'   # {}
docker inspect service-manager-backend --format '{{json .HostConfig.Binds}}'               # 只应有 data 卷
```

## 6. 真实数据抽验

| 场景 | 期望 |
|---|---|
| personal-web 一个 compose 项目 | 可以拆成多个业务服务，也可把前后端合并成一个 |
| immich（4 个组件） | 可合并为一个业务服务，`required` 决定整体运行状态 |
| homeassistant / xiaomusic（host 网络） | 端口显示「宿主网络，未自动采集」，可人工补录 |
| caddy / ddns-go / songloft（无 compose 标签） | 归入未分组候选，`source_key` 为 `nas:container:<id>`，重建后需人工重新关联 |
| 任一已登记容器 `docker compose up -d` 重建 | 台账关联不变（`nas:compose:{project}:{service}:{n}`），观测自动更新 |
| 自签证书入口 | 状态 `invalid` + 原因「自签证书」，到期时间仍可见（不是「无法连接」） |
| 自签证书入口的 URL 维度 | 显示**可达**（HTTP 层确实答话；证书问题由 TLS 列负责），不误报「不可达」 |

## 7. 回滚

1. 先备份：设置页「下载 JSON」，或 `docker exec service-manager-backend sh -c 'cp /app/data/service-manager.sqlite3 /app/data/manual-backup.sqlite3'`
2. `./scripts/deploy-nas.sh nginx` 前先删掉 `nginx/web.conf` 里 `service_manager_*` 的 upstream 与 location 三处，再 reload
3. `docker compose -f docker-compose.nas.yml stop service-manager-frontend service-manager-backend service-manager-socket-proxy`
4. 移除容器与专用网络，**保留** `service-manager-data` 卷（台账在其中）：
   `docker compose -f docker-compose.nas.yml rm -f service-manager-frontend service-manager-backend service-manager-socket-proxy`
5. 验证首页 `/` 与至少一个既有应用仍可访问

## 8. 已知边界（V1 明确不做）

- 不做容器启停、exec、compose 编辑、反代/DNS 修改、证书签发续期、自动升级
- 端口总览**不包含宿主进程的全部监听**，不能据此证明端口空闲
- 不解析 Compose 文件内容（不读 YAML/.env/私钥），只展示 Docker 标签里的路径元信息
- 只读一层：前端「从台账移除」只删本应用记录与关联，容器照常运行

## 9. 2026-11-12 实机上线记录（首次）

```bash
./scripts/deploy-nas.sh service-manager both --no-pull   # 三容器起来，backend healthy
./scripts/deploy-nas.sh nginx --no-pull                  # nginx -t 通过后 reload
```

冒烟结果（`https://127.0.0.1:9443`）：

| 项 | 结果 |
|---|---|
| `/services` | 200 |
| `/services/_next/static/css/*.css` | 200 |
| `/api/services/health` | 200 `{"status":"ok"}` |
| `/api/services/services`（未登录） | 401 |
| `/api/services`（无尾斜杠） | 401（**不是 404** → 精确兜底生效） |
| 登录 → cookie | HttpOnly / Path=/api / Secure=TRUE |
| 登录后 `/api/services/summary` | 200，`docker_available=true` |
| `/api/services/discovery` | 48 个候选、13 个 Compose 项目 |

socket-proxy 只读边界（从后端容器内发起，期望仅前三项 200，其余 403）：

```
GET  /containers/json   200      POST /containers/create   403
GET  /version            200      POST /containers/x/kill   403
GET  /_ping              200      POST /containers/x/exec   403
GET  /images/json        403      DELETE /containers/x      403
GET  /networks           403      GET  /volumes              403
GET  /info               403      POST /images/create       403
```

容器隔离：proxy `PortBindings={}` 且只在 `service-manager-docker-net`（`Internal: true`）；
后端 `Binds` 只有 `service-manager-data`，**没有 docker.sock**。

### 上线时踩到并已修的两个生产缺陷

1. **`/api/services` 裸路径 404**：nginx 只有带尾斜杠的 location，裸路径不匹配 → 生产 404
   而开发期 Next rewrite 的 `:path*` 能匹配。已补 `location = /api/services` 精确兜底。
2. **所有写操作 401（登录却正常）**：nginx 的 `$host` **不含端口**，浏览器 Origin 含端口，
   字面比较不等 → Origin 校验失败。登录路由本来就没挂 Origin 校验，所以只有它能过。
   已两处同改：nginx 改 `$http_host`；后端同源判断放宽到「hostname + scheme 相同」。
   **口诀：登录能过、其它写操作 401 → 先查 nginx 传的 Host 带没带端口。**
