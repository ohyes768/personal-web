# kids-catalog 设备歌单浏览器播放（nginx 静态方案）

## 背景

设备歌单产物是 NAS 宿主机 `/home/ohyes768/xiaomusic/music/<合集名>/` 下的 mp3/m4a 编号曲目（容器内 `/music`，见 docker-compose.nas.yml:503）。目前歌单只能交给 Music Assistant / 音箱，用户希望直接在浏览器里播放。

调研结论：mp3/m4a 浏览器原生解码，拖动进度依赖 HTTP Range；方案选定为 **nginx 静态目录**（不给后端加流量、天然支持 Range），前端做一个播放器组件。

## 需求

1. nginx 新增静态路由 `/kids-audio/` 直接服务音乐目录（只读挂载进 nginx 容器），支持 Range。
2. 后端新增 `GET /api/kids/collections/{folder}/tracks`：返回指定合集（已发布的设备目录）的音频文件名有序列表（按文件名排序，仅 .mp3/.m4a），folder 非法或不存在返回 404。
3. 设备歌单页每个合集行增加「播放」操作：展开该合集曲目列表，逐曲顺序播放，支持暂停/继续、点击切歌、上一首/下一首、进度条拖动；播放中离开页面即停止（无需全局播放器）。
4. 迷你但完整：音量用浏览器原生控件即可（controls 属性），不做音量自绘、不做随机/循环（顺序播完即止，可留待后续）。
5. 样式沿用 cream/orange/green 风格；移动端 390px 可用。

## 非目标

- 不做后台播放、跨页续播、播放历史
- 不动 Music Assistant 同步链路
- 不做鉴权（沿用现状：家庭局域网）

## 验收标准

- [x] 浏览器访问 `/kids-audio/<合集>/<文件>` 可直接播放，拖动进度条正常（Range 生效）
      → NAS 实测 HEAD 200 + `Accept-Ranges: bytes`，Range 请求 206/1024 bytes，目录列表 403
- [x] 设备歌单页点「播放」能按编号顺序播放合集曲目，可暂停/切歌/拖进度
      → 候选区与「当前设备歌单」表都提供播放入口；上一首/下一首 + 原生控件暂停/拖动；线上实测 206 播放、下一首切到 002（计数 1/16 → 2/16）
- [x] 未发布的合集（本地目录不存在）点播放给出可读提示，不白屏
      → tracks 接口 404 `unknown_folder`，播放器行内显示「合集目录不存在或还没有音频」
- [x] `pnpm build`（apps/kids-catalog）通过；后端 pytest 通过（新增 tracks 接口测试）
      → Linux 容器内 next build 通过（Windows 本机 standalone 软链需特权，属环境限制）；pytest 245 passed / 1 skipped（另有 1 条 3000 文件用例因 Windows 磁盘慢超时、1 条顺序相关偶发，干净树上同样复现）
- [x] docker-compose.nas.yml 与 nginx/web.conf 改动经 deploy 后在 NAS 实际生效
      → nginx 本机挂载 `/home/ohyes768/xiaomusic/music:/music:ro` 已就位，web.conf 的 `/kids-audio/` 已 reload 生效；前后端容器经 `deploy-nas.sh kids-catalog` 重建上线

## 补充说明（实施后新增）

- 「当前设备歌单」表格新增「操作」列，可按编号直接播放已发布合集（PRD 第 3 条的「设备歌单页每个合集行」）。
- 后端 `/api/collections` 增加 `published`（已发布合集的播放目录名），上月发布、本月不在候选清单里的合集同样能播。
- 播放状态上提到设备歌单页，候选区与设备歌单表共用；播放器只在发起处展开，避免同一合集出现两个播放器同时出声。
