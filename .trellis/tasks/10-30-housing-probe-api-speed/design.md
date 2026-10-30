# 设计

租金采集与发现共用 rental_list_api_url(seed, offset=0, search_id=None)，避免API参数漂移。发现白名单只允许该固定第一页请求。XingfuliDiscovery.verified_rental_seed(seed,nid)读取列表JSON，验证status/data/items/has_more和每行身份，返回列表内真实可采集种子；无有效列表返回None/抛错，拒绝关联。

DiscoveryCheckpoint 提供同名未缓存步骤，通过_call计预算、取消和诊断；对历史注入客户端无此能力时继续原双核验，以保持旧兼容测试/适配器语义。ProbeService默认走新方法，以返回的已验证种子绑定，保留现有资料fresh=True与发布锁下身份复查。源身份仍为nid，seed单独存储；旧种子不在列表时使用列表中明确归属的种子。

前端ProbeState增可选current_step，运行态由实际步骤显示进度，终态沿用stage。选择/重试先清空旧步骤与诊断，避免旧结果污染新操作。

不并发请求、不降低间隔；对比保留双HTML仅换文案，本方案减少真实请求且复用已验证的列表API。无需数据库迁移，回滚相关代码即可。
