#!/usr/bin/env bash
# NAS 上 `sh` 是 dash 的别名，dash 不支持 set -o pipefail；
# 如果被 dash 调用，自动 reexec 到 bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

# =============================================================================
# NAS 部署脚本（Ubuntu Server + docker-compose.nas.yml）
# 完整帮助: ./scripts/deploy-nas.sh --help
# =============================================================================

set -euo pipefail

# 切到 repo root（脚本位于 <root>/scripts/）— docker compose -f 用相对路径必须在此目录
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.nas.yml"
BUILDX_BUILDER="nas-builder"

show_help() {
    cat <<'EOF'
NAS 部署脚本（Ubuntu Server + docker-compose.nas.yml）

用法:
  ./scripts/deploy-nas.sh <target> [side] [options]

target:
  dividend | douyin | rss-relay | all

side:（默认 both）
  backend | frontend | both

options:
  --no-pull     跳过 git pull + submodule update
  --cold        强制冷构建（全部加 --no-cache；默认热构建）
  --no-buildx   前端也退回 docker compose build（默认 frontend 走 buildx）
  --tail        部署完后 tail 日志（默认关）
  -h, --help    显示本帮助

构建行为（两个正交开关）:
  (默认)              frontend → buildx 热构建；backend → compose 热构建
  --cold              同上路径，但全部 --no-cache
  --no-buildx         frontend/backend 都走 compose 热构建
  --cold --no-buildx  全部 compose --no-cache

示例:
  ./scripts/deploy-nas.sh dividend backend
  ./scripts/deploy-nas.sh dividend frontend
  ./scripts/deploy-nas.sh dividend both
  ./scripts/deploy-nas.sh douyin both
  ./scripts/deploy-nas.sh rss-relay both
  ./scripts/deploy-nas.sh all
  ./scripts/deploy-nas.sh dividend frontend --no-pull
  ./scripts/deploy-nas.sh dividend frontend --cold
  ./scripts/deploy-nas.sh dividend frontend --no-buildx
EOF
}

# ---- 参数解析 ----
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    show_help
    exit 0
fi

if [[ -z "${1:-}" ]]; then
    show_help
    exit 1
fi

TARGET="$1"
shift

# side 可省略；若写成 flag（如 ./deploy-nas.sh dividend --cold），当作 both
if [[ "${1:-}" == backend || "${1:-}" == frontend || "${1:-}" == both ]]; then
    SIDE="$1"
    shift
else
    SIDE="both"
fi

DO_PULL=true
COLD=false        # --cold：强制冷构建
USE_BUILDX=true   # 默认 frontend 走 buildx；--no-buildx 关闭
DO_TAIL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull)    DO_PULL=false;    shift ;;
        --cold)       COLD=true;        shift ;;
        --no-buildx)  USE_BUILDX=false; shift ;;
        --tail)       DO_TAIL=true;     shift ;;
        -h|--help)
            show_help
            exit 0
            ;;
        # 旧 flag 兼容提示（已废弃）
        --no-cache|--no-cache=false|--no-cache-buildx)
            echo "错误: '$1' 已废弃。" >&2
            echo "  热构建是默认行为；强制冷构建用 --cold；关闭 buildx 用 --no-buildx。" >&2
            echo "  查看帮助: $0 --help" >&2
            exit 1
            ;;
        *)
            echo "未知参数: $1" >&2
            echo "查看帮助: $0 --help" >&2
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

# ---- frontend buildx context 映射 ----
# USE_BUILDX=true 时前端走 docker buildx，pnpm install 走 Dockerfile cache mount 复用
get_buildx_config() {
    local svc="$1"
    case "$svc" in
        dividend-frontend)  echo "apps/dividend:apps/dividend/Dockerfile:dividend-frontend" ;;
        douyin-frontend)    echo "apps/douyin:apps/douyin/Dockerfile:douyin-frontend" ;;
        rss-relay-frontend) echo "apps/rss-relay:apps/rss-relay/Dockerfile:rss-relay-frontend" ;;
        *) return 1 ;;
    esac
}

# ---- 确保 buildx builder 存在（docker-container driver → 持久 cache volume） ----
ensure_buildx_builder() {
    local builder_name="${1:-$BUILDX_BUILDER}"
    if docker buildx inspect "$builder_name" >/dev/null 2>&1; then
        return 0
    fi
    echo ""
    echo "==> 首次跑，自动创建 buildx builder '$builder_name'（持久 cache volume）"
    docker buildx create --name "$builder_name" --driver docker-container --bootstrap >/dev/null
    echo "    已创建 '$builder_name'（cache 跨构建保留）"
}

compose_build() {
    local svc="$1"
    local args=()
    if $COLD; then
        args+=(--no-cache)
    fi
    docker compose -f "$COMPOSE_FILE" build "$svc" "${args[@]}"
}

buildx_build_frontend() {
    local svc="$1"
    local cfg ctx df tag
    cfg=$(get_buildx_config "$svc")
    ctx=$(echo "$cfg" | cut -d: -f1)
    df=$(echo  "$cfg" | cut -d: -f2)
    tag=$(echo "$cfg" | cut -d: -f3)

    local args=(
        --builder "$BUILDX_BUILDER"
        --tag "${tag}:latest"
        --load
        -f "$df"
    )
    if $COLD; then
        args+=(--no-cache)
    fi
    docker buildx build "${args[@]}" "$ctx"
}

SERVICES=$(get_services "$TARGET" "$SIDE")
echo "============================================================"
echo "部署目标: $SERVICES"
echo "  pull:      $DO_PULL"
echo "  cold:      $COLD"
echo "  buildx:    $USE_BUILDX"
echo "  tail:      $DO_TAIL"
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
if $USE_BUILDX; then
    ensure_buildx_builder "$BUILDX_BUILDER"
    if $COLD; then
        echo "==> [3/4] build（buildx frontend + compose backend，--cold）"
    else
        echo "==> [3/4] build（buildx frontend + compose backend，热构建）"
    fi
    for svc in $SERVICES; do
        if get_buildx_config "$svc" >/dev/null; then
            echo "  --- buildx build $svc ---"
            buildx_build_frontend "$svc"
        else
            echo "  --- compose build $svc ---"
            compose_build "$svc"
        fi
    done
else
    if $COLD; then
        echo "==> [3/4] docker compose build（--cold）"
    else
        echo "==> [3/4] docker compose build（热构建）"
    fi
    for svc in $SERVICES; do
        echo "  --- compose build $svc ---"
        compose_build "$svc"
    done
fi

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
