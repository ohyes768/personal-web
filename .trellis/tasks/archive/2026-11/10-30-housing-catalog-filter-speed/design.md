# Design

用户已明确批准直接实施资料版本缓存与来源分组索引。

使用有界进程内缓存包装 inventory/auction_tasks。版本由 SQLite主库/WAL、property_types.json、binjiang_coordinates.json 和法拍任务依赖的 auction_records.json 的 inode/size/mtime_ns/ctime_ns 组成。构建前后版本一致才保存，异常不缓存，重启清空。支持外部SQL与原子替换，避免依赖每个写入口手工清缓存。锁内单次构建，返回深拷贝，防调用方污染。最多8个数据目录，避免测试/多实例路径无界增长。

community_views 和 inventory 分别把 matched sources 按 community_id 一次分组并保持顺序。瓶颈是 Python 列表扫描，单加 SQL 索引不能解决。

统计 effect 仅依赖搜索/区域/刷新，列表 effect 独立依赖分类/筛选/翻页及active/pipeline配置。初次等待配置，其后无需等统计。保留200ms防抖、AbortController及分页越界处理。

coverage 不缓存，保持租金过期状态和实时业务文件正确。读取变化期间仍保留原有非跨文件事务读取语义，但结果不缓存；下一次请求重建。准入规则、API包络、任务轮询、写冲突保护不变。
