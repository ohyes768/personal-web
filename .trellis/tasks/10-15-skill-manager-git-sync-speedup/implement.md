# 执行计划：git 同步提速

改动集中在 3 个文件 + 2 个测试文件，方案已在 PRD 定稿，无独立 design。

## 步骤

### 1. `src/services/git_cache.py`

1.1 合并 ls-remote：删除 `_ls_remote_head` / `_ls_remote_tags`，新增
    `_ls_remote_refs(remote) -> tuple[str, list[str]]`，一次
    `git ls-remote <remote> HEAD --tags --refs`（超时用
    `_REACHABILITY_TIMEOUT_SECONDS`）解析 HEAD SHA 与 tags；解析失败/命令
    失败/超时按 R2 语义抛 `UnreachableRepositoryError`。
1.2 `check_update` 改调 `_ls_remote_refs`；`UpdateInfo` 字段与
    `_record_check_success` / `_record_check_failure` 不变；ls-remote 阶段的
    `GitOperationError`/`GitTimeoutError` 包装为 `UnreachableRepositoryError`
    后仍走 `_record_check_failure` 再抛出。
1.3 `ensure_cached` 已有缓存分支：`fetch` → `["fetch", "--depth", "1",
    "origin", revision]`；更新方法 docstring 中"只拉目标 SHA"的注释为浅拉取。
1.4 `ensure_cached` 首次 clone 分支：`clone` 增加 `"--depth", "1"`（放在
    `--progress` 前，与 `scan()` 参数风格一致）。
1.5 模块顶部 docstring 的 check_update 描述同步（"仅一次 ls-remote"）。

### 2. `src/services/task_manager.py`

2.1 `_execute_register`（~L355）、`_execute_register_batch`（~L379）、
    `_execute_clone`（~L413）：删除 `self._git_cache.verify_reachable(...)` 行；
    `UnreachableRepositoryError` 已在错误映射内，无需新增分支。
2.2 `_execute_scan`（~L331）的预检保留，不动。

### 3. `src/api/routes.py`

- 不改行为；仅当注释提及"两次 ls-remote"或 `check_update` 语义处同步措辞
  （如有）。routes 同步预检（L475/559/656/751）全部保留。

### 4. 测试更新（`tests/`）

4.1 `test_git_cache.py`：
   - `check_update` 相关用例：断言一次 `_run_git` 调用参数为
     `["ls-remote", remote, "HEAD", "--tags", "--refs"]`；HEAD 缺失/网络失败
     用例改断言 `UnreachableRepositoryError`。
   - `ensure_cached` 用例：断言 clone 带 `--depth 1`、fetch 带 `--depth 1`；
     离线 fixture（本地路径 remote）下 git 对 `--depth` 的 local-transport
     忽略/支持行为以实际运行为准——`scan()` 已用 `--depth 1` 且通过，照抄
     其测试基线。
4.2 `test_task_manager.py`：register / register_batch / clone_cache 用例删除
     对任务内 verify_reachable 的断言（如有 mock 断言）；scan 用例保留。

### 5. 验证

```bash
cd backend/skill-manager
UV_CACHE_DIR=.uvcache uv run pytest tests/ -v
```

全量通过后走 2.2 全范围检查（lint/类型如有配置一并跑）。

## 回滚点

- 每步独立可回滚；浅拉取引入的 shallow 边界对缓存仓库无破坏性（仅元数据
  标记），回滚 = 还原 git 参数即可，无需迁移缓存数据。
