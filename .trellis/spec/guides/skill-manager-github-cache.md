# Skill Manager GitHub 缓存生命周期

> **Purpose**: 讲清 GitHub 来源 Skill 的发布源（本环境缓存）何时被 clone/fetch、
> 仓库共享缓存与 staging 发布模型（2026-09-30）如何工作、缓存缺失为什么会
> 导致"已阻止"死锁、以及 Clone 端点如何打破死锁。
> 排查"源不可用：source directory does not exist"报错前必读。

---

## 缓存是什么

GitHub 来源 Skill 的发布源不在源库，而在本环境缓存目录。自 2026-09-30 起
缓存是**仓库维度共享**的，发布经 **staging 快照**落地：

```
${GITHUB_SKILL_CACHE_ROOT}/
├── repos/<owner>__<repo>/        # 整仓 clone，同仓库所有条目共享一份
│   └── <registry.path>/SKILL.md  # path 为 "." 时即仓库根
├── staging/<skill-id>/<rev12>/   # 发布快照：skill 子目录 + shared_paths
│   └── (rev12 = full sha 前 12 位；缓存缺失时为 "uncached")
├── .tmp/                          # 首次 clone 的临时目录，成功后原子 rename
```

（扫描临时 clone 在 `${STATE_DIR}/scan/*`，用完即删，不落缓存根。）

- `repos/` 目录名 `<owner>__<repo>`：owner 段禁止下划线（URL 规范化正则
  保证），`__` 分隔可用 `partition("__")` 可逆解析回 (owner, repo)；
- 删除登记条目时若该仓库已无其他条目引用，共享缓存随之清理；同仓库还有
  条目则保留。

**登记真源是 skill-manager 自己的 SQLite（`registry_skill` 表）**，环境本地；
缓存也是环境本地的。skills 源库的登记/发布 sync 工具链已于 2026-09-22 废弃
（`registry.json` / `sync-config.json` / `scripts/sync_*.py` 全部删除）——
skill-manager **不读源库任何登记文件**：自研 Skill 经 `sync_local()` 对账自动
登记，GitHub Skill 经 API 登记，见
[skill-manager-registry-sync.md](./skill-manager-registry-sync.md)。

## clone/fetch 的全部触发点

| 环节 | 代码位置 | 行为 |
|------|---------|------|
| UI 登记 | `POST /skills/github` → 同步预检 + 后台任务 → `check_update` + `ensure_cached` | 缓存缺失 clone，已有 fetch |
| UI 批量登记 | `POST /skills/github/batch` → 同步校验 + 后台 `register_batch` 任务 | 仓库级 ensure_cached 一次 + 逐项 ensure_skill_path_cached |
| 卡片 Clone 按钮 | `POST /skills/github/{id}/clone` → 同上 | 缓存缺失时 clone，已有则 fetch |
| UI 扫描 | `POST /skills/github/scan` → 同步预检 + 后台任务 → `scan()` | 临时 clone，用完即删 |
| 发布执行 | `_ensure_cached_at_recorded_revision` | 有成功检查记录才 fetch/checkout |
| 计划预览 / 检查更新 | `plan` / `check-updates` | **只读，绝不 fetch**（design 4.2/5） |

四个写入口（登记/批量登记/Clone/扫描）自 2026-09-26 起均为**后台任务**（`GithubTaskManager`，
内存态、daemon 线程）：同步段只做密码校验 + ≤30s ls-remote 预检，202 返回
`{task_id, kind}`，前端经 `GET /skills/github/tasks/{task_id}` 轮询。要点（勿回退）：

- clone 统一走 `_run_git_streaming`（Popen + 读线程），`git --progress` 的
  进度行以 **`\r` 而非 `\n`** 分隔，管道读取必须按 `[\r\n]` 双分隔符切行并
  保留残尾缓冲（`_ProgressLineSplitter`），只按 `\n` 迭代会把整个进度当成一行；
- 超时靠"stdout/stderr 各一条 drain 线程 + 主线程 `wait(remaining)` 到点
  kill"实现——只 drain stderr 不 drain stdout 的话，git 挂死时 stdout 管道
  永不关闭，`stderr.read()` 会永远阻塞，超时失效；
- 后台 clone 超时 `_GIT_TIMEOUT_SECONDS = 1800`（nginx 300s 只约束单次 HTTP
  往返，不再约束 git 时长）；`verify_reachable` 仍是独立 30s；
- 首次 clone 落 `.tmp/<repo>-<uuid>` 校验后原子 `replace` 进 `repos/<owner>__<repo>`，
  失败不留半成品（根治"中断半成品导致快速失败"）；rename 前发现正式目录已存在
  （并发 clone 先行落地）则弃本次 tmp 直接复用；`state/scan/*` 与 `.tmp/*`
  残留由 lifespan 启动时 `cleanup_stale_workspaces` 清理；
- 任务是内存态，服务重启即丢（轮询得 404 `task_not_found`），完结任务 30
  分钟后惰性回收；前端对 404 的提示文案依赖这一语义。

## staging 发布模型（2026-09-30）

GitHub 条目的 symlink 不再指向缓存子目录，而是指向 **staging 快照**
（`Publisher.stage_github_skill`，publisher.py）：

- 路径 `staging/<skill-id>/<rev12>/`，rev12 = full sha 前 12 位；
  组装内容 = `shared_paths` 随行资源（仓库根级目录/文件，如 `tools/`）先拷 +
  skill 本体子目录后拷（本体覆盖同名）；`.git` 永不进产物；
- 每次 rev 一个独立快照目录：共享缓存后续 fetch/checkout 到其他 revision
  不影响已发布内容，symlink 原子切换零悬空窗口；
- 同 rev 目录已存在（重复发布同版本）直接复用；组装落 `.tmp` 后原子 rename；
- 每个 skill 只保留最新 **2** 个 rev 目录（`st_mtime_ns` 倒序清理），
  回滚意义上够用且控磁盘；
- 计划预览用 `planned_staging_dir` 只读计算，不组装；
- 删除登记时 `remove_staging` 清掉该 skill 全部 rev（尽力而为）。

**shared_paths 的语义**：登记/批量登记时随条目落库（`registry_skill.shared_paths`），
发布时从共享缓存仓库根拷进快照，解决合集仓库根级共享资源（如 ai-berkshire
的 `tools/` 断链）问题。前端默认预选候选 SKILL.md 引用到的顶层路径，且
**排除候选目录的祖先目录**（勾上 `codex-skills/` 会把整棵候选树拷进快照）。

## 启动迁移（2026-09-30 一次性兼容）

共享缓存模型上线时，旧「每 skill.id 一份整仓 clone」布局由 lifespan 启动时
的 `services/migration.py` 处理，**全部无网络**（绝不 fetch/clone）：

1. `migrate_legacy_cache`：`${CACHE_ROOT}/<skill.id>/` 搬到 `repos/<owner>__<repo>/`。
   同仓库多份旧缓存只保留先落地的一份（发布时按各条目记录 revision 重新
   fetch/checkout，无数据损失），多余副本直接删除；单项失败只记日志不阻断启动；
2. `republish_active_github_skills`：迁移后旧 symlink target 失效，对
   deployment 中 status=active 的 github 条目用缓存当前 checkout 状态重组
   staging 并替换链接（等价自动重发布）。失败逐条记 deployment_history
   （result=error）+ warning 日志不阻断启动——缓存缺失的条目由 UI 的
   `link_missing` 暴露，管理员经 Clone 重建后再手动发布。

## 批量登记（2026-09-30）

合集仓库（一个 repo 含多个 SKILL.md）经 `POST /skills/github/batch` 一次
登记多条：同步段密码校验 + 全量路径校验（含 `/etc`、`..` 逃逸、批内重复，
400 `invalid_path` 零缓存副作用）→ 202 后台 `register_batch` 任务：

- 仓库级 `ensure_cached` 只执行一次，逐项 `ensure_skill_path_cached`（纯
  文件系统校验，零 git 操作）+ upsert；
- 逐项成败快照进 `results`（running 中即可轮询到已完成项），单项失败不
  中断后续项；skill_id 撞已有登记时派生 `-2` 后缀；
- 全部失败 → 整体 state=error（`error_code=cache_failed`），results 保留
  供前端逐项展示；
- 密码只进同步请求体，绝不进任务快照/日志（AC5）。

## 死锁的成因与打破方式（2026-09 修复）

发布执行虽然有 `ensure_cached` 自救，但计划预览对缓存缺失判 `blocked` →
前端只发布 add/update 项 → 永远走不到发布。**没有 Clone 端点前，已注册但
缓存丢失的 Skill 界面上无法发布。**

修复要点（勿回退）：

- `SkillCard.cache_missing`：github 来源且 `!(repos/<owner>__<repo>/.git).is_dir()`
  （`GitCacheService.is_cached`）。纯文件系统判断、零 git 子进程，与
  `ensure_cached` 决定 fetch/clone 的口径一致；
- Clone 端点语义必须与**登记流程**一致（`check_update` → `ensure_cached`），
  **不能**改用 `_ensure_cached_at_recorded_revision`——它在无成功检查记录时是
  no-op，对"缓存根本不存在"的场景无效；
- 前端 `cache_missing` 时禁用目标 chips 与"加入队列"，强制先 Clone。

## 相关坑

- **symlink 全命名空间一致**：symlink target 是写入时的字面路径。Hermes/
  OpenClaw 跑在宿主机，所以 NAS 部署必须用**同路径 bind mount**
  （`${VAR}:${VAR}`，env 根 = 宿主路径，`SKILL_MANAGER_TARGETS_MOUNT_ROOT`
  不传）——容器内写的路径即宿主机路径，两侧解析一致。任何"容器 A 路径 +
  宿主机消费"的组合都会断链（2026-09 生产实锤：`~/.hermes/skills/<id>` →
  `/mnt/...` 宿主机不可解析）。迁移/回滚步骤见
  [deploy/README-same-path-mounts.md](../../../deploy/README-same-path-mounts.md)；
- **运行镜像必须含 git**：`python:3.12-slim` 不带 git，Dockerfile 漏装时所有
  git 调用（登记/检查更新/Clone）抛 `FileNotFoundError` → 500（2026-09 生产
  实际发生）。已双保险：Dockerfile 补装 git；`_run_git` 把 `FileNotFoundError`
  包装为 `GitOperationError`，降级为 400 cache_failed；
- **NAS 生产容器的 GitHub 连通性**：直连被墙（GnuTLS -110），走宿主机
  FastGithub 代理——但它只听 127.0.0.1 且为 MITM 模式，容器侧需要
  socat 转发 + HTTPS_PROXY + GIT_SSL_CAINFO 三件套，完整步骤见
  [deploy/README-fastgithub.md](../../../deploy/README-fastgithub.md)；
- Windows 开发机非提权进程无法创建 symlink（WinError 1314），发布会在
  publisher 建临时 `.next` 链接一步失败——本地只验收 plan 与 clone，
  完整发布链路在 Docker/Linux 验证；pytest 侧见
  [Windows 测试环境契约](./testing-environment.md) 的 `requires_symlink`；
- **github path 的绝对路径判定必须用 `PurePosixPath`**（routes.py 同步校验、
  registry `_check_path`、git_cache `_require_safe_relative_path` 三处同口径）：
  Windows 上 `Path("/etc").is_absolute()` 为 False（无盘符不算绝对），用
  `Path` 判定会把 `/etc`、`/..` 逃逸路径放进后台任务，最后只能靠 cache_failed
  兜底而不是同步 400。仓库 path 是 posix 仓库路径，不是本机路径；
- 手工往 SQLite `registry_skill` 表插 GitHub 条目不会触发 clone，发布前必须走
  Clone 按钮（或补一次登记流程）；
- 登记/删除**无任何 git 写依赖**（2026-09-21 迁移后）：源目录不需要是 git
  仓库、不需要凭据；此前"git add/commit registry.json 失败导致登记/删除
  报错"（NAS `git add` 128 等）一类问题已随迁移根除；
- 删除已登记 GitHub 条目只影响**本环境**的 DB、状态库与缓存；源库已无
  registry.json（工具链废弃），不存在"管理台操作要回写源库"的桥。
