# skill-manager git 同步提速：ls-remote 合并 + 浅拉取

## Goal

线上（NAS 容器，慢速出口访问 github.com，实测 FastGithub ~51 KiB/s）「同步缓存」/
「登记」操作慢：每次 `git ls-remote` 都是一次全新 TCP+TLS 握手 + `/info/refs`
请求，单次 5–10s。当前一次「同步缓存」端到端要 5 次网络往返：

```
routes 同步预检 verify_reachable   → ls-remote HEAD          (1)
任务内 verify_reachable            → ls-remote HEAD          (2)  ← 与(3)重复
任务内 check_update _ls_remote_head → ls-remote HEAD          (3)  ← 与(2)重复
任务内 check_update _ls_remote_tags → ls-remote --tags --refs (4)
任务内 ensure_cached fetch          → fetch origin <sha>      (5)
```

另有传输量问题：`ensure_cached` 首次 clone 是**全量 clone（无 --depth 1）**，
与 `scan()` 的浅 clone 不一致；skill 缓存只用于工作区 checkout，历史无用。

优化后：网络往返 5 → 3（预检 1 + 合并后的 check_update 1 + fetch 1），
首次 clone 与增量 fetch 均为浅拉取（只传最新快照层）。

## Requirements

### R1 ls-remote 合并（check_update 单次网络请求）

- `_ls_remote_head` + `_ls_remote_tags` 两次 `ls-remote` 合并为一次请求同时
  解析出 HEAD SHA 与 tags 列表；`check_update` 对外行为（UpdateInfo 字段、
  github_check 记录）不变。
  **实施订正（实测 git 2.49）：** argv 用 `["ls-remote", <url>, "HEAD",
  "refs/tags/*"]` 而非 `HEAD --tags --refs`——存在显式 pattern 时
  `--tags`/`--refs` flags 不生效（只返回 HEAD 行拿不到 tags）；`refs/tags/*`
  pattern 等价取到全部 tag refs，peeled `^{}` 行解析时跳过（等价旧
  `--refs` 过滤）。

### R2 任务内冗余预检删除 + unreachable 语义保持

- `task_manager` 的 `_execute_register` / `_execute_register_batch` /
  `_execute_clone` 中任务内的 `verify_reachable` 调用删除（routes 同步预检
  保留，AC1 快速 400 语义不变；`_execute_scan` 的预检保留——scan 路径无
  check_update，仅此一次 ls-remote）。
- `check_update` 内部的 ls-remote 改用 `_REACHABILITY_TIMEOUT_SECONDS`（30s，
  元数据请求快速失败），失败/超时改抛 `UnreachableRepositoryError`，使
  task_manager 错误映射（unreachable 文案）与前端展示不变；失败仍写
  github_check 记录（`_record_check_failure` 口径不变）。

### R3 浅拉取（减少传输）

- `ensure_cached` 已有缓存分支：`git fetch` 增加 `--depth 1`，只拉目标 SHA
  的快照层，不补全中间历史；`checkout --force` 不变。
- `ensure_cached` 首次 clone 分支：`git clone` 增加 `--depth 1`，与 `scan()`
  对齐；检出/校验/原子 rename 流程不变。
- 发布路径（`install.py` / `_ensure_cached_at_recorded_revision` 传入历史
  revision）不回归：浅 fetch 任意可达 SHA 在 GitHub 端可用（现有
  `fetch origin <sha>` 已依赖 SHA-in-want），本地已有该对象时 fetch 无传输。

## Constraints

- 全部 Git 调用保持固定列表参数（shell=False），不引入外部拼接。
- 错误码与前端文案（unreachable / download_timeout / cache_failed 等）逐字
  不变；前端零改动。
- `@serialized` 串行锁、共享缓存目录布局、原子 rename 语义不变。

## Acceptance Criteria

- [ ] `check_update` 仅发起 1 次 `ls-remote`（HEAD 与 tags 同请求返回）。
- [ ] 「同步缓存」任务（clone_cache）不再调用 `verify_reachable`；routes
      同步预检行为不变。
- [ ] `ensure_cached` 的 clone 与 fetch 命令均带 `--depth 1`。
- [ ] `backend/skill-manager` 全量 pytest 通过（含离线 fixture 仓库下浅拉取
      与浅 fetch 的行为验证）。
- [ ] 现有 `test_git_cache.py` / `test_task_manager.py` 断言更新后覆盖：
      合并 ls-remote 的参数、任务内无冗余预检、浅拉取参数。
