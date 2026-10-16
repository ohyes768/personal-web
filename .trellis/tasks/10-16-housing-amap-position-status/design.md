# 设计
沿用directory_position.PositionJob、已知名称查询和当前TMSF目录。主档payload增加amap_position（持久化状态、候选、选择证据、检查时间、错误），不建新来源。纯状态投影统一处理历史coordinate_evidence与新证据。inventory投影位置状态，API按状态过滤后分页，详情返回快照revision。候选查询先网络后事务，完整快照对比及资格复核；人工确认只用服务器已存候选，手工点经共享边界验证。
目录已有有效坐标默认不覆盖，但仍可补POI证据；manual位置受保护。重试失败保留有效匹配和坐标。前端新增定位面板，列表状态/操作及过滤，复用已存在任务进度与轮询。
主要文件：directory_position.py（查询/任务与确认）、独立状态投影模块、directory_workflow.py（catalog投影）、directory_workflow_routes.py（接口）、DirectoryFlowWorkspace及新定位面板（UI）；新独立测试避免改动其他窗口正在编辑的测试。
