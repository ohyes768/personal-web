# Housing-Map 法拍采集合同

适用：法拍脚本、查询API、手动采集job，未来新增定时任务也须复用collect_auctions。

- 来源是来拍公开辅助数据，source=laipai，auction_platform单独保存。不得标为阿里直接采集。
- upstream BASE=https://api.faeping.com/api/webV1，client: PC；searchObject列表count有整数/数字字符串两种返回形态。
- 先筛杭州住宅，再按area_code=330108取详情，详情核验ID/地区/用途。法院所在地不是标的所在地。
- 状态todo/doing/done/pause/failure/break/revocation/debt，未知保留source_status并显示unknown。只有done+正deal_price才保存成交价。
- auction_id为拍卖轮次身份，asset_id为object_id；以source+auction_id更新，不能按小区或房产ID覆盖不同轮次。
- 上游评估价字段appraise_price；金额整数元。面积优先结构字段，再调查表/公告明确建筑面积；缺失null。end_at表示拍卖结束，不承诺法院确认或付清尾款。
- 独立data/auction_records.json，版本1。失败/取消不写盘，限量增量合并保留旧数据并complete=false；不影响price_snapshots.jsonl及评分。
- OS侧车文件锁覆盖整次事务、跨CLI/API互斥；不能删除运行中锁文件。线程取消后等待线程真正退出才释放锁。服务关闭须await shutdown_refresh。
- HTTP POST/GET/DELETE /api/auctions/refresh，启动202、冲突409；GET /api/auctions分页查询。nginx外部前缀/api/map。不接受任意上游URL或输出路径。
- 不保存完整含姓名/电话/账号的公告，只保留物业事实白名单；后续前端按纯文本显示。风险缺失不代表无风险。
- 测试：tests/test_auctions.py，Windows pytest --basetemp=.pytest-tmp-auction。无浏览器依赖，复用curl_cffi；定时采集未接入scheduler。

说明：backend/housing-map/docs/auctions.md。实测2026-10-09：CLI和API均限量采集3条；454711成交价4760000、面积149.3。分页列表会变化，complete只代表当前遍历完成，不保证区域全量覆盖。
