# 技术设计：GitHub 克隆后台任务化

## 边界与不变量

- 只动 skill-manager 前后端；nginx / docker-compose / NAS 部署脚本零改动。
- GitCacheService 的既有同步方法保留：`verify_reachable`（≤30s 预检）、
  `scan`（同步版仍被后台任务复用）、`check_update`、`current_revision`。
- 真源不变：登记真源仍是 SQLite `registry_skill`；任务状态是易失的派生态，
  不入 SQLite。
- 密码边界：路由同步段 `ensure_admin_password` 通过后才创建任务；任务上下文
  只携带 `RegistrySkill` 与 canonical URL，无密码字段。

## 1. 流式 git 执行器（git_cache.py）

现状 `_run_git` 用 `subprocess.run(capture_output=True)`，只能在结束后拿到
stderr，且 `--progress` 的进度行以 `\r` 分隔（非 `\n`），`text=True` 迭代按
`\n` 切分会把整个进度当成一行。

新增：

```python
@dataclass(frozen=True)
class GitProgress:
    phase: str            # negotiating | receiving | resolving
    percent: int | None   # 0-100，negotiating 阶段为 None
    detail: str           # 原始行尾片段，如 "3.2 MiB | 51.00 KiB/s"

def _run_git_streaming(
    self, argv: list[str], on_progress: Callable[[GitProgress], None],
    cwd: Path | None = None, timeout: int = _GIT_TIMEOUT_SECONDS,
) -> str:
```

实现要点：

- `subprocess.Popen(["git", *argv], stdout=PIPE, stderr=PIPE, text=True,
  encoding="utf-8", errors="replace")`；stdout 读完后循环读 stderr。
- stderr 手工缓冲：`buf += chunk`，按 `\r` 与 `\n` 两种分隔符切出完整行，
  残尾留在缓冲（进度行会被下一帧覆盖，只解析最新完整行即可）。
- 进度正则：`Receiving objects:\s+(\d+)%\s+\((\d+)/(\d+)\)(.*)` → receiving；
  `Resolving deltas:` → resolving；其余含 `remote:` 前缀的行忽略。
  每解析出一帧调用 `on_progress`，TaskManager 侧做节流（同一 percent 不重复写）。
- 超时：`deadline = monotonic() + timeout`，读 stderr 时用
  `select`/带超时的 `stderr.read(1)` 不可移植（Windows），改为
  **读线程 + 主线程 `proc.wait(remaining)`**：主线程等待超时后
  `proc.kill()`、join 读线程、抛 `GitTimeoutError`。避免 Windows 上
  Popen 与 select 的兼容坑。
- 返回 stdout（与 `_run_git` 同语义）；非零退出读 stderr 缓冲拼
  `GitOperationError`（与现行为一致）。
- `scan()` / `ensure_cached()` 增加可选 `on_progress` 参数向下传递给
  clone 调用；默认 None 时退化为现有行为（`scan()` 改为内部统一走
  streaming runner + `--progress`，无回调时仅丢弃进度）。ls-remote /
  fetch / checkout 仍走原 `_run_git`（它们不产生百分比进度）。

## 2. TaskManager（新文件 services/task_manager.py）

```python
TaskKind = Literal["scan", "register", "clone_cache"]

@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    kind: TaskKind
    repository: str
    skill_id: str | None       # scan 为 None
    state: Literal["running", "done", "error"]
    stage: str                 # remote_check | receiving | resolving | discover | registry
    progress_percent: int | None
    progress_detail: str       # "45% (1589/3531) | 51.00 KiB/s"
    error_code: str | None
    error_message: str | None
    created_at: str            # UTC ISO
    updated_at: str
```

- 内部 `dict[str, _MutableTask]` + `threading.Lock`；对外只发冻结快照
  （不可变约定）。内部可变对象仅 TaskManager 持有，更新走
  `_update(task_id, **fields)` 统一改 `updated_at`。
- 执行：`threading.Thread(target=self._run, daemon=True)`。`_run` 按 kind
  分派：
  - `scan`：`git_cache.scan(url, on_progress=...)` → 候选列表存入任务
    结果（快照含 `candidates: list[str]`，仅 scan 且 state=done 时非空）。
  - `register`：`check_update` → `ensure_cached` → `registry.upsert`；
    stage 依次 remote_check / receiving|resolving / registry。
  - `clone_cache`：`check_update` → `ensure_cached`。
- 异常映射：`GitTimeoutError → download_timeout`、
  `UnreachableRepositoryError → unreachable`、`RegistryValidationError →
  registry_conflict`、其余 `GitCacheError → scan_failed/cache_failed`
  （与第一阶段路由映射一致）；非预期异常 → `internal_error`，
  `logger.exception` 记录堆栈。
- 回收：查询时惰性清理（`state` 非 running 且 `updated_at` 超过 30 分钟
  则删除并返回 task_not_found）；不引入定时器线程。
- 挂载：`app.state.task_manager = GithubTaskManager(settings, git_cache,
  registry, store)`；路由经 `src.api.dependencies.get_task_manager` 取。
  > 实施修订：实际签名为 `GithubTaskManager(git_cache, registry, clock=...)`
  > ——settings/store 无用途已去除；`clock` 注入支撑惰性回收的确定性测试。
- TaskManager 复用 GitCacheService 单例，因此 remotes 注入（测试离线
  fixture）天然生效。

## 3. 半成品缓存根治（git_cache.ensure_cached）

首次 clone 分支改为：

```
tmp = github_skill_cache_root / ".tmp" / f"{skill.id}-{uuid4().hex}"
clone 到 tmp → _validated_skill_dir(tmp) 校验 → ensure 父目录存在 →
tmp.replace(cache_dir)   # 同盘原子 rename
```

- `.tmp` 残留：clone 失败时 `finally` 清理本次 tmp；启动清理函数
  一并清空整个 `.tmp` 目录（与 scan 残留同一清理入口）。
- `cache_missing` 判断（routes 列表卡片）不变：`.git` 目录判定不受影响。
- 与后台任务的交互：同 skill 重复创建 clone 任务可能并发 clone 同一
  tmp 前缀（uuid 不同不冲突），rename 到同一目标——最后一个 rename 前
  检查目标已存在则删除本次 tmp 并直接校验既有目录。前端在任务运行中
  禁用重复提交，属双保险。

## 4. 启动清理（main.py lifespan）

```python
def cleanup_stale_workspaces(settings) -> tuple[int, int]:
    # 清空 settings.state_dir / "scan" 与 github_skill_cache_root / ".tmp"
    # 返回 (清掉的 scan 目录数, 清掉的 tmp 目录数)，logger.info 记录
```

lifespan 启动段调用（失败仅 warning，不阻断启动）。单测直接测函数。

## 5. API 契约（routes.py + models.py）

| 端点 | 方法 | 请求 | 同步响应 |
|---|---|---|---|
| `/api/skills/github/scan` | POST | `ScanRequest` | 400 unreachable / 202 `{task_id, kind:"scan"}` |
| `/api/skills/github` | POST | `RegisterGithubSkillRequest` | 401/400 同步错误 / 202 `{task_id, kind:"register"}` |
| `/api/skills/github/{id}/clone` | POST | `AdminPasswordRequest` | 401/404/400 同步错误 / 202 `{task_id, kind:"clone_cache"}` |
| `/api/skills/github/tasks/{task_id}` | GET | - | 200 `TaskSnapshot` / 404 `task_not_found` |

- task_id：`uuid4().hex`。
- 预检失败（unreachable/invalid_repository）与第一阶段同步行为保持一致，
  前端无需为此改文案。
- `AsyncTaskCreatedResponse`、`TaskSnapshot` 加入 models.py；快照含
  `candidates`（scan done 时）。
- 撤销原同步响应：scan 的 `ScanResponse`、register 的 `SkillCard`、
  clone 的 `{skill_id, revision}` 不再由这三个 POST 直接返回——前端改从
  快照/列表获取。这是**前端与后端同仓同发**的契约变更，一次 PR 内同步改。

## 6. 前端（apps/skill-manager）

- `lib/types.ts`：`TaskSnapshot`、`AsyncTaskCreated`。
- `lib/api.ts`：`startGithubScan / registerGithubSkill / cloneGithubCache`
  返回 task_id；新增 `getGithubTask(taskId)`；删除解析旧同步响应的代码。
- `RegisterGithubDialog`：
  - 扫描：`startGithubScan` → `pollTask`（2s setInterval）；`progress_percent`
    非空显示"克隆中 45% · 51 KiB/s"，否则沿用 `扫描中 M:SS…` 计时；done 后
    从快照 `candidates` 填充列表（复用现有渲染）；关闭对话框 `clearInterval`。
  - 错误：`task.error.code/message` 直接展示（文案与第一阶段一致）。
- 新组件 `TaskProgressDialog`（props: `task: TaskSnapshot | null`，`title`，
  `onDone`，`onClose`）：登记/Clone 确认后接管 ConfirmActionDialog 的位置，
  展示 stage + 百分比 + 速度 + 已用时；done 自动调 `onDone`（关框 + 刷新
  列表 + notice），error 展示错误并提供"关闭"。
- `page.tsx`：`performRegister` / `performClone` 改为创建任务后把轮询状态
  交给 `TaskProgressDialog`；成功 notice 文案不变。
- 不做：服务端取消、卡片徽章、重连恢复。

## 7. 兼容与回滚

- nginx 不动：`/api/skills/` 前缀 location 覆盖新 GET 端点，300s 读超时
  对毫秒级轮询无意义但无害。
- 前后端同 PR 发布；回滚 = revert 分支（无数据迁移，SQLite 未动）。
- 生产 uvicorn 单进程，daemon 线程随进程退出，无僵尸任务；重启后残留由
  启动清理兜底。

## 风险

| 风险 | 缓解 |
|---|---|
| `\r` 进度解析漏帧/死循环 | 单测喂真实 `git clone --progress` 抓样字节流（含 `\r` 覆盖与残尾） |
| Windows 上 Popen 超时杀进程残留读线程 | kill 后 join 读线程（带超时），读线程持有的是已关闭管道 |
| 并发 clone 同 skill 的 rename 竞争 | rename 前查目标存在则弃 tmp（见 §3）；前端禁重复提交 |
| reload 模式丢任务 | 仅 dev 环境，PRD 已声明可接受 |
