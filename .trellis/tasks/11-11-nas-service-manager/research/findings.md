# 规划研究：NAS 服务管理台

研究日期：2026-11-11。仅阅读本地代码、官方文档和 NAS 元数据；未执行部署、启停、配置修改，也未读取容器环境变量或证书私钥。

## 1. 用户决策

当前聊天已完整保留讨论，无需另查历史会话。

- 起点是软件收藏和版本监控，最终收敛到 NAS 服务管理。
- 使用 Docker Compose；第一版管理台账、读取状态、检查 URL/证书、浏览发布动态。
- 是否升级由人决定；接受暂不修改 Compose、端口、域名和容器运行状态。
- 本轮只要求完成规划，尚未授权实现或部署。

## 2. 仓库证据

| 证据 | 结论 |
|---|---|
| `docker-compose.nas.yml:594-635` | task-web 已用 Docker socket，但承担执行职责，不能复用其执行入口作为本管理台的数据 API |
| `docker-compose.nas.yml:641` | 现有应用网络实际名称为 `nginx_nginx-bridge` |
| `nginx/web.conf` 的 upstream、`listen 9443 ssl`、路径 location | 域名、端口、路径共同决定入口；仅记录域名不足以定位服务 |
| `nginx/html/index.html:221`、`:251` | 新模块需要首页入口与健康检查列表接线 |
| `scripts/deploy-nas.sh:31-36`、`:187-228` | Nginx 是独立 Compose 项目；新模块需补 target/all/buildx/帮助接线 |
| `.trellis/spec/guides/new-service-onboarding.md` | 新模块遵循 Next.js 无 BFF + FastAPI + Nginx API 转发，以及全部部署接入点；其中旧端口示例不能当作当前可用端口 |
| `apps/task-web/next.config.mjs` | 本地 API rewrite 设置 `basePath:false`；生产使用 standalone |
| `backend/skill-manager/src/main.py` | lifespan 初始化、依赖注入与结构化错误可参考；不引入跨应用业务模块依赖 |
| `.trellis/spec/backend/testing-environment.md` | Windows pytest 临时目录必须留在项目盘 |

已定向搜索现有 package/Dockerfile/next 配置、NAS Compose、Nginx、部署脚本，未发现前端 3012、后端 8102 被现有模块配置使用；NAS TCP 监听列表也未见这两个端口。端口只是规划预留，部署前仍需重查。

当前工作区已有 task-web 和金融脚本等其他未提交改动，本任务不拥有这些文件；后续接线必须在其最新内容上增量修改。

## 3. NAS 实测证据

通过已配置 SSH 连接执行 `docker ps`、字段受限的 `docker inspect`、`docker version`、`ss -lntH`。

- Docker Server 为 **29.1.3**，需要客户端 API 协商；不能固定老 API 版本。
- `personal-web` 项目工作目录 `/home/ohyes768/personal-web`，配置文件 `docker-compose.nas.yml`；一个项目包含多组业务服务，不适合一项目一卡片。
- `immich` 项目包含 server、database、machine-learning、redis，适合人工归成一个业务服务。
- `music-assistant`、`homeassistant`、`xiaomusic`、`nodered` 使用 host 网络；Docker 映射列表不能代表宿主机完整端口占用。
- `caddy`、`songloft`、`ddns-go` 等运行容器缺少 Compose 标签；需要未分组容器与手工台账兜底。
- 存在已退出任务容器和缺少工作目录的任务镜像容器，不能自动全部收入首页；需要候选导入与忽略。
- freshrss 的配置文件标签为相对路径 `docker-compose.yml`；只有同时有绝对工作目录时才可拼接为宿主路径。
- Nginx 运行时挂载多份配置，实际 `web.conf` 来源在独立 nginx 目录；只解析本仓库文件不足以得到全 NAS 反代配置。
- Nginx 发布多个 HTTPS 端口；证书检查必须尊重 URL 显式端口。
- Caddy 同时存在，但未见配置 bind mount；第一版不自动解析任一代理工具。
- 不保存完整运行容器清单到规划，仅保留上述影响架构的事实。

## 4. 外部一手资料与设计推论

- [Docker Compose services](https://docs.docker.com/reference/compose-file/services/)：Compose 提供 project/service 标签；host 网络没有普通端口映射。推论：以稳定标签绑定组件，但 host 端口必须标记未采集。
- [Docker Engine API](https://docs.docker.com/reference/api/engine/)：Engine/客户端有版本协商和最低版本约束。推论：采集器使用 Docker SDK 自动协商，补 Docker 29.1 集成验证。
- [Docker daemon access](https://docs.docker.com/engine/security/protect-access/)：Docker socket 是敏感访问入口。设计不将 `:ro` 挂载误称为 Docker API 只读权限。
- [Tecnativa docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)：可按 API 类别限制访问；`POST=0` 仅允许 GET/HEAD。推论：专用网络中的 socket proxy 优于业务后端直挂 socket，仍须过滤 inspect 中的敏感字段。
- [GitHub Release API](https://docs.github.com/en/rest/releases/releases?apiVersion=latest)：Release 与普通 Git tag 不等价，公开 Release 可匿名读取。第一版仅处理 Release，不将无 Release 项目误报为最新。
- [GitHub API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)：推荐条件请求、串行请求与遵守限流。设计采用定时队列、ETag、Retry-After/reset 退避。

以上外部文档用于技术核实，具体轮询频率、数据模型和界面范围均为本任务设计选择。

## 5. 方案比较与推荐

| 路线 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 纯手工台账 | 最快，零 Docker 接入 | 状态和端口容易过期 | 保留为 Docker 断连时的可用能力 |
| 台账 + Docker 读取 + URL/TLS/Release 检查 | 覆盖已确认需求，人工信息与观测分离 | 需 socket proxy、状态缓存和导入流程 | **V1 推荐** |
| 完整部署/反代/更新控制平台 | 操作集中 | 需处理写配置、回滚和不同代理工具 | 留到后续另行规划 |

未发现必须向用户补问才能完成规划的产品阻塞项。未明确的细节已作为设计默认值公开列出，待文档评审调整。
