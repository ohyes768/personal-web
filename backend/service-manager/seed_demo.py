"""一次性本地演示数据注入（评审用，不提交）。

覆盖状态维度：running/healthy、stopped、partial、unhealthy、
TLS 过期、未读 Release（版本 当前→最新）、未入账容器、游离宽限期内容器、
数据源不可用（docker_last_error）。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from src.db import Store

DB = "data/service-manager.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def new_id() -> str:
    return str(uuid.uuid4())


def mount(src, dst, ro=False):
    return {"kind": "bind", "source": src, "destination": dst, "read_only": ro}


def comp_row(
    source_key, project, service_name, name, image, version, state, health,
    ports, mounts, last_seen,
):
    if service_name is None:
        working_dir = None
        compose_files = []
    else:
        working_dir = f"/srv/docker/{service_name}"
        compose_files = [
            {"raw": "docker-compose.yml",
             "resolved": f"/srv/docker/{service_name}/docker-compose.yml",
             "path_state": "relative_resolved"}
        ]
    return (
        source_key, project, service_name, new_id(), name, image, "", version,
        state, health, "bridge",
        json.dumps(ports), json.dumps(mounts),
        working_dir, json.dumps(compose_files),
        0, last_seen, last_seen, 1,
    )


def check_row(target_type, target_id, kind, status, state, last_attempt, last_success, error,
              payload=None):
    return (
        target_type, target_id, kind, status, state, last_attempt, last_success,
        json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        *([None, error] if error else [None, None]),
    )


def in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def main() -> None:
    Store(DB).initialize()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # 数据源不可用（本机无 Docker Desktop）
    conn.execute(
        "INSERT OR REPLACE INTO runtime_state(key,value) VALUES('docker_last_error', ?)",
        (
            "error during connect: Get \"http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine"
            "/v1.48/version\": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.",
        ),
    )

    # ---------------- services ----------------
    specs = [
        ("nginx 反代", "全站统一入口：basic auth + 路由分发", ["核心", "入口"],
         "挂了所有服务都不可达，最高优先级。"),
        ("dividend 股息率", "A 股高股息分析前后端", ["个人", "股息"], ""),
        ("task-web 定时任务", "预登记任务调度与执行记录", ["个人", "自动化"],
         "后端 + 前端两个组件，前端 depends_on 后端健康检查。"),
        ("housing-map 购房地图", "滨江区楼盘与房价数据", ["个人"], ""),
        ("rss-relay 转发", "RSS 聚合转发", ["对外"],
         "证书到期一直没续，TLS 维度应显示红色。"),
        ("index-trends 宽基趋势", "沪深300 周线通道与估值", ["个人", "指数"],
         "源码仓库已配，最新 release v2.3.0 未读。"),
    ]
    sids: dict[str, str] = {}
    for name, desc, tags, notes in specs:
        sid = new_id()
        sids[name] = sid
        conn.execute(
            "INSERT INTO services(id,name,description,tags,notes,revision,created_at,updated_at)"
            " VALUES (?,?,?,?,?,1,?,?)",
            (sid, name, desc, json.dumps(tags, ensure_ascii=False), notes,
             ago(86400 * 30), ago(3600)),
        )

    # ---------------- docker_components（上次扫描观测） ----------------
    H = ago(0)
    components = [
        comp_row("nas:compose:nginx:web:1", "nginx", "web", "nginx-web",
                 "nginx:1.27-alpine", "1.27.0", "running", "healthy",
                 [{"host_ip": "0.0.0.0", "host_port": 80, "container_port": 80, "protocol": "tcp"}],
                 [mount("/var/run/docker.sock", "/var/run/docker.sock", ro=True)], H),
        comp_row("nas:compose:dividend:api:1", "dividend", "api", "dividend-api",
                 "personal/dividend-select:2026.11.2", "2026.11.2", "running", "not_configured",
                 [], [mount("/data/dividend", "/data")], H),
        comp_row("nas:compose:dividend:web:1", "dividend", "web", "dividend-web",
                 "personal/dividend-web:2026.11.2", "", "exited", "not_configured",
                 [], [], H),
        comp_row("nas:compose:task-web:api:1", "task-web", "api", "task-web-api",
                 "personal/task-web-api:1.4.1", "1.4.1", "running", "healthy",
                 [], [mount("/data/task-web", "/data")], H),
        comp_row("nas:compose:task-web:web:1", "task-web", "web", "task-web-web",
                 "personal/task-web-web:1.4.1", "", "running", "not_configured",
                 [], [], H),
        comp_row("nas:compose:housing-map:api:1", "housing-map", "api", "housing-map-api",
                 "personal/housing-map:0.9.7", "0.9.7", "running", "unhealthy",
                 [], [mount("/data/housing-map", "/data")], H),
        comp_row("nas:compose:rss-relay:relay:1", "rss-relay", "relay", "rss-relay",
                 "personal/rss-relay:1.0.3", "1.0.3", "running", "healthy",
                 [], [], H),
        comp_row("nas:container:8f3a2b1c9d4e", None, None, "temp-migrate-2026-11-24",
                 "postgres:16-alpine", "16.3", "running", "healthy",
                 [], [mount("/var/lib/postgresql", "/var/lib/postgresql")], ago(2 * 86400)),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO docker_components(source_key,project,service_name,"
        "container_id,container_name,image_ref,image_id,image_version,state,health,"
        "network_mode,ports,mounts,compose_working_dir,compose_files,oneoff,last_seen_at,"
        "first_seen_at,scan_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        components,
    )

    # ---------------- 绑定（source_key → 服务） ----------------
    bindings = [
        (sids["nginx 反代"], "nas:compose:nginx:web:1", "nginx"),
        (sids["dividend 股息率"], "nas:compose:dividend:api:1", "api"),
        (sids["dividend 股息率"], "nas:compose:dividend:web:1", "web"),
        (sids["task-web 定时任务"], "nas:compose:task-web:api:1", "api"),
        (sids["task-web 定时任务"], "nas:compose:task-web:web:1", "web"),
        (sids["housing-map 购房地图"], "nas:compose:housing-map:api:1", "api"),
        (sids["rss-relay 转发"], "nas:compose:rss-relay:relay:1", "relay"),
    ]
    for service_id, source_key, label in bindings:
        conn.execute(
            "INSERT INTO service_components(id,service_id,source_key,required,label,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (new_id(), service_id, source_key, 1, label, ago(86400 * 20)),
        )

    # ---------------- endpoints + 检查 ----------------
    endpoints = [
        ("nas-nginx.example", sids["nginx 反代"], "主入口", "external",
         "https://192.168.1.10/", None, None),
        ("dividend-internal", sids["dividend 股息率"], "管理面板", "external",
         "http://192.168.1.10:3003/dividend", None, None),
        ("housing-map", sids["housing-map 购房地图"], "主入口", "external",
         "https://map.192.168.1.10.nip.io/map", None, None),
        ("rss-relay", sids["rss-relay 转发"], "外部订阅入口", "external",
         "https://rss.example.com/", None, None),
        ("task-web-admin", sids["task-web 定时任务"], "管理入口", "external",
         "https://admin.192.168.1.10.nip.io/", None, None),
    ]
    ep_ids: dict[str, str] = {}
    for name, service_id, label, kind, url, probe, range_spec in endpoints:
        eid = new_id()
        ep_ids[name] = eid
        conn.execute(
            "INSERT INTO endpoints(id,service_id,label,kind,url,probe_url,enabled,"
            "expected_status_ranges,tls_check,route_target,renewal_note,revision,"
            "created_at,updated_at) VALUES (?,?,?,?,?,NULL,1,?,?,NULL,?,1,?,?)",
            (eid, service_id, label, kind, url,
             json.dumps(range_spec or ["200"]), 1 if url.startswith("https") else 0,
             "到期 2026-12-20" if name == "rss-relay" else "",
             now(), now()),
        )

    checks = [
        # url 检查：nginx reachable, dividend unreachable（端口被占用了还没修）,
        # housing-map reachable, rss reachable
        check_row("endpoint", ep_ids["nas-nginx.example"], "url", "success", "reachable", ago(120), ago(120), None),
        check_row("endpoint", ep_ids["dividend-internal"], "url", "error", "unreachable", ago(95), ago(86400 * 3),
                  "connect ECONNREFUSED 192.168.1.10:3003"),
        check_row("endpoint", ep_ids["housing-map"], "url", "success", "reachable", ago(200), ago(200), None),
        check_row("endpoint", ep_ids["rss-relay"], "url", "success", "reachable", ago(150), ago(150), None),
        # TLS：全档位演示。valid/expiring/expired 带 payload（天数 + 到期日）；
        # task-web-admin 指向不可达主机 → 检查失败（有 error，无 payload）；
        # dividend 是 http 入口 → 不查证书（前端显示「-」）。
        check_row("endpoint", ep_ids["nas-nginx.example"], "tls", "success", "valid",
                  ago(120), ago(120), None,
                  {"not_after": in_days(38), "days_remaining": 38}),
        check_row("endpoint", ep_ids["housing-map"], "tls", "success", "expiring",
                  ago(200), ago(200), None,
                  {"not_after": in_days(12), "days_remaining": 12}),
        check_row("endpoint", ep_ids["rss-relay"], "tls", "success", "expired",
                  ago(150), ago(86400 * 48), None,
                  {"not_after": in_days(-47), "days_remaining": -47}),
        check_row("endpoint", ep_ids["task-web-admin"], "tls", "error", "unknown",
                  ago(90), None, "TLS 握手失败: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF"),
        # releases：index-trends unread 2
        check_row("service", sids["index-trends 宽基趋势"], "releases", "success", "unread", ago(300), ago(300), None),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO check_results(target_type,target_id,check_kind,"
        "check_status,current_state,last_attempt_at,last_success_at,last_success_payload,"
        "error_code,error_message,next_due_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(*row, now()) for row in checks],
    )

    # ---------------- release_sources + releases（index-trends） ----------------
    rs_id = new_id()
    conn.execute(
        "INSERT INTO release_sources(id,service_id,owner,repo,installed_tag_note,"
        "revision,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)",
        (rs_id, sids["index-trends 宽基趋势"], "ranxianglei", "personal-web", "v2.1.0",
         ago(86400 * 10), ago(300)),
    )
    releases = [
        (118, "v2.3.0", "v2.3.0 宽基趋势观察", ago(3600 * 5), None),
        (117, "v2.2.0", "v2.2.0", ago(86400 * 12), None),
    ]
    for rid, tag, rname, pub, _ in releases:
        conn.execute(
            "INSERT OR REPLACE INTO releases(owner,repo,release_id,tag,name,"
            "published_at,updated_at,body,html_url,prerelease) VALUES (?,?,?,?,?,?,?,?,?,0)",
            ("ranxianglei", "personal-web", rid, tag, rname, pub, pub,
             "changelog", f"https://github.com/ranxianglei/personal-web/releases/tag/{tag}"),
        )
    # 只把 v2.2.0 标记已读 → v2.3.0 未读
    conn.execute(
        "INSERT OR REPLACE INTO release_reads(release_source_id,release_id,read_at)"
        " VALUES (?,?,?)",
        (rs_id, 117, ago(86400 * 8)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO release_sync(owner,repo,etag,latest_release_id,"
        "truncated,baseline_done,last_checked_at,state,error) VALUES (?,?,?,?,?,?,?,?,?)",
        ("ranxianglei", "personal-web", "W/\"demo\"", 118, 0, 1, ago(300), "success", None),
    )

    # ---------------- 未入账：temp-migrate 容器未绑定 ----------------
    # nas:container:8f3a2b1c9d4e 已观测、未绑定 → 发现页「未入账」候选

    conn.commit()
    # 验证
    rows = conn.execute(
        "SELECT s.name, c.state, c.health, c.image_version FROM services s"
        " LEFT JOIN service_components b ON b.service_id=s.id"
        " LEFT JOIN docker_components c ON c.source_key=b.source_key").fetchall()
    for r in rows:
        print(f"{r['name']:<16} state={r['state']} health={r['health']} ver={r['image_version']}")
    print("components observed:", len(components),
          "| endpoints:", len(endpoints), "| checks:", len(checks))
    print("dividend-web should be exited (partial 运行档)")
    conn.close()


if __name__ == "__main__":
    main()
