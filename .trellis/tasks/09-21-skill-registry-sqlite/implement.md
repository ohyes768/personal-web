# 执行计划：登记真源迁移 SQLite

## 步骤

1. **db.py**：`registry_skill` 表入 `_SCHEMA` + 5 个新方法
   → 验证：现有 pytest 全绿（schema 追加不破坏旧表）。
2. **registry.py 重写**：DB 版 RegistryService（list/get/upsert/remove）+
   `import_registry_json_if_empty`；删除文件版 load/_save/commit_registry_change
   → 验证：test_registry.py 重写后全绿。
3. **main.py + dependencies.py + routes.py**：装配传 store、启动迁移、
   list/register/delete 三处切换、删除 git 提交调用
   → 验证：全量 pytest（test_api.py 中途写文件的用例与 git 断言用例同步改造）。
4. **新增测试**：迁移 5 场景（首启导入/二次跳过/损坏失败/非空忽略/文件逐字节未变）、
   非 git 目录登记删除成功、无 git 子进程断言
   → 验证：`UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿。
5. **docs/skill-manager-nas-setup.md**：改写 registry git 相关段落
   → 验证：通读无残留旧语义描述。
6. **收尾检查**：全量 pytest + 对照 PRD 验收标准逐条核验 + dev 起服务手测
   （导入 → 列表 → 登记 → 删除，registry.json 全程不变）。

## 验证命令

```bash
cd backend/skill-manager && UV_CACHE_DIR=.uvcache uv run pytest tests/ -v
```

前端零改动，无需 lint/build。

## 手测要点（Windows dev 环境）

- `.skill-manager-dev/state` 的 DB 若已有数据，先确认 registry_skill 表行为
  （本地 dev registry.json 在 F:/personal-projects/skills，17+3 条）。
- 删除真实 GitHub 条目（如 luopan，缓存缺失态）验证全链路后重新登记恢复，
  或者用一次性条目验证后删除。

## 回滚点

- 单 commit 提交，revert 即回滚；registry_skill 表多余无副作用。

## 审查关口

- 步骤 4 后：人工核对错误码对照表（design routes 改动点一节）与 PRD R5。
- 步骤 6 后：进入提交（Phase 3.4）。
