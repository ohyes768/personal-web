# NAS 服务管理台 V1 技术设计

状态：规划完成，待用户评审；不开始实现。日期：2026-11-11。

## 1. 推荐方案与默认决策

采用独立 `service-manager` 前后端模块，复用 monorepo 的部署方式；管理单台 NAS、一个 Docker Engine。数据写入自己的 SQLite，Docker、反代、Compose 均只读或仅记录。一个业务服务关联多个容器组件，Compose 项目作为定位和筛选维度。

下列为设计默认值，不冒充用户已逐项确认：

| 项目 | 默认选择 |
|---|---|
| 路径 | 页面 `/services`，对外 API `/api/services/*`，后端内部 `/api/*` |
| 端口 | 前端 3012，后端 8102；实施/部署前再次检查 |
| 数据 | SQLite named volume `service-manager-data`，UTC ISO 8601 带时区时间；界面按 Asia/Shanghai 显示 |
| 自动读取 | Docker 元数据经 socket proxy；不挂载全部 NAS 目录，不解析 Compose 文件内容 |
| 人工管理 | 服务归组、访问入口、反代关系、缺失部署路径、版本备注、笔记 |
| 身份 | 单管理员登录，所有台账与管理 API 均需认证；仅最小健康端点公开 |
| 刷新 | Docker 60 秒；URL 5 分钟；证书 12 小时；Release 6 小时；都支持手动触发 |
| 提醒 | 首页异常计数、服务徽章、未读发布；不接外部消息推送 |

## 2. 架构与边界

```text
浏览器 /services
  → Nginx /api/services/* → FastAPI /api/* → SQLite
                                  ├→ 专用 Docker socket proxy → Docker Engine
                                  ├→ 已登记 HTTP(S) URL / TLS
                                  └→ api.github.com 的公开 Release
```

新建 `apps/service-manager`（Next.js/React/TypeScript）与 `backend/service-manager`（Python 3.12/FastAPI/SQLite）。后端采用 httpx 做 HTTP 请求、docker SDK 读取 Engine、cryptography 解析公开证书、itsdangerous 签名会话；具体依赖版本在实现时锁进 uv.lock。前端无 BFF，开发 rewrite 与生产 Nginx 都剥 `/api/services` 到后端 `/api`。凭据只由后端环境提供，不能使用 NEXT_PUBLIC。

不调用 task-web 的任务执行器，不绑定它的数据库或调度配置。自己的检查任务在 FastAPI lifespan 中启动，由一个后台 asyncio 调度循环维护固定周期；单 uvicorn worker，避免重复调度。网络 I/O、Docker SDK 同步调用不阻塞事件循环（SDK 放线程池）。

### Docker 接入

- 新增 socket proxy，仅它挂载 `/var/run/docker.sock`；业务后端通过专用 internal 网络访问 proxy 2375。
- proxy 不发布主机端口，不接公共 app-net；只有后端同时连接该专网与 app-net。
- 配置 `CONTAINERS=1`、`PING=1`、`VERSION=1`、`POST=0`；其他类别显式关闭，包括 IMAGES/INFO/EVENTS/NETWORKS/VOLUMES/EXEC/SECRETS。V1 不需要 image inspect 或 volume inspect。
- `CONTAINERS=1` 不是响应字段级授权，inspect 仍可能含环境变量。采集器立即投影白名单字段，禁止保存或日志打印原始 inspect；不提供任意 Docker API 透传。
- `:ro` 仅指 socket 文件挂载，API 只读由 proxy 方法限制实现。上线前实测 GET 成功，创建/重启/exec/DELETE 被拒绝。
- proxy 镜像在实施时选择可获取的明确版本并锁定 digest，先验证 Docker 29.1.3 的 API 协商；不在规划期下载或部署镜像。
- Docker 不可用不阻断台账启动。API 返回旧观测、最后成功时间与采集失败原因。

## 3. 数据模型与稳定身份

所有人工实体使用 UUID；人工信息与观测表分开，编辑使用整数 `revision` 防止旧表单覆盖新记录。

| 表 | 关键字段与语义 |
|---|---|
| `services` | id/name/description/category/tags/notes/revision/created_at/updated_at；用户拥有 |
| `service_components` | id/service_id/source_key/required；source_key 唯一归属，required 默认 true |
| `component_overrides` | source_key、人工工作目录/config_files/data_paths/version_note；仅补充或覆盖显示，不改 Docker |
| `docker_components` | source_key、project/service_name/container_id/name/image_ref/image_id/state/health/network_mode/ports/mounts/compose_paths/last_seen_at/scan_id；归一化观测 |
| `discovery_decisions` | source_key/ignored；隐藏候选，不丢资源总览中的真实端口 |
| `endpoints` | id/service_id/label/kind/url/probe_url/enabled/expected_status_ranges/tls_check/route_target/renewal_note/revision；kind=internal/external/admin |
| `port_notes` | id/service_id/host_ip/host_port/container_port/protocol/note/revision；用于 host/手工端口，不冒充实测 |
| `release_sources` | id/service_id/owner/repo/installed_tag_note；每服务最多一个仓库，多个服务可共用上游缓存 |
| `releases` | owner/repo/release_id/tag/name/published_at/updated_at/body/html_url/prerelease；仓库+release_id 唯一 |
| `release_reads` | release_source_id/release_id/read_at；已读属于用户服务关联，不与仓库缓存混淆 |
| `check_results` | target_type/target_id/check_kind/check_status/current_state/last_attempt_at/last_success_at/last_success_payload/error_code/error_message/next_due_at；目标+检查类型唯一 |
| `refresh_jobs` | id/kind/target_id/state/started_at/finished_at/counts/error；记录最近 7 天，不存完整网络响应 |
| `runtime_state` | schema_version/registry_revision/docker_scan_generation/checker_heartbeat 等内部状态 |

`ports`、`mounts` 等嵌套字段可存 JSON，但在后端 Pydantic 模型中统一验证/解码，前端不自行重解析原始 Docker 数据。

### 组件身份规则

- Compose 常驻容器键：`nas:compose:{project}:{service}:{container-number}`，缺编号用 1；oneoff 标签为 true 的任务容器不自动并入常驻组件，归临时候选。
- 同一 project/service 重建容器时，容器 ID 可变化，业务关联不变化；缺必要标签的容器键为 `nas:container:{id}`，重建后由人重新关联。
- 同一 Compose 项目可拆成多个业务服务；一个业务服务可有前端、后端、数据库等组件。不依赖名字后缀自动合并。
- 默认候选显示常驻 running/stopped 组件；oneoff 和已退出无标签容器放“临时/已退出”折叠区；忽略操作持久化。
- Docker 列表完成才递增 scan generation。获取中断不发布半份全局快照；单容器 inspect 因删除返回 404 可标记本轮缺失，其余传输失败中止该轮发布。
- 已登记组件在成功全量扫描中未出现，标为 missing，保留台账；采集失败不能推断为 missing。既有 stopped/exited 容器单独显示停止，不当作消失。

### 路径与数据卷

Compose `working_dir` 与 `config_files` 是宿主机路径元信息，不是管理台容器内可直接读取的路径。config_files 保存原始有序列表；相对路径只有在已知绝对 working_dir 时归一拼接，否则标“相对路径，位置未确认”。缺失字段可手工填写。

bind mount 显示宿主 Source → 容器 Destination、ro/rw；named volume 显示卷名 → Destination，必要时显示 Docker 报告的 Source，明确“不等于已备份”。路径不检查存在性、不提供文件浏览、不读取 YAML、`.env`、私钥内容。

## 4. 发现、导入和编辑流程

1. 初次登录显示空台账与“发现容器”；立即运行一次 Docker 扫描，不强制等待它才能手工新增。
2. 候选页按 Compose project 筛选，显示组件、状态、镜像、路径和端口；允许多选后建立一个业务服务，也可追加到现有服务。
3. 点击确认才写入台账；导入 API 校验候选仍存在且未被别的服务绑定。可勾选组件是否影响业务运行状态（required）。
4. 用户补名称/用途/入口/仓库；不自动拼造公网 URL。扫描刷新只更新观测，不覆盖手工内容。
5. 台账“移除”只删除本应用关联与人工信息，UI 明示保留运行容器；组件回到候选。忽略与移除分开。

## 5. URL、域名和端口契约

### 入口与反代

URL 保存 scheme、主机、显式端口、路径，保留必要查询参数，但拒绝 userinfo、敏感凭据参数；不存账号密码。域名总览从 endpoint 推导，不另建需要手工同步的域名表。IP 入口显示为 IP，不强制归为域名。

`route_target` 是可选对象 `{component_source_key?, scheme, host, port, path_prefix?, note?}`，表示人工登记的代理目标，不宣称已验证 Nginx/Caddy 配置。允许域名多路径、多端口和多个服务共享证书。

`url` 用于浏览器打开，`probe_url` 可选，用于后端探测不同入口；两者不同，页面明确显示检查的 URL。容器内 localhost 指管理台自身，不能当成 NAS localhost：新建 localhost 探测目标时阻止保存并说明使用可达的 NAS 地址/同网络容器名；不静默改写。所有结果标注“从管理台后端探测”，不声称等于公网用户视角。

### 端口总览

- 自动记录 host_ip/host_port/container_port/protocol/address_family/network_mode；区分发布端口和仅 expose 内部端口。
- 端口总览覆盖全部发现组件（含未导入和已忽略），支持“仅已登记服务”筛选，避免漏掉其他容器占用。
- 仅同主机、同协议、同地址族且 IP 绑定重叠的有效发布/人工规划端口才提示“潜在重叠”。0.0.0.0 与具体 IPv4 相交；IPv6 通配仅在 IPv6 内比较；跨族标明未判断双栈行为。
- 自动同一端口多容器观测作为需人工核查项，不断言 Docker 已成功运行冲突绑定。stopped 容器端口标“历史/配置映射”，不算当前有效占用；人工端口始终注明来源。
- host 网络组件显示“共享宿主网络，未自动采集监听端口”，允许人工补录。页面永久注明“不包含宿主进程全部监听，不能据此证明端口空闲”；V1 不装宿主 agent、不运行 ss 扫描。

## 6. 检查与状态

### 通用状态

各维度分开：runtime=running/partial/stopped/missing/unknown；health=healthy/unhealthy/starting/not_configured/unknown；URL=reachable/auth_required/unexpected_status/unreachable/unknown；TLS=valid/expiring/expired/invalid/unknown；release=unread/no_unread/no_releases/error/not_configured。

required 组件全部运行才是 runtime running，部分运行则 partial，全部停止则 stopped，存在 missing 则 missing；未关联组件则 unknown。Docker health 未配置显示 not_configured，不能写“健康”。首屏可聚合异常徽章，但不得用一个绿色图标抹平不同维度。

每次检查记录 last_attempt；成功才替换 last_success 与 payload。通用 check_status=never/success/error，current_state 使用各维度枚举。网络故障将 check_status 标 error，并将当前状态设为该维度的失败值（如 URL unreachable、TLS unknown、release error、runtime unknown），显示旧值时间，不能继续把旧绿色结果显示成当前有效。超过 2 个检查周期未成功的观测加 stale；手动刷新也不改变周期定义。错误 HTTP 状态和证书无效是完成检查得到的异常观测，不等同采集器未完成请求。

### URL

仅检查用户登记且启用的 HTTP(S) 目标；允许 LAN/容器 DNS，这是 NAS 场景必需。拒绝非 HTTP 协议、URL 凭据和云元数据地址 169.254.169.254；重定向每跳同样验证，最多 3 跳。先 HEAD，405/501 时用流式 GET，最多读 64 KiB；单次总超时 10 秒，并发上限 4。

默认 200–399 为 reachable，401/403 为 auth_required（能连接，但需要认证）；其他 HTTP 响应为 unexpected_status，保留状态码，不当作网络不通。可为特定端点配置期望范围。TLS 握手失败保持独立错误，不绕过验证作为 URL 成功。探测不传浏览器 cookie、管理员口令或 GitHub Token。

### TLS

从登记的 HTTPS `url` 原始主机和端口检查（缺省 443），不从 probe_url 或最终跳转站点代替它；以 SNI/主机名验证链和域名，保存 subject/SAN/issuer/not_before/not_after/fingerprint。相同 host+port 复用检查，不同端口分别检查。

30 天内 expiring，过期 expired，域名/信任链不正确 invalid；days_remaining 以 UTC 差值向下取整。验证失败可额外获取公开叶证书解析到期时间，但仍保留 invalid，不因此显示有效；若解析失败到期值为 null。既不读取私钥，也不据可访问证书断言续期任务正常；renewal_note 只是人工说明。

### GitHub Release

- 用户填写 GitHub owner/repo 或仓库 URL，后端正规化为公开仓库；只访问 api.github.com，仓库更名重定向仅允许 GitHub 官方 API 主机。
- 每仓库共享缓存，串行检查；拉取 `/releases?per_page=100`，按 Link 分页最多 3 页；过滤 draft 和 prerelease，保存原始更新说明与链接，不做 AI 摘要或自动抽取结论。
- 用 `/releases/latest` 单独获取 GitHub 标注的最新正式发布；列表按 published_at 倒序展示，不靠 tag 字符串排序推断最新。
- 第一次成功同步把已获取历史 Release 标为已读；之后新 ID 未读。打开详情不会隐式标已读，支持逐条/将当前已加载发布全部标已读。
- 不完整分页时明确“仅覆盖最近 300 条”，不把未抓取区间计为已读；下次检查用相同分页请求/ETag 更新缓存。304 作为检查成功，保持原内容。
- 无 Release、最新正式版不存在、仓库不可访问、限流和网络错误分别显示；列表为空但 repo 可访问才显示 no_releases；所有 Release 为 prerelease 时显示“暂无正式发布”。
- installed_tag_note 是人工版本备注；镜像 ref/image ID 是实际 Docker 观测。`latest`、`stable`、自建镜像、digest 不等于软件版本。只有人工标签与 Release tag 精确一致时显示“与所填版本一致”，不一致显示“版本待判断”，不计算落后多少版。
- 尊重 Retry-After 和 X-RateLimit-Reset，不立即重试；全局 GitHub 队列串行。无 token 也能用，token 仅放 NAS 环境变量，绝不返回前端。

### 调度与手动刷新

检查只遍历已登记端点/仓库，Docker 扫描覆盖全 Engine。手动刷新创建持久化 job，202 返回 job_id；同一 kind+target 正在运行则返回现有 job（deduplicated=true），不重复请求。kind 限定 docker/url/tls/releases/all；url/tls/releases/all 的 target_id 为可选业务 service_id，缺省全体服务，docker 不接受 target_id。全量与单服务刷新在底层共用 endpoint/host+port/repo 锁，避免不同外层 job 重复探测；all 中 GitHub 仍遵守退避。

每类任务互斥且有超时，一项失败不阻断其他服务。重启将旧 running job 标 interrupted，然后按 next_due_at 恢复；不补跑整个停机期间每个周期。任务状态包含 queued/running/completed/partial_failed/failed/interrupted。

## 7. API 与认证契约

以下为对外路径；后端统一 `/api` 路由，Nginx `/api/services/xxx` → `/api/xxx`。

| 方法与路径 | 结果 |
|---|---|
| GET `/api/services/health` | 公开，仅返回进程 ready，不泄漏台账；Docker 失败不返回整体 503 |
| POST `/api/services/auth/login` | `{password}`；成功设置签名 session cookie |
| GET `/api/services/auth/session`；POST `.../logout` | 会话状态；清 cookie |
| GET `/api/services/summary` | 各维度计数、检查状态与最后成功时间 |
| GET/POST `/api/services/services` | 分页搜索/筛选列表；手工创建 |
| GET/PATCH/DELETE `/api/services/services/{id}` | 详情/带 revision 编辑/仅移除台账；PATCH 原子更新人工字段与关联 |
| GET `/api/services/discovery` | 候选按 project/state/ignored 筛选 |
| POST `/api/services/discovery/import` | 候选多选新建或关联业务服务，事务性校验重复绑定 |
| PATCH `/api/services/discovery/decisions` | 批量忽略/取消忽略，返回新 registry_revision |
| GET `/api/services/resources/ports`；GET `.../domains` | 端口与域名投影，包含来源、限制及搜索 |
| GET `/api/services/services/{id}/releases` | 已缓存正式发布与已读状态 |
| POST `/api/services/services/{id}/releases/read` | 显式 release_ids，不能隐含标记尚未获取的发布 |
| POST `/api/services/refresh`；GET `.../jobs/{id}` | `{kind,target_id?}` → 202/job_id；状态轮询 |
| GET `/api/services/backup/export` | schema_version=1 的人工台账 JSON 下载 |
| POST `/api/services/backup/preview` | 验证上传 JSON，返回数量、差异、digest、registry_revision |
| POST `/api/services/backup/restore` | 同一文件+预览 digest+revision+confirm=true；事务替换人工台账 |

列表返回 `{items,total,page,page_size}`，默认 page_size=50，最大 100。结构化错误 `{code,message,field_errors?}`，400 格式错误、401 未登录、404 记录不存在、409 revision/绑定冲突、413 导入过大、503 当前操作依赖不可用。网络检查失败通常写 job 结果，不作为列表 API 的 500。

人工台账及其关联的 mutation 在事务里递增全局 registry_revision；实体 PATCH 同时核对实体 revision。登录、检查结果和 job 状态不递增 registry_revision。导出只包含人工实体和候选忽略决定，排除运行快照、历史 job、release 缓存/已读标记、密码/Token/session。恢复预览显示将被替换的数量，保留当前 SQLite 一份本地恢复前备份（使用 SQLite backup API），在一个事务内替换人工表、清关联缓存/检查结果并提升 revision；失败整笔回滚。恢复与检查快照写入通过应用维护锁串行，恢复前正在执行的检查结果作废，恢复后不因旧任务回写已移除目标；发布已读状态在后续第一次同步重建基线。解析上限 5 MiB/1000 服务/5000 端点，外键和唯一约束全部先验证；不自动读入 JSON 中的文件路径，不自动执行外部检查。

管理员口令及 session 签名密钥通过 NAS env 提供，缺失时后端拒绝启动。登录常量时间比较；会话有效 12 小时，cookie HttpOnly/SameSite=Strict/Path=/api/services；生产 Secure，本地显式关闭 Secure。写请求校验 Origin 与配置的同源 allowlist，禁用跨域 wildcard。注销清 cookie；签名密钥轮换撤销全部会话。登录失败按来源限速，5 次/分钟返回 429；反代仅信任明确配置的代理来源，避免任意 X-Forwarded-For 绕过。仅自己的 env 配置，不继承其他应用密码作为隐式默认值。

## 8. 页面与交互

以信息表格为主，第一版不设计复杂拓扑图或拖拽。

1. `/services`：服务首页。顶部搜索（名称/用途/标签/域名/端口/路径）、分类/异常筛选；列表显示名称、主入口、运行/URL/TLS 独立状态、新发布未读数。支持手工新增、发现导入、打开入口。
2. `/services/service/{id}`：详情。概览入口与备注；组件列表及 required；部署路径和数据卷；反代关系和端口；检查结果；发布说明。路径可复制，HTTP(S) 可打开，编辑使用表单，删除明确只影响台账。
3. `/services/resources?tab=ports|domains|certificates`：资源总览。绑定 IP、协议、来源可见；证书按 host+port 去重，显示被哪些入口使用；风险和未知不混在“有效”中。
4. `/services/discovery`：候选导入页，支持选择多组件归组、关联已有服务、忽略；已退出/一次性容器默认折叠。
5. `/services/settings`：数据导出/恢复预览、检查周期只读说明、Docker/GitHub 接入是否就绪；不在网页输入系统 Token。登录为全站入口门禁视图。

页面都有原生 `<a href="/">← 返回首页</a>`。375px 下列表转为可读卡片或局部滚动表格，主要操作可键盘使用；颜色外辅以文字。复制成功即时反馈；旧数据明确时间戳；无数据、未配置、未检查、检查失败分别提供文案。发布正文使用安全 Markdown 渲染，禁止 raw HTML，链接仅 http/https。

## 9. 部署与回滚

新增前后端 Dockerfile 与 proxy 服务；前端主机绑定 `127.0.0.1:3012:3012`，后端仅 expose 8102，proxy 仅 internal 网络 2375。backend 在 app-net 能探测可达端点；不为自动访问其他容器而加入所有 Docker 网络，也不将后端设为 host 网络。其余网络目标用 NAS 已发布入口。

配置至少包括 SERVICE_MANAGER_ADMIN_PASSWORD、SERVICE_MANAGER_SESSION_SECRET、SERVICE_MANAGER_PUBLIC_ORIGIN、SERVICE_MANAGER_DOCKER_HOST、SERVICE_MANAGER_GITHUB_TOKEN（可选）、SERVICE_MANAGER_DATA_DIR、SERVICE_MANAGER_SECURE_COOKIE、周期设置。提供变量名与示例，不往文档写真实值。

按新服务契约补齐 Compose、Nginx 三件套、deploy-nas target/all/buildx/help、首页入口、dev bat、DOCKER_DEPLOY/README/CLAUDE/专用 setup 文档和 gitignore；实现时才登记新 package/spec，不在本规划改共享 Trellis 配置。

部署验收包括 proxy ACL、API 协商、basePath 静态资源和会话 cookie 路由。全程不重启被管理服务。回滚只撤新模块的路由/首页入口和三容器，保留 named volume；已有其他服务与 Compose 数据不迁移。DB 升级前备份，未知未来 schema_version 拒绝打开，禁止用删卷作为升级手段。

## 10. 规划自审结论

- 范围对应 PRD R1–R10 和 implement.md 的 M1–M6；无待定产品阻塞项。
- 需要部署时填写的凭据和 NAS 地址属于运维配置，不是规划缺口。
- V1 明确不保证完整宿主端口发现、配置文件存在性、代理配置同步、自动版本比较和证书续期成功。
- 所有尚未实施的验证项留在实施清单，不将文档研究当作功能验证。
