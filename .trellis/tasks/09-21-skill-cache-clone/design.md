# 技术设计：Skill 管理台缓存丢失 Clone 按钮

## 边界与不变量

- Clone 只在 `GITHUB_SKILL_CACHE_ROOT/<skill-id>/` 之内产生写入；源库、
  OpenClaw/Hermes 目标目录、注册表一律不动。
- 发布计划预览保持只读（绝不 fetch）——"已阻止"仍是安全网，本任务不改
  `_plan_one` 的判定。
- 复用 `GitCacheService` 既有方法，不在 routes 层直接拼 git 命令。

## 数据流

```
GET /api/skills（list_skills）
  └─ 对 github 来源 skill：cache_missing = not (cache_root/<id>/.git).is_dir()
     （纯文件系统判断，零 git 子进程；与 ensure_cached 的 fetch/clone 分支、
      current_revision 的判定口径一致）
  └─ SkillCard.cache_missing 返回给前端

POST /api/skills/github/{skill_id}/clone（密码保护）
  ├─ ensure_admin_password                     # 与登记/发布一致（R5）
  ├─ _require_known_skill → 404               # 复用现有 helper
  ├─ skill.source != GITHUB → 400
  ├─ git_cache.check_update(skill)            # 只读 ls-remote + 刷新检查记录
  │    └─ 失败（GitCacheError）→ 400 cache_failed
  └─ git_cache.ensure_cached(skill, info.remote_revision)
       └─ 失败 → 400 cache_failed
  返回：{"skill_id": ..., "revision": 检出的 revision}
```

Clone 端点语义刻意与登记流程（routes.py:184-185 `check_update` + `ensure_cached`）
一致，而**不是**复用 `_ensure_cached_at_recorded_revision`——后者在无成功检查
记录时是 no-op，对"缓存根本不存在"的场景无效。

## 契约变更

### 后端 models.py

```python
class SkillCard(BaseModel):
    ...
    cache_missing: bool = False   # 仅 github 来源可能为 True；local 恒 False
```

`_build_card` 增加 `cache_missing` 参数（由 `list_skills` 计算后传入，
`list_skills` 需新增 `get_settings` 依赖）。

### 新端点（routes.py）

```
POST /api/skills/github/{skill_id}/clone
body: AdminPasswordRequest
200: {"skill_id": str, "revision": str}
404: skill_not_found（未知 skill，复用 _require_known_skill）
400: invalid_skill（非 GitHub 来源）/ cache_failed（ls-remote 或 clone 失败）
401/403: 密码错误（ensure_admin_password 现有行为）
```

路由段数与既有 `/skills/{skill_id}/targets/{target}/rollback` 不冲突，
FastAPI 按注册顺序匹配无歧义。

### 前端（字段名保持后端 snake_case 直传，与 has_update 等现况一致）

- `types.ts`：`SkillCard.cache_missing: boolean`
- `api.ts`：`cloneGithubCache(skillId: string, password: string)`
- `SkillPool.tsx`：`SkillCardItem` 新增 `cacheMissing` prop：
  - `cacheMissing` 时在卡片底部行内展示"缓存缺失"提示 + Clone 按钮；
  - 目标 chips `disabled={queued || cacheMissing}`；
  - "加入队列" `disabled={cacheMissing}`（title="请先 Clone 缓存"），
    原 `targetHint` 提示逻辑保留不变；
- `page.tsx`：新增 `pendingClone` 状态 + `performClone(password)`，复用
  `ConfirmActionDialog`（title="确认 Clone 缓存"）；成功后
  `refreshSkills()` + notice `「name」缓存已就绪`。

## 权衡与取舍

- **cache_missing 用 `.git` 目录判断**而非调 `current_revision`（rev-parse）：
  列表接口每次请求要对 N 个 skill 起子进程，文件系统判断零开销；且与
  `ensure_cached` 决定 fetch/clone 的口径完全一致。
- **Clone 需要密码**：与全部写端点（登记/发布/回滚/下架）保持一致；
  虽然它只写缓存根，风险低于发布，但例外一次就会腐蚀 R5 的简单模型。
- **不放宽 plan 判定**：让"已阻止"继续兜底（例如 clone 后目录又被删），
  UI 层引导先 Clone 即可，后端安全语义零改动。
- **端点返回简单 JSON** 而非重建后的完整卡片：前端 clone 成功后本来就要
  `refreshSkills()` 全量刷新（部署状态等也要对齐），避免两套组装逻辑。

## 兼容与回滚

- `cache_missing` 带默认值 `False`，旧前端消费新后端不受影响；
  新前端消费旧后端时字段为 `undefined`（falsy）→ 不显示 Clone 按钮，
  行为退回现状，无破坏。
- 回滚点：整体一个 commit，revert 即完全回到现状；无数据迁移、无状态文件
  变更（github_check 记录多写一条属正常业务数据）。

## 安全复核

- skill_id 经 `_require_skill_id`（现有正则校验）后才拼路径，且最终路径由
  `ensure_cached` 内部以 `cache_root / skill.id` 构造并校验登记路径相对性
  （`_require_safe_relative_path`）；
- 仓库 URL 来自注册表（登记时已规范化校验），端点不接受任何 URL 输入；
- 所有 git 调用走 `GitCacheService._run_git`（固定列表参数、shell=False、
  timeout 60s）。
