# 执行计划：手动链接导入下载新合集

## 步骤

### 1. 后端：链接解析与预检模块
- [x] 新建 `backend/kids-catalog/src/link_import.py`：`parse_album_link`、`probe_album`、`LinkImportError`（design.md 契约）
- [x] 新建 `backend/kids-catalog/tests/test_link_import.py`：链接格式（两平台 www/m/尾斜杠/query）、单曲链接拒绝、probe 各分支，mock 网络层
- 验证：`python -m pytest tests/test_link_import.py -v` → 26 passed

### 2. 后端：数据模型与 Catalog
- [x] `src/main.py` Catalog：albums 加 `source` 列（pragma 迁移）；`refresh()` 清理加 `source='chart'` 条件、upsert 不覆盖已有 source
- [x] `Catalog.import_album(row)`：upsert manual + 幂等 + 触发下载（直接复用 queue()）
- [x] `tests/test_api.py` 增补：import 后触发 refresh，manual 专辑与 job 仍在；重复 import 幂等
- 验证：`python -m pytest tests/test_api.py -v` → 19 passed

### 3. 后端：API 端点
- [x] `POST /api/albums/import`（body 校验、LinkImportError → 422）
- [x] `tests/test_api.py` 增补：成功（假 downloader）/付费拒绝/非法链接/body 校验/幂等返回
- 验证：`python -m pytest tests/ -v` → 132 passed, 1 skipped

### 4. 前端：导入入口
- [x] `apps/kids-catalog/app/page.tsx`：输入框 +「获取」按钮 + 结果 message（按 job 状态措辞）；专辑卡片「手动添加」标记
- [x] heading（本月精选）改按 chart 来源取 last_seen，避免手动导入把月份标题顶掉
- [x] 手动专辑的年龄行改为「用户自主选择 · 不做年龄筛选」，不冒充平台年龄依据
- 验证：`pnpm build` 通过；生产构建 + Playwright 实机走通真实链接（导入→下载→合集候选）

### 5. 收尾
- [x] 全量 `python -m pytest tests/ -v` + 前端 `pnpm build`
- [x] 更新 spec（新增 `.trellis/spec/backend/kids-catalog/backend/manual-import.md`，index.md 加引用）与 CLAUDE.md 项目结构说明
- [x] 质量检查（trellis-check）：修复 8 处问题并补 15 条用例，最终 `147 passed, 1 skipped` + build 通过
- [x] commit

## 质量检查发现并修复的问题

1. **陈旧 `skipped_paid` 任务挡住手动导入**（真 bug）：`queue()` 只对 `failed`/`needs_authorization` 重试，
   旧的「整张付费跳过」任务会被幂等直接返回，导致预检已确认可下载却永不下载。
   修法：预检确认非付费时先清掉该专辑的 `skipped_paid` 任务再入队。
2. `import_album` 返回值展开 `**queued` 会带出 `queue()` 的 `id` 键、且 `reason` 可能缺失 →
   改为显式返回 `{album_pk, title, job_id, status, reason}`。
3. `vip_label` 类型异常时 `in` 判断抛 TypeError → 500；`maxPageId` 非 int 时比较抛 TypeError → 均已归一化。
4. `_fetch` 错误文案两个平台混用时分不清来源 → 加平台标签。
5. 前端：FastAPI 请求体校验失败时 `detail` 是数组，原代码只判字符串会退化成无信息的「获取失败」→ 补 `detailText`。
6. 前端：`importMessage` 缺 `unavailable`/`skipped_paid` 两个可达状态文案，落到默认「开始下载」会说谎 → 补齐。
7. CSS：`.import button` 特异性压过全局 `button:disabled`，禁用态仍显示深绿 → 补 `.import button:disabled`。

检查 agent 另实测通过：老库迁移（存量行 `source='chart'`）、并发导入同一专辑只触发 1 次下载、
导入→下载→设备合集候选→生成歌单→设备端按编号查询的完整跨层链路。

## 设计修正记录（实现期实测发现）

初版设计按曲目级 `isfree` 判定蜻蜓付费，实测语义相反：`isfree=true` 标记的是 VIP 专辑里的**免费集**
（`sale_props` 列出同一批 id，实测这些节目 HTTP 206 可下，专辑里其余节目全部 401）。
改用专辑级 `vip_label == "会员畅听"` 判定整张付费，与网页榜单侧 `sale_type == 1` 一一对应（9/9 付费、5/5 免费命中）。

## 回滚点

- 每步独立可测，pytest 全绿才进下一步
- 涉及 sqlite 迁移仅加列带默认值，老代码兼容新库；回滚代码后新列残留无害

## 真实链接验证清单（已全部实机跑过）

- 喜马拉雅免费：`https://www.ximalaya.com/album/4436043`（宝宝巴士经典儿歌，864 曲）→ 预检通过、导入成功
- 喜马拉雅付费：`https://www.ximalaya.com/album/15746968` → 报「付费专辑不支持下载」✓
- 蜻蜓免费：`https://m.qingting.fm/vchannels/326665/`（宝宝巴士三字儿歌）→ 导入成功，91 曲全部下载完成并成为设备合集候选 ✓
- 蜻蜓付费：`https://m.qingting.fm/vchannels/464506/` → 报「付费专辑不支持下载」✓
- 非法：单曲链接、无关 URL → 报「单曲链接不支持 / 无法识别的链接」✓
