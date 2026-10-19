# Design

目录路由增加只读 coverage projection，不放进 inventory/admitted，避免关联查询递归。每请求批量读取 registry sources/meta、法拍存储、租金发布快照和最近 job。

复用 auction_history.property_key、rental_reference.storage.load_current、statistics.select_valid/is_stale。法拍只认当前 matched，asset 优先其次轮次；任一身份 ignored 优先排除。不限成交/日期，缺 asset 轮次单列。详情额外返回记录，列表不含明细。

租金使用当前 matched Fang source 对应快照，允许旧 community ID 下相同 source。有效样本优先，附 stale/该小区最近失败。仅当前关联之后的该小区 job 错误视为更新失败。无快照和已发布空快照区分；未关联时依 review reason 区分待采集、待关联、来源缺失、搜索失败。

catalog 新增 auction=has|none或空、rental=状态或空，覆盖计算先于过滤分页。不收录不受新增筛选影响。前端延用表格、data-label 窄屏布局，法拍按钮打开既有详情并展示记录。

无迁移、无采集、无关联写入。业务存储损坏返回错误，不能伪装为零。回滚移除投影调用和新增列即可。
