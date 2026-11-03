# 实施计划：Kid 支持网易云音乐链接下载与设备歌单

任务路径：`.trellis/tasks/11-02-kids-netease-music/`
包：`backend/kids-catalog`、`apps/kids-catalog`
验证记录：`verification.md`｜接口实测结论：`research/findings.md`｜技术设计：`design.md`

## 阶段 1：链接解析与预检（`backend/kids-catalog/src/link_import.py`）

- [x] 1.1 加平台常量 `NETEASE_PLAYLIST = "网易云歌单"`、`NETEASE_ALBUM = "网易云专辑"`，加 `NETEASE_REFERER` 与接口 URL 常量。
- [x] 1.2 加正则 `_NETEASE_PATH` / `_NETEASE_SINGLE` / `_NETEASE_SHORT`；写 `_parse_netease_link()` 辅助函数处理：
  - hash 路由（`#/playlist?id=` / `#/album?id=`）
  - `/m/playlist`、`/m/album` 移动版路径
  - 缺 scheme 兜底
  - query 参数顺序不固定（`?userid=1&id=` 与 `?id=&userid=` 都要认）
- [x] 1.3 `parse_album_link`：命中返回 `(platform, album_id)`；单曲与短链 `163.cn` 明确拒绝并给出可读提示。
- [x] 1.4 更新 `_SUPPORTED` 文案，加入网易云支持的两种链接类型。
- [x] 1.5 `probe_album` 加网易云分支：歌单走 `/api/v3/playlist/detail`，专辑走 `/api/v1/album/{id}`；失败统一抛 `LinkImportError`。
- [x] 1.6 网易云 `probe` 返回 `sale_type=None`。
- [x] 1.7 检查点：`pytest tests/test_link_import.py -q` 通过（74 个用例）。

## 阶段 2：下载器（`backend/kids-catalog/src/downloader.py`）

- [x] 2.1 `Track.ext` 网易云用 `mp3`。
- [x] 2.2 `DownloadReport` 增加 `skip_reasons`（`SkipReason` NamedTuple 的 tuple，保持 frozen dataclass 可哈希）+ `skip_summary()`。
- [x] 2.3 `_fetch_json` 复用现有 `referer` 参数。
- [x] 2.4 `_list_netease_playlist`：`trackIds` 取 ID → `/api/song/detail/?ids=` 分批（200）取标题 → 按 trackIds 顺序输出。
- [x] 2.5 `_list_netease_album`：`/api/v1/album/{id}` 的 `songs[]` 一次全量映射。
- [x] 2.6 `_netease_batch_urls`：批量取直链，**按 id 建字典对齐**（返回顺序不保证与请求一致）；`-110` → VIP 原因，`404`/无 url → 无音源。
- [x] 2.7 `_download_netease` + `_download_netease_one`：分批取直链边取边下（直链 20 分钟过期）；403/404 → skip，超时/其他 → failed；记录 `skip_reasons`。
- [x] 2.8 `_download_file` 的 Referer 按平台参数化。
- [x] 2.9 检查点：`pytest tests/test_downloader.py -q` 通过（28 个用例）。

## 阶段 3：主服务与前端（`backend/kids-catalog/src/main.py`、`apps/kids-catalog/app/page.tsx`）

- [x] 3.1 `main.py`：`_run_download` 的 `reason` 拼接加入 `skip_reasons` 明细。
- [x] 3.2 `main.py`：`import_album` 对 `sale_type=None` 无需改动（`!= 1` 成立，不触发整张跳过）；已验证 NULL 落库回读为 None。
- [x] 3.3 前端 `page.tsx`：导入框 placeholder 加入「网易云歌单·专辑」。
- [x] 3.4 前端：`sale_type==null` 时网易云渲染「逐曲判定」徽标 + 混排说明 tooltip。
- [x] 3.5 检查点：`pnpm exec tsc --noEmit` 与 `pnpm build` 通过。

## 阶段 4：测试补齐

- [x] 4.1 `tests/test_link_import.py`：解析（含 hash 路由、移动版、缺 scheme、query 顺序、单曲/短链拒绝、缺 id）、平台不串台、`probe_album` 各分支。
- [x] 4.2 `tests/test_downloader.py`：曲目列表、**直链乱序返回按 id 对齐**（防回归）、`-110`/`404` 跳过原因、网络失败归 failed、403 归 skipped、落盘文件名、断点续传、`resolve_url`、`skip_summary`。
- [x] 4.3 `tests/test_api.py`：导入排队 → 设备歌单候选 → 逐条跳过原因上屏、歌单与专辑同 ID 不撞库。
- [x] 4.4 全量 `pytest -q`：237 passed，2 个失败为改动前既有（见 `verification.md`）。

## 阶段 5：质量检查与收尾

- [x] 5.1 跑质量检查：spec 合规、类型检查、测试、跨层数据流、代码复用、可哈希性回归。
- [x] 5.2 更新 `.trellis/spec/backend/kids-catalog/backend/manual-import.md`：网易云接口契约、付费判定口径、ID 冲突方案、返回顺序坑、分批上限、跳过原因。
- [x] 5.3 真实网络端到端验证（歌单 + 专辑 + 幂等重跑）：`research/e2e_netease_check.py`，结果见 `verification.md`。

## 验证命令

```bash
cd backend/kids-catalog
python -m pytest -q                      # 全量
python -m pytest tests/test_link_import.py -q
python -m pytest tests/test_downloader.py -q
python -m pytest tests/test_api.py -q

cd ../../apps/kids-catalog
npx tsc --noEmit
npm run build
```

## 回滚点

- 阶段 1–3 全部是**增量分支**，回滚 = 删掉 `link_import.py` / `downloader.py` 的网易云分支 + 前端文案。
- **无数据库 schema 变更**（复用 `platform` 字符串列），无迁移、无数据回滚脚本。
- 已下载的网易云音频留在 `music_dir/<标题>/`，不回滚（与喜马拉雅/蜻蜓的已下载内容一致处理）。
