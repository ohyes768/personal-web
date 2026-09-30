# skill-manager 合集仓库批量登记（共享缓存 + staging 发布）

## Goal

让「一个 GitHub 仓库 = 多个 skill + 根级共享资源」的合集仓库（如
[ai-berkshire](https://github.com/xbtlin/ai-berkshire)，22 个候选 skill + 根级 `tools/`）
能以合理成本登记与发布：

1. **一次登记多个候选目录**（当前单次登记只能选一个 path）；
2. **同仓库共享一份 clone 缓存**（当前每个 skill.id 各 clone 一整份仓库，22 个 = 22 份各 ~60MB）；
3. **发布产物包含根级共享资源**（当前 symlink 只指向单个子目录，`python3 tools/xxx.py` 一类调用全部断链）。

## 背景与问题

以 ai-berkshire 为实例（2026-09-29 实测分析）：

- 仓库根无 SKILL.md，`codex-skills/` 下 22 个子目录各含 SKILL.md（扫描会全部列为候选）；
- 21/22 个 skill 的 SKILL.md 硬依赖仓库根 `tools/`（`python3 tools/financial_rigor.py ...`），
  另有跨 skill 文本引用（`skills/financial-data.md`）；codex-skills 子目录本身只有 SKILL.md；
- 当前登记模型：`RegisterGithubSkillRequest` 单 `path` 字段 + UI radio 单选，
  想要 N 个就走 N 遍「输入 URL → 扫描 → 选目录 → 登记」；
- 当前缓存模型：`ensure_cached` 把整仓 clone 到 `GITHUB_SKILL_CACHE_ROOT/<skill.id>/`，
  同仓库 N 个条目 = N 份全量 clone；
- 当前发布模型：symlink 直接指向缓存内子目录（`<cache>/<skill.id>/<path>`），
  链接目标里没有 `tools/` 等根级资源，21/22 个 skill 发布后在 Hermes/OpenClaw 上
  执行到工具调用步骤必然失败。

用户决策（2026-09-30）：缓存按仓库共享；tools/ 断链问题一并纳入本任务解决。

## Requirements

### R1 批量登记 API 与任务

- 新增 `POST /api/skills/github/batch`：一次提交同一仓库的多个候选
  `{password, repository, shared_paths, items: [{path, name, tags, summary}]}`；
- skill id 沿用现有派生规则（repo 名 + 路径末段，冲突加序号），同批内互不冲突；
- 整批为**一个后台任务**（202 + 轮询）：密码校验与可达性预检同步，clone/入库后台执行；
  逐项记录成败，单项失败不影响其他项（仓库级失败如 clone 超时则整批 error）；
- 单条登记 `POST /api/skills/github` 保留（batch items 长度为 1 等价，不强制合并）。

### R2 按仓库共享 clone 缓存

- 缓存目录改为 `${GITHUB_SKILL_CACHE_ROOT}/repos/<owner>__<repo>/`
  （owner 段不含下划线，`__` 分隔无歧义）；同仓库任意数量条目共享一份 clone；
- `ensure_cached` / `current_revision` / `cache_missing` 判定全部改为仓库维度；
- 登记同仓库第二个及以后条目**不再触发 clone**（缓存已存在时仅 fetch/校验）。

### R3 staging 发布模型（含根级共享资源）

- `RegistrySkill` 新增 `shared_paths: list[str]`（github 条目专用，仓库根相对路径，
  如 `["tools", "AGENTS.md"]`；登记时写入，批量登记 UI 勾选）；
- GitHub 条目发布时组装 staging 目录（skill 子目录内容 + shared_paths 逐项拷贝），
  symlink 改指 staging，不再直指缓存内子目录；local 条目发布行为不变；
- staging 落在 `${GITHUB_SKILL_CACHE_ROOT}/staging/<skill-id>/<short-rev>/`
  （不新增配置项与受控根），发布写新 rev 目录 + 原子替换 symlink，零悬空窗口；
  仅保留每个 skill 最新 2 个 rev 目录，更旧的自动清理；
- `shared_paths` 校验：相对路径、不穿越仓库根；发布时资源缺失 → 该项 blocked
  （错误信息含缺失路径）；拷贝顺序为先 shared_paths 后 skill 本体（本体可覆盖同名）。

### R4 扫描结果增强

- scan 候选从裸 path 列表扩展为 `[{path, name, description}]`
  （name/description 取自各 SKILL.md frontmatter，缺失降级为目录名/空）；
- scan 同时返回仓库根**顶层目录/文件清单**（排除 `.git`、工具目录）与
  「候选 SKILL.md 文本中引用到的顶层路径」预选集合，供批量登记 UI 勾选 shared_paths。

### R5 存量数据迁移与部署兼容

- DB：`registry_skill` 表新增 `shared_paths` 列（JSON text，默认 `[]`），
  启动时 `PRAGMA table_info` 检测缺列则 `ALTER TABLE ADD COLUMN`；
- 缓存迁移：启动时把旧 `<cache>/<skill.id>/.git` 整目录移动到
  `repos/<owner>__<repo>/`；同仓库多份旧缓存只保留其一（其余删除——发布时会按
  各条目记录 revision 重新 fetch/checkout，无数据损失）；
- 已发布链接修复：迁移后原 symlink target（旧缓存路径）失效，启动迁移对
  deployment 记录中 status=active 的 github 条目自动重组 staging 并替换 symlink
  （等价自动重发布；失败记 history error，不阻断启动，UI 上以 link_missing 暴露）。

### R6 前端登记交互（批量）

- RegisterGithubDialog 候选区从 radio 单选改为 checkbox 多选 + 全选/清空；
  多选时逐项填写不现实：name/tags/summary 输入区隐藏，各条目用 scan 返回的
  frontmatter 预填（登记后在管理看板逐条编辑；提示文案说明这一点）；
  单选时保留现有手动填写表单（行为不变）；
- 新增「随行共享资源」勾选区：仓库根顶层条目 checkbox 列表，
  预选 scan 检测到的引用集合；单条登记同样可用（shared_paths 对单条也生效）；
- 密码确认弹窗展示「将登记 N 个 skill · 随行 M 个共享路径」；
- 任务进度轮询复用现有 useGithubTask，完成后刷新列表。

## Constraints

- 后端 `backend/skill-manager/`，前端 `apps/skill-manager/`，均改；
- 不新增第三方依赖；沿用现有任务/快照/密码/错误码体系与 Tailwind 风格；
- Windows dev 侧 symlink 受限（WinError 1314）：本地验收 plan/scan/登记/缓存，
  完整发布链路在 Docker/Linux 验证（既有 `requires_symlink` 契约）；
- `SKILL_ID_PATTERN`、basePath `/skills`、nginx/Docker 部署形态不变；
- 语义变化的既有行为仅限：GitHub 条目 symlink target（缓存子目录 → staging）与
  缓存目录布局；对外 API 契约只增不破（scan 结果结构扩展为新增字段）。

## Acceptance Criteria

- [ ] 对 ai-berkshire 走一次批量登记：选 2 个候选（如 investment-research、
      financial-data）+ 勾选 `tools`，扫描→多选→密码确认→任务 done，
      registry 出现 2 条记录且 `shared_paths=["tools"]`；
- [ ] 批量登记后 `${GITHUB_SKILL_CACHE_ROOT}/repos/` 下只有**一份**该仓库 clone
      （`repos/xbtlin__ai-berkshire/`），两条目 cache_missing 均为 false；
- [ ] 发布上述任一条目到 Hermes：`${HERMES_SKILLS_ROOT}/<id>/` 内同时可见
      SKILL.md 与 `tools/`（含 financial_rigor.py），symlink 指向
      `staging/<id>/<short-rev>/`；
- [ ] shared_paths 指向不存在路径时，plan 显示 blocked 且含缺失路径，
      发布该项失败不波及队列内其他项；
- [ ] scan 结果含各候选 name/description 与顶层资源清单；单选登记行为与改版前
      一致（可手动填 name/tags/summary）；
- [ ] 存量升级：带旧 `<cache>/<skill.id>/` 缓存与 active 部署记录的环境启动后，
      缓存位于 repos/ 新路径，已发布链接 target 已更新为 staging 且内容可解析
      （link_missing 不出现）；
- [ ] 重复发布同一 skill 到新 revision：旧 rev staging 目录保留 1 份、更旧清理，
      symlink 原子切换（无中间悬空态）；
- [ ] 后端 `python -m pytest tests/ -v` 全绿（含新增用例）；前端 `pnpm build`、
      `pnpm lint` 通过。

## Notes

- 明确不做（另立任务或拒绝）：
  - depends_on 编排关系的登记入口（数据模型字段保留，本次不加 UI/API）；
  - staging 之外的发布回滚功能（回滚已整体移除，见 09-23-skill-manager-remove-rollback）；
  - 自动分析任意仓库的共享资源依赖（R4 的引用预选是顶层目录名的粗匹配，仅作预选）。
- 设计决策（2026-09-30）：
  - 缓存共享与 tools/ 断链修复由用户拍板一并纳入（AskUserQuestion 确认）；
  - staging 放 cache root 下 `staging/`：免新增配置项与受控根，publisher 越界校验
    （`_inside_controlled_roots`）天然覆盖；
  - rev 后缀目录 + 原子 symlink 替换：避免「删旧目录→rename 新目录」之间的悬空窗口。
