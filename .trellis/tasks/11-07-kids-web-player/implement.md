# 实现清单：设备歌单浏览器播放

## 顺序

1. 后端：main.py 新增 `GET /api/collections/{folder}/tracks`（404 语义 + 排序 + 仅 .mp3/.m4a）
2. 后端测试：tests/ 新增 tracks 接口用例（正常、未知 folder 404、非音频文件被过滤）
3. 前端：新增 `app/audio-player.tsx` 播放器组件；device-playlist.tsx 合集行接「播放」
4. 前端验证：`pnpm exec tsc --noEmit` + `pnpm build`（apps/kids-catalog）；390px 布局自查
5. 后端验证：`cd backend/kids-catalog && .venv/Scripts/python -m pytest -q`（Windows 本机）
6. 部署文件：仓库 nginx/web.conf 加 `/kids-audio/` location；NAS 本机 /home/ohyes768/nginx/docker-compose.yml 加 `/music:ro` 挂载（不在仓库内，改挂载需 up -d 重建）
7. 收尾：提交 → NAS `./scripts/deploy-nas.sh nginx` + 重建 kids-catalog 前后端容器 → NAS 实测 Range 与播放

## 验证命令

```bash
cd apps/kids-catalog && pnpm exec tsc --noEmit && pnpm build
cd backend/kids-catalog && .venv/Scripts/python -m pytest -q
# NAS 实测（部署后）：
curl -sI "http://<nas>/kids-audio/<folder>/<file>" | grep -i accept-ranges
curl -s -r 0-1023 -o /dev/null -w "%{http_code}\n" "http://<nas>/kids-audio/<folder>/<file>"   # 期望 206
```

## 回滚点

- 步骤 1-5 纯代码新增，git revert 即可
- 步骤 6 单独成提交（web.conf），回滚 = 还原 web.conf 并 `deploy-nas.sh nginx`；NAS 本机挂载属环境变更，删掉 volume 行再 up -d 即回滚

## 实施结果（2026-11-11）

| 步骤 | 状态 | 说明 |
| --- | --- | --- |
| 1 后端 tracks 接口 | ✅ 已有 | `GET /api/collections/{folder}/tracks`，另补 `published` 字段 |
| 2 后端测试 | ✅ | `tests/test_web_player.py` 7 条（排序/过滤/404/穿越/已发布目录） |
| 3 前端播放器 | ✅ | `audio-player.tsx` + 候选行与设备歌单表双入口 |
| 4 前端验证 | ✅ | `tsc --noEmit` 通过；next build 在 Linux 容器内通过 |
| 5 后端验证 | ⚠️ | 245 passed / 1 skipped；2 条失败在干净树上同样复现（3000 文件用例 Windows 磁盘慢超时 + 1 条顺序相关偶发） |
| 6 部署文件 | ✅ | `nginx/web.conf` 的 `/kids-audio/` 已生效；NAS 本机 nginx 挂载 `/music:ro` 已就位 |
| 7 部署实测 | ✅ | 前后端容器重建上线；线上 206 Range、播放/下一首/计数、390px 布局均实测通过 |

提交：`3573ac9f`（补缺）、`bff06dae`（单播放器）、`ec3b704e`/`17633de6`/`ffcb168a`（390px 窄屏排版）
