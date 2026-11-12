#!/usr/bin/env python3
"""按实测结果批量登记 service-manager 的访问入口。

入口来源是 nginx 的反代配置 + 容器实际端口，每条都先从管理台后端容器里
实测过可达（curl 返回码非 000），再写进台账。

用法：python3 scripts/fill-service-endpoints.py --password <口令> [--dry-run]
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

PW = "personal-web"

# 服务名 → (入口 URL, 入口类型, 备注)
# kind: external=公网域名入口；internal=仅内网可达
ENDPOINTS: list[tuple[str, str, str, str]] = [
    ("股息率分析", "https://web.duomi77.cn:9443/dividend", "external", "首页卡片入口"),
    ("抖音文字稿", "https://web.duomi77.cn:9443/douyin", "external", "首页卡片入口"),
    ("宏观经济", "https://web.duomi77.cn:9443/macro", "external", "首页卡片入口"),
    ("基金筛选", "https://web.duomi77.cn:9443/funds", "external", "首页卡片入口"),
    ("房产信息地图", "https://web.duomi77.cn:9443/map", "external", "首页卡片入口"),
    ("哆咪故事库", "https://web.duomi77.cn:9443/kids", "external", "首页卡片入口"),
    ("RSS中转服务", "https://web.duomi77.cn:9443/rss", "external", "首页卡片入口"),
    ("Skill管理台", "https://web.duomi77.cn:9443/skills", "external", "首页卡片入口"),
    ("宽基趋势观察", "https://web.duomi77.cn:9443/index-trends", "external", "首页卡片入口"),
    ("定时任务管理", "https://web.duomi77.cn:9443/tasks", "external", "首页卡片入口"),
    ("服务管理台", "https://web.duomi77.cn:9443/services", "external", "首页卡片入口"),
    ("FreshRSS", "https://rss.duomi77.cn:10443/", "external", "独立反代端口 10443"),
    ("小音乐", "https://xiaomusic.duomi77.cn:6443/", "external", "独立反代端口 6443"),
    ("相册 immich", "http://192.168.31.73:2283/", "internal", "直连容器发布端口；nginx 7443 需走容器名"),
    ("音乐工作站", "http://192.168.31.73:4000/", "internal", "直连容器发布端口；music.duomi77.cn:2443 的反代指向旧 IP 已失效"),
    ("智能家居", "http://192.168.31.73:8123/", "internal", "Home Assistant 直连；nginx 5443 未发布端口"),
    ("股票分析", "http://192.168.31.73:58080/", "internal", "行情服务直连；nginx 3443 亦可"),
    ("DDNS 动态域名", "http://192.168.31.73:9876/", "internal", "ddns-go 管理界面，直连端口"),
    ("闲鱼监控", "http://192.168.31.73:8010/", "internal", "直连容器发布端口"),
]

# 这些服务实测没有任何外部可达入口，只能人工登记
NO_ENDPOINT: list[tuple[str, str]] = [
    ("SearXNG", "只监听 127.0.0.1:8888，容器外无法访问"),
    ("语音转写", "只监听 127.0.0.1:10300，容器外无法访问"),
    ("音乐助手", "host 网络容器，8093 未监听"),
    ("n8n 工作流", "容器已退出（exited），4443 返回 400"),
]

COOKIE = ""


def call(path: str, method: str = "GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Origin": ORIGIN}
    if COOKIE:
        headers["Cookie"] = COOKIE
    req = urllib.request.Request(
        f"{BASE}/api/services{path}", data=data, method=method, headers=headers
    )
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
        COOKIE = resp.headers.get("Set-Cookie", "").split(";")[0]
        if not COOKIE:
            raise SystemExit("登录未拿到 cookie")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    if not args.password:
        print("需要 --password（管理口令）", file=sys.stderr)
        return 2

    login(args.password)
    _, listing = call("/services?page_size=100")
    ids = {item["name"]: item["id"] for item in listing["items"]}

    ok, skipped, failed = 0, 0, []
    for name, url, kind, note in ENDPOINTS:
        service_id = ids.get(name)
        if not service_id:
            print(f"  ✗ 找不到服务：{name}")
            failed.append(name)
            continue
        # 已有同名入口就跳过
        # 路径说明：call() 已经拼了 "/api/services"，这里传的是"对外路径去掉
        # /api/services 之后"的部分。nginx 会再剥一层前缀，所以对外的详情路径是
        # /api/services/services/{id} → 后端 /api/services/{id}。
        _, detail = call(f"/services/{service_id}")
        if any(e["url"] == url for e in detail.get("endpoints", [])):
            print(f"  跳过（已有该入口）: {name}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  [dry-run] {name} ← {url}")
            ok += 1
            continue
        status, body = call(
            f"/services/{service_id}/endpoints",
            "POST",
            {
                "label": note,
                "kind": kind,
                "url": url,
                "enabled": True,
                "tls_check": url.startswith("https://"),
                "expected_status_ranges": [],
                "renewal_note": "",
            },
        )
        if status == 201:
            print(f"  ✓ {name} ← {url}")
            ok += 1
        else:
            print(f"  ✗ {name}: HTTP {status} {body}")
            failed.append(name)

    print("\n未登记入口（无外部可达地址，需人工处理）：")
    for name, reason in NO_ENDPOINT:
        print(f"  - {name}：{reason}")

    print(f"\n完成：登记 {ok}，跳过 {skipped}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
