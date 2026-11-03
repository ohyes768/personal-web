# 验证记录（2026-11-02）

## 1. 真实网络端到端（唯一权威口径）

脚本：`.trellis/tasks/11-02-kids-netease-music/research/e2e_netease_check.py`
运行：`cd backend/kids-catalog && uv run python ../../.trellis/tasks/11-02-kids-netease-music/research/e2e_netease_check.py`

```
=== https://music.163.com/playlist?id=13907752641
  解析: 网易云歌单 / 13907752641
  预检: 标题='婴儿哄睡必听 | 引导0-6个月新生儿入睡 拍嘘白噪柔旋律助眠' 曲目数=39 sale_type=None
  下载: 成功 33 / 跳过 6 / 失败 0
  跳过原因示例: SkipReason(title='白噪音婴儿睡眠 羊水声+嘘声哄宝宝入睡', reason='VIP 付费曲目，平台未放行')
  落盘目录: '婴儿哄睡必听  引导0-6个月新生儿入睡 拍嘘白噪柔旋律助眠'
  落盘: 33 个文件, 目录大小 62705608 字节
  首个文件: 001-（宝宝催眠3分钟入睡）子宫羊水声+嘘嘘声.mp3 magic=b'ID3'
  重跑: 成功 33（应等于首轮，文件已存在）

=== https://music.163.com/album?id=164558809
  解析: 网易云专辑 / 164558809
  预检: 标题='携风入梦丨高效催眠、舒缓治愈钢琴纯音' 曲目数=8 sale_type=None
  下载: 成功 6 / 跳过 2 / 失败 0
  跳过原因示例: SkipReason(title='助眠（助眠、疗愈钢琴纯音）', reason='VIP 付费曲目，平台未放行')
  落盘目录: '携风入梦丨高效催眠、舒缓治愈钢琴纯音'
  落盘: 6 个文件, 目录大小 14583694 字节
  首个文件: 001-入夜（助眠、疗愈钢琴纯音）.mp3 magic=b'ID3'
  重跑: 成功 6（应等于首轮，文件已存在）

全部通过
```

覆盖点：
- 歌单与专辑两条链路（解析 → 预检 → 下载 → 落盘 → 幂等重跑）
- 免费曲真实落盘且为合法 mp3（`ID3` 头）
- VIP 曲逐条跳过并带可读原因，**未计入失败**
- 重复下载不重复落盘（断点续传）
- 落盘目录名与 `sanitize_filename` 一致（`|` 被去掉）

## 2. 后端 pytest

命令：`cd backend/kids-catalog && KIDS_DATA_DIR=... KIDS_MUSIC_DIR=... uv run python -m pytest -q`

结果：**238 passed, 3 failed**（多次运行的失败集合在 {2 个稳定失败 + 0~1 个偶发} 之间浮动）

3 个失败是**改动前就存在的失败**（用 `git stash` 回到原始代码跑全量，失败集合完全相同）：

| 失败用例 | 单独跑 | 性质 |
|---|---|---|
| `test_device_collections.py::test_long_collections_are_counted_from_nas_without_ma_limit[3000]` | 通过 | 全量跑时的顺序/资源依赖 |
| `test_playlist_ma_sync.py::test_partial_tag_failure_retries_without_reconfirming_completion` | 通过 | 同上 |

`tests/test_api.py` 另有 1–2 个偶发失败（`test_partial_job_requeues_for_completion`、
`test_import_album_replaces_stale_paid_skip_job`），**原始代码同样偶发**（原代码 4 次运行中 2 次失败），
属既有的后台下载线程时序抖动，非本次改动引入。

新增用例全部通过：
- `tests/test_link_import.py`：新增 13 个用例（解析 15 组参数化 + 预检各分支 + 平台不串台 + 缺 id 拒绝）
- `tests/test_downloader.py`：新增 12 个用例（含**返回乱序按 id 对齐**的回归锚点）
- `tests/test_api.py`：新增 4 个用例（导入排队 / 成为设备歌单候选 / 逐条跳过原因 / 歌单专辑同 ID 不撞库）

## 3. 前端

```
cd apps/kids-catalog
pnpm exec tsc --noEmit   → 通过（exit 0）
pnpm build               → 通过（Next.js 15.5.26，静态生成 4/4）
```

## 4. 已知环境限制（非本次改动引入）

- macOS 上 `src/main.py` 模块级 `app = create_app()` 会写 `/app/data`（Linux 容器路径），
  macOS 只读根文件系统导致 `tests/test_api.py` 收集期报 `OSError: Read-only file system: '/app'`。
  **原始代码同样如此**，需设 `KIDS_DATA_DIR` / `KIDS_MUSIC_DIR` 绕开。
- `pnpm` 未全局安装，本次用 `corepack` 提供的 `~/.cache/node/corepack/v1/pnpm/12.16.1`；
  `pnpm install` 会重写 `package.json`（加 `packageManager` 字段）与 lockfile，**已 revert，不在本次改动内**。

## 5. 未覆盖/有意不做

- 网易云短链 `163.cn`（实测 SSL EOF / HTTP 502，不可达）→ 明确拒绝并提示用完整链接。
- 网易云专辑级付费判定 → `sale_type=None`，逐曲判定。
- 网易云曲目 tag 写入、MA 集成、设备播放 → 属独立功能线，本期不动。
