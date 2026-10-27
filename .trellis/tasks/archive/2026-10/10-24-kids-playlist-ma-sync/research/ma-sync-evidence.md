# 2026-10-24 NAS 只读调查

- kids 后端已有 MA URL/token/root，未读取或输出 token 内容。
- MusicAssistant.call('providers') 认证成功；本地来源 filesystem_local--p6a8VRdW、available=true。该ID只作调查证据，代码需动态发现。
- 运行中的 MA `/api-docs/commands.json` 确认 music/sync 返回 BackgroundTask[]，接受 media_types/providers；tasks/get 接受 task_id；tasks/list 返回任务列表。
- 任务字段包括 id/status/last_error/progress/metadata等，现有任务有success状态；同步状态值需根据实际模型定义补充，不猜测成功。
- 听，小蜗牛艾玛目录18个M4A，前三个文件五字段均为空；tag_audio预览needs_change=18。设备generation done，items编号2/title听，小蜗牛艾玛/count18。
- 真实文件尚未修改，未触发新的MA扫描，也未更改生产配置。
