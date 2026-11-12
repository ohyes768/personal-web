#!/usr/bin/env bash
# =============================================================================
# Let's Encrypt 通配符证书（*.duomi77.cn）签发与续期
#
# 用法:
#   ./scripts/setup-ssl-cert.sh install     首次安装 acme.sh（已装则跳过）
#   ./scripts/setup-ssl-cert.sh issue       签发证书并装到 nginx 目录
#   ./scripts/setup-ssl-cert.sh renew       手动续期（平时由 cron 自动跑）
#   ./scripts/setup-ssl-cert.sh status      看当前证书状态与下次续期时间
#   ./scripts/setup-ssl-cert.sh keys        从 ddns-go 读取阿里云 Key 并导出（eval 用）
#
# 依赖：阿里云 DNS 权限的 AccessKey（阿里云 RAM 控制台创建，只要 AliyunDNSFullAccess）。
# 默认直接复用 ddns-go 里已在用的那把（它本来就在做 alidns 解析更新）；
# 想用独立密钥就自己 export Ali_Key / Ali_Secret 再跑 issue。
#
# 为什么用 DNS-01 而不是 HTTP-01：通配符证书只能用 DNS 验证；
# 而且不用对外开 80 端口，内网 NAS 也能签。
# =============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

ACME_HOME="${ACME_HOME:-$HOME/.acme.sh}"
ACME="$ACME_HOME/acme.sh"
DOMAIN="duomi77.cn"
WILDCARD="*.duomi77.cn"
# nginx 容器把宿主机 ~/nginx/ssl 挂成 /etc/nginx/ssl，所以证书放这里
SSL_DIR="${SSL_DIR:-$HOME/nginx/ssl}"
NGINX_CONTAINER="${NGINX_CONTAINER:-nginx}"
DDNS_CONTAINER="${DDNS_CONTAINER:-ddns-go}"
RELOAD_CMD="docker exec $NGINX_CONTAINER nginx -s reload"
# raw.githubusercontent.com 在国内经常超时，优先走本机代理（mihomo 7890）
PROXY="${PROXY:-http://127.0.0.1:7890}"

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\n[错误] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- install
cmd_install() {
    if [ -x "$ACME" ]; then
        log "acme.sh 已安装：$($ACME --version 2>/dev/null | tail -1)"
        return 0
    fi

    log "安装 acme.sh 到 $ACME_HOME"
    # 官方 one-liner 会再下一次 raw.githubusercontent，国内常卡住；
    # 先自己把 acme.sh 取下来，在它所在目录执行 --install。
    local tmp
    tmp="$(mktemp -d)"
    _fetch "https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh" \
        "$tmp/acme.sh" || die "下载 acme.sh 失败"
    (cd "$tmp" && sh acme.sh --install --home "$ACME_HOME" >/dev/null)
    rm -rf "$tmp"
    [ -x "$ACME" ] || die "安装后仍找不到 $ACME"
    log "已安装：$($ACME --version 2>/dev/null | tail -1)"

    log "切换默认 CA 为 Let's Encrypt"
    # acme.sh 3.x 默认走 ZeroSSL，需要额外注册（要邮箱 + EAB），不如 LE 干净
    "$ACME" --set-default-ca --server letsencrypt >/dev/null
    echo "    默认 CA: $("$ACME" --info 2>/dev/null | grep -o 'https://[^ ]*letsencrypt[^ ]*' | head -1 || echo letsencrypt)"
}

# ---------------------------------------------------------------- issue
cmd_issue() {
    [ -x "$ACME" ] || die "先跑：$0 install"

    _ensure_dns_plugin
    _load_aliyun_keys

    log "签发 $WILDCARD（DNS-01 / dns_ali）"
    "$ACME" --issue --dns dns_ali -d "$WILDCARD" -d "$DOMAIN" --keylength ec-256

    _install_cert
}

# ---------------------------------------------------------------- renew
cmd_renew() {
    [ -x "$ACME" ] || die "acme.sh 未安装"
    log "手动续期（平时由 cron 每小时检查一次）"
    "$ACME" --renew -d "$WILDCARD" --ecc --force
    _install_cert
}

# ---------------------------------------------------------------- status
cmd_status() {
    local crt="$SSL_DIR/le.crt"
    [ -f "$crt" ] || die "还没有证书：$crt（先跑 $0 issue）"

    log "证书文件"
    openssl x509 -in "$crt" -noout -subject -issuer -dates

    log "到期与续期"
    local not_after days
    not_after=$(openssl x509 -in "$crt" -noout -enddate | cut -d= -f2)
    if date --version >/dev/null 2>&1; then
        days=$(( ($(date -d "$not_after" +%s) - $(date +%s)) / 86400 ))
    else
        days=$(( ($(date -j -f "%b %d %T %Y %Z" "$not_after" +%s) - $(date +%s)) / 86400 ))
    fi
    echo "    剩余 $days 天"
    grep -hE "Le_NextRenewTimeStr" "$ACME_HOME/$WILDCARD"_ecc/*.conf 2>/dev/null \
        | sed 's/^/    /' || echo "    （未找到续期计划）"

    log "线上实际提供的证书（对照是否已 reload）"
    timeout 12 openssl s_client -connect 127.0.0.1:9443 -servername "web.$DOMAIN" \
        </dev/null 2>/dev/null | openssl x509 -noout -serial -dates 2>/dev/null \
        | sed 's/^/    /' || echo "    连不上 9443"

    log "cron"
    crontab -l 2>/dev/null | grep -i acme | sed 's/^/    /' || echo "    （没有 cron 任务）"
}

# ---------------------------------------------------------------- keys
# 供 `eval "$(./scripts/setup-ssl-cert.sh keys)"` 使用
cmd_keys() {
    command -v docker >/dev/null || die "需要 docker"
    docker exec "$DDNS_CONTAINER" cat /root/.ddns_go_config.yaml 2>/dev/null \
        | python3 -c '
import sys, shlex
try:
    import yaml
except ImportError:
    sys.exit("需要 python3 的 yaml 模块（pip install pyyaml）")
d = yaml.safe_load(sys.stdin)
dns = d["dnsconf"][0]["dns"]
print("export Ali_Key=" + shlex.quote(dns["id"]))
print("export Ali_Secret=" + shlex.quote(dns["secret"]))
'
}

# ---------------------------------------------------------------- helpers
_install_cert() {
    log "安装到 $SSL_DIR 并挂 reload 钩子"
    mkdir -p "$SSL_DIR"
    "$ACME" --install-cert -d "$WILDCARD" --ecc \
        --key-file       "$SSL_DIR/le.key" \
        --fullchain-file "$SSL_DIR/le.crt" \
        --reloadcmd      "$RELOAD_CMD"

    chmod 644 "$SSL_DIR/le.crt"
    chmod 600 "$SSL_DIR/le.key"

    log "验证线上证书"
    local got
    got=$(timeout 12 openssl s_client -connect 127.0.0.1:9443 -servername "web.$DOMAIN" \
        </dev/null 2>/dev/null | grep -E "Verify return code" | head -1 || true)
    echo "    $got"
    case "$got" in
        *"0 (ok)"*) echo "    ✓ 证书链已被系统信任" ;;
        *) echo "    ✗ 仍未被信任，检查 nginx 配置是否指向 $SSL_DIR/le.crt" ;;
    esac
}

_load_aliyun_keys() {
    if [ -n "${Ali_Key:-}" ] && [ -n "${Ali_Secret:-}" ]; then
        log "使用环境变量里的阿里云 AccessKey（长度 ${#Ali_Key}/${#Ali_Secret}）"
        return 0
    fi
    log "从 $DDNS_CONTAINER 读取阿里云 AccessKey（复用它已有的 DNS 权限）"
    local out
    out=$(cmd_keys) || die "读取失败；也可以自己 export Ali_Key/Ali_Secret 再跑"
    eval "$out"
    [ -n "${Ali_Key:-}" ] || die "没读到 Ali_Key"
    echo "    已载入（长度 ${#Ali_Key}/${#Ali_Secret}）"
}

_ensure_dns_plugin() {
    local plugin="$ACME_HOME/dnsapi/dns_ali.sh"
    if [ -f "$plugin" ]; then
        return 0
    fi
    log "补装 dns_ali 插件（单文件安装不自带 dnsapi/）"
    mkdir -p "$ACME_HOME/dnsapi"
    _fetch "https://raw.githubusercontent.com/acmesh-official/acme.sh/master/dnsapi/dns_ali.sh" \
        "$plugin" || die "下载 dns_ali.sh 失败（可设 PROXY= 重试）"
    chmod +x "$plugin"
    echo "    已装：$plugin"
}

# 直连优先，失败再走代理
_fetch() {
    local url="$1" dest="$2"
    if timeout 90 curl -sSL --connect-timeout 20 -o "$dest" "$url" 2>/dev/null && [ -s "$dest" ]; then
        return 0
    fi
    if [ -n "$PROXY" ]; then
        echo "    直连失败，改用代理 $PROXY"
        timeout 90 curl -sSL -x "$PROXY" --connect-timeout 20 \
            -o "$dest" "$url" 2>/dev/null && [ -s "$dest" ]
        return $?
    fi
    return 1
}

# ---------------------------------------------------------------- main
case "${1:-}" in
    install) cmd_install ;;
    issue)   cmd_issue ;;
    renew)   cmd_renew ;;
    status)  cmd_status ;;
    keys)    cmd_keys ;;
    *)
        cat <<EOF
用法: $0 <命令>

  install   首次安装 acme.sh（已装则跳过），并把默认 CA 切到 Let's Encrypt
  issue     签发 $WILDCARD 通配符证书，装到 $SSL_DIR 并挂 nginx reload 钩子
  renew     手动强制续期（平时由 cron 每小时自动检查）
  status    当前证书、剩余天数、下次续期时间、线上实际证书、cron
  keys      打印阿里云 AccessKey 的 export 语句（eval 用）

环境变量：
  ACME_HOME         默认 \$HOME/.acme.sh
  SSL_DIR           默认 \$HOME/nginx/ssl（nginx 容器挂成 /etc/nginx/ssl）
  NGINX_CONTAINER   默认 nginx
  DDNS_CONTAINER    默认 ddns-go（从这里复用阿里云 Key）
  PROXY             默认 http://127.0.0.1:7890（GitHub 直连超时时用）

签完还要做一件事：把 nginx 各 conf 里的
  ssl_certificate /etc/nginx/ssl/server.crt  →  /etc/nginx/ssl/le.crt
  ssl_certificate_key /etc/nginx/ssl/server.key  →  /etc/nginx/ssl/le.key
然后重建 nginx 容器（不是 reload）：
  cd ~/nginx && docker compose up -d --force-recreate nginx
EOF
        exit 1
        ;;
esac
