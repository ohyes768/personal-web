# 执行计划：设备歌单手动选择合集 + 独立 tab

前置：backend 用 `backend/kids-catalog`（依赖已就绪）；前端 `apps/kids-catalog`。基线测试先跑一遍确认全绿。

## 步骤

### 1. 后端：候选行查询 + generate 过滤
- [x] `Catalog.device_candidate_rows()`：只读 SQL，返回 `{folder, title, source_id}`（与 `device_candidates()` 同源同序）
- [x] `DeviceCollections.start(prepare, selected_folders=None)` / `_generate` 按 folder 过滤 `sources`；一致性检查改为对比选中集合
- [x] `main.py`：`ConfirmCollection` 旁新增 `GenerateCollections(folders: list[str] | None)`；路由校验（[] → 422；未知 folder → 422 报出）；`GET /api/collections` 响应加 `candidates`（含 completions 状态 → `confirmed`）
- 验证：`python -m pytest tests/test_device_collections.py tests/test_api.py -v`

### 2. 后端测试
- [x] folders 过滤：选中子集 → 快照只含选中；未选者不进 skipped
- [x] `folders: []` → 422；未知 folder → 422 且信息含未知项；缺省 → 全量（兼容）
- [x] `GET /api/collections` 返回 candidates 字段，folder/title/confirmed 正确
- [x] 生成期间未选合集状态变化不再导致整体失败（一致性检查范围缩小）
- 验证：同上，全绿

### 3. 前端：tab 拆分
- [x] `page.tsx`：`?tab=` 切换（默认 catalog），`<DevicePlaylist/>` 移入 playlist 分支
- [x] `globals.css`：tab 条样式
- 验证：`pnpm build` 通过；dev 环境两个 tab 直达/刷新保持

### 4. 前端：候选勾选清单
- [x] `device-playlist.tsx`：类型加 `candidates`；默认全选（只记取消项，刷新不丢）；复选框行（含未确认标记）
- [x] 生成 POST `{folders}`；空选择前端拦截；running 时禁用勾选
- 验证：dev 环境走查——部分勾选生成、全选生成、全不选拦截、unconfirmed 确认流程、轮询

### 5. 收尾
- [x] 更新 `docs/哆咪音频管理-功能说明.md`（设备歌单 tab、手动选择）
- [x] 全量后端测试 + `pnpm build`
- [x] spec 更新（若形成新约定）+ commit

## 回滚点

- 每步独立可 revert；步骤 1/2 仅后端，步骤 3/4 仅前端，互不阻塞。
- 生成接口缺省行为不变，任意时刻回滚前端即恢复全量生成。

## Review gates

- 步骤 2 完成后：后端契约（candidates 字段、folders 语义）确认再动前端。
- 步骤 4 完成后：浏览器走查截图确认交互。
