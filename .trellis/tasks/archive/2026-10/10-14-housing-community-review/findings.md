# 代码依据与现状

## 数据与数量
- 2026-10-14 本聊天前段只读核对 NAS：398 个有效主档；来源873条（TMSF427、Amap376、Fang38、Laipai32）；待关联405条（29+309+35+32）。这是当时快照，后续验收必须重新导出，不能写成固定业务期望。
- 最近采集只处理TMSF/Amap：new376+existing427=matched465+pending338=803。按来源身份计数，不是去重小区数量。
- community_registry.sqlite3 位于运行时 DATA_DIR，NAS 为 /app/data，使用 housing-map-data 卷；本轮未写线上数据。

## 已查证边界
- community_registry.py：sources 唯一键为 source/kind/sid；创建+关联事务已存在；不同分期保留，人工决定与 rejected 优先；删除主档会把关联来源标为 ignored，因此不能直接复用删除操作表达新的审核排除。
- residential_classifier.py：Amap只提供线索；TMSF/Fang住宅用途证据冲突、公寓/其他/未知保持待核实；尚无人工住宅确认字段。
- directory_routes.py：两个列表分别返回主档与来源行，没有按小区聚合的待审核实体；已关联但住宅未确定的主档不属于 pending 来源查询。
- data_loader.py load_communities：从主档读取全部有效小区；load_coordinates 有地址与围栏校验。routes.py地图额外按道路名称、静态合并成员与坐标围栏筛选，物业类型来自旧 property_types.json。新主档及最新类型证据可能与地图展示不同步。
- auction_association.py：identity 按 asset_id，否则 auction_id；groups 聚合同房产轮次，尚不按小区聚合。缺名/旧关联冲突禁止自动关联；pending_records 返回 rounds 和候选。
- 独立法拍/租金采集入口保持；目录采集按钮只TMSF/Amap。本任务改审核汇总，不把法拍网络采集塞进目录任务。

## 会话决定
- tab名称、列与三种审核操作已在本聊天确认。
- 用户选择明确住宅且无疑点自动收录；来拍未关联候选也进入待审核，同小区多套房聚合，多轮拍卖不计为多套房。
- 当前住宅全量展示旧契约与本轮住宅收录后展示要求冲突；以本轮用户要求为准，实施时更新 spec，保留原始数据与历史ID。

## 关键代码定位（2026-10-14）
- community_registry.py:107 创建来源主档；:157 ingest；:183 自动匹配；:244 删除的连带影响。
- residential_classifier.py:98 当前多来源用途分类。
- directory_routes.py:91 主档查询；:150 来源查询；:183 从来源创建。
- data_loader.py:236 主档读取；:251 坐标过滤；api/routes.py get_communities 为地图入口。
- auction_association.py:9 资产/轮次身份；:22 历史同步；:49 当前待关联读取。
- 上述相对路径均以 backend/housing-map/src/ 为根；行号仅作本轮研究定位，实施前按符号查找最新位置。
