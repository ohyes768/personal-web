# Journal - tang (Part 1)

> AI development session journal
> Started: 2026-10-10

---



## Session 1: 股息率选股关注与批量收藏

**Date**: 2026-10-10
**Task**: 股息率选股关注与批量收藏
**Package**: backend/dividend-select

### Summary

新增选股关注 Tab；三年平均/最近年度 ROE 默认均10%；补历史ROE与前一季度扣非同比，连续两季下降排除；三态筛选、批量收藏失败重试、独立收藏列表。相关后端80项、前端4项、类型检查及构建通过。已完成工作提交与任务归档，未推送或部署；首次使用需强制刷新财务指标。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `e08c68c` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 核对并收尾9项历史任务

**Date**: 2026-10-10
**Task**: 核对并收尾9项历史任务
**Package**: backend/douyin-processor

### Summary

核对前9项进行中任务，7项按最终提交和当前实现归档；保留开发规范初始化（大量空模板）及dividend scheduler（shutdown传不支持的timeout参数，缺双跑/n8n停用验收）。相关后端68项测试和两前端类型检查通过，线上months及2026-09 signal只读验证成功。每项保存核对记录，无业务代码修改，未推送或部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `d46b53b` | (see git log) |
| `75bf16d` | (see git log) |
| `57f40db` | (see git log) |
| `897815f` | (see git log) |
| `df247d5` | (see git log) |
| `accf209` | (see git log) |
| `bf31570` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 租金来源管理与顶部更新入口

**Date**: 2026-10-12
**Task**: 租金来源管理与顶部更新入口
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

完成 SQLite 租金来源关联管理、顶部更新入口、旧数据卷 seed 兼容与来源变更后的快照隔离。自动关键词搜索受来源限制，链接导入已验证可用。后端 278 项、前端 33 项测试及 lint、build、浏览器验收通过。任务已归档，未推送、未部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `e6c6c7e` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session: Skill Manager Hermes-only install

**Date**: 2026-10-13
**Task**: Skill Manager 仅保留 Hermes 并简化 GitHub 与自研安装流程
**Package**: skill-manager

### Summary

新增 Hermes 单目标安装编排：共享 InstallDialog、自动取计划、一次密码确认；OpenClaw 标识、配置、UI 全部退出，旧数据迁移到 `retired_deployment` 备份并提供受限的旧链接清理脚本。后端 218 项、前端 28 项（vitest）测试通过；tsc、eslint、next build 干净。规划文档 PRD/design/implement 已就位；未推送未部署。

### Main Changes

- 后端：新增 `install.py`（计划/任务编排、版本固定、错误分类）、`operation_lock.py`（仓库与目标互斥）；`models/db/config/migration` 清理 OpenClaw 枚举，保留退役 `openclaw` 字面量以阻止新增。
- 后端路由：新增 `/api/skills/install/preview`、`/api/skills/install`、`/api/skills/install/tasks/{id}`；移除 /publish/plan 与 /publish 写路径；保留导出目标路由。
- 前端：`InstallDialog` 统一 GitHub 与自研流程；删除 `PublishQueue`，简化 `SourceWorkspace`、`RegisterGithubDialog`、`SkillPool`、`DeployBoard`、`page.tsx`；二级导航去掉 agent 切换；静态导出独立视图保留。
- 部署：`docker-compose.nas.yml` 去掉 OpenClaw 挂载与变量；`docs/skill-manager-nas-setup.md`、`deploy/README-same-path-mounts.md` 同步。
- 脚本：`scripts/cleanup_retired_target.py` 默认 dry-run，仅匹配未变更、归管理器拥有的旧链接，文件和外部链接保持原样。
- 规范：`.trellis/spec/guides/skill-manager-frontend.md`、`skill-manager-github-cache.md` 增补 Hermes 单目标与版本固定章节。

### Git Commits

| Hash | Message |
|------|---------|
| e9b9926 | feat(skill-manager): add Hermes-only install orchestration backend |
| a49ab4d | feat(skill-manager): replace publish queue with Hermes InstallDialog |
| 51cf74d | chore(skill-manager): retire OpenClaw from deployment and docs |
| 2f1cbcf | docs(skill-manager): record hermes-only install in spec and journal |

### Testing

- Backend `pytest`: 218 passed
- Frontend `vitest`: 28 passed
- `tsc --noEmit`, `eslint src`, `next build`: clean
- 浏览器端到端 + 真 NAS 安装未在本次会话执行

### Status

[OK] **Completed（待用户确认提交；未推送未部署）**

### Next Steps

- NAS 实机验证 Hermes 一键安装与旧链接清理脚本（仓库内清理脚本需在挂载旧 OpenClaw 目录时执行）


## Session 4: Housing-map 新房住宅证据与位置补全

**Date**: 2026-10-14
**Task**: Housing-map 新房住宅证据与位置补全
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

支持独立新房项目身份、住宅证据失败保留与冲突待审；新增单条用途和位置补全、历史坐标来源与地图投影；新房价格隔离。后端483、前端54测试及lint/build通过，真实案例隔离桌面和移动验收通过。自动规则v5需重新预演启用；新房详情验证页独立报错，本机未配置高德服务Key，历史位置标明来源。未部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `11ffafc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
