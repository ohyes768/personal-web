# Skill Manager GitHub 缓存生命周期

> **Purpose**: 讲清 GitHub 来源 Skill 的发布源（本环境缓存）何时被 clone/fetch、
> 缓存缺失为什么会导致"已阻止"死锁、以及 Clone 端点如何打破死锁。
> 排查"源不可用：source directory does not exist"报错前必读。

---

## 缓存是什么

GitHub 来源 Skill 的发布源不在源库，而在本环境缓存目录：

```
${GITHUB_SKILL_CACHE_ROOT}/<skill-id>/        # 整仓 clone
  └── <registry.path>/SKILL.md                # path 为 "." 时即仓库根
```

**登记真源是 skill-manager 自己的 SQLite（`registry_skill` 表，2026-09-21
从 registry.json 迁移）**，环境本地；缓存也是环境本地的。skills 源库的
`registry.json` 已归还给源库 sync 工具链（4 个 sync 脚本），skill-manager
只在首次启动、表为空时做一次只读导入，之后绝不读写该文件。

## clone/fetch 的全部触发点

| 环节 | 代码位置 | 行为 |
|------|---------|------|
| UI 登记 | `POST /skills/github` → `check_update` + `ensure_cached` | clone 一次 |
| 卡片 Clone 按钮 | `POST /skills/github/{id}/clone` → 同上 | 缓存缺失时 clone，已有则 fetch |
| 发布执行 | `_ensure_cached_at_recorded_revision` | 有成功检查记录才 fetch/checkout |
| 计划预览 / 检查更新 | `plan` / `check-updates` | **只读，绝不 fetch**（design 4.2/5） |

## 死锁的成因与打破方式（2026-09 修复）

发布执行虽然有 `ensure_cached` 自救，但计划预览对缓存缺失判 `blocked` →
前端只发布 add/update 项 → 永远走不到发布。**没有 Clone 端点前，已注册但
缓存丢失的 Skill 界面上无法发布。**

修复要点（勿回退）：

- `SkillCard.cache_missing`：github 来源且 `!(cache_root/<id>/.git).is_dir()`。
  纯文件系统判断、零 git 子进程，与 `ensure_cached` 决定 fetch/clone 的口径一致；
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
- 手工往 SQLite `registry_skill` 表插 GitHub 条目不会触发 clone，发布前必须走
  Clone 按钮（或补一次登记流程）；
- 登记/删除**无任何 git 写依赖**（2026-09-21 迁移后）：源目录不需要是 git
  仓库、不需要凭据；此前"git add/commit registry.json 失败导致登记/删除
  报错"（NAS `git add` 128 等）一类问题已随迁移根除；
- 删除已登记 GitHub 条目只影响**本环境**的 DB、状态库与缓存；skills 仓库
  registry.json 归 sync 工具链，管理台操作不反映到它（未来"界面编辑 +
  手动导入/导出"任务会补这个桥）。
