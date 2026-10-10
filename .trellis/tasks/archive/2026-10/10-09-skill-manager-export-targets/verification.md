# 验收记录与提交清单（2026-10-09）

## 已实现

Windows Codex / Windows Claude Code 导出目标、免密 ZIP 下载与台账、源变化 stale
检测、重新导出覆盖记录、单独清除台账、数据库启动迁移、登记删除级联清理。
link 目标仍走密码保护的发布/下架；export 不进入 plan、symlink 核对或启动重发布。
前端含目标选择弹窗、短版本/日期、黄色源已更新徽章与免密删除确认。

## 验证

- 前端：`pnpm exec tsc --noEmit`、`pnpm lint` 通过；`pnpm test` 9 passed。
- API 最终全量：`python -m pytest tests/test_api.py -xq --basetemp .pytest-tmp/final`
  → 50 passed、6 skipped。
- 新增 export 定向：API 与 exporting 测试 → 11 passed。
- 第一轮后端全量：176 passed、13 skipped、3 failed；后续补了 3 项 API
  回归（旧空哈希、密码/混合目标无副作用、删除登记级联）。
- 最终其余后端测试（排除已全量验证的 API 文件及上述 3 项既有失败）：
  130 passed、7 skipped、3 deselected。
- 最终分批合计：180 passed、13 skipped；3 项既有部署配置失败单列。
- `git diff --check` 通过。
- symlink 相关测试按既有 Windows 无特权环境规则跳过；未做 NAS 部署。

### 既有失败（本次未修改测试、Compose 或 nginx 配置）

1. `test_skill_manager_exposes_required_mounts`：旧挂载字符串断言不匹配同路径挂载。
2. `test_skill_manager_backend_has_only_allowed_mounts`：旧白名单不匹配同路径挂载与 CA 挂载。
3. `test_nginx_routes_skill_manager`：首页改版后，旧 `href="/skills/"` 字符串断言失效。

PRD 原写“2 项既有部署漂移”，实际为 3 项；本轮保留这三项并明确记录，不扩大修改范围。

## 浏览器验收

使用 `.pytest-tmp/export-browser` 隔离源与 SQLite，不触碰真实技能或台账。
通过 playwright-cli 操作实际 Next 页面与 FastAPI：

1. 自研卡片 → 导出弹窗（Codex/Claude 单选、无密码）。
2. 下载 ZIP → 卡片出现 Windows Codex、短版本、日期与最新。
3. 修改隔离源、刷新 → 黄色源已更新（`stale.png`）。
4. 点击记录重新导出 → 下载新 ZIP，提示恢复最新。
5. 清除记录弹窗明确“不动本地已解压文件” → 确认后台账 chip 消失。
6. 读取浏览器实际下载 ZIP，确认根只有 SKILL.md 且含 Version two；清除台账后源文件仍在。

## 设计修正与限制

- 导出限定 export 目标，避免覆盖 `(skill_id,target)` 唯一行中的 symlink 发布记录。
- GitHub 使用仓库共享缓存登记子目录，不包含 shared_paths；不会 fetch/clone。
- 哈希长度编码且与 ZIP 使用同一内容快照，排除 .git 与 symlink。
- 当前快照和 ZIP 在内存中组装，适用个人 MB 级 Skill；大目录未来需临时文件快照。
- 导出台账说明“已下载”，管理台不确认 Windows 已安装。

## 提交清单（仅本任务文件）

### 1. feat(skill-manager): 新增外部导出目标与版本台账

- backend/skill-manager/src/models.py
- backend/skill-manager/src/db.py
- backend/skill-manager/src/api/routes.py
- backend/skill-manager/src/services/exporting.py
- backend/skill-manager/src/services/publisher.py
- backend/skill-manager/src/services/migration.py
- backend/skill-manager/tests/test_api.py
- backend/skill-manager/tests/test_exporting.py
- backend/skill-manager/pyproject.toml
- backend/skill-manager/uv.lock

### 2. feat(skill-manager): 增加导出弹窗与源更新提示

- apps/skill-manager/src/lib/targets.ts
- apps/skill-manager/src/lib/targets.test.ts
- apps/skill-manager/src/lib/types.ts
- apps/skill-manager/src/lib/queue.ts
- apps/skill-manager/src/lib/api.ts
- apps/skill-manager/src/components/ExportDialog.tsx
- apps/skill-manager/src/components/SkillPool.tsx
- apps/skill-manager/src/components/SourceWorkspace.tsx
- apps/skill-manager/src/components/PublishQueue.tsx
- apps/skill-manager/src/app/page.tsx

### 3. docs(skill-manager): 记录导出安装与目标分类契约

- docs/skill-manager-nas-setup.md
- .trellis/spec/guides/skill-manager-export-targets.md
- .trellis/spec/guides/index.md
- .trellis/spec/guides/skill-manager-github-cache.md
- .trellis/spec/guides/skill-manager-registry-sync.md
- .trellis/tasks/10-09-skill-manager-export-targets/（计划、验收、截图）

### 不纳入提交的其他工作

- .trellis/tasks/10-09-community-auction-history/
- .trellis/tmp-refresh-btn-stale.png
- backend/housing-map/data/ 的 6 项未跟踪采集文件
- backend/rss-relay/uv.lock

2026-10-10 用户已授权按本清单提交并推送；提交后按 Trellis 归档任务、记录日志，不创建 PR。
