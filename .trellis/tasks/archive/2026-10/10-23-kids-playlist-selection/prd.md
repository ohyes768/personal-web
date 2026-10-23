# 哆咪音频设备歌单：手动选择合集生成 + 独立tab页

## Goal

哆咪的故事库（`/kids`）两处改动：

1. 生成设备歌单时，由「无条件全量收录本月已下载合集」改为「手动勾选哪些合集进入歌单」。
2. 设备歌单从首页内嵌 section 拆出，成为独立 tab 页；首页专注本月精选专辑目录。

## 背景

- 现状：`apps/kids-catalog/app/page.tsx` 单页内嵌 `<DevicePlaylist/>`；后端 `DeviceCollections.start()` 无条件把 `catalog.device_candidates()`（本月全部 `done` 专辑）生成歌单。
- 设备端按编号消费快照（`/api/device/v1/collections`、`by-number`），编号语义不可破坏。

## Requirements

### R1 手动选择合集（生成时）

- 设备歌单 tab 内展示「本月已下载完成的合集」候选清单，每项可勾选，**默认全选**（与现状行为一致，老流程直接点生成即可）。
- 候选清单同时标出未确认下载完整的合集（现有 unconfirmed 语义），勾选后参与生成，校验不过仍进「未加入歌单」列表。
- 点击「生成歌单」按当前勾选生成；未勾选的合集不进歌单、也不出现在 skipped 里。
- 一次都没选（清单为空或手动全取消）时给出明确提示，不发起生成。

### R2 设备歌单独立 tab

- `/kids` 顶部提供 tab 切换：「本月精选」（专辑目录+获取最新+下载）与「设备歌单」。
- tab 状态反映到 URL（刷新/分享后停留在同一 tab）。
- 设备歌单 tab 承载：当前歌单快照表、生成控制（候选勾选+生成按钮）、未加入歌单的确认流程——即现有 `device-playlist.tsx` 全部能力。
- 首页不再内嵌设备歌单 section。

### 兼容与不变量

- `POST /api/collections/generate` 缺省 body（不传 folders）= 全部候选，行为与现状一致（兼容旧调用方/习惯）。
- 快照 schema（编号、排序、revision、resolve 语义）不变，设备端无感知。
- 下载、目录刷新、月度轮换逻辑不动。

## Out of Scope

- 候选范围扩展到历史月份/NAS 全目录（仍限本月 done 专辑）。
- 勾选状态跨会话持久化（每次进页面默认全选）。
- 歌单曲目级编辑、试听、播放。

## Acceptance Criteria

- [ ] `/kids?tab=playlist` 直达设备歌单 tab，刷新后 tab 不丢；默认落在「本月精选」。
- [ ] 候选清单默认全选；取消部分勾选后生成，歌单只含勾选合集；未勾选项不出现在 skipped。
- [ ] 全不选时点生成，前端提示且不发请求（或后端 422），不破坏现有歌单。
- [ ] 不传 folders 直接调 `POST /api/collections/generate` 仍全量生成（兼容）。
- [ ] 生成中的轮询、失败提示、unconfirmed「确认此合集已下载完整」流程在新 tab 内照常工作。
- [ ] 后端测试覆盖：folders 过滤、空列表拒绝、未知 folder 忽略或报错（按 design 约定）、缺省全量、candidates 返回字段。
