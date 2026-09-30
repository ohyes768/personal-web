# 技术设计：合集仓库批量登记（共享缓存 + staging 发布）

> 对应 prd.md R1-R6。改动域：`backend/skill-manager/`（git_cache / publisher /
> registry / task_manager / db / models / routes）+ `apps/skill-manager/`（登记弹窗）。

## 1. 总体数据流（改后）

```
扫描（临时 clone，现状保留 + 结果增强）
  → 候选 [{path, name, description}] + 顶层资源清单 + 引用预选
批量登记（一个后台任务）
  → ensure_cached 仓库维度 clone/fetch 一次（repos/<owner>__<repo>）
  → 逐项 upsert registry（含 shared_paths）
发布（每 skill × target）
  → _ensure_cached_at_recorded_revision（fetch + checkout 记录的 revision）
  → 组装 staging/<skill-id>/<short-rev>/（skill 子目录 + shared_paths 拷贝）
  → 原子替换 symlink → staging rev 目录；清理过期 rev 目录
```

## 2. 数据模型与存储

### 2.1 RegistrySkill（models.py）

- 新增 `shared_paths: list[str] = []`；local 条目校验必须为空，github 条目每项要求：
  相对路径、不含 `..`、非空、去重排序（与 tags 同款规范化）；
- `_reject_duplicate_repo_path` 唯一键 `(repository, path)` 不变。

### 2.2 SQLite（db.py）

- `registry_skill` 表新增列 `shared_paths TEXT NOT NULL DEFAULT '[]'`（JSON text，
  与 tags 同款存法）；启动迁移：`PRAGMA table_info(registry_skill)` 缺列则
  `ALTER TABLE ... ADD COLUMN`（幂等，SQLite ADD COLUMN 带默认值即可，无数据回填）；
- `_row_to_registry_skill` / `upsert_registry_skill` 同步读写该列；
- deployment / github_check / deployment_history 表不动（github_check 仍按 skill
  维度记录，同仓库多条目重复 ls-remote 幂等无害，换取零改动）。

## 3. 共享缓存（git_cache.py 重构核心）

### 3.1 路径派生

```python
def repo_cache_dir(canonical: str) -> Path:
    # "https://github.com/xbtlin/ai-berkshire" → repos/xbtlin__ai-berkshire
    owner, repo = canonical.removeprefix("https://github.com/").split("/")
    return settings.github_skill_cache_root / "repos" / f"{owner}__{repo}"
```

- owner 段（GitHub 规则）不含下划线 → `__` 拼接无歧义、可逆解析；
- 正则校验沿用 `_GITHUB_HTTPS_RE` 的捕获组，派生结果天然合法目录名。

### 3.2 ensure_cached / current_revision 语义

- `ensure_cached(skill, revision, on_progress)`：目标目录由 `<skill.id>` 改为
  `repo_cache_dir`；fetch/checkout/tmp-clone-then-rename 流程不变；
  SKILL.md 校验仍按 `<repo_dir>/<skill.path>/SKILL.md`；
- `current_revision(skill)` → 读 `repo_cache_dir` 的 HEAD；
- **revision 竞争**：共享 clone 只有一个 checkout 状态；发布 A（rev1）后发布 B
  （rev2）会移动 HEAD。因为 staging 是**发布时拷贝快照**（§4），各 skill 的发布
  产物固定在各自记录的 revision，共享 clone 的 HEAD 只是「最后一次操作的状态」，
  不承载任何 skill 的长期语义。发布路径里 revision 一律取「本次 checkout 之后
  的 rev-parse HEAD」，与逐条目记录天然一致；
- scan 工作区与 `.tmp` clone 临时目录机制不变。

### 3.3 存量迁移（新函数 `migrate_legacy_cache(settings, registry, store)`，lifespan 启动时执行）

```
for skill in registry 中 source=github 的条目:
    legacy = cache_root / skill.id          # 旧布局
    target = repo_cache_dir(skill.repository)
    if legacy/.git 存在:
        if target 不存在: os.replace(legacy, target)        # 期望主路径
        else: 删除 legacy（同仓库多余副本；发布时按记录 revision 重新 fetch）
    # legacy 不存在且 target 也不存在 → cache_missing，UI 引导 Clone，不自动处理
```

- 同批处理 active 部署修复（§5.3）；迁移失败逐条记日志，绝不阻断启动。

## 4. staging 发布（publisher.py + routes.py）

### 4.1 目录布局与受控根

```
${GITHUB_SKILL_CACHE_ROOT}/staging/<skill-id>/<short-rev>/
    SKILL.md ...（<repo>/<path>/ 全部内容）
    tools/ ...（shared_paths 逐项拷贝）
```

- staging 位于 cache root 内 → `_inside_controlled_roots` / publisher 越界校验
  **零改动**天然覆盖；unpublish 的「链接必须指向受控根内」校验同样成立；
- `<short-rev>` = `git rev-parse --short HEAD`（发布时从共享 clone 取）。

### 4.2 组装算法（`Publisher.publish` 内 github 分支）

```
1. _ensure_cached_at_recorded_revision（routes 侧，现状保留）
2. repo_dir = repo_cache_dir；校验 <repo_dir>/<skill.path>/SKILL.md 存在
3. staging_parent = cache_root/staging/<skill.id>/<short-rev>
   若 staging_parent 已存在（同 rev 重复发布）→ 直接复用跳过组装
4. tmp = cache_root/staging/.<skill.id>.<uuid>.tmp
   拷贝 <repo_dir>/<skill.path>/* → tmp/          # skill 本体
   for p in skill.shared_paths:                    # 共享资源
       src = <repo_dir>/p；resolve 后必须在 repo_dir 内
       缺失 → PublishBlockedError（含 p），清理 tmp
       存在 → 拷贝到 tmp/p（先 shared 后本体的顺序保证本体覆盖同名）
5. os.replace(tmp, staging_parent)                 # 目标不存在时原子
6. 既有 _atomic_swap 流程：symlink → staging_parent（原子替换）
7. 清理 staging/<skill.id>/ 下除最新 2 个 rev 外的旧目录
```

- 目录拷贝用 `shutil.copytree` / `shutil.copy2`（纯拷贝，不 symlink——symlink 套
  symlink 在 NAS 同路径挂载两侧的解析语义不可控）；
- local 条目：publish 全流程不变（源库目录直链）。

### 4.3 计划预览（`_plan_one`）与账实核对

- github 条目 source 解析改为「staging 候选路径」：`staging/<id>` 下最新 rev 目录；
  action 判定：现有链接 resolved == 该 staging 路径 → unchanged，否则 update/add；
  `resolve_registry_source` 语义拆分——发布用（组装 staging）与 plan 用（只读定位）
  分开，避免 plan 产生副作用；
- `cache_missing`（SkillCard）判定改为 `repo_cache_dir(...)/.git` 不存在；
- `link_missing` 账实核对逻辑不变（symlink 存在 + 指向受控根）。

### 4.4 revision 与 history

- `deployment.source_revision` / history 记录统一为 staging 的 `<short-rev>`
  全量 sha（保持现有 full-sha 口径，`short-rev` 只用于目录名）；
- `publish` 的 revision 参数由 routes 传入（checkout 后 rev-parse），publisher 不调 git。

## 5. API 与任务（routes.py / task_manager.py）

### 5.1 模型新增

```python
class GithubRegisterItem(BaseModel):
    path: str; name: str; tags: list[Tag] = []; summary: str = ""

class RegisterGithubBatchRequest(BaseModel):
    password: str; repository: str
    shared_paths: list[str] = []
    items: list[GithubRegisterItem]  # min_length=1

class ScanCandidate(BaseModel):        # 扩展（ Breaking：str → 对象）
    path: str; name: str = ""; description: str = ""

class ScanTopLevelEntry(BaseModel):
    path: str; is_dir: bool

class ScanResult:                      # TaskSnapshot.result 结构扩展
    candidates: list[ScanCandidate]
    top_level: list[ScanTopLevelEntry]
    referenced_paths: list[str]        # 候选 SKILL.md 引用到的顶层路径（预选）
```

- scan 的 `referenced_paths`：对每个候选 SKILL.md 全文做粗匹配（顶层条目名出现
  在文本中即算，如 `tools/`、`tools/financial_rigor.py` 命中 `tools`）。

### 5.2 批量登记端点

- `POST /api/skills/github/batch` → 202 `{task_id, kind: "register_batch"}`；
- 同步段：密码 + normalize + `verify_reachable`（≤30s）+ items 预校验
  （path 非空、相对、去重；`_derive_skill_id` 同批内 existing 集合并入本批已派生 id
  防批内冲突）；
- 后台段（`GithubTaskManager.start_register_batch`）：`check_update`（仓库维度一次）
  → `ensure_cached`（一次）→ 逐项 upsert（校验 `<repo_dir>/<path>/SKILL.md`）；
  快照 result 为逐项成败列表 `[{skill_id, status, error?}]`，任务整体 state：
  全败 error / 否则 done；
- `TaskKind` 增加 `"register_batch"`；错误码映射沿用 `_cache_error_code` 一套。

### 5.3 启动迁移 + active 部署自动重发布

- lifespan 顺序：DB 列迁移 → `migrate_legacy_cache` → 对 deployment 中
  status=active 且 source=github 的条目逐个执行「§4.2 组装 + symlink 替换」
  （用各条目 `source_revision` checkout 后组装；无记录 revision 时用缓存 HEAD）；
  失败记 `deployment_history`（action=publish, result=error）+ warning 日志；
- 该重发布为部署自身维护操作，不走密码（与启动对账同级别）。

## 6. 前端（apps/skill-manager）

- `lib/types.ts`：ScanCandidate/TaskSnapshot 类型扩展、RegisterGithubBatchInput；
- `lib/api.ts`：`registerGithubBatch()`；
- `RegisterGithubDialog`：
  - 候选 checkbox 多选 + 全选/清空；`selected: Set<path>`；
  - 选中数 = 1 → 展示现有 name/tags/summary 手填表单（行为不变）；
    选中数 ≥ 2 → 隐藏表单，展示只读预填列表（name/description 来自 scan），提示
    「登记后可在管理看板逐条编辑」；
  - 「随行共享资源」区块：top_level 渲染 checkbox，referenced_paths 预选；
    单选/多选均可用；
  - 提交：多选 → batch API；单选 → 现有单条 API（带 shared_paths，模型加字段）；
  - ConfirmActionDialog 文案区分单/批；
- `useGithubTask` 轮询复用（kind 扩展透传），完成后刷新列表逻辑不变。

## 7. 兼容性与回滚

- **对外契约**：scan 的 candidates 从 `list[str]` 变 `list[ScanCandidate]` 为本系统
  内部前后端同步变更（无第三方消费方）；其余 API 只增不破；
- **升级顺序**：先起后端（自动列迁移 + 缓存迁移 + active 重发布）再刷新前端；
  NAS 同路径挂载约束不变（staging 在 cache root 内，路径两侧一致）；
- **回滚**：代码回滚后旧版 `ensure_cached` 找不到 `<cache>/<skill.id>` →
  cache_missing，重新 Clone 即可（repos/ 布局旧版不识别但无害）；staging 目录
  残留无副作用；registry_skill 新列旧版代码不读，SQLite 兼容；
- **风险点**：
  - 大仓库整仓拷贝 shared_paths 的体积（如误勾 `reports/` 3000+ 文件）——UI 预选
    只选被引用的顶层路径，用户可取消；不做硬限制，trust admin；
  - checkout 竞争只在「同一批发布内跨仓库」不存在、同仓库多 rev 时存在，
    逐项串行执行（现状即串行）无并发问题；后台任务并发clone 同仓库时
    `ensure_cached` 的 tmp-then-rename + 已存在即复用双保险已覆盖。

## 8. 测试策略

- 单测（pytest，fixture 沿用本地 git 仓库注入 remotes）：
  - git_cache：repo_cache_dir 派生/可逆、迁移三分支（移动/多余副本删除/双缺失）、
    ensure_cached 仓库维度幂等；
  - publisher：staging 组装内容（本体 + shared_paths）、资源缺失 blocked、
    同 rev 复用、旧 rev 清理保留 2 份、unpublish 不动 staging；
  - registry：shared_paths 规范化与穿越拒绝；
  - task_manager：batch 任务逐项成败快照、批内 id 冲突；
  - routes：batch 端点同步预检 400 语义、plan 对 staging 路径的 action 判定；
- Windows 契约：symlink 相关用例沿用 `requires_symlink` 标记；
- 手工验收：ai-berkshire 实仓走 PRD AC 全流程（本地 dev 验登记/缓存/scan，
  Docker/Linux 验发布与迁移）。
