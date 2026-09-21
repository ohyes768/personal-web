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

注册记录（registry.json）随源库同步到**所有环境**，缓存却是**环境本地**的。
所以任何"手工写入注册表"或"换环境/重建缓存卷"的场景，缓存必然缺失。

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
- 手工往 registry.json 加 GitHub 条目不会触发 clone，发布前必须走
  Clone 按钮（或补一次登记流程）。
