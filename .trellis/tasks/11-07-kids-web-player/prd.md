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

- [ ] 浏览器访问 `/kids-audio/<合集>/<文件>` 可直接播放，拖动进度条正常（Range 生效）
- [ ] 设备歌单页点「播放」能按编号顺序播放合集曲目，可暂停/切歌/拖进度
- [ ] 未发布的合集（本地目录不存在）点播放给出可读提示，不白屏
- [ ] `pnpm build`（apps/kids-catalog）通过；后端 pytest 通过（新增 tracks 接口测试）
- [ ] docker-compose.nas.yml 与 nginx/web.conf 改动经 deploy 后在 NAS 实际生效
