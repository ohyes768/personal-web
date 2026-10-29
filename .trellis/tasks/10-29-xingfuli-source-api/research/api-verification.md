# 幸福里小区主页 API 只读验证

日期：2026-10-29（Asia/Shanghai）。未修改代码、生产关联或快照。

## 已验证接口

- `GET https://m.xflapp.com/f100/api/neighborhood/info?neighborhood_id=<小区ID>`
- `GET https://m.xflapp.com/f100/api/same_neighborhood_rent?neighborhood_id=<小区ID>&city_id=1853&offset=0&count=10`

接口及参数来自主页实际引用的 `NeighborDetail.fab1df0d.js`，模块85539的JX、dJ调用；未执行脚本，未使用登录Cookie或绕过验证。

## 结果

- 万科璞悦湾：资料API status=0，ID=6584028761644073220，滨文路670号，GCJ02=120.137265,30.170317，city_id=1853；ID、名称、地址、坐标均与HTML解析结果一致。
- 租房入口API status=0，total=24，items=10；10个入口种子ID与主页解析结果完全一致。条目不含显式neighborhood_id，不能把按小区ID查询成功当作房源归属核验，绑定前仍须用详情/列表核对。
- 欣盛东方郡资料API复测成功：ID=6854812199240614151，春晓路198号，GCJ02=120.213989,30.197716，city_id=1853，district_name=滨江。

## 可替代范围与性能边界

资料API可替代主页身份/地址/坐标读取；租房入口另需第二次API请求。不能把原来一页的逻辑简单替换成每候选两次API并宣称减少请求。应先用资料API评估候选，只有最终确认的候选才读租房入口并执行归属核验。成功API资料可沿用断点缓存，绑定前的新鲜证据仍按原契约校验。当前仅少量样本验证，不代表全量、多日稳定或速度提升已经实测。
