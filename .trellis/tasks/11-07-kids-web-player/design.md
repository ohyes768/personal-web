# 技术设计：设备歌单浏览器播放（nginx 静态方案）

## 数据流

```
nginx /kids-audio/<folder>/<file>  ──alias──▶  /music/<folder>/<file>   (宿主 xiaomusic/music, ro)
浏览器 <audio src="/kids-audio/...">  ◀── 200/206 (Range)
设备歌单页 ── GET /api/kids/collections/{folder}/tracks ──▶ 后端列出文件名（排序）
```

## 1. nginx（仓库 nginx/web.conf + NAS 本机 nginx compose）

- ⚠️ 修正（实施时发现）：nginx 容器不在仓库 docker-compose.nas.yml 里，而是 NAS 本机 `/home/ohyes768/nginx/docker-compose.yml` 管理的独立容器。音乐目录挂载加在那边：`- /home/ohyes768/xiaomusic/music:/music:ro`，改挂载需 `docker compose up -d` 重建（restart 不会新增挂载）。
- 仓库 nginx/web.conf（/api/kids/ 之后）：

```nginx
# kids-catalog 设备歌单浏览器播放：只读服务已发布合集音频；Range 由 nginx 静态模块原生支持
location /kids-audio/ {
    alias /music/;
    add_header Accept-Ranges bytes;
    types { audio/mpeg mp3; audio/mp4 m4a; }
}
```

注意：alias 末尾斜杠配对；关闭 autoindex（目录列表不给看，只允许直链文件）；现有 server 已是局域网 http，无额外鉴权。

## 2. 后端接口（backend/kids-catalog/src/main.py）

`GET /api/collections/{folder}/tracks`（经 nginx rewrite 变为 /api/kids/collections/...）：

- 用 `DeviceCollections.audio_files(folder, music_dir)` 取文件，按文件名 `sorted()` 返回 `{'tracks': [{'file': name}, ...]}`
- 复用 device-playlist 现有的 folder 校验思路：folder 不在候选/本地不存在 → HTTPException 404 `{'code': 'unknown_folder'}`
- 安全：路径只用 folder 名拼 `Path(music_dir)/folder`，沿用 `safe_child`/sanitize 约定，禁止 `..`

## 3. 前端（apps/kids-catalog/app/device-playlist.tsx + 新 audio-player.tsx）

- 合集行加「播放」按钮（disabled 条件：生成中）；点击拉取 tracks 并展开播放列表
- `<audio controls preload="none">`，`onEnded` 自动下一首；组件内部 state：当前 folder、曲目索引
- `src = /kids-audio/${encodeURIComponent(folder)}/${encodeURIComponent(file)}`（folder 含中文，必须逐段编码）
- 请求失败/404 → 行内可读提示；同时只播一个合集（切换时重建 audio src）

## 兼容与回滚

- 纯新增：nginx location、compose 挂载、一个 GET 接口、一个前端组件，不改既有行为
- 回滚 = 还原 web.conf/compose 并重启 nginx；接口与前端组件保留不影响旧功能
