# 0–1岁儿童专辑候选脚本

独立预研版，不与主站整合，不下载音频，不需要账号或付费接口。

## 运行

在本目录安装依赖并运行（Python 3.10+）：

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python hot_albums.py
```

按北京时间写入 `data/hot-albums/YYYY-MM-0-1.json`、`.csv`、`.md`。同一月份重复运行只读取这份 0–1 岁缓存，不会重新访问网站；原先的 `YYYY-MM.json` 儿童候选不会被读取或覆盖。

## 严格年龄口径

输出最多 30 条，但可以少于 30 条：数量不足时不会用普通儿童、睡前故事、儿歌或学龄内容补齐。

- 蜻蜓FM：只读取公开的儿童 `0–1岁` 筛选页，记录为“蜻蜓FM年龄筛选”，可信度高。
- 喜马拉雅：只保留儿童热播榜中标题或简介明确写有 `0–1岁`、`0岁+`、`婴儿`、`婴幼儿` 的作品，记录为“详情简介明确年龄标注”，可信度中。
- 每条记录有 `age_band`、`age_evidence`、`age_confidence`。这只是平台或版权方的年龄声明，仍建议家长试听后决定是否播放。

结果是本月采集快照，不是官方月榜；“免费采集”不代表作品音频免费。

## 风控与去重

单次只读取蜻蜓robots和年龄分类页、打开一次喜马拉雅榜单；无翻页、账号、代理、签名破解或自动重试。浏览器仅阻止音频播放和本机回环请求。遇到访问限制会停止。

失败时保留当月 `.attempt`，避免定时任务持续重试；人工排查后才删除它。进程异常退出可能留下 `.collect.lock`，确认没有运行任务后再删除。按“平台+专辑ID”去重；不同平台的同名作品仍保留为不同来源。

本版不读取或改动旧的 `catalog.sqlite3`、下载记录；未来音频下载应另接入文件登记及内容校验。

## NAS

在 NAS 的可写持久化目录运行：

```sh
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
python hot_albums.py --output-dir /你的持久化目录/kids-catalog
```

设置每月一次任务即可。Chromium 需要受支持的 Linux 环境；精简 NAS 系统建议使用兼容容器。当前仅在 Windows 上验证脚本，不包含自动创建 NAS 任务。

## 测试

```sh
python -m unittest discover -s . -p test_hot_albums.py
```