# Skill 发布管理台 · 技术设计

## 1. 目标与边界

`skill-manager` 是 personal-web 内独立部署的管理应用。它管理自研 Skills 与 GitHub 开源 Skills，供管理员在双栏工作台中筛选、编排并发布到 NAS 宿主机上的 OpenClaw、Hermes。

本期没有用户体系、自动检查/发布、SSH 目标或 Windows 发布。公开只读查询可不登录；任何持久化或文件系统变更都要求管理密码。

## 2. 架构

```text
Browser ── /skills ──> Next.js frontend ── /api/skills ──> FastAPI backend
                                                               ├─ Skills source Git clone
                                                               ├─ GitHub repository cache
                                                               ├─ SQLite state/audit database
                                                               ├─ OpenClaw skills root (bind mount)
                                                               └─ Hermes skills root (bind mount)
```

### 2.1 新应用结构

- `apps/skill-manager`：Next.js 工作台，使用 `/skills` basePath；只调用受控的后端 API。
- `backend/skill-manager`：FastAPI，唯一拥有 Git、文件扫描、发布、回滚和密码验证能力。
- `docker-compose.nas.yml`：新增 frontend、backend 服务与只读/读写 bind mount。
- `nginx/web.conf`：为 `/skills` 页面、静态资源与 `/api/skills` 后端路由增加反代规则。

前端容器不拥有宿主机发布目录；后端也不拥有 Docker socket、宿主机根目录或任意可配置的路径写入权限。

### 2.2 固定环境配置

后端只从环境变量读取以下路径，并在进程启动时 `resolve()`、验证目录存在且位于挂载根内：

| 配置 | 含义 |
|---|---|
| `SKILLS_SOURCE_ROOT` | NAS 上 `ohyes768/skills` 的 Git clone |
| `GITHUB_SKILL_CACHE_ROOT` | 外部 GitHub 仓库缓存 |
| `OPENCLAW_SKILLS_ROOT` | OpenClaw 生效的 skills 目录 |
| `HERMES_SKILLS_ROOT` | Hermes 生效的 skills 目录 |
| `SKILL_MANAGER_STATE_DIR` | SQLite、发布快照和临时工作目录 |
| `SKILL_MANAGER_ADMIN_PASSWORD` | 管理密码，仅服务端读取 |

OpenClaw 与 Hermes 不是 API 入参的任意路径；它们只是固定 target key 到上述目录的映射。

## 3. 注册表与数据

### 3.1 Source registry

把 `skill-agent-matrix.html` 的内嵌 JSON 迁移到 `${SKILLS_SOURCE_ROOT}/registry.json`。注册表进入 Skills Git 仓库，故标签、GitHub 仓库、Skill 目录和展示元数据可审阅、可版本化。

每个条目至少包含：

```json
{
  "id": "stable-slug",
  "name": "display-name",
  "source": "local | github",
  "path": "relative/path/when/local-or-github-subdir",
  "repository": "https://github.com/owner/repo",
  "tags": ["research", "finance"],
  "summary": "...",
  "status": "active | deprecated"
}
```

- `source=local` 的 `path` 必须位于源库根内且目录包含 `SKILL.md`。
- `source=github` 的 `repository` 必须是规范化的 `https://github.com/<owner>/<repo>`；`path` 是扫描确认的仓库内相对目录，可为 `.`。
- 服务器端生成稳定 `id`，拒绝路径分隔符、路径穿越和重复项。
- 管理台登记 GitHub Skill 时用原子文件替换写入 `registry.json`，再执行限定的 Git add/commit；配置的仓库写入凭据仅用于推送该仓库的注册表变更。推送失败保留本地已提交版本，并在审计中标明“待推送”。

### 3.2 SQLite 状态库

SQLite 不替代 Git registry，只保存运行状态：

- `deployment`：skill、target、来源 revision、缓存路径/源路径、当前 symlink 目标、状态、发布时间。
- `deployment_history`：每次发布、下架、回滚的前后目标、结果、错误摘要和时间。
- `github_check`：远端版本/commit、检查时间、检查结果。
- `rollback_snapshot`：每个 skill × target 最近一次可恢复的 symlink 目标。

## 4. 左右双栏交互

### 4.1 可用 Skill 池（左栏）

左栏卡片显示名称、简介、标签、来源、远端版本、本地缓存版本、OpenClaw/Hermes 当前状态和更新标记。筛选支持名称、来源、标签、启用状态、未发布、待更新与发布失败。

“检查 GitHub 更新”仅执行 `git ls-remote`/读取当前 cache revision，更新 `github_check`，不 clone、pull 或发布。自研 Source 刷新采用 fast-forward-only 拉取 Skills 源库，失败时保持上一次已知工作树并展示原因。

### 4.2 发布队列（右栏）

把卡片加入右栏时选择 OpenClaw、Hermes 或两者。右栏为瞬时 UI 状态，不改变部署配置；移出右栏仅取消本次操作。

后端提供计划预览。每项按 `add`、`update`、`unchanged`、`blocked` 分类，展示目标、当前版本、待发布版本及阻止原因。只有选择 `add`/`update` 的项能进入发布确认。

### 4.3 受保护操作

新增 GitHub Skill、发布、下架与回滚均先展示确认 modal，再提交管理密码。密码只在本次请求体中传输，前端不持久化、后端不记录明文。

下架是单独危险操作；从队列移除绝不下架。回滚只能恢复该 target 的最近一次成功快照。

## 5. GitHub Skill 登记与更新

1. 管理员输入 GitHub 仓库 URL。
2. 后端验证 URL 的 host/path，clone 到 state 临时目录；不接受任意 Git protocol、文件路径或 command 参数。
3. 递归扫描候选 `SKILL.md`，忽略 `.git`、缓存、隐藏工具目录，返回候选相对目录。
4. 管理员选择一个候选，设置显示名、简介和标签；后端再次验证所选目录与 `SKILL.md`。
5. 后端把仓库按登记 ID 缓存至 `GITHUB_SKILL_CACHE_ROOT/<id>`，写入注册表、提交配置变更，并返回新卡片。

后续更新以手动“检查更新”开始。管理员将已更新的条目放入右栏并发布时，后端 fetch、检出受记录的 tag/commit，验证缓存内路径，随后再创建目标链接。不会因检查动作自动更改 Agent 能力。

## 6. Linux 发布与回滚

### 6.1 安全发布算法

对于每一项 `skill × target`：

1. 解析 source（自研库目录或 GitHub cache 子目录），确保目录及 `SKILL.md` 存在，且 `resolve()` 位于受控根中。
2. 计算目标链接 `${TARGET_ROOT}/${skill-id}`；拒绝目标名非法、目标根外路径、普通目录或指向根外的异常链接。
3. 在同一 target 目录创建唯一临时 symlink，例如 `.skill-id.<uuid>.next`，并验证它解析至预期 source。
4. 若现有正式 symlink 合法，先记录其目标作为回滚快照；用同文件系统 `rename()` 原子替换正式链接。
5. 写入 `deployment`、`deployment_history`，并返回成功结果。

每个项在独立事务/异常边界处理。某项失败只记录该项，绝不删除或重定向其他 Skill。临时链接在失败后清理。

### 6.2 下架与回滚

- 下架仅接受已知 `skill-id` 和 target；删除前确认正式链接存在、为 symlink、解析后位于受控根；然后删除链接本身，不递归删除任何目录。
- 回滚从 `rollback_snapshot` 取上一次成功目标，重新走临时链接与原子替换流程；没有快照则明确报错。
- 发布成功后按 target 配置显示“已生效”或“需手动重载”；本期不自动重启宿主机进程。

## 7. API 与错误契约

| API | 作用 | 密码 |
|---|---|---|
| `GET /api/skills` | 卡片、筛选数据和 target 状态 | 否 |
| `POST /api/skills/github/scan` | 临时 clone 与 `SKILL.md` 候选扫描 | 否 |
| `POST /api/skills/github` | 登记选定 GitHub Skill | 是 |
| `POST /api/skills/check-updates` | 检查远端/缓存版本 | 否 |
| `POST /api/skills/publish/plan` | 返回队列差异与阻止项 | 否 |
| `POST /api/skills/publish` | 执行发布 | 是 |
| `POST /api/skills/{id}/targets/{target}/rollback` | 回滚 | 是 |
| `DELETE /api/skills/{id}/targets/{target}` | 下架 | 是 |

错误格式统一为稳定 machine code、可展示中文消息与可选 item id。密码错误返回 401；非法 ID/path/target 返回 400；状态冲突返回 409；单项发布失败以 200 的批量逐项结果表达，不伪装为整体成功。

## 8. 验证策略

- 后端单元测试：注册表校验、GitHub URL 规范化、多目录 `SKILL.md` 扫描、密码验证、计划计算、拒绝路径穿越和非法 target。
- 文件系统测试：临时链接校验、原子替换、普通目录保护、单项失败隔离、下架不递归删除、回滚恢复。
- API 测试：只读端点、密码保护端点、批量混合结果、更新检查不写缓存/不发布。
- 前端测试：筛选、队列添加/移出无副作用、目标选择、发布计划、密码确认和失败反馈。
- 部署检查：Compose bind mount 只包含固定五类目录；Nginx `/skills` 与 `/api/skills` 路由正确；容器内不含 Docker socket。

## 9. 运维与回滚

- 任何发布失败以单项结果呈现，已有链接保持不变。
- 管理台自身部署失败可删除其 Compose 服务与 Nginx 路由；既有 Agent 的技能链接不受影响。
- 配置/注册表错误可从 Skills Git 历史恢复；已发布项可从 SQLite 快照回滚。
- NAS 部署前必须提供真实的 target 绝对路径、受限 bind mount、管理密码以及可选的 Skills 仓库写入凭据；路径不在管理界面中编辑。
