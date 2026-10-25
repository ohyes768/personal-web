# 幸福里移动网页租金采集验证

验证日期：2026-10-23（Asia/Shanghai）。只读验证；未修改项目代码、生产关联或租金快照。

## 结论

已知小区的列表、详情及完整分页在本地和连接的 NAS 出口可读；NAS 全量翻页验证通过。未使用登录账号、Cookie、付费服务或验证码处理。尚不能宣称长期稳定，自动发现小区流程也未通过。

| 小区 | 来源 neighborhood_id | 各页条数 | 唯一房源 ID | 整租标记 | 合租标记 | 最终 has_more |
|---|---|---|---:|---:|---:|---|
| 风雅钱塘 | 6581030816598458638 | 20 / 20 / 12 | 52 | 42 | 10 | false |
| 欣盛东方郡 | 6854812199240614151 | 20 / 20 / 20 / 13 | 73 | 69 | 4 | false |

各小区跨页重复 listing ID 均为 0，所有返回记录的 neighborhood_id 均与该组一致。整租标记不等于通过现有项目的整租住宅质量过滤；同一实体房源重复挂牌尚未核验。房源数量是本次快照，可能随时变化。

## 已验证入口与字段

- 风雅钱塘列表：https://m.xflapp.com/zufang/neighbor-house-list/hz-7502229388495274018.html
- 欣盛东方郡列表：https://m.xflapp.com/zufang/neighbor-house-list/hz-7694922441520431153.html
- 风雅钱塘详情：https://m.xflapp.com/zufang/hz-7660466810168328198.html （6000 元/月，130.76㎡，3室1厅）
- 欣盛东方郡详情：https://m.xflapp.com/zufang/hz-7694922441520431153.html （8000 元/月，89㎡，3室2厅2卫）

HTTP HTML 包含 `script[name="pia-ssr-data"]` JSON。列表位于 `data._list`，分页状态位于 `data._hasMore`、`data._updateParams`。记录包括字符串 `id`、`neighborhood_id`、`rent_price`、`rent_price_unit`、`rental_type`、`title`、`sub_title`。抽查 rental_type=1 对应整租，2 对应合租。面积和户型需解析展示字段，不能假设存在独立数值字段。

详情位于 `data.info.card_info`，`core_data.main_info` 有价格与付款方式，`core_data.core_info` 有户型、面积、楼层、朝向；`neighborhood` 含小区名称和真实小区 ID；`surrounding_info` 含地图坐标。不要采集与租金统计无关的经纪人个人信息。

## 分页验证

从页面实际引用的公开 JS 定位到 `GET https://m.xflapp.com/f100/api/search_api/rent`。这是网页内部接口，不是有稳定性承诺的开放 API。

本次成功参数：

```text
channel_id=94349583687
house_id=<列表 URL 中的种子房源 ID>
house_type=3
aid=1370
app_name=f100
count=20
refresh_type=2
offset=<上一页返回的 offset>
search_id=<上一页返回的 search_id>
list_style=same_neighborhood_list
```

返回根 `status=0`、`message=success`，`data.items` 为记录，续传 `offset` 与 `search_id`，以 `has_more=false` 收敛。本次各次分页间等待至少5秒，没有签名计算或 Cookie 注入。

关键：列表 URL 数字是种子房源 ID，并非 neighborhood_id。不能把种子房源 ID 写进小区关联主键。种子下架后的行为尚未验证。

## 未通过或待验证事项

1. **自动搜索未通过**：从真实搜索 UI 提交“璞悦湾”后，浏览器长期停在加载中。直接读取 `/zufang/hz?full_text=璞悦湾&trigger_search=1` 返回 HTTP 200，但 `window._SSR_DATA` 中是20个不同小区的全市房源（如都市水乡、港郦中心），未证明关键词生效。不可将其当作璞悦湾搜索命中。
2. **直接关键词接口尚未打通**：对已发现 rent 接口的一次关键词试验（city_id、full_text 等基础参数）返回 `status=1001, message=params error`，不应解释为空房源。
3. **城市跳转异常**：欣盛东方郡详情的“在租74套”在浏览器中跳到 `/xiaoqu/bj-6854812199240614151.html`，小区名称/地址正确但在租显示暂无、部分链接标北京。此入口不适合作为可靠租赁列表入口。本次使用已验证的 same_neighborhood_list 路径。
4. **数据口径**：挂牌租金，不是成交租金；小区卡片“元/月起”混入合租，不能当作整租参考均价。详情小区建造年份也存在可疑值（东方郡显示1990年），不应用其覆盖权威目录。
5. **稳定性边界**：只完成当日低频验证，未验证多日连续成功、全部住宅覆盖、种子下架、房源更新时间、真实房源去重或规模化风控。

## 建议接入边界

先以已确认小区进行试点，关联保存真实 neighborhood_id、可访问种子房源入口及证据；每页检查归属、去重与游标推进，分页失败不可发布为完整快照。保留现有住宅目录、合租/分割排除、同实体去重、单位租金中位数与旧快照保留语义。来源失败与空房源分开。自动搜索另做验证后再启用，不能照搬此次未生效的 full_text HTML 搜索。
