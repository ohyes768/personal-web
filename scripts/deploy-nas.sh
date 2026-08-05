#!/usr/bin/env bash
# NAS 上 `sh` 是 dash 的别名，dash 不支持 set -o pipefail；
# 如果被 dash 调用，自动 reexec 到 bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

# =============================================================================
# NAS 部署脚本（Ubuntu Server + docker-compose.nas.yml）
# =============================================================================
# 用法：
#   ./scripts/deploy-nas.sh dividend backend              # 只 dividend 后端
#   ./scripts/deploy-nas.sh dividend frontend             # 只 dividend 前端
#   ./scripts/deploy-nas.sh dividend both                 # dividend 前后端
#   ./scripts/deploy-nas.sh douyin both                   # douyin 前后端
#   ./scripts/deploy-nas.sh rss-relay both                # rss-relay 前后端
#   ./scripts/deploy-nas.sh all                           # 全部 6 个服务
#
# 可选参数：
#   --no-pull        跳过 git pull + submodule update
#   --no-cache=false 关闭 --no-cache（默认开）
#   --no-tail        部署完不 tail 日志（适合 cron 调用）
#
# 示例：
#   ./scripts/deploy-nas.sh dividend backend              # 拉最新 + 后端 build + restart + tail logs
#   ./scripts/deploy-nas.sh all --no-tail                 # 拉最新 + 全部 build + restart + 不 tail
#   ./scripts/deploy-nas.sh dividend frontend --no-pull   # 不 pull，直接 build + restart
# =============================================================================

set -euo pipefail

COMPOSE_FILE="docker-compose.nas.yml"

# ---- 参数解析 ----
TARGET="${1:-}"
SIDE="${2:-both}"

# 校验必填
if [[ -z "$TARGET" ]]; then
    echo "用法: $0 <target> <side> [options]"
    echo "  target: dividend | douyin | rss-relay | all"
    echo "  side:   backend | frontend | both (默认 both)"
    echo "  options: --no-pull | --no-cache=false | --no-tail"
    exit 1
fi

shift 2 2>/dev/null || true

DO_PULL=true
NO_CACHE=true
DO_TAIL=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull)        DO_PULL=false;    shift ;;
        --no-cache)       NO_CACHE=true;    shift ;;
        --no-cache=false) NO_CACHE=false;   shift ;;
        --no-tail)        DO_TAIL=false;    shift ;;
        -h|--help)
            grep '^#' "$0" | head -30
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

# ---- 服务映射 ----
get_services() {
    local target="$1" side="$2"
    case "$target" in
        dividend|douyin|rss-relay)
            case "$side" in
                backend)  echo "${target}-backend" ;;
                frontend) echo "${target}-frontend" ;;
                both)     echo "${target}-backend ${target}-frontend" ;;
                *)
                    echo "错误: side 必须是 backend | frontend | both，实际 '$side'" >&2
                    exit 1
                    ;;
            esac
            ;;
        all)
            if [[ "$side" != "both" ]]; then
                echo "提示: target=all 时 side 强制 both（忽略 '$side'）" >&2
            fi
            echo "dividend-backend dividend-frontend douyin-backend douyin-frontend rss-relay-backend rss-relay-frontend"
            ;;
        *)
            echo "错误: target 必须是 dividend | douyin | rss-relay | all，实际 '$target'" >&2
            exit 1
            ;;
    esac
}

SERVICES=$(get_services "$TARGET" "$SIDE")
echo "============================================================"
echo "部署目标: $SERVICES"
echo "  pull:    $DO_PULL"
echo "  no-cache: $NO_CACHE"
echo "  tail:    $DO_TAIL"
echo "============================================================"

# ---- Step 1: git pull + submodule update ----
if $DO_PULL; then
    echo ""
    echo "==> [1/4] git pull"
    git pull

    echo ""
    echo "==> [2/4] git submodule update --remote --merge"
    # --remote: 拉子模块远端最新 commit（默认是 superproject 锁定的 gitlink）
    # --merge:  fast-forward merge 子模块 master 到本地（不 detach HEAD）
    git submodule update --remote --merge
fi

# ---- Step 2: build ----
echo ""
echo "==> [3/4] docker compose build"
BUILD_ARGS=()
if $NO_CACHE; then
    BUILD_ARGS+=(--no-cache)
fi
for svc in $SERVICES; do
    echo "  --- build $svc ---"
    docker compose -f "$COMPOSE_FILE" build "$svc" "${BUILD_ARGS[@]}"
done

# ---- Step 3: restart ----
echo ""
echo "==> [4/4] docker compose up -d --force-recreate"
docker compose -f "$COMPOSE_FILE" up -d --force-recreate $SERVICES

# ---- 验证状态 ----
echo ""
echo "============================================================"
echo "部署完成。当前容器状态："
echo "============================================================"
docker compose -f "$COMPOSE_FILE" ps $SERVICES

# ---- tail logs ----
if $DO_TAIL; then
    echo ""
    echo "============================================================"
    echo "tail logs（Ctrl+C 退出，不会停止容器）："
    echo "============================================================"
    docker compose -f "$COMPOSE_FILE" logs -f --tail 50 $SERVICES
fi
