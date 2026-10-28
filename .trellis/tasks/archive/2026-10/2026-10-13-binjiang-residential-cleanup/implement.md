# 实施
1. 编写清理脚本 scripts/filter_residential_communities.py：
   - 读 tmsf property_types、fang samples
   - 输出 residential_communities.json、pending_communities.json、non_residential_communities.json
2. 更新 community_directory.py 在 import 时忽略 non_residential，但仍保留 sources。
3. 在 prepare_directory 标记 prepared 版本号。
4. 测试 test_directory_filtering.py 覆盖三类集合。