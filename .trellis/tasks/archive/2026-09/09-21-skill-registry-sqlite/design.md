# 技术设计：登记真源迁移 SQLite

## 总体形状

保持 `RegistryService` 作为 API 边界（9 处路由依赖注入不变），内部从
"registry.json 文件读写 + git 提交" 改为 "SkillStateStore 的 registry_skill 表"。
`main.py` 装配处传入 store；启动时执行一次性导入。

## 数据库（db.py）

`_SCHEMA` 追加一张表（不建新库、不加迁移框架）：

```sql
CREATE TABLE IF NOT EXISTS registry_skill (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ('local','github')),
    path        TEXT NOT NULL,
    repository  TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    summary     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','deprecated')),
    depends_on  TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

SkillStateStore 新增方法（短连接模式与现有一致）：

- `list_registry_skills() -> list[RegistrySkill]`（按 id 排序，tags/depends_on 反序列化）
- `get_registry_skill(skill_id) -> RegistrySkill | None`
- `upsert_registry_skill(skill: RegistrySkill) -> None`（INSERT OR REPLACE，
  created_at 保留旧值——先 SELECT 再写，或 `datetime('now')` 首次生成）
- `delete_registry_skill(skill_id) -> bool`（返回是否存在）
- `count_registry_skills() -> int`（迁移判断用）

repository 存 `str(HttpUrl)`；重建 RegistrySkill 时 github 无 repository 视为
数据损坏（启动导入有模型校验兜底，正常运行不会出现）。

## RegistryService 重写（services/registry.py）

```python
class RegistryService:
    def __init__(self, store: SkillStateStore, source_root: Path) -> None: ...
    def list_skills(self) -> list[RegistrySkill]      # 原 load().skills
    def get(self, skill_id) -> RegistrySkill | None
    def upsert(self, skill: RegistrySkill) -> None    # 校验 + store.upsert
    def remove(self, skill_id: str) -> None           # 不存在抛 RegistryValidationError
    def discover_local(self) -> list[RegistrySkill]   # 原样保留（目录扫描，路由未用）
```

- 删除 `load()`（返回 RegistryFile 的文件版）、`registry_path`、`_save`、
  `commit_registry_change`、`COMMIT_MESSAGE`、`subprocess` 导入。
- 保留 `RegistryValidationError`（routes 已在捕获），语义变为"登记操作失败/未知 id"。
- `_check_path`（local 需源库根内 SKILL.md、github 相对路径）与 tags 排序去重
  逻辑原样保留，在 upsert 前执行。
- 唯一性校验：upsert 前用 `list_skills()` 查重（重复 id / github 重复
  repository+path，排除自身），拒绝信息与现状一致。

## 一次性导入（registry.py 新函数）

```python
def import_registry_json_if_empty(store: SkillStateStore, source_root: Path) -> int
```

- `registry_skill` 表非空 → 返回 0，什么都不做（含 registry.json 不存在的场景）。
- 表空且文件存在 → `RegistryFile.model_validate` 解析，逐条
  `upsert_registry_skill`，返回条数；解析失败抛异常（main 启动失败，消息含
  registry.json 路径与原因）。
- agents 字段忽略（R4）。全程只读该文件，绝不写入。

## main.py 装配

```python
store = SkillStateStore.from_settings(settings)      # 现有顺序调整，store 先建
app.state.store = store
app.state.registry = RegistryService(store, settings.skills_source_root)
imported = import_registry_json_if_empty(store, settings.skills_source_root)
logger.info("registry migration: imported %d skills", imported)
```

（具体以 main.py 现有 lifespan/组装代码为准，保持 get_store/get_registry
依赖入口不变。）

## routes.py 改动点（最小化）

| 位置 | 现状 | 改为 |
|------|------|------|
| list_skills (~86) | `registry.load().skills` | `registry.list_skills()`；`registry_invalid` 分支删除 |
| `_require_known_skill` | 遍历 `registry.load().skills` | `registry.get(skill_id)` |
| 登记路由 (~249) | upsert + `commit_registry_change` | upsert（无 git） |
| 删除路由 (~649) | remove + commit，git 失败 500 | remove（无 git）；`delete_failed` 分支随之消失 |
| 其余 6 处 | 仅注入依赖 | 不变 |

PRD R5 的错误码逐条对照现状：401 密码、400 local_source、409 skill_active、
404 unknown_skill 均不因迁移改变。

## 测试策略

- 现有 fixtures 在 tmp 源库写 registry.json → 启动导入自动生效，大部分用例
  无需改动即可继续通过。
- 必须改造的用例：test_api.py 中"测试中途回写 registry.json 模拟跨环境同步"
  的两处（~332、~544）改为直接调 `registry.upsert`；断言 git commit 计数、
  断言 registry.json 内容变化的用例改为断言 DB 状态 + registry.json 未变。
- 新增：迁移用例（首启导入条数、二次启动不重复导入、损坏文件启动失败、
  表非空时忽略文件、迁移后文件逐字节未变）、无 git 仓库环境登记/删除成功、
  upsert 唯一性拒绝。
- test_registry.py 重写为 DB 版服务测试（tmp sqlite + tmp 源库目录）。

## 兼容与回滚

- API 契约、前端、SQLite 读取路径（deployment 等既有表）零变更。
- registry.json 保留在 skills 仓库原样提交，sync 脚本继续可用；未来编辑器
  任务的导出功能落地上线前，console 登记的内容不会出现在 registry.json
  （已在 PRD Goal 声明该代价，用户已确认）。
- 回滚 = revert 单 commit；DB 里 registry_skill 表多出来不影响旧版代码
  （旧版只读 registry.json）。

## 文档

- `docs/skill-manager-nas-setup.md`：删除/改写 "登记会把 registry.json commit
  到源库 / 凭据推送" 相关段落 → 新语义（DB 真源，无 git 写依赖；registry.json
  归 sync 工具链）。
- `.trellis/spec/guides/skill-manager-github-cache.md` 的多环境 registry 语义
  与"手工改 registry.json"相关坑 → 标注已被本迁移取代（step 3.3 处理）。
