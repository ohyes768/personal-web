# 滨江住宅法拍采集

来源为来拍科技公开辅助数据，竞拍平台可能是淘宝。不能将其标为阿里直接采集，也不保证覆盖区域全部标的。现有定时任务不触发此采集。

## 脚本

在 backend/housing-map 下使用服务Python环境：

```sh
python scripts/fetch_binjiang_auctions.py --max-pages 100
python scripts/fetch_binjiang_auctions.py --max-pages 5 --limit 3
python scripts/fetch_binjiang_auctions.py --max-pages 5 --dry-run --output data/auction_probe.json
```

默认文件data/auction_records.json（持久化数据卷）。max-pages范围1–500、limit范围0–10000；limit=0不限制滨江匹配条数。dry-run不写数据，但会创建锁侧车文件；输出JSON包括complete、pages、processed、matched、saved及finished_at。失败退出1，保留旧数据。结束时complete=false表示限量或分页上限截断；即使true也只表示遍历当前上游列表，不能保证整个区域覆盖或分页期间完全一致。

## HTTP

服务直连路径/api，nginx路径/api/map：

| 动作 | 服务路径 | 说明 |
|---|---|---|
| POST | /api/auctions/refresh?max_pages=5&limit=3 | 后台启动，202；另一个脚本/API采集运行时409 |
| GET | /api/auctions/refresh | 查询running、phase、processed、matched、result、error |
| DELETE | /api/auctions/refresh | 请求取消；正在执行的HTTP请求结束后退出；无运行任务409 |
| GET | /api/auctions?page=1&page_size=20 | 查询列表；可加status=done或community_id，小区没有准确匹配时为null |

API不允许指定输出路径或上游URL。取消不会直接终止线程；等待在途请求退出再释放文件锁。采集完成前旧数据继续可查询。错误/取消整批不落盘；正常限量批次增量合并，未采集到的旧记录保留。空数据不会推断旧拍卖已撤回。

## 字段口径

来源键source=laipai；auction_id是一轮拍卖、asset_id对应上游object_id，不能按房产ID覆盖不同轮次。状态按来源原值todo/doing/done/pause/failure/break/revocation/debt保存，未知值status=unknown并保留source_status。

金额字段均为整数元：start_price_yuan、appraisal_price_yuan、deal_price_yuan。仅done且有正成交价时输出deal_price_yuan；不把起拍价写为成交价。end_at是来源拍卖结束时间，已成交不代表法院确认、付清尾款或过户。

area_m2为建筑面积，依次取结构字段、调查表、公告中的明确面积；不能可靠提取时null，并记录area_source。deal_unit_price为成交总价/建筑面积，元/㎡，没有成交价/面积时null。车位等打包标的可能影响可比性，使用时需回查source_url及original_url。

只保留白名单物业风险说明，不保存完整含个人信息的公告，缺失风险说明不意味着没有风险。参考评估价也不能解释为当前市场价。原始链接及描述是外部数据，后续前端应按纯文本显示。

## 上游合同

公开前端确认BASE=https://api.faeping.com/api/webV1，client: PC。GET /searchObject筛organization_type=1、province=330000、city=330100、second_class=residence；count可为整数或数字字符串。只按area_code=330108取详情GET /auction/{auction_id}，再次校验用途/区县/ID；业务status必须200。依赖现有curl_cffi，无新增浏览器依赖。

API变化、错误页、分页重复与解析异常将使该批失败，不覆盖有效快照。侧车锁由OS在进程退出时释放，不要删除运行中锁文件。
