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

- [ ] 定义 design.md 中各表、唯一约束、外键与带时区时间模型，设置 pytest basetemp 为 `.pytest-tmp`。
- [ ] 先写台账持久化、重复 source_key、PATCH 旧 revision、删除只移除台账的失败用例；运行确认确实因缺功能失败。
- [ ] 实现 SQLite/registry 与 `/services` CRUD，分页默认 50、最大 100；人工新增不依赖 Docker。
- [ ] 写登录前 401、错误口令、限速、过期会话、篡改 cookie、Origin 不匹配、注销的 API 用例。
- [ ] 实现 auth 和 lifespan；生产 env 缺密码/签名密钥拒绝启动，测试用 dependency overrides 注入固定值。
- [ ] 执行 `uv run pytest tests/test_registry.py tests/test_auth.py -v`，确认全通过；Docker 依赖不可用不影响 CRUD。

**交付**：可认证的空台账后端，覆盖 A1、A2 的唯一约束和 A13 的 API 边界。

## M2：Docker 发现与组件导入

**新增文件**：`src/docker_reader.py`、`src/discovery.py`、`tests/test_docker_reader.py`、`tests/test_discovery.py`、`tests/fixtures/docker_inventory.json`。

**步骤**

- [ ] fixture 包含 personal-web 多组业务、immich 多组件、host 网络、无标签、相对 config_files、stopped、oneoff、同 service 重建；使用合成数据，不包含 NAS 凭据。
- [ ] 写白名单投影/稳定身份/相对路径/重建保关联/扫描失败保旧数据的失败测试。
- [ ] 实现 SDK API 自动协商与 timeout；只调用 version/ping/container list+inspect；SDK 不调用 exec/logs/archive/image pull。
- [ ] 实现完整扫描 generation 事务发布、404 消失处理、状态/health 分离；不记录原始 inspect。
- [ ] 实现发现候选、批量归组、追加、required、忽略与取消；幂等校验以 source_key 唯一约束为准。
- [ ] API 测试并发导入同一组件得到一个成功和一个 409；扫描不能覆盖人工入口/笔记。
- [ ] 执行 `uv run pytest tests/test_docker_reader.py tests/test_discovery.py -v`，确认 A2–A4 通过。

**交付**：可读 Docker 元数据并确认导入，未分组/缺字段服务有兜底。

## M3：访问入口、资源投影与导出恢复

**新增文件**：`src/resources.py`、`src/backup.py`、`tests/test_resources.py`、`tests/test_backup.py`。

**步骤**

- [ ] 实现 endpoint/route_target/port_notes 的模型、事务更新和来源标记；endpoint 的用户 URL 与探测 URL 分离。
- [ ] 写 8097 内部 expose 重复不冲突、TCP/UDP 分开、通配与单 IP 重叠、IPv6 边界、host 未知、stopped 历史映射的测试。
- [ ] 实现端口总览覆盖全部候选，域名按 endpoint 推导，证书按 host+port 去重；各行返回服务/组件引用用于跳转。
- [ ] 实现跨名称/用途/标签/域名/端口/路径搜索，参数化 SQL 与一致分页，不在前端另建搜索真源。
- [ ] 写人工台账 JSON 导出/恢复 round-trip、重复绑定、缺外键、schema 错误、超大 JSON、过期预览 revision 与事务中途失败用例。
- [ ] 实现预览 digest、确认恢复、恢复前 SQLite backup、事务替换及缓存失效；导出排除凭据/运行快照/发布缓存/已读标记/历史 job，恢复后发布从新基线开始。
- [ ] 执行 `uv run pytest tests/test_resources.py tests/test_backup.py -v`，确认 A5/A6/A12 通过。

**交付**：完整可检索台账与可恢复数据；端口总览不会把内部端口冒充宿主端口。

## M4：URL、证书、发布动态及检查调度

**新增文件**：`src/checks/common.py`、`src/checks/http_probe.py`、`src/checks/tls_probe.py`、`src/checks/github.py`、`src/checks/scheduler.py`、`src/jobs.py`；对应 `tests/test_http_probe.py`、`test_tls_probe.py`、`test_releases.py`、`test_scheduler.py`。

**步骤**

- [ ] 定义统一检查 envelope、last_attempt/last_success/check_status/current_state/stale，失败不清旧 payload。
- [ ] 用可控本地 HTTP fixture 测 200/401/404、HEAD 405 后 GET、重定向跳数、非 HTTP/凭据/localhost/元数据地址、响应截断与总超时；实现有限探测。
- [ ] 用测试生成的证书与固定时钟测有效/30 天阈值/过期/SAN 不符/不可信/连接失败，显式 TLS 端口与 SNI 均应被断言。
- [ ] 实现 TLS 验证结果与可选公开叶证书解析分离，失败链不能被当成有效链；证书不从本机证书文件读取。
- [ ] 用 HTTP mock 测 Release 稳定版过滤、latest 独立结果、初次基线、后续未读、显式已读、共享缓存隔离、分页截断、304、404、429 与限流重置。
- [ ] 实现 GitHub 串行请求/ETag/退避；安装版本只作备注，原始发布说明保留原文。
- [ ] 实现单 worker 后台循环、每目标锁、全量/单目标刷新去重、job 持久化、重启 interrupted、7 天 job 清理和 checker heartbeat。
- [ ] 测试 Docker 故障、GitHub 限流与某个 URL 超时不影响其他任务；手动刷新不能绕过全局 GitHub 退避。
- [ ] 执行 `uv run pytest tests/test_http_probe.py tests/test_tls_probe.py tests/test_releases.py tests/test_scheduler.py -v`，确认 A7–A10 通过。

**交付**：定时/手动检查都遵守同一状态和任务契约，失败可定位。

## M5：前端页面与可用性

**新增文件**

- `apps/service-manager/package.json`、`pnpm-lock.yaml`、`next.config.mjs`、`tsconfig.json`、`eslint.config.mjs`、`Dockerfile`、`.dockerignore`。
- `src/app/layout.tsx`、`globals.css`、`page.tsx`、`service/[id]/page.tsx`、`resources/page.tsx`、`discovery/page.tsx`、`settings/page.tsx`。
- `src/lib/api.ts`（API 客户端/类型）、`src/lib/status.ts`（状态文案）、`src/components/SessionGate.tsx`、`ServiceForm.tsx`、`EndpointForm.tsx`、`StateBadge.tsx`、`ReleaseList.tsx`、`RestoreDialog.tsx`。
- `playwright.config.ts`、`e2e/service-manager.spec.ts`；服务/端点表单过大时按职责拆分，不堆入 page.tsx。

**步骤**

- [ ] 先加载前端技能/规范，在已批准信息结构内制定具体视觉样式；这属于实施时 UI 工作，不在当前文档中假定已有设计系统。
- [ ] 创建 Next.js standalone，basePath `/services`；开发 rewrite `/api/services/:path*` → backend `/api/:path*`，basePath=false。
- [ ] 实现会话门禁、统一 API 错误与 409 重新加载提示；不把密码/Token 写入 localStorage，不创建 Next BFF。
- [ ] 实现首页/详情/导入页，支持分组、required 和忽略；所有状态显示来源、最后成功时间和错误。
- [ ] 实现资源页三标签、搜索筛选、入口跳转、路径复制；保留端口采集范围提示。
- [ ] 实现 Release 安全 Markdown、逐条已读与恢复预览确认；用户取消不得修改数据。
- [ ] Playwright 覆盖登录、导入两个组件、编辑入口、搜索域名/端口、刷新失败、读发布、导出/恢复、删除台账；浏览器走真实测试后端，外部探测用 fixtures。
- [ ] 在 375px/1440px 检查布局、键盘焦点、返回首页与复制；前端所有用户 URL/原文链接限制 http/https。
- [ ] 执行 `pnpm exec eslint .`、`pnpm exec tsc --noEmit`、`pnpm build`、`pnpm exec playwright test`；Windows standalone 若遇现有 symlink 限制，补 Linux 镜像构建验证，不把非 standalone 构建等同 NAS 部署通过。

**交付**：五个页面可完成主要管理流程，覆盖 A11 与 API/UI 跨层验收。

## M6：NAS 接线、全量验收与回滚材料

**新增**：`docs/service-manager-nas-setup.md`、`scripts/start-service-manager-dev.bat`、`.trellis/spec/backend/service-manager/backend/index.md`、`contracts.md`、`.trellis/spec/apps/service-manager/frontend/index.md`。

**修改**：`docker-compose.nas.yml`、`nginx/web.conf`、`nginx/html/index.html`、`scripts/deploy-nas.sh`、`DOCKER_DEPLOY.md`、`README.md`、`CLAUDE.md`、`.gitignore`、`.trellis/config.yaml`。

**步骤**

- [ ] 部署前重新确认端口 3012/8102、网络名与 env 配置；镜像 proxy 锁定 digest，记录实测兼容版本。
- [ ] Compose 新增 frontend/backend/socket-proxy 三服务、data volume 与 internal Docker 读取网络；后端不挂 socket/宿主目录，proxy 不发布端口。
- [ ] 为 Nginx 补 upstream、页面、静态资源、API 三件套，确认无尾斜杠请求覆盖；前端路由和 API 前缀不双拼。
- [ ] 更新 deploy-nas target/all/buildx/help、首页卡片与健康列表、启动脚本、文档、ignore 与新 package/spec；不改变旧模块行为。
- [ ] 后端全量 `uv run pytest tests/ -v`；前端 lint/typecheck/build/e2e 全量；`docker compose -f docker-compose.nas.yml config --quiet` 和 `bash -n scripts/deploy-nas.sh` 通过。
- [ ] 有实现部署授权后才构建/启动新模块；执行 Nginx 配置测试，静态资源/页面/API/登录 cookie 冒烟。
- [ ] 从后端网络验证 proxy 允许必要 GET，同时对新建/重启/exec/DELETE 与非授权类别使用无副作用的无效目标请求，断言 proxy 403；不拿真实业务容器试写操作。
- [ ] 对实际 NAS 选取 personal-web 多服务、immich 多组件、host 网络、无标签各一例导入验证；不调整被管理容器配置。
- [ ] 使用专用验收实例/数据卷验证恢复与回滚，禁止用生产台账做破坏性恢复实验。
- [ ] 全范围 trellis-check，逐项登记 A1–A14 证据；按项目要求更新 spec、审核本任务提交文件列表。没有用户实现授权时停留在规划状态。

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
