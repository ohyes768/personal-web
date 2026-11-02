# 设计

## 数据流与修改边界
- xingfuli_rentals.py：使用公开列表API，从种子ID直接offset=0请求，续传服务端offset/search_id；保留单位/归属/分页完整性检查，不请求详情或HTML。
- statistics.py：增加显式幸福里列表证据资格，不放开所有detail_fetched=false。复用select_valid的筛选与重复规则作为采集配额标准；floor=null，沿用现有疑似重复规则，宁可少计，不声称识别全部同实体挂牌。
- refresh.py/storage.py：快照记录抽样模式、quota与过滤后qualified；详情请求计数保持0，不能再拿detail_success充当列表有效数。保留原子发布、取消不发布及来源变更复查。
- rental_routes.py与前端类型/租金面板：透传抽样模式，新列表快照提示未经逐套核验；旧详情快照保留原显示，无数据迁移。
- xingfuli_transport/discovery/rentals与probe/matching/refresh调用链：统一3秒默认/下限，避免上层默认5秒抵消修改；Fang默认值不动。

## 兼容与失败
旧6小时成功快照复用保留且展示原证据，不能当作本轮新API采集。未知证据仍排除；错误响应不伪造零租金。空列表没有可靠归属证据则失败保留旧数据。达到分页上限仍用原truncated语义。
3秒间隔保留共享请求锁及一小时冷却，不并发突破限速槽。回退代码可恢复详情采集，列表快照证据必须继续准确可读。

## 真实接口研究
GET https://m.xflapp.com/f100/api/search_api/rent
参数：channel_id=94349583687、house_id=种子ID、house_type=3、aid=1370、app_name=f100、count=20、refresh_type=2、offset=0、list_style=same_neighborhood_list。续页使用返回的offset/search_id。
已测种子7645222208480559123，目标小区6584028761644073220。仅低频公开只读验证，未发布快照。网页内部接口可能变化，需失败关闭。
