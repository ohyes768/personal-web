#!/usr/bin/env python3
"""按分组方案批量建立 service-manager 台账（一次性脚本）。

只写人工台账，不碰任何容器。已存在的服务会跳过。
用法：python3 scripts/bulk-import-service-ledger.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request

BASE = "https://127.0.0.1:9443"
ORIGIN = "https://127.0.0.1:9443"
CTX = ssl._create_unverified_context()

PW = "nas:compose"
PERSONAL = "nas:compose:personal-web:"

# (服务名, 分类, 用途说明, 标签, [组件 source_key 后缀])
GROUPS: list[tuple[str, str, str, list[str], list[str]]] = [
    ("股息率分析", "金融", "A 股高股息分析：红利指数成分股股息率排名与 M120 均线偏离",
     ["public", "stock"], ["dividend-frontend:1", "dividend-backend:1"]),
    ("抖音文字稿", "内容", "收藏的抖音视频转文字稿，按发布时间浏览回顾",
     ["media"], ["douyin-frontend:1", "douyin-backend:1"]),
    ("基金筛选", "金融", "多维筛选债券基金，对比收益表现并持续跟踪",
     ["public", "fund"], ["fund-select-frontend:1", "fund-select-backend:1"]),
    ("房产信息地图", "生活", "滨江小区参考房价、评分与地铁通勤，地图选点",
     ["housing"], ["housing-map-frontend:1", "housing-map-backend:1", "housing-map-browser:1"]),
    ("宽基趋势观察", "金融", "沪深300 月收盘线性回归通道，回看指数当前位置",
     ["public", "index"], ["index-trends-frontend:1", "index-trends-backend:1"]),
    ("哆咪故事库", "生活", "宝宝的故事与儿歌音频，资源检查与下载管理",
     ["kids", "family"], ["kids-catalog-frontend:1", "kids-catalog-backend:1"]),
    ("宏观经济", "金融", "利率、汇率、流动性与风险偏好的每日追踪",
     ["public", "macro"], ["macro-frontend:1", "macro-backend:1"]),
    ("RSS中转服务", "内容", "汇集 AI 助手推送的内容，FreshRSS 集中订阅阅读",
     ["rss"], ["rss-relay-frontend:1", "rss-relay-backend:1"]),
    ("Skill管理台", "工具", "统一克隆、登记与管理 Skill，发布到 OpenClaw / Hermes",
     ["skill", "hermes"], ["skill-manager-frontend:1", "skill-manager-backend:1"]),
    ("定时任务管理", "工具", "NAS 定时任务：调度时间、启停、执行记录与日志排查",
     ["cron"], ["task-web-frontend:1", "task-web-backend:1"]),
    ("服务管理台", "工具", "本台账自身：容器发现、部署路径、端口域名、证书与发布动态",
     ["infra", "self"], ["service-manager-frontend:1", "service-manager-backend:1",
                        "service-manager-socket-proxy:1"]),
    ("相册 immich", "生活", "家庭照片与视频相册（server + 机器学习 + postgres + redis）",
     ["photo", "family"], ["immich:immich-server:1", "immich:immich-machine-learning:1",
                           "immich:database:1", "immich:redis:1"]),
    ("智能家居", "生活", "Home Assistant 与 Node-RED 联动（host 网络）",
     ["home"], ["homeassistant:homeassistant:1", "homeassistant:nodered:1"]),
    ("股票分析", "金融", "每日股票分析与行情服务（analyzer + server）",
     ["stock"], ["daily-stock-analysis:analyzer:1", "daily-stock-analysis:server:1"]),
    ("n8n 工作流", "工具", "n8n 自动化工作流引擎",
     ["automation"], ["n8n:n8n:1"]),
    ("FreshRSS", "内容", "RSS 订阅聚合服务",
     ["rss"], ["freshrss:freshrss:1"]),
    ("SearXNG", "工具", "私有搜索引擎聚合器",
     ["search"], ["searxng:searxng:1"]),
    ("音乐助手", "生活", "Music Assistant 媒体播放服务",
     ["media"], ["music-assistant:music-assistant:1"]),
    ("小音乐", "生活", "自建音乐服务",
     ["media"], ["xiaomusic:xiaomusic:1"]),
    ("语音转写", "工具", "Whisper 语音转写服务",
     ["ai"], ["duomi-voice:whisper:1"]),
    ("闲鱼监控", "工具", "AI 闲鱼捡漏监控",
     ["monitor"], ["ai-goofish-monitor:app:1"]),
    ("文件系统服务", "工具", "file-system-go 文件访问服务",
     ["tool"], ["file-system-go:file-system-go:1"]),
    ("Nginx 反代", "工具", "全站唯一 TLS 入口，统一反代各服务",
     ["infra", "gateway"], ["nginx:nginx:1"]),
    ("DDNS 动态域名", "工具", "阿里云 DNS 动态解析，维护 *.duomi77.cn 记录",
     ["infra", "dns"], ["nas:container:a7944ce50a2d"]),
    ("音乐工作站", "媒体", "songloft 自建音乐工作站",
     ["media"], ["nas:container:92bca0e7d07c"]),
]

# 不进台账的候选：一次性任务、构建工具、僵尸容器、其它项目的附属容器
IGNORE_REASONS: list[tuple[str, str]] = [
    ("nas:compose:personal-web:economic-frontend:1", "别的 compose 项目的孤儿容器（created 未运行）"),
    ("nas:compose:personal-web:hermes-trigger-image:1", "一次性任务镜像容器（build-only）"),
    ("nas:container:1699896bcd9f", "caddy 僵尸容器：cmd=sleep infinity，从未真正启动"),
    ("nas:container:1b48829b50d7", "buildx 构建工具容器，不是对外服务"),
    ("nas:container:430e057a3eb7", "n8n 的附属 webhook 容器，已归入 n8n 工作流"),
    ("nas:container:6112984eeeb6", "一次性任务容器（exited）"),
    ("nas:container:b19ce0434af2", "一次性 git-pull 任务容器（exited）"),
    ("nas:container:78bd3ebba172", "一次性 git-pull 任务容器（exited）"),
    ("nas:container:8a9881f08348", "一次性 git-pull 任务容器（exited）"),
    ("nas:container:2283289e6bdc", "一次性 git-pull 任务容器（exited）"),
    ("nas:container:4280ecc71714", "一次性 git-pull 任务容器（exited）"),
]


def key(suffix: str) -> str:
    """把分组里的短标识还原成完整 source_key。"""
    if suffix.startswith("nas:container:"):
        return suffix
    if suffix.startswith("n8n:") or suffix.startswith("freshrss:") or suffix.startswith("searxng:") \
            or suffix.startswith("music-assistant:") or suffix.startswith("xiaomusic:") \
            or suffix.startswith("duomi-voice:") or suffix.startswith("ai-goofish-monitor:") \
            or suffix.startswith("file-system-go:") or suffix.startswith("nginx:") \
            or suffix.startswith("immich:") or suffix.startswith("homeassistant:") \
            or suffix.startswith("daily-stock-analysis:"):
        return "nas:compose:" + suffix
    return PERSONAL + suffix


COOKIE = ""


def call(path: str, method: str = "GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Origin": ORIGIN}
    if COOKIE:
        headers["Cookie"] = COOKIE
    req = urllib.request.Request(f"{BASE}/api/services{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, context=CTX) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def login(password: str) -> None:
    global COOKIE
    req = urllib.request.Request(
        f"{BASE}/api/services/auth/login",
        data=json.dumps({"password": password}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
    )
    with urllib.request.urlopen(req, context=CTX) as resp:
        if resp.status != 200:
            raise SystemExit("登录失败")
        COOKIE = resp.headers.get("Set-Cookie", "").split(";")[0]
        if not COOKIE:
            raise SystemExit("登录未拿到 cookie")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    password = args.password
    if not password:
        print("需要 --password（管理口令）", file=sys.stderr)
        return 2

    login(password)
    _, existing = call("/services?page_size=100")
    have = {item["name"] for item in existing["items"]}

    created, skipped, failed = 0, 0, []
    for name, category, desc, tags, suffixes in GROUPS:
        if name in have:
            print(f"  跳过（已存在）: {name}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  [dry-run] 将创建: {name} ← {[key(s) for s in suffixes]}")
            created += 1
            continue
        status, body = call(
            "/discovery/import",
            "POST",
            {
                "components": [
                    {"source_key": key(s), "required": True} for s in suffixes
                ],
                "name": name,
                "description": desc,
                "category": category,
                "tags": tags,
            },
        )
        if status == 200:
            print(f"  ✓ {name}（{len(suffixes)} 组件）")
            created += 1
        else:
            print(f"  ✗ {name}: HTTP {status} {body}")
            failed.append((name, status, body))

    if not args.dry_run:
        for source_key, reason in IGNORE_REASONS:
            status, body = call(
                "/discovery/decisions", "PATCH",
                {"source_keys": [source_key], "ignored": True},
            )
            mark = "✓" if status == 200 else "✗"
            print(f"  {mark} 忽略 {source_key.split(':')[-1]}（{reason}）")
            if status != 200:
                failed.append((source_key, status, body))

    print(f"\n完成：新建 {created}，跳过 {skipped}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
