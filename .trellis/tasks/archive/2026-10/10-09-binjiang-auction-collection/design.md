# 技术方案

## 选择
推荐来拍公开JSON接口：已实测无需登录返回价格，复用curl_cffi，无浏览器依赖。浏览器采集更重；淘宝官方API需尚未取得的应用凭证。来源明确标laipai，原竞拍平台另记taobao，完整性未知。

## 数据通路
GET /searchObject，client: PC，organization_type=1、province=330000、city=330100、second_class=residence、perPage=12，page递增。默认全状态是否成立在实施前实测；只抓area_code=330108，GET /auction/{id}再核对地区用途。检查HTTP/业务status、JSON结构、分页变化；超时低频重试，业务错误不能算空结果。

auction_id是一轮拍卖，object_id是一套标的。价格字段start_price/appraise_price/deal_price标准化整数元；只有done且deal_price正数记录成交价。end_time表示结束时间，不声称已完成履约。嵌套面积和风险公告需用实际响应核对，面积缺失保留null。

## 模块与契约
- services/auction_fetcher.py：固定域名HTTP、上游校验和标准化；可注入客户端离线测试。
- services/auction_store.py：独立版本化auction_records.json，来源+auction_id合并，跨进程锁和临时文件原子替换；失败/取消保留旧文件。
- services/auction_refresh.py：共享采集服务，手动后台任务；返回processed、matched、saved、errors、complete、时间和失败原因；分页/条数上限明确有界。
- api/auction_routes.py：GET /api/auctions分页查询；POST/GET/DELETE /api/auctions/refresh启动202、状态、取消；运行中启动返回409。nginx外部路径/api/map/auctions及/api/map/auctions/refresh。
- scripts/fetch_binjiang_auctions.py：复用同一服务，支持--max-pages、--limit、--output、--dry-run，失败非零退出。

## 安全与兼容
HTTP入口不接受任意输出路径或任意上游URL。只保留http(s)原拍卖链接；公告提取文本与风险说明，避免存整份含个人资料响应。名称/别名唯一匹配才绑定community_id。增量限量抓取保留旧记录并注明不完整。不改原价格快照、评分、前端及scheduler，不自动部署；停用新增路由可回滚入口。
