# 房天下杭州挂牌租金采集

从 `backend/housing-map` 运行，使用现有虚拟环境和 curl_cffi，不新增依赖。

```powershell
.\.venv\Scripts\python.exe scripts/fetch_fang_rentals.py --community-id 2010067741 --community-id 2011095896 --community-id 2010356262 --max-pages 3 --details --output-dir ../../.tmp/fang-rentals
```

以上 ID 分别为房天下的风雅钱塘、璞悦湾、东方郡 ID，**不是透明售房网 ID**。
小区列表页地址中的 `house-xm数字` 是来源小区 ID。需单独核对地址、苑区和别名后才可关联现有小区；不自动模糊匹配。

区域分页：

```powershell
.\.venv\Scripts\python.exe scripts/fetch_fang_rentals.py --url https://zu.fang.com/hz/house-a0154/n31/ --url https://zu.fang.com/hz/house-a0156/n31/ --max-pages 2 --sleep 2 --output-dir ../../.tmp/fang-rentals-region
```

滨江代码 154、萧山代码 156。区域模式不限定萧山接壤板块；后续需通过小区映射筛选。
默认每个入口最多 3 页，所有请求之间等待 2 秒，超时 20 秒。`--details` 对每个去重房源再请求一次详情补地址和物业类型，默认关闭。

## 输出

- `fang_rentals.jsonl`：本次房源快照，按 `source_listing_id` 去重。来源 ID 包括 URL 中的三段数字。
- `fang_rentals_report.json`：成功页数、请求数、重复 ID 数、入口分页截断和逐项错误。

两个文件各自以临时文件原子替换，**重复执行会覆盖相同目录的上次结果**；需要历史请每次指定不同输出目录。文件对不承诺事务一致性，不支持同时写同一目录。
部分失败保留成功样本并返回退出码 1；成功访问的明确空列表返回 0。登录、拦截或无法识别的页面记录为错误；不会绕过验证。分页达上限在 `truncated_seeds` 标记，不代表已采全。

所有价格为**挂牌月租（元/月）**，面积单位㎡；`published_at` 保持 null，`captured_at` 为 UTC 采集批次开始时间，不是发布时间或维护日期。小区字段取结构化小区链接，标题可能出现多个小区名称，因此不用于归属。

`quality_flags` 中 `shared_rental` 是合租，`suspected_partition` 是标题含独立厨卫/隔断/单间等词的疑似分割出租（可能误判，需复核），`non_residential` 是详情中的非住宅，`missing_*`/`invalid_*` 表示关键字段缺失或非正数，`detail_fetch_failed` 表示详情未验证。合租和可疑房源保留供审核，不自动生成租金平均值或租售比。不同来源 ID 仍可能是同一套房，本版不宣称完成同套去重。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_fang_rentals.py -q --basetemp=.pytest-tmp-fang
```
