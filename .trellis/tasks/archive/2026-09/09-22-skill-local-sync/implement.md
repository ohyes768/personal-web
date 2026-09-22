# 执行计划：自研 skill 列表请求时对账同步

前置：prd.md / design.md 已评审。验证命令均在 `backend/skill-manager/` 下执行。

## 步骤

### 1. 后端：RegistryService 对账能力
- [ ] `src/services/registry.py`：新增 `_parse_skill_md_frontmatter()`（design §1，零依赖）
- [ ] `discover_local()` 候选带上 frontmatter 的 name/summary
- [ ] 新增 `sync_local() -> int`：diff 后仅 upsert 新 id（design §1）
- 验证：`uv run pytest tests/test_registry.py -v`

### 2. 后端：路由接线 + source_missing
- [ ] `src/models.py`：`SkillCard.source_missing: bool = False`
- [ ] `src/api/routes.py` `list_skills`：调 `sync_local()`（捕获 OSError/RegistryValidationError → warning）；
      `_build_card` 增加 `source_missing` 判定（LOCAL 且 SKILL.md 非普通文件）
- [ ] 新增 `tests/test_local_sync.py` 六个用例（design §7）
- 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v`

### 3. 前端：卡片源缺失提示
- [ ] `apps/skill-manager/src/lib/types.ts`：SkillCard 加 `source_missing`
- [ ] `apps/skill-manager/src/components/SkillPool.tsx`："源缺失"徽章 + 禁用加入队列（对齐 cache_missing）
- 验证：`cd apps/skill-manager && pnpm build`

### 4. 浏览器验证（review gate）
- [x] 启动前后端，源库新建含 frontmatter 的 skill 目录 → 刷新页面出现卡片（隔离环境已验证）
- [x] 改名该目录 → 卡片保留 + "源缺失"徽章 + 加入队列禁用；改回 → 恢复（隔离环境已验证）
- [ ] 现有 GitHub 条目卡片行为不变（tsc + 后端测试已覆盖；真实环境待重启验证）

### 5. 去除源库 registry.json 依赖（R6，用户追加）
- [x] `src/models.py`：删 `RegistryFile`/`RegistryAgent`
- [x] `src/services/registry.py`：删 `REGISTRY_FILENAME`、`import_registry_json_if_empty`、`RegistryFile` import；更新 docstring
- [x] `src/main.py`：删 lifespan 导入调用
- [x] `src/db.py`：更新 docstring
- [x] `tests/test_registry.py`：删迁移/只读测试、pydantic import 保留
- [x] `tests/test_api.py`：删 `LOCAL_REGISTRY`、registry.json 写入与只读断言；client fixture 预热 `GET /api/skills` 触发对账
- [x] 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` → 111 passed, 14 skipped
- [ ] 源库物理 `registry.json` 与 `backend/skill-manager/scripts/migrate_registry.py`：归源库 sync 工具链/历史工具，不删（告知用户单独决定）

## 回滚点

- 每步独立可 revert；无 DB schema 变更。步骤 2 完成前 API 无行为变化。

## 完成定义

- PRD 验收标准全部勾选；`uv run pytest tests/ -v` 全绿；`pnpm build` 通过；
  浏览器验证通过。
