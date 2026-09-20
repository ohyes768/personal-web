# Skill 发布管理台

## Goal

新增一个独立的 NAS 管理应用，用可视化双栏发布流程管理自研与 GitHub 开源 Agent Skills，并将选中的 Skill 安全发布到 NAS 宿主机运行的 OpenClaw 和 Hermes。

## Confirmed Facts

- Skill 源库是 `https://github.com/ohyes768/skills.git`；Windows 开发源目录为 `F:/personal-projects/skills`。
- 源库目前以 `skill-agent-matrix.html` 内嵌 JSON 记录 Skill、Agent 分配与 GitHub 版本；现有 Python 脚本分别处理自研 Skill、GitHub Skill 缓存/安装与 GitHub 版本检查。
- OpenClaw 与 Hermes 运行在 NAS Linux 宿主机，而非 Windows 或容器内；现有 Windows junction 实现不能用于生产发布。
- personal-web 当前 NAS 部署使用 Docker Compose 与外部 Nginx，现有应用没有通用登录体系。

## Requirements

### R1. 独立管理台与双栏发布体验

- 新建独立应用，作为 personal-web 的一个独立 NAS 服务和反向代理路由部署。
- 左栏为可用 Skill 池，支持按名称、来源（自研/GitHub）、标签、状态与更新状态筛选。
- 右栏为本次发布队列，支持在左右栏之间添加/移除；移出队列仅取消本次选择，不影响已发布的 Skill。
- 队列明确选择发布目标：OpenClaw、Hermes 或两者，并在提交前展示将新增、更新、跳过的项。
- 左栏卡片展示标签、来源、远端/缓存版本以及两个目标的部署状态；右栏自动汇总新增、更新与无需操作项。

### R2. Skill 来源与登记

- 同时管理自研 Skill 库与 GitHub 开源 Skill。
- 将当前静态 HTML 的内嵌注册表迁移为 Skills Git 仓库中独立、可版本控制的 `registry.json`；发布历史与运行状态不写回注册表。
- 首版支持从界面新增 GitHub Skill：输入 GitHub 仓库地址，后台拉取到受控临时缓存，扫描并校验 `SKILL.md`。
- 多 Skill 仓库须允许管理员从扫描到的候选目录选择要登记的 Skill；该目录为系统发布定位信息。
- Skill 可配置多个标签；标签是界面分组与筛选的主要分类方式。

### R3. GitHub 更新

- 管理员手动触发检查 GitHub 更新；页面展示远端最新版本/commit、本地缓存版本和每个 Agent 的已发布版本。
- 发现更新后，管理员自行筛选加入右栏并发布；首版不自动更新或自动发布。
- 检查更新不下载或发布；实际缓存更新仅随管理员确认的发布执行。

### R4. NAS Linux 发布、状态与回滚

- NAS 端维护自研 Skills Git clone 与 GitHub Skill 缓存；不依赖 Windows `F:` 路径。
- 发布到 OpenClaw/Hermes 时使用 Linux symbolic link，目标路径、缓存路径及源库路径均由部署时的受限配置提供。
- 发布以可验证的临时链接和原子替换完成；单项失败不得破坏其他已部署 Skill。
- 展示每个目标的已部署状态、来源版本和最近一次发布结果；保留一次可回滚的已知版本。
- 提供独立“下架”操作；下架不得与从发布队列移除混淆。

### R5. 写操作保护

- 浏览、筛选和检查 GitHub 更新不要求登录。
- 新增 GitHub Skill、发布、更新、下架和回滚均要求在确认窗口输入由 NAS 环境变量提供的管理密码。
- 密码不持久化、不回显；服务端不得允许调用方传入任意文件系统路径或命令。
- 确认发布时必须展示逐项计划与执行结果；下架、回滚同样须密码确认。

### R6. 容器权限边界

- 管理台运行于 Docker 容器，但仅挂载 NAS 宿主机的 Skills 源库、GitHub 缓存、OpenClaw 技能目录、Hermes 技能目录和应用状态目录。
- 不挂载 Docker socket、宿主机根目录或其他无关目录。
- 管理台由独立 Next.js 前端与 FastAPI 后端组成；SQLite 仅保存发布审计、回滚快照和运行状态。

## Acceptance Criteria

- [ ] 管理台以独立服务和路由在 NAS 部署，且可进入双栏发布界面。
- [ ] 管理员能以名称、来源、标签、状态、更新状态筛选左栏 Skill，并将任意 Skill 加入/移出右栏队列；移出不会改变当前部署。
- [ ] 管理员可登记一个 GitHub 仓库；系统拒绝无 `SKILL.md` 的候选，能从多 Skill 仓库中选择有效目录，并保存标签。
- [ ] 手动检查更新后，GitHub Skill 展示远端、本地缓存、OpenClaw 与 Hermes 的版本差异；不会自动发布。
- [ ] 对选择的一个或两个目标发布时，服务只在配置的 NAS 目录内创建/替换 Linux symbolic link，并以原子替换保证失败不破坏现有已发布链接。
- [ ] 发布、更新、下架和回滚要求正确管理密码；错误密码或未认证请求不会改变文件系统或注册信息。
- [ ] 单项发布失败时，页面显示该项原因，未失败项和既有 Skill 均保持可用。
- [ ] 管理员可查看每个目标的部署状态与最近一次发布记录，并可把某项回滚至上一次成功版本。

## Out of Scope

- 多用户、角色权限、用户注册与长期账户体系。
- GitHub 更新的定时检查、自动更新或自动发布。
- SSH、远程主机、Docker 容器内 Agent 或 Windows 目标的发布。
- 把队列移除当作下架操作。
