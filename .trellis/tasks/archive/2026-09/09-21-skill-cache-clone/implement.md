# 执行计划：Skill 管理台缓存丢失 Clone 按钮

前置：design.md 已确认契约。全程在 monorepo 单仓库内改
`backend/skill-manager` 与 `apps/skill-manager`。

## Step 1 后端：模型与列表字段

- [x] `src/models.py`：`SkillCard` 增加 `cache_missing: bool = False`
- [x] `src/api/routes.py`：`list_skills` 注入 `Settings`（`get_settings`），
      计算 `cache_missing`（github 来源 → `not (cache_root/<id>/.git).is_dir()`；
      local → False），传入 `_build_card`
- 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v -k list` 全绿；
  `curl -s localhost:8097/api/skills | python -m json.tool | grep cache_missing`
  能看到 uzi-skill / luopan 为 true（本地 dev 后端在跑）

## Step 2 后端：Clone 端点

- [x] `src/api/routes.py` 新增 `POST /skills/github/{skill_id}/clone`
      （密码 → 404/400 校验 → `check_update` → `ensure_cached` →
      返回 `{"skill_id", "revision"}`），错误契约见 design.md
- [x] `tests/` 新增端点测试：clone 成功（用既有离线 remotes fixture）、
      未知 skill 404、非 GitHub 来源 400、check 失败 400、密码错误
      （对照既有 register/publish 测试的夹具写法）
- 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿、无回归

## Step 3 前端：类型与 API

- [x] `src/lib/types.ts`：`SkillCard` 增加 `cache_missing: boolean`
- [x] `src/lib/api.ts`：新增 `cloneGithubCache(skillId, password)`
      （对照 `rollbackSkill` 的写法与错误处理）

## Step 4 前端：卡片 UI 与交互

- [x] `SkillPool.tsx`：`SkillCardItem` 加 `cacheMissing` prop；cacheMissing
      时展示"缓存缺失" + Clone 按钮；chips/加入队列禁用（title 提示）；
      `SkillPool` 透传字段
- [x] `page.tsx`：`pendingClone` 状态 + `performClone`，复用
      `ConfirmActionDialog`；成功 `refreshSkills()` + notice
- 验证：`pnpm lint` 通过（apps/skill-manager 下）

## Step 5 浏览器全流程验收（对照 prd.md Acceptance Criteria）

- [x] uzi-skill / luopan 卡片出现"缓存缺失"+Clone，chips 与加入队列禁用
- [x] 本地来源卡片、缓存正常的 GitHub 卡片无 Clone 按钮
- [x] 点 Clone → 弹密码框 → 输错密码 → 弹框内报错
- [x] 输对密码 → 缓存目录生成、卡片恢复可用、notice 提示
- [x] 生成发布计划 → 该项为"新增"（不再"已阻止"）
- [~] 实机"确认发布"最后一步被既有环境限制挡住：Windows 非提权进程创建
      symlink 报 WinError 1314（本地来源 skill 同样失败，非本任务回归；
      与 13 个 requires_symlink skip 一致；生产 Docker/Linux 不受影响）
- [x] 检查无 console 报错

## Step 6 收尾

- [x] 2.2 全量质量检查（后端 pytest + 前端 lint + 既有测试回归）
- [x] 3.3 视需要更新 `.trellis/spec`（Clone 端点契约）
- [x] 3.4 提交（含本会话早前的 SkillPool UX 提示修复，一并入库；
      launch.json 单独评估是否入库）

## 回滚点

- 每个 Step 独立可回退；最终单 commit，revert 即回到现状。
- Step 5 验收失败但后端已改：可先 revert 前端两个文件恢复原交互。
