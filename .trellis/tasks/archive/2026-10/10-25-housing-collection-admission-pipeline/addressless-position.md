# 无地址高德候选人工核对（2026-10-27）

## Scope / Trigger
白马湖小区鸿雁苑的真实高德响应为 status=1、info=OK、infocode=10000，POI B023B0ABX6 的 address=[]、住宅小区类型及坐标正常。不是限流。旧流程把无地址候选转入 review，又同时禁止人工选择，导致无法完成。

## Signatures
现有 POST /api/directory/workflow/catalog/{cid}/position/confirm 增加 coordinates_verified:boolean=false（strict）。服务 confirm_position 同名参数缺省 false，不增加端点或数据库结构。

## Contracts
选择有效坐标候选 → 精确坐标地图入口 → 人工勾选 → 原 revision/poi_id 加 coordinates_verified:true。无地址时只有明确 true 才能确认；后端读取保存的候选坐标，不信任客户端提供的替代坐标。所有 POI 候选重新验证 district、finite GCJ02、区内边界。保存 manual、confirmed_at 和 coordinates_verified=true，保留原空地址与 POI ID/类型。切换候选或 revision 重置勾选；忙碌、缺 revision 或无效坐标不能提交。手填坐标仍须有有效地址。

## Validation & Error Matrix
- 无核对标记的无地址候选：409；非严格布尔标记：422。
- 伪造 ID、过期 revision、无效或区外坐标、区域不符：409。
- 有效候选经核对确认：200，state=manual，类型沿用所选 POI。
- 原来源实际地址不补成高德地址，不绕过实际地址、用途和挂牌收录门槛。

## Good / Base / Bad Cases
Good：唯一无地址住宅主体保持 review，经人工核对变 manual，再按既有双来源用途与收录规则处理。
Base：有地址候选仍按原流程确认，无需新增勾选。
Bad：解除前端禁用却保留后端无地址拒绝；或把来源地址伪造成高德地址；或勾选一次后自动沿用到其他候选。

## Tests Required
test_position_status.py 覆盖无标记拒绝、有效人工确认、保留空地址/类型/实际地址、过期版本、无效/区外/区域不符、API 严格布尔。
test_collection_pipeline.py 覆盖真实形态 address=[] 的唯一候选 review → manual → admitted，selected POI 同时成为用途证据。
position-status.test.cjs 覆盖可选无地址候选、精确地图链接、勾选门槛及确认后不误标来源地址。
浏览器检查覆盖实际选择/勾选/提交 payload、切换候选和 revision 重置、busy 禁用，1440/390 视口无横向溢出。

## Wrong vs Correct
Wrong：禁止一切无地址 POI 确认，或删除地址校验后无条件接受。
Correct：显式坐标核对 + 保存候选/版本/区域校验 + manual 证据，空地址保持为空。

## Validation results
- 后端定位、v2 流程、目录、用途及 API 相关 154 项通过；前端定位/用途相关 25 项通过。
- 浏览器独立 React 组件交互验证通过，未写生产数据。
- TypeScript、ESLint、Next 生产构建通过。沙箱内构建遇到 CSS 子进程限制，获准在沙箱外运行后通过。
- 前端全量 77 passed / 3 failed：community-management 的旧断言不接受现有 details；rental-dashboard 与 rental-sources 引用已缺失的租金组件。本次未改这些文件。
- 未提交、未部署。
