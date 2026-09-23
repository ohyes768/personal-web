# skill-manager 移除后端回滚功能

## Goal

彻底移除后端回滚功能。分析结论（见 09-23-skill-manager-source-tabs 任务 PRD R5）：
rollback 的快照记录 previous_link_target 恒等于当前链接路径（两种来源的发布链接
均指向稳定路径），且 rollback 不检出 previous_revision，对所有 UI 可达场景无效。
前端入口已在上一任务删除；本任务删除后端全部实现。

## Requirements

- R1 删除 rollback API 端点（POST /skills/{skill_id}/targets/{target}/rollback）
- R2 删除 Publisher.rollback()、RollbackUnavailableError、_snapshot_current 及全部快照调用点
- R3 删除 rollback_snapshot 表（DDL）、RollbackSnapshot dataclass、store 的
  set/get/delete_rollback_snapshot(s) 方法、_row_to_snapshot
- R4 PublishResultItem.action 字面量收紧（去掉 "rollback"）；HistoryEntry.action 为 str，
  历史 JSONL/旧行含 rollback 记录不受影响，仅更新 docstring
- R5 删除 delete skill 流程中的 delete_rollback_snapshots 调用
- R6 删除/调整相关测试（test_api / test_db / test_publisher），保证套件全绿
- R7 前端已无引用（上一提交已删 rollbackSkill），无需改动

## Acceptance Criteria

- [ ] `grep -ri rollback src/` 无残留（历史注释/迁移文件除外，当前无迁移机制）
- [ ] `UV_CACHE_DIR=.uvcache uv run pytest tests/ -v` 全绿
- [ ] OpenAPI schema（GET /openapi.json）不再含 rollback 端点

## Notes

- 决策：不修复而是移除（2026-09-23，用户拍板）。若未来需要「发布新版翻车退回旧版」，
  正确设计是 rollback 时对 GitHub 缓存执行 ensure_cached(previous_revision) + 链接原子替换，
  届时按新需求重建。
