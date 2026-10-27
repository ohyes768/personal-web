# 设计
复用 DirectoryJob、collect_names、tmsf_names。POST /directory/collection 增加 mode=all|retry_failed，默认 all。GET 状态补充 retryable（当前未忽略 TMSF 错误来源数量），空历史返回 idle 状态。
后端统一失败谓词；重试从持久化来源重建已知名单与 project 索引项，不请求名单/新房发现索引。community 详情兜底仍可读取必要索引。复用详情解析、缓存、取消、入库与自动分类，不实现另一套采集器。
UI 仅 TMSF 行显示第二按钮，沿用 action 回调和轮询。数据在运行结束后重算失败数量。
