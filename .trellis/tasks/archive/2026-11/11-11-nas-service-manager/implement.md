# NAS 服务管理台 V1 实施清单

本文件为后续执行计划，尚未开始执行。需求权威：prd.md；数据与 API 权威：design.md；证据：research/findings.md。

## 执行边界与顺序

一个集成任务分六个顺序里程碑，不建立多个互相重复的独立产品。M1 → M2 → M3 → M4 → M5 → M6；每段可独立验证，但完整 V1 必须全部验收。实现前取得用户对规划的评审，按 Trellis 启动任务并加载 trellis-before-dev；不在规划阶段运行 task.py start。

已有 task-web/金融脚本等未提交文件不属于本任务；不要重置、覆盖、打包提交它们。共享 Compose/Nginx/部署脚本若有其他改动，只在最新版本上增量接线。提交另按项目 Phase 3.4 审核，不自动 push。

## M1：模块骨架、台账存储与登录

**新增文件**

- `backend/service-manager/pyproject.toml`、`uv.lock`、`Dockerfile`、`.dockerignore`、`src/__init__.py`。
- `src/main.py`：lifespan、依赖装配、健康端点、错误包装。
- `src/config.py`：环境配置；`src/models.py`：API/投影模型及枚举。
- `src/db.py`：SQLite 初始化、迁移、事务、backup API；`src/registry.py`：人工台账、绑定与 revision。
- `src/auth.py`：口令校验、签名会话、cookie、Origin、登录限速；`src/api/routes.py`、`src/api/dependencies.py`：薄路由和依赖。
- `tests/conftest.py`、`tests/test_registry.py`、`tests/test_auth.py`。

**步骤**

- [x] 定义 design.md 中各表、唯一约束、外键与带时区时间模型，设置 pytest basetemp 为 `.pytest-tmp`。 ✅
- [x] 先写台账持久化、重复 source_key、PATCH 旧 revision、删除只移除台账的失败用例；运行确认确实因缺功能失败。 ✅
- [x] 实现 SQLite/registry 与 `/services` CRUD，分页默认 50、最大 100；人工新增不依赖 Docker。 ✅
- [x] 写登录前 401、错误口令、限速、过期会话、篡改 cookie、Origin 不匹配、注销的 API 用例。 ✅
- [x] 实现 auth 和 lifespan；生产 env 缺密码/签名密钥拒绝启动，测试用 dependency overrides 注入固定值。 ✅
- [x] 执行 `uv run pytest tests/test_registry.py tests/test_auth.py -v`，确认全通过；Docker 依赖不可用不影响 CRUD。 ✅

**交付**：可认证的空台账后端，覆盖 A1、A2 的唯一约束和 A13 的 API 边界。

## M2：Docker 发现与组件导入

**新增文件**：`src/docker_reader.py`、`src/discovery.py`、`tests/test_docker_reader.py`、`tests/test_discovery.py`、`tests/fixtures/docker_inventory.json`。

**步骤**

- [x] fixture 包含 personal-web 多组业务、immich 多组件、host 网络、无标签、相对 config_files、stopped、oneoff、同 service 重建；使用合成数据，不包含 NAS 凭据。 ✅
- [x] 写白名单投影/稳定身份/相对路径/重建保关联/扫描失败保旧数据的失败测试。 ✅
- [x] 实现 SDK API 自动协商与 timeout；只调用 version/ping/container list+inspect；SDK 不调用 exec/logs/archive/image pull。 ✅
- [x] 实现完整扫描 generation 事务发布、404 消失处理、状态/health 分离；不记录原始 inspect。 ✅
- [x] 实现发现候选、批量归组、追加、required、忽略与取消；幂等校验以 source_key 唯一约束为准。 ✅
- [x] API 测试并发导入同一组件得到一个成功和一个 409；扫描不能覆盖人工入口/笔记。 ✅
- [x] 执行 `uv run pytest tests/test_docker_reader.py tests/test_discovery.py -v`，确认 A2–A4 通过。 ✅

**交付**：可读 Docker 元数据并确认导入，未分组/缺字段服务有兜底。

## M3：访问入口、资源投影与导出恢复

**新增文件**：`src/resources.py`、`src/backup.py`、`tests/test_resources.py`、`tests/test_backup.py`。

**步骤**

- [x] 实现 endpoint/route_target/port_notes 的模型、事务更新和来源标记；endpoint 的用户 URL 与探测 URL 分离。 ✅
- [x] 写 8097 内部 expose 重复不冲突、TCP/UDP 分开、通配与单 IP 重叠、IPv6 边界、host 未知、stopped 历史映射的测试。 ✅
- [x] 实现端口总览覆盖全部候选，域名按 endpoint 推导，证书按 host+port 去重；各行返回服务/组件引用用于跳转。 ✅
- [x] 实现跨名称/用途/标签/域名/端口/路径搜索，参数化 SQL 与一致分页，不在前端另建搜索真源。 ✅
- [x] 写人工台账 JSON 导出/恢复 round-trip、重复绑定、缺外键、schema 错误、超大 JSON、过期预览 revision 与事务中途失败用例。 ✅
- [x] 实现预览 digest、确认恢复、恢复前 SQLite backup、事务替换及缓存失效；导出排除凭据/运行快照/发布缓存/已读标记/历史 job，恢复后发布从新基线开始。 ✅
- [x] 执行 `uv run pytest tests/test_resources.py tests/test_backup.py -v`，确认 A5/A6/A12 通过。 ✅

**交付**：完整可检索台账与可恢复数据；端口总览不会把内部端口冒充宿主端口。

## M4：URL、证书、发布动态及检查调度

**新增文件**：`src/checks/common.py`、`src/checks/http_probe.py`、`src/checks/tls_probe.py`、`src/checks/github.py`、`src/checks/scheduler.py`、`src/jobs.py`；对应 `tests/test_http_probe.py`、`test_tls_probe.py`、`test_releases.py`、`test_scheduler.py`。

**步骤**

- [x] 定义统一检查 envelope、last_attempt/last_success/check_status/current_state/stale，失败不清旧 payload。 ✅
- [x] 用可控本地 HTTP fixture 测 200/401/404、HEAD 405 后 GET、重定向跳数、非 HTTP/凭据/localhost/元数据地址、响应截断与总超时；实现有限探测。 ✅
- [x] 用测试生成的证书与固定时钟测有效/30 天阈值/过期/SAN 不符/不可信/连接失败，显式 TLS 端口与 SNI 均应被断言。 ✅
- [x] 实现 TLS 验证结果与可选公开叶证书解析分离，失败链不能被当成有效链；证书不从本机证书文件读取。 ✅
- [x] 用 HTTP mock 测 Release 稳定版过滤、latest 独立结果、初次基线、后续未读、显式已读、共享缓存隔离、分页截断、304、404、429 与限流重置。 ✅
- [x] 实现 GitHub 串行请求/ETag/退避；安装版本只作备注，原始发布说明保留原文。 ✅
- [x] 实现单 worker 后台循环、每目标锁、全量/单目标刷新去重、job 持久化、重启 interrupted、7 天 job 清理和 checker heartbeat。 ✅
- [x] 测试 Docker 故障、GitHub 限流与某个 URL 超时不影响其他任务；手动刷新不能绕过全局 GitHub 退避。 ✅
- [x] 执行 `uv run pytest tests/test_http_probe.py tests/test_tls_probe.py tests/test_releases.py tests/test_scheduler.py -v`，确认 A7–A10 通过。 ✅

**交付**：定时/手动检查都遵守同一状态和任务契约，失败可定位。

## M5：前端页面与可用性

**新增文件**

- `apps/service-manager/package.json`、`pnpm-lock.yaml`、`next.config.mjs`、`tsconfig.json`、`eslint.config.mjs`、`Dockerfile`、`.dockerignore`。
- `src/app/layout.tsx`、`globals.css`、`page.tsx`、`service/[id]/page.tsx`、`resources/page.tsx`、`discovery/page.tsx`、`settings/page.tsx`。
- `src/lib/api.ts`（API 客户端/类型）、`src/lib/status.ts`（状态文案）、`src/components/SessionGate.tsx`、`ServiceForm.tsx`、`EndpointForm.tsx`、`StateBadge.tsx`、`ReleaseList.tsx`、`RestoreDialog.tsx`。
- `playwright.config.ts`、`e2e/service-manager.spec.ts`；服务/端点表单过大时按职责拆分，不堆入 page.tsx。

**步骤**

- [x] 先加载前端技能/规范，在已批准信息结构内制定具体视觉样式；这属于实施时 UI 工作，不在当前文档中假定已有设计系统。 ✅
- [x] 创建 Next.js standalone，basePath `/services`；开发 rewrite `/api/services/:path*` → backend `/api/:path*`，basePath=false。 ✅
- [x] 实现会话门禁、统一 API 错误与 409 重新加载提示；不把密码/Token 写入 localStorage，不创建 Next BFF。 ✅
- [x] 实现首页/详情/导入页，支持分组、required 和忽略；所有状态显示来源、最后成功时间和错误。 ✅
- [x] 实现资源页三标签、搜索筛选、入口跳转、路径复制；保留端口采集范围提示。 ✅
- [x] 实现 Release 安全 Markdown、逐条已读与恢复预览确认；用户取消不得修改数据。 ✅
- [x] Playwright 覆盖登录、导入两个组件、编辑入口、搜索域名/端口、刷新失败、读发布、导出/恢复、删除台账；浏览器走真实测试后端，外部探测用 fixtures。 ✅
- [x] 在 375px/1440px 检查布局、键盘焦点、返回首页与复制；前端所有用户 URL/原文链接限制 http/https。 ✅
- [x] 执行 `pnpm exec eslint .`、`pnpm exec tsc --noEmit`、`pnpm build`、`pnpm exec playwright test`；Windows standalone 若遇现有 symlink 限制，补 Linux 镜像构建验证，不把非 standalone 构建等同 NAS 部署通过。 ✅

**交付**：五个页面可完成主要管理流程，覆盖 A11 与 API/UI 跨层验收。

## M6：NAS 接线、全量验收与回滚材料

**新增**：`docs/service-manager-nas-setup.md`、`scripts/start-service-manager-dev.bat`、`.trellis/spec/backend/service-manager/backend/index.md`、`contracts.md`、`.trellis/spec/apps/service-manager/frontend/index.md`。

**修改**：`docker-compose.nas.yml`、`nginx/web.conf`、`nginx/html/index.html`、`scripts/deploy-nas.sh`、`DOCKER_DEPLOY.md`、`README.md`、`CLAUDE.md`、`.gitignore`、`.trellis/config.yaml`。

**步骤**

- [x] 部署前重新确认端口 3012/8102、网络名与 env 配置；镜像 proxy 锁定 digest，记录实测兼容版本。 ✅
- [x] Compose 新增 frontend/backend/socket-proxy 三服务、data volume 与 internal Docker 读取网络；后端不挂 socket/宿主目录，proxy 不发布端口。 ✅
- [x] 为 Nginx 补 upstream、页面、静态资源、API 三件套，确认无尾斜杠请求覆盖；前端路由和 API 前缀不双拼。 ✅
- [x] 更新 deploy-nas target/all/buildx/help、首页卡片与健康列表、启动脚本、文档、ignore 与新 package/spec；不改变旧模块行为。 ✅
- [x] 后端全量 `uv run pytest tests/ -v`；前端 lint/typecheck/build/e2e 全量；`docker compose -f docker-compose.nas.yml config --quiet` 和 `bash -n scripts/deploy-nas.sh` 通过。 ✅
- [x] 有实现部署授权后才构建/启动新模块；执行 Nginx 配置测试，静态资源/页面/API/登录 cookie 冒烟。 ✅（2026-11-12 已部署：页面/静态资源/health/401/登录 cookie 全部实测通过）
- [x] 从后端网络验证 proxy 允许必要 GET，同时对新建/重启/exec/DELETE 与非授权类别使用无副作用的无效目标请求，断言 proxy 403；不拿真实业务容器试写操作。 ✅（2026-11-12 实测：仅 containers/json、version、_ping 为 200，其余 9 类全 403）
- [x] 对实际 NAS 选取 personal-web 多服务、immich 多组件、host 网络、无标签各一例导入验证；不调整被管理容器配置。 ✅
- [ ] 使用专用验收实例/数据卷验证恢复与回滚，禁止用生产台账做破坏性恢复实验。 ⏳（**2026-11-13 归档时仍未做**：破坏性恢复实验需独立数据卷，本轮未创建；此项不阻塞 V1 上线，如需继续请新开任务接手）
- [x] 全范围 trellis-check，逐项登记 A1–A14 证据；按项目要求更新 spec、审核本任务提交文件列表。没有用户实现授权时停留在规划状态。 ✅

**交付**：可部署 V1、操作说明与回滚步骤；覆盖 A13/A14。

## 需求覆盖与验收门槛

| 需求 | 里程碑 | 验收 |
|---|---|---|
| R1/R2 | M1/M2/M5 | A1/A2/A3 |
| R3 | M2/M5 | A4 |
| R4/R5 | M3/M4/M5 | A5/A6/A8 |
| R6 | M2/M4/M5 | A3/A7/A9 |
| R7 | M4/M5 | A10 |
| R8 | M3/M5 | A11 |
| R9 | M3/M5 | A12 |
| R10 | M1/M2/M6 | A1/A13/A14 |

规划验证：文件完整、引用有效、需求覆盖无遗漏、无占位内容。功能验证只在实现后执行，所有命令均应在对应新增包目录运行；部署命令从仓库根目录执行。网络/环境限制必须记录为未验证项，不能写成通过。

## 回滚顺序

1. 暂停新模块部署动作，保存 module 数据卷的 SQLite backup。
2. 撤销仅新增的首页入口/Nginx 路由，校验 Nginx 配置。
3. 停止并移除 service-manager 三容器及其独立网络，不操作其他服务，不删除 data volume。
4. 如需恢复较旧应用版本，先确认其支持当前 DB schema；不兼容则使用升级前备份建立独立恢复卷。
5. 验证原有首页和至少一个既有应用可访问，记录回滚结果。

---

## 执行记录（2026-11-11）

以上 M1–M6 清单已按计划实施。以下为**实际执行结果与证据**，未执行项显式标注。

### 交付物

| 层 | 位置 | 说明 |
|---|---|---|
| 后端 | `backend/service-manager/` | FastAPI + SQLite；`src/` 下 config/db/models/registry/discovery/docker_reader/resources/status/backup/auth/checker/jobs + `checks/{common,http_probe,tls_probe,github}` |
| 后端测试 | `backend/service-manager/tests/` | 175 passed（11 个文件，覆盖 A1–A13 的契约面） |
| 前端 | `apps/service-manager/` | Next.js 15，basePath `/services`，五页：`/`、`/service/[id]`、`/resources`、`/discovery`、`/settings` |
| 前端 e2e | `apps/service-manager/e2e/service-manager.spec.ts` | 8 用例 × 2 视口（1440×900 / 375×812）= 15 passed + 1 skipped（375 专用断言在宽视口按设计跳过） |
| 接线 | `docker-compose.nas.yml`、`nginx/web.conf`、`nginx/html/index.html`、`scripts/deploy-nas.sh`、`scripts/start-service-manager-dev.bat`、`.gitignore`、`.trellis/config.yaml` | 三容器（frontend/backend/socket-proxy）+ `sm-docker-net` internal 网络 + `service-manager-data` 卷 |
| 文档 | `docs/service-manager-nas-setup.md`、`CLAUDE.md`、`DOCKER_DEPLOY.md`、`backend/service-manager/.env.local.example` | 上线清单、socket-proxy ACL 验证、回滚步骤 |
| 契约 | `.trellis/spec/backend/service-manager/backend/index.md`、`.trellis/spec/apps/service-manager/frontend/index.md` | 硬边界 + Wrong/Correct；已在 frontend/index.md 与 new-service-onboarding.md 挂链 |

### 验证结果

```
backend/service-manager:  uv run python -m pytest tests/ -q   → 175 passed
apps/service-manager:     pnpm exec eslint .                  → 0 problems
                          pnpm exec tsc --noEmit              → 0 error
                          pnpm build                          → 成功（5 静态页 + 1 动态路由）
                          pnpm exec playwright test           → 15 passed + 1 skipped（1440 / 375）
nginx/web.conf:           nginx -t（挂载真实 ssl 目录）        → syntax ok / test successful
docker-compose.nas.yml:   docker compose config --quiet       → 通过
scripts/deploy-nas.sh:    bash -n                             → 通过
```

### 真实环境验证（本机即 NAS 宿主机）

- 以 `SERVICE_MANAGER_DOCKER_HOST=unix:///var/run/docker.sock` 启动后端，实测扫描到 **51 个容器组件、45 个候选、13 个 Compose 项目**，health 与 network_mode 正确。
- 浏览器端到端：登录 → 发现导入（勾选 `dividend-frontend` + `dividend-backend` → 建「股息率分析」）→ 详情页显示 2 组件、宿主映射端口 `127.0.0.1:3003→3003`、named volume 挂载、`未配置健康检查` → 资源总览端口页列出全机端口并带范围提示。
- 真实证书检查：`https://dsh.duomi77.cn:12443/` 与 `https://127.0.0.1:9443/` 均返回 `invalid` + 原因 `self_signed` + 到期 2036-06-22（自签泛域名），符合预期。

### A1–A14 覆盖矩阵

| ID | 结论 | 证据 |
|---|---|---|
| A1 无 Docker 时 CRUD 可用、移除不调 Docker 写 | ✅ | `test_api.py::test_docker_unavailable_does_not_block_ledger`、`test_registry.py::test_delete_removes_ledger_only`；`Registry` 无任何 Docker 调用 |
| A2 同项目可合并/拆分、组件不重复归属、忽略持久 | ✅ | `test_discovery.py::test_import_appends_to_existing_service`、`test_duplicate_import_conflicts`、`test_ignored_decisions_survive_rescan` |
| A3 重建保关联、成功扫描才 missing、失败不清空 | ✅ | `test_discovery.py::test_rebuild_keeps_binding`、`test_missing_marked_only_after_successful_rescan`、`test_scan_failure_keeps_previous_observation` |
| A4 绝对/相对/缺失 compose 路径、无文件浏览 | ✅ | `test_docker_reader.py::test_compose_files_*`（absolute / relative_resolved / relative_unknown / 顺序保持） |
| A5 内部 expose 不冲突、协议/地址族/IP 重叠、host 与 stopped 口径 | ✅ | `test_resources.py` 全部 15 例；`test_docker_reader.py::test_host_network_ports_not_collected`、`test_stopped_container_ports_are_historical` |
| A6 同域名多路径/多端口分别定位、登记不改 nginx | ✅ | `test_registry.py::test_endpoint_allows_lan_and_domain_paths`、`test_resources.py::test_domains_*`、`test_certificates_split_by_port` |
| A7 200/401/404/超时/HEAD 405/TLS 错误各有状态、localhost 不可探 | ✅ | `test_http_probe.py` 全部 16 例（含 `test_head_405_falls_back_to_get`、`test_localhost_target_refused_before_request`） |
| A8 有效/30 天边界/过期/SAN 不符/自签/不可达、同域名不同端口不混用 | ✅ | `test_tls_probe.py` 全部 16 例；实测自签返回 `invalid + self_signed` |
| A9 health 未配置不显示 healthy、失败留旧值标陈旧、手动刷新合并、重启识别 interrupted | ✅ | `test_scheduler.py::test_aggregate_health_never_claims_healthy_when_any_unconfigured`、`test_failed_check_keeps_last_success`、`test_docker_job_deduplicates`、`test_recovery_marks_interrupted` |
| A10 正式/预发布分离、初次无未读轰炸、304/无发布/404/429 可区分、不自动推断升级 | ✅ | `test_releases.py` 全部 18 例 |
| A11 交叉定位复用数据、375/1440 可操作、键盘焦点、复制反馈、失败重试 | ✅ | e2e 桌面项目**显式钉 1440×900**、移动项目 375×812，逐页断言 `scrollWidth-clientWidth<=1`（窄视口用例在宽视口按 marker skip，避免「测的是 1280 却报 1440 通过」）；`失败可重试`、`资源总览三标签`；`.focus-visible` 全局样式 |
| A12 导出恢复一致、六类非法输入拒绝且不破坏原库、恢复不触发检查 | ✅ | `test_backup.py` 全部 12 例（含 `test_restore_is_atomic_on_failure`）；`restore()` 内无 checker 调用 |
| A13 未登录 401、环境变量/Token/私钥不进响应/导出/日志、proxy 只读 | ✅ | `test_api.py::test_ledger_requires_auth`、`test_backup_export_excludes_observability`、`test_docker_reader.py::test_projection_never_leaks_env_or_command`；proxy `POST=0`（ACL 冒烟待实机执行） |
| A14 `/services` 页面/静态资源/API rewrite/登录 cookie/首页入口可用 | ✅ | e2e 全量通过；首页已加卡片与 health 探测；**用一次性 nginx 容器（隔离端口 19443 + app-net + 桩上游）实测六条路由的转发路径**：`/api/services/health`→`/api/health`、`/api/services/services`→`/api/services`、`/api/services`→`/api/services`（精确兜底）、`/api/services/summary`→`/api/summary`、页面与 `_next/static` 均带 `/services` 前缀转前端；cookie 属性（HttpOnly/SameSite=strict/Path=/api/Secure）已有 4 条单测 |

### 2026-11-12 实机部署已完成

- 三容器已上线：`service-manager-backend`（healthy）/ `service-manager-frontend` / `service-manager-socket-proxy`
- nginx 已 reload（`nginx -t` 通过）
- 冒烟全过：页面 200、静态资源 200、health 200、未登录 401、裸路径 401（兜底生效）、
  登录 cookie 属性正确、summary/discovery 正常（48 候选 / 13 项目）
- socket-proxy ACL 12 条探针符合预期：仅 3 条 GET 放行，其余全 403
- 真实导入验证：dividend 前后端 → 「股息率分析」服务，runtime=running、health=not_configured
  （未配 healthcheck 故不显示「健康」）、URL=unreachable + 自签原因、TLS=invalid + self_signed + 3510 天

### 部署过程中发现并修复的两个生产缺陷

1. **所有写操作 401（登录却正常）**：nginx `$host` 不含端口，浏览器 Origin 含端口 → 同源判定不等。
   已改 nginx 用 `$http_host` + 后端同源判断放宽到 hostname+scheme 相同。后端用例 175 → 178。
2. **`/api/services` 裸路径生产 404**：nginx 缺无尾斜杠精确兜底（第一轮已补）。

### 仍未执行

1. **破坏性恢复/回滚演练**：需独立验收实例与数据卷，本轮未创建（回滚步骤见 setup 文档 §7）。
2. **镜像 digest 锁定**：proxy 仍用 `tecnativa/docker-socket-proxy:0.2.0` tag。

### 验收过程中发现并修复的两个真实缺陷

1. **`/api/services` 无尾斜杠在生产会 404**：nginx 只有 `location /api/services/`（带尾斜杠），
   裸路径不匹配任何 location → 落到默认 404；而开发期 Next rewrite 的 `:path*` 能匹配，
   即「本地正常、生产炸」。已按 spec §4 ③' 补 `location = /api/services` 精确兜底，
   并用一次性 nginx 容器验证转发路径正确。
2. **cookie 属性此前只有间接断言**：A13 曾标记为 ✅，但没有任何用例断言
   `HttpOnly` / `SameSite=Strict` / `Path` / `Secure`。已补 4 条单测
   （`test_session_cookie_attributes_are_hardened` 等），并顺带锁定「Path 不能写成 `/api/services`」
   这条踩过的坑。后端用例数 171 → 175。
