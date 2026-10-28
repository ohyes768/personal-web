# 轮廓上传接口与前端展示

## Goal

后端提供 `POST /api/map/boundaries/import` 接收脚本生成的轮廓合集,鉴权+校验后原子落盘;前端识别新来源 `osm-building` 并以虚线渲染,与快照轮廓可区分。

## Requirements

- **鉴权**:环境变量 `HOUSING_ADMIN_TOKEN`;请求头 `X-Admin-Token` 常量时间比较;未配置 token 时接口返回 503(功能显式关闭)。线上公网可达,此接口必须带门禁。
- **请求体**:`{source: "osm-building", boundaries: [{community_id, coordinate_system: "gcj02", rings: [[[lng,lat]...]], meta?}]}`。
- **逐条校验**(拒绝不影响其他条目):
  1. community_id 存在于当前展示小区集合
  2. ring 坐标 ≥3 点且首尾闭合
  3. 坐标落在滨江∪萧山接壤围栏内(复用现有 is_in_scope)
  4. 面积 sanity:≤1 km²(防聚类粘连的巨多边形)
- **落盘**:合并进 `binjiang_polygons_merged.json`(同 cid 覆盖,幂等);写入前备份到 `data/boundaries-backup/`(保留最近 5 份);原子写(临时文件 + rename)。
- **响应**:通过数量 + 拒绝清单(cid + 原因)。
- **前端**:轮廓渲染来源白名单放开 `osm` → `osm|osm-building`;`osm-building` 用虚线描边区分。
- 生效即时:落盘后 `GET /api/map/communities` 即返回新轮廓,无需重启。

## Acceptance Criteria

- [x] 无/错 token → 401;服务端未配 token → 503
      （hmac.compare_digest 常量时间比较；test_missing_token_returns_503、test_wrong_token_returns_401）
- [x] 四类校验各自有拒绝用例,响应含 cid+原因;合法条目不受同批非法条目影响
      （test_reject_unknown_community / test_reject_open_ring / test_reject_out_of_scope / test_area_limit_unit / test_reject_wrong_source；test_partial_accept_mixed_batch 覆盖混合批次）
- [x] 合法上传落盘后 communities 接口返回该轮廓(source=osm-building);重复上传覆盖不重复
      （test_accept_writes_entry_with_meta_and_backup、test_reupload_is_idempotent；写入 source=osm-building，_meta.matched 计数去重追加。链路：上传落 binjiang_polygons_merged.json → load_polygons → effective_polygons → /communities 下发 boundary_source=osm-building）
- [x] 落盘前有备份、写入为原子操作(测试覆盖)
      （rotate_backup 保留最近 5 份，test_rotate_backup_keeps_recent_five；tempfile.mkstemp + os.replace 原子写）
- [x] 前端 osm-building 轮廓以虚线渲染(本地数据验证)
      （BinjiangMap.tsx 白名单 osm|osm-building，strokeStyle dashed）
- [x] `python -m pytest tests/ -v` 与前端 `pnpm build` 无新增失败
      （后端全量 968 passed；前端 130 测试、tsc、lint、build 全通过）

## Dependencies

- 无前置依赖,可先于 boundary-estimate-script 开发;联调在脚本任务端到端步骤进行。
