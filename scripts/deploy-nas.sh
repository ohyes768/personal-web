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
#   --no-pull           跳过 git pull + submodule update
#   --no-cache=false    关闭 --no-cache（默认开）
#   --no-cache-buildx   关闭 buildx 持久 cache（默认开启 frontend 走 buildx）
#                       首次跑会自动 docker buildx create nas-builder --driver docker-container
#                       pnpm install 第二次起从 ~358s 降到 < 10s
#                       仅对 frontend 生效，backend 仍走 docker compose build
#   --tail              部署完后 tail 日志（默认关，需要时显式加）
#
# 示例：
#   ./scripts/deploy-nas.sh dividend backend              # 拉最新 + 后端 build + restart + tail logs
#   ./scripts/deploy-nas.sh all --no-tail                 # 拉最新 + 全部 build + restart + 不 tail
#   ./scripts/deploy-nas.sh dividend frontend --no-pull   # 不 pull，直接 build + restart
#   ./scripts/deploy-nas.sh dividend frontend --no-cache-buildx  # frontend 临时走 docker compose build
# =============================================================================

set -euo pipefail

# 切到 repo root（脚本位于 <root>/scripts/）— docker compose -f 用相对路径必须在此目录
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.nas.yml"

# ---- 参数解析 ----
TARGET="${1:-}"
SIDE="${2:-both}"

# 校验必填
if [[ -z "$TARGET" ]]; then
    echo "用法: $0 <target> <side> [options]"
    echo "  target: dividend | douyin | rss-relay | all"
    echo "  side:   backend | frontend | both (默认 both)"
    echo "  options: --no-pull | --no-cache=false | --no-cache-buildx | --no-tail"
    exit 1
fi

shift 2 2>/dev/null || true

DO_PULL=true
NO_CACHE=true
USE_CACHE=true    # 默认开启 buildx 持久 cache（frontend 加速）
DO_TAIL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull)          DO_PULL=false;    shift ;;
        --no-cache)         NO_CACHE=true;    shift ;;
        --no-cache=false)   NO_CACHE=false;   shift ;;
        --no-cache-buildx)  USE_CACHE=false;  shift ;;
        --tail)             DO_TAIL=true;     shift ;;
        -h|--help)
            grep '^#' "$0" | head -40
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

# ---- frontend buildx context 映射 ----
# USE_CACHE=true 时前端走 docker buildx 持久 cache，pnpm install 走 cache mount 复用
get_buildx_config() {
    local svc="$1"
    case "$svc" in
        dividend-frontend)  echo "apps/dividend:apps/dividend/Dockerfile:dividend-frontend" ;;
        douyin-frontend)    echo "apps/douyin:apps/douyin/Dockerfile:douyin-frontend" ;;
        rss-relay-frontend) echo "apps/rss-relay:apps/rss-relay/Dockerfile:rss-relay-frontend" ;;
        *) return 1 ;;
    esac
}

# ---- 确保 buildx builder 存在（持久 cache volume） ----
ensure_buildx_builder() {
    local builder_name="${1:-nas-builder}"
    if docker buildx inspect "$builder_name" >/dev/null 2>&1; then
        return 0
    fi
    echo ""
    echo "==> 首次跑，自动创建 buildx builder '$builder_name'（持久 cache volume）"
    docker buildx create --name "$builder_name" --driver docker-container --bootstrap >/dev/null
    echo "    已创建 '$builder_name'（cache 跨构建保留）"
}

SERVICES=$(get_services "$TARGET" "$SIDE")
echo "============================================================"
echo "部署目标: $SERVICES"
echo "  pull:          $DO_PULL"
echo "  no-cache:      $NO_CACHE"
echo "  use-cache(bx): $USE_CACHE"
echo "  tail:          $DO_TAIL"
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
if $USE_CACHE; then
    ensure_buildx_builder nas-builder
    echo "==> [3/4] docker buildx build (buildx cache frontend)"
    for svc in $SERVICES; do
        if cfg=$(get_buildx_config "$svc"); then
            ctx=$(echo "$cfg" | cut -d: -f1)
            df=$(echo  "$cfg" | cut -d: -f2)
            tag=$(echo "$cfg" | cut -d: -f3)
            cache_ref="nas-cache-${svc}"
            echo "  --- buildx build $svc ---"
            docker buildx build \
                --cache-from "type=registry,ref=${cache_ref}" \
                --cache-to   "type=inline" \
                --tag "${tag}:latest" \
                --load \
                -f "$df" \
                "$ctx"
        else
            # backend / 不支持 buildx 的服务 → 回退 docker compose build
            echo "  --- compose build $svc（backend 不走 buildx） ---"
            docker compose -f "$COMPOSE_FILE" build "$svc"
        fi
    done
else
    echo "==> [3/4] docker compose build"
    BUILD_ARGS=()
    if $NO_CACHE; then
        BUILD_ARGS+=(--no-cache)
    fi
    for svc in $SERVICES; do
        echo "  --- build $svc ---"
        docker compose -f "$COMPOSE_FILE" build "$svc" "${BUILD_ARGS[@]}"
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
