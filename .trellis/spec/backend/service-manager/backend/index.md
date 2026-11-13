# service-manager 后端契约（NAS 服务管理台）

> 来源：11-11-nas-service-manager（V1）。产品权威 `.trellis/tasks/11-11-nas-service-manager/prd.md`，
> 数据与 API 权威 `design.md`。本文只记**实现时容易被改坏**的边界。

## 1. Scope / Trigger

改 `backend/service-manager`（台账、Docker 投影、资源总览、检查调度、备份恢复、认证）时读本文。

## 2. 硬边界（改这些等于改契约）

### 2.1 Docker 只读，且必须经投影

- 只允许 `version` / `ping` / `container list` / `container inspect`。
- `docker_reader.project_container()` 把 inspect **投影到白名单字段**（id/name/image/两个 compose 标签/
  state/health/network_mode/ports/mounts）。`Env`、`Cmd`、`Hostname`、原始 inspect **永不落库、永不进日志**。
  生产上还有 `docker-socket-proxy` 的 `POST=0` 兜底，但代码层不得依赖它。
- socket-proxy 的镜像**必须锁 digest**（`tag@sha256:...`）：它是全仓唯一摸得到
  `docker.sock` 的容器，tag 可被移动，恶意镜像能无视 `POST=0` 全放行。
  升级见 `docs/service-manager-nas-setup.md` §5，改完要重跑白名单探针。
- 采集失败（超时/连接拒绝）**不发布半份快照**，也不把「采不到」当成「容器消失了」：
  `missing` 只在一次**成功全量扫描**里没出现才标。

### 2.2 组件身份

- Compose 容器：`nas:compose:{project}:{service}:{container-number}`，重建（换 container id）后关联不变。
- 缺 compose 标签：`nas:container:{id 前 12 位}`，重建后需人工重新关联。**不要试图猜名字合并**。
- `com.docker.compose.oneoff=true` 的容器不进候选、不可导入。
- `source_key` 在 `service_components` 上 UNIQUE：一个组件只能属于一个业务服务。

### 2.3 状态维度不许合并

`runtime` / `health` / `url` / `tls` / `release` 五个枚举各自独立，任何聚合都要保留分维度信息。

- **Docker health 未配置 = `not_configured`，页面显示 `-`**（该维度对这个服务不适用，
  不是异常，也不需要使用者去维护）。聚合只统计**配了健康检查**的 required 组件：
  一个都没配 → `-`；配了的按 unhealthy > starting > unknown > healthy 聚合。
  混合时（前端没配、后端有）用已配组件的状态，覆盖范围在 tooltip 里写「N/M 个组件配置了检查」——
  前端容器本来就不需要自我检查（它是 `depends_on: service_healthy` 的「等别人」的一方），
  把它算成「没检查」反倒掩盖了后端报出的真实状态。
- `required` 组件全 running → `running`；部分 → `partial`；全停 → `stopped`；有 `missing` → `missing`；
  没绑组件 → `unknown`。
- 检查失败时 `check_status=error`，`current_state` 仍写该维度的失败值，**只保留**旧 `last_success` 与 payload，
  页面据 `last_success_at` 显示旧值时间。超过 2 个周期没成功才标 `stale`。
- HTTP 4xx/5xx 与证书无效都是「检查跑完了、观测到异常」→ `check_status=success`。
  只有网络/协议层失败（timeout、connect_error、TLS 握手拿不到证书）才是 `check_status=error`。

### 2.4 端口「重叠」口径

只有**同主机 + 同协议 + 同地址族 + IP 绑定重叠 + 同宿主端口**才提示潜在重叠。
`0.0.0.0` 覆盖任意 IPv4；IPv6 通配（`::`）只在 IPv6 内比较；跨族标「未判断」。
容器内部 `expose`（`host_port=None`）与 stopped 容器的 `historical` 映射**都不算**当前占用。
`host` 网络容器没有映射列表，只能人工补录。

### 2.5 探测与证书

- 探测目标（`probe_url` 或 `url`）不能是 loopback：容器内 localhost 指管理台自身，直接 400 拒绝，不静默改写。
- 云元数据地址（169.254.169.254 等）与 URL 里的账号密码/凭据类 query 一律拒绝。
- HEAD 先试，405/501 才退 GET，最多读 64 KiB，总超时 10 秒，并发 4，重定向 ≤3 跳且每跳重新校验。
- **证书不被信任不算「不可达」**：校验失败（自签/链不全/域名不符）时跳过校验重试一次，
  HTTP 层确实答话就按 HTTP 码判定（可达/需认证/状态异常），payload 记 `tls_verified=false` 与 `tls_error`。
  证书本身的问题一律由 TLS 维度单独报（`invalid` + 原因 + 到期日）——URL 维度只回答「能不能进去」。
  跳过校验后仍连不上才算 `unreachable`。
- 证书从**登记 URL 的原始 host+port** 检查（不从 probe_url、不从最终跳转站点），同 host 不同端口分别检查。
- `invalid` 要带原因（`self_signed`/`hostname_mismatch`/`expired_chain`/`untrusted_ca`）：
  自签证书没过期 ≠ 坏证书，页面要能区分。验证失败后允许单独取公开叶证书展示到期时间，**状态仍是 invalid**。

### 2.6 认证与写保护

- 口令常量时间比较；session 用 itsdangerous 签名，12 小时，cookie `HttpOnly` + `SameSite=Strict` + `Path=/api`
  （`/api` 同时覆盖外部的 `/api/services/*` 与后端直连的 `/api/*`；不能写成 `/api/services`，否则直连全 401）。
- 写请求（非 GET/HEAD/OPTIONS）必须带 Origin，且满足其一：与请求 Host 同源 / 命中 allowlist /
  与 `X-Forwarded-Host` 同源**且直连方是回环地址**（仅开发期 Next rewrite 用）。
- **直连前端容器端口时写操作会被拒**（e2e / SSH 隧道场景）：Next 的 rewrite 代理是
  `changeOrigin: true`，会把 `Host` 改写成后端容器地址（`service-manager-backend:8102`），
  后端按 `Origin == Host` 判同源必然不等；而「信任 `X-Forwarded-Host`」那条只认回环直连方，
  容器网桥的源 IP 不是回环 → 401「请求来源不被允许」。生产走 nginx 不受影响
  （nginx 用 `$http_host` 保留原始 Host）。修法是给后端显式 allowlist 回环来源：
  NAS compose 默认 `SERVICE_MANAGER_ALLOWED_ORIGINS=http://127.0.0.1:3012,http://localhost:3012`，
  只放开这两个确切来源，伪造来源（`https://evil.example`、换个端口、换 IP）依旧 401。
- **反代的 `$host` 不含端口**：nginx 文档里 `$host` 是「去掉端口的 host 名」，
  而浏览器 Origin 带端口（`https://web.duomi77.cn:9443`）。字面比较必然不等 →
  生产上所有写操作 401，而开发期 Next rewrite 会带 `X-Forwarded-Host` 所以本地正常。
  两处都要做：nginx 侧用 `$http_host`（保留原始 Host），后端侧同源判断放宽到
  「hostname 与 scheme 相同即接受」（跨站仍拒绝）。这是「本地正常、生产炸」的真实案例。
- 登录失败按来源限速 5 次/分钟。生产缺口令或签名密钥时 `Settings` 直接抛错，拒绝启动。

### 2.7 归属（我维护的 / 别人的）

- 归属是**台账里的一条字段**：`services.ownership` = `mine` | `other`，**逐条可改**
  （详情页头部下拉、列表行内下拉都直接 PATCH）。
- 不再由 compose 项目名单全局推导分组；`SERVICE_MANAGER_OWN_PROJECTS`（默认 `personal-web`）
  **只作为新建服务时的默认值**：
  - 没关联容器（人工登记）→ `mine`
  - 组件的 compose 项目命中 own 名单 → `mine`
  - 其余（有容器但没有 compose 标签、或项目不在名单里）→ `other`
- 旧库没有这一列时：启动时 `registry.backfill_ownership()` 按上面口径回填一次
  （列值 `''` 表示未判定，回填只动未判定的行，用户改过的不会被覆盖）。
  加列是向后兼容的（`ALTER TABLE`），**不升 schema 版本**。
- `GET /api/services` 的每项带 `projects`：该服务包含的 compose 项目，
  由 `service_components.source_key`（`nas:compose:{project}:...`）反解，**不额外问 Docker**；
  现在只作来源信息展示，**不再决定分组**。

### 2.8 备份与恢复

- 导出只含**人工表**：services / service_components / component_overrides / endpoints / port_notes /
  release_sources / discovery_decisions。排除观测、检查结果、job、release 缓存与已读、以及任何凭据。
  恢复时**归属也一起还原**；老备份没有 `ownership` 字段时按 2.7 的默认口径兜底，不要全落一边。
- 恢复三步不可省：`preview`（返回 digest + registry_revision）→ 用**同一份字节** `restore` →
  校验 digest 与 revision 一致 → 先 `backup_to()` 落一份本地快照 → 单事务替换 → 失败整笔回滚。
- 恢复会清空 `check_results` 与 `release_reads`，并把 `release_sync.baseline_done` 归零
  （下次同步重建基线，避免历史未读轰炸）。恢复**不触发**任何外部检查。

## 3. 验证命令

```bash
cd backend/service-manager
uv sync && uv run python -m pytest tests/ -v      # 175 passed
```

覆盖矩阵：`test_api.py`（A1/A13/A14 面）、`test_registry.py`、`test_docker_reader.py`（A3/A4/A5）、
`test_discovery.py`（A2/A3）、`test_resources.py`（A5/A6）、`test_backup.py`（A12）、
`test_http_probe.py`（A7）、`test_tls_probe.py`（A8）、`test_releases.py`（A10）、`test_scheduler.py`（A9）。

## 4. Wrong vs Correct

```python
# Wrong：把 inspect 原样存档，或把未配置 health 当成健康
conn.execute("INSERT ... raw_inspect", (json.dumps(attrs),))
health = "healthy" if state.get("Status") == "running" else "unknown"

# Correct：投影白名单；health 只从 State.Health.Status 读，缺失即 not_configured
projected = project_container(attrs)          # 无 Env/Cmd/Hostname
project_health(state_block)                   # {} → not_configured
```

```python
# Wrong：采集失败就把所有组件标 missing
except DockerUnavailable: mark_all_missing()

# Correct：失败只记录错误，保留旧观测；missing 只由「成功扫描里没出现」产生
except DockerUnavailable as exc: self._record_error(str(exc)); return
```
