# 实施计划

1. 等用户对最终方案明确批准后task.py start；读取trellis-before-dev与租金采集/发现/统计规范。
2. 添加API首屏、筛选后10套早停、分页补位、错误/空/归属失败保留旧快照、新旧证据统计隔离回归。
3. 实现列表API采集与统一统计过滤配额，更新任务计数、快照抽样元数据和旧快照兼容。
4. 统一幸福里3秒默认/下限及上层参数，回归共享限速/冷却/取消。
5. 更新API与前端类型/口径说明/测试；同步生效规范和替代旧详情采样契约的范围。
6. trellis-check：后端.venv/bin/python -m pytest --basetemp=/tmp/housing-list-api-tests；前端npm run lint、npx tsc --noEmit、node --test tests/*.test.cjs、npm run build。沙箱端口限制的测试按需在允许临时本地端口的环境重跑。
7. 小批低频只读烟测请求数、有效数、字段归属及耗时，不发布测试快照。提交/推送及部署按后续授权执行。

回滚：API结果不能验证则失败关闭并保留旧快照；不扩大到其他来源或统计分组阈值、准入规则。


实施1–7项开发与验证均已完成，详见verification.md；用户已授权提交/推送；部署尚未执行。
