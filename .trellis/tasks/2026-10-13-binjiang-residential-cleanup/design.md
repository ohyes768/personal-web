# 设计
- 复用 community_directory.py 的 import 流程：增加 is_residential_community 决定是否进入 communities 表。
- 非住宅但来源 ID 已记录到 sources 表，确保可以恢复。
- 写入 backup/diagnostics/<filename>.pre-residential.json 记录删除/标记前的快照。