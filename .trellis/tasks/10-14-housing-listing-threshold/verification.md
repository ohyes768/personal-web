# 质量核查
使用 trellis-before-dev、trellis-check、trellis-update-spec，保留其他在途新房与 Skill Manager 修改。
后端全量回归479 passed（2条现有Starlette弃用警告）；新增测试覆盖挂牌边界、失败/未知、新房豁免、恢复与人工拒绝、API列表与409、历史主档挂牌。
前端53 tests passed；eslint和tsc通过。构建首次受沙箱内部端口限制，在允许端口的环境重试通过。最终相关回归61 passed。
不修改生产数据库、不跑全量外部采集、不提交或推送其他任务修改。

提交隔离验证：以 HEAD 加本任务改动构建临时副本，全量后端462 passed，证明不依赖在途新房/位置补全修改。
