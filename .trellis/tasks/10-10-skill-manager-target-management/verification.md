# 导出目标管理验证

## 实现结果

- SQLite 动态目标配置及一次性默认目标迁移；稳定 ID、名称/目录说明/备注/启停、记录计数与 CRUD API。
- 删除检查所有部署行，导出写台账和审计同事务复验启用/存在，避免并发停用/删除后写入台账。
- 一级导航导出目标管理，页面共享动态配置、卡片动态名称及停用历史清除、空目标与加载失败提示。
- 启动重发布、列表 link_missing 与删除 Skill 发布检查只处理固定 LINK_TARGET_IDS；部署队列仍固定 NAS 目标。
- Next 开发 rewrite 与生产 Nginx 集合/子路径代理同步；说明文档明确前后端更新与 Nginx reload。

## 测试证据

全部命令在各包目录运行，Windows basetemp 位于项目盘。

1. 后端首次红灯：`tests/test_api.py -k 'target_management or custom_export_target'` 两项失败（目标管理路由不存在）。
2. 前端首次红灯：动态目标 helper 测试失败（enabledExportTargets 未实现）。
3. 后端专项：`.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_exporting.py tests/test_targets.py --basetemp=.pytest-tmp/target-management -q` → **59 passed, 6 skipped**（55.93 秒）。
4. 后端完整：`pytest tests --basetemp=.pytest-tmp/target-full -q` → **187 passed, 13 skipped, 3 failed**（111.09 秒）。失败均为旧部署文件断言：test_skill_manager_exposes_required_mounts、test_skill_manager_backend_has_only_allowed_mounts、test_nginx_routes_skill_manager。
5. 既有失败核实：临时 pytest plugin 将 compose_text/nginx_text fixture 替换为 `git show HEAD:docker-compose.nas.yml` / `git show HEAD:nginx/web.conf` 的原始内容，仅运行上述 3 项，仍 **3 failed**。未修改 Git HEAD 或工作区配置；原因是旧断言不匹配已存在的 mount 必填提示/CA 挂载和已迁移的首页导航。
6. 后端排除上述既有失败完整回归：`pytest tests -k 'not test_skill_manager_exposes_required_mounts and not test_skill_manager_backend_has_only_allowed_mounts and not test_nginx_routes_skill_manager' --basetemp=.pytest-tmp/target-clean -q` → **187 passed, 13 skipped, 3 deselected**（117.46 秒）。
7. 最后后端聚焦：test_exporting.py、test_targets.py、新增 Nginx 路由测试 → **8 passed**（0.44 秒）。包含默认目标删除后重启不复活、修改持久化、旧数据库台账迁移、removed 行阻止删除、打包后写入前启停/删除复验，以及自定义目标启动跳过。
8. 前端 `pnpm exec tsc --noEmit` 与 `pnpm lint` 通过；`pnpm test` → **13 passed**。包含动态目标选择、安装说明、停用/空列表/加载失败渲染，以及 HTML pattern 的 Unicode v 校验回归。
9. `git diff --check` 通过（仅 LF/CRLF 提示）。代码审计无残留静态 EXPORT_TARGETS；deployment target 强转枚举的两个调用均先固定 link 集合过滤。

## 浏览器证据

见 [browser-verification.md](./browser-verification.md)。隔离数据验证完整 CRUD、ZIP 下载内容、记录数、改名历史、停用/清除、有记录删除拦截及 375px 布局。浏览器发现的 HTML pattern 转义问题已修复并增加回归。

## 环境与后续

- Windows 缺真实 symlink 特权，相应用例按既有 marker 跳过；NAS 发布链路未在本机真实运行。
- 前端依赖目录在沙箱内 realpath 报 EPERM，通过自动审批后正常运行检查；未修改依赖清单。
- 未在 NAS 执行 nginx -t、部署、提交或推送。上线需技能管理器前后端更新并 reload Nginx。
- 以上前端证据为实现者验证；独立检查代理正在核对刷新加载态和长文案布局，其最终复验记录应随检查报告一起读取。

## 最终独立复核
Trellis check 复核并修正每次目标刷新加载态、长名称/备注换行、删除弹窗滚动。
最终父会话复跑 tsc、lint、13 项前端测试以及 8 项后端迁移/事务/Nginx 专项全部通过；375px 最长允许文案与空启用目标场景通过浏览器验收。
任务实现完成，保留 in_progress 等待提交；未执行会自动提交的任务归档/日志脚本。
