# Housing-Map 小区合并契约

> **适用场景**：合并重复小区（同名/别名不同）、改合并前端入口、或为验证造可合并数据。

## 后端合并语义

`POST /api/map/directory/communities/{被并方id}/merge`，body `{"community_id": 保留方id}`
（`community_registry.py:_merge`，单条事务）。

| 行为 | 细节 |
|------|------|
| 别名并入 | `keep.aliases = 去重(keep.aliases + 被并方 community_name + 被并方 aliases)` |
| 字段补齐 | `address/district/longitude/latitude/coordinate_system` **仅在保留方为空时**补被并方的值，不覆盖 |
| 高德定位 | **`amap_position`（POI 匹配结果、candidates、确认状态）不迁移**——合并后保留方的定位仍是自己那条；被并方的人工定位证据会丢失，需在保留方重新核对 |
| 来源记录 | `sources.cid` 整体迁移到保留方（法拍/租金来源随之迁移） |
| 被并方 | 写 `merged_to` 软链，随即从已收录列表消失（`community_views` 过滤 `merged_to IS NULL`） |
| 拒绝条件 | 双方都有 `fang`/`xingfuli` 的 matched 来源 → 409「两个小区都有租金来源，请先解除错误来源再合并」 |
| 市场状态 | `market_state` 不在合并字段内，**跟保留方走**（新房/二手房混选必须让用户确认保留方） |
| 事件 | 写 `merge` event，payload 含 `previous`（被并方合并前快照），数据层面可人工恢复 |

前端入口：目录页「已收录」Tab 的多选合并（`MergeDialog.tsx`）；老审核台 `CommunityWorkspace` 没有合并入口。

## 准入硬门槛（造数据的坑）

- 目录流程启用后（`meta.directory_flow_version == 'tmsf-directory-v1'`），`decide_admission('admit')`
  直接抛错「住宅名单按透明售房网资料自动分类，不能手工绕过条件」。
- 最终 `admission_state` 由 `directory_policy.eligibility()` **重算**，`community_admission` 里写
  `admitted` 不作数。门槛依次为：tmsf 来源非空 → 名称一致 → 区域 ∈ {滨江, 萧山} → 用途类型齐全 →
  有效地址 → listing 门槛 → `position_gate`（高德定位须 matched/manual 且有住宅类 typecode）。
- **本地开发库的已收录列表通常是空的**（没跑过高德定位流程），别指望拿库里现成数据验证合并。

## 隔离验证环境

改生产/开发数据前，用独立副本验证：

1. 后端：`HOUSING_DATA_DIR=<副本 data 目录> uvicorn ... --port <独立端口>`（`data_loader.DATA_DIR` 支持该环境变量）。
2. 前端：复制一份 app 目录并同步最新 `src`，`HOUSING_API_ORIGIN=http://127.0.0.1:<后端端口>`
   （`next.config.js` 的 rewrite 读这个变量），独立端口启动。
3. **Next dev 跨域保护**：dev server 拒绝非 localhost 来源的 dev resources，页面会卡在「加载中」且不发
   API 请求。用 `localhost` 访问，或在 `next.config.js` 加 `allowedDevOrigins: ['127.0.0.1']`。
4. **造 admitted 数据**：往副本 `community_registry.sqlite3` 插三行——`communities`（payload 含
   `address_origin: 'manual'`、地址、`coordinate_system: 'gcj02'`）、`community_admission`
   （`state: 'admitted'`、`decision_kind: 'manual'`）、`sources`（tmsf matched，`property_type: '住宅'`、
   `market_state`、`listing_count`）。多个 tmsf 来源要改 `sid`，否则 `(source,kind,sid)` 唯一约束会互相顶掉。
5. 收尾：`next dev` 的子进程会脱离 shell 继续监听，删目录报 `Device or resource busy`；先按 PID 停掉
   监听进程再删。临时目录不要留在仓库里（用 `.tmp-*` 前缀，删干净再提交）。

## 前端列表列宽约定

目录表是 `table-layout: fixed` + `nth-child` 百分比列宽。加 checkbox 列必须同步列宽规则并限定作用范围
（`.catalog-selectable.catalog-admitted`），否则新列塌成 0 宽、其他模式（待处理/不收录）列错位。
窄屏（≤760px）走卡片态，`.catalog-selectable` 的首列被隐藏 → 移动端不可多选合并。
