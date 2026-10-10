# 浏览器验收（2026-10-10）

使用 playwright-cli 独立 target-management 浏览器会话。FastAPI 8097 / Next 3008，数据仅在 backend/skill-manager/.pytest-tmp/target-browser，不使用真实技能或台账。

已操作通过：
1. /skills?view=targets 加载两个初始 Windows 目标，均 0 条记录。
2. 新增 qa-laptop（验收笔记本 Codex），目录 D:/tools/codex/skills、备注浏览器验收；导出弹窗立即出现新目标及说明。
3. 在 QA Skill 卡片选该目标下载，实际下载 qa-skill-8f6fe30907c4.zip；管理页记录数更新为 1。
4. 有记录时删除弹窗明确告知先清除，删除按钮禁用。
5. 目标改名为改名验收 Codex，Skill 原台账同步显示新名称；停用后台账保留、重导出禁用、清除可用。
6. 清除记录后管理页记录数归零；目标删除成功。
7. 375x812 管理页与新增表单 documentElement.scrollWidth=375，没有横向溢出；mobile-dialog.png 已目视检查，表单和按钮可见。
8. 发现 HTML pattern 的短横线需按 Unicode v 转义，已通知实现者修复；浏览器实际读取修复后的 pattern 并 new RegExp(pattern, 'v').test('qa-laptop') 返回 true。

截图：targets.png、mobile.png、mobile-dialog.png。Next 开发环境有 favicon 404；修复后没有新的业务错误。首次启动受沙箱套接字/Chrome 限制，自动审批后正常启动。

Nginx 接入回归：新增集合精确匹配和单项目录前缀测试，改前失败、改后 1 passed。未在 NAS 执行 nginx -t 或部署。

补充最终复核：
- 全部目标停用后，导出弹窗显示无启用目标，下载禁用；管理导出目标入口正确导航到管理页。
- 100 字符连续名称与 2000 字符连续备注，在 375px 页面仍 scrollWidth=375。导出弹窗高度 731px、内容高度 1320px，按设计内部滚动，mobile-long-dialog.png 已目视检查。
- 下载 ZIP 读取验证根目录仅 SKILL.md，内容包含 Version one。
- 父会话最终前端 tsc/lint/13 tests 全部通过，后端迁移/事务/代理专项 8 passed。
