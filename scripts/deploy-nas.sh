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

# 加载根 .env 到环境变量：compose 会自动读它做插值，但下面 frontend 走 buildx
# 直构建、不经 compose，NEXT_PUBLIC_* 的 build args 需要从 shell 环境取值
if [[ -f .env ]]; then
    set -a
    . ./.env
    set +a
fi

COMPOSE_FILE="docker-compose.nas.yml"
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
# 带国内 registry mirror 的 builder（旧名 nas-builder 不继承 daemon.json 加速，会直连 Docker Hub 超时）
BUILDX_BUILDER="nas-builder-cn"
BUILDKITD_CONFIG="scripts/buildkitd-nas.toml"
# nginx target 配置（容器名可被环境变量覆盖）
# 注：nginx 容器已 bind mount 仓库 nginx/web.conf → /etc/nginx/conf.d/web.conf，
# 所以脚本只负责 reload，不再 cp/mv；NGINX_CONF_DEST 已废弃。
# nginx compose 文件在另一个项目里（~/-/nginx/），路径可被环境变量覆盖。
NGINX_CONTAINER="${NGINX_CONTAINER:-nginx}"
NGINX_COMPOSE_FILE="${NGINX_COMPOSE_FILE:-/home/ohyes768/nginx/docker-compose.yml}"
# task-web 业务仓库（方案 B：脚本+依赖由 stock-info-dingding 自维护）
# STOCK_INFO_HOST_PATH  = 业务镜像 stock-info:latest 的构建 context
# TASK_WEB_WORKSPACE_HOST_PATH = task-web-backend 挂载给 docker 任务用的 workspace
# 两者默认同一份 checkout；这里显式给默认值并 export，保证 compose 插值
# 与下面 git pull 的目标是同一个路径。
STOCK_INFO_HOST_PATH="${STOCK_INFO_HOST_PATH:-/home/ohyes768/stock-info-dingding}"
TASK_WEB_WORKSPACE_HOST_PATH="${TASK_WEB_WORKSPACE_HOST_PATH:-$STOCK_INFO_HOST_PATH}"
export STOCK_INFO_HOST_PATH TASK_WEB_WORKSPACE_HOST_PATH

show_help() {
    cat <<'EOF'
NAS 部署脚本（Ubuntu Server + docker-compose.nas.yml）

用法:
  ./scripts/deploy-nas.sh <target> [side] [options]

target:
  dividend | douyin | rss-relay | macro | fund-select | housing-map | skill-manager | kids-catalog | index-trends | task-web | nginx | all
  （nginx 只同步 nginx/web.conf 到 nginx 容器并 reload，不走 build/up，忽略 side）

side:（默认 both）
  backend | frontend | both

options:
  --no-pull     跳过 git pull（personal-web 与 task-web 业务仓库都跳过）
  --cold        强制冷构建：清 Docker 层缓存 + 换新的空 pnpm store（真正重下依赖）
  --no-buildx   前端也退回 docker compose build（默认 frontend 走 buildx）
  --tail        部署完后 tail 日志（默认关）
  -h, --help    显示本帮助

构建行为（两个正交开关）:
  (默认)              frontend → buildx 热构建；backend → compose 热构建
  --cold              同上路径，但 --no-cache + 新 pnpm store（不复用已下包）
  --no-buildx         frontend/backend 都走 compose 热构建
  --cold --no-buildx  全部 compose 真冷构建

说明:
  task-web 连带处理业务仓库 stock-info-dingding（方案 B：业务代码不进本仓）：
    1) 先在业务仓库 checkout 上 git pull --ff-only 更新代码
    2) 再 docker compose build stock-info-image 重建 stock-info:latest
    3) 校验 /workspace/stock-info-dingding 下的运行时 env_file 是否就位（缺失只告警）
  路径默认 /home/ohyes768/stock-info-dingding，可用根 .env 里的
  STOCK_INFO_HOST_PATH / TASK_WEB_WORKSPACE_HOST_PATH 覆盖；
  side=frontend 时跳过以上步骤（前端不依赖业务镜像）。

  buildx 使用 docker-container 驱动时，不会继承宿主机 daemon.json 的
  registry-mirrors。脚本会创建 nas-builder-cn，并加载
  scripts/buildkitd-nas.toml（Docker Hub → 国内镜像）。
  若拉基础镜像仍超时：改 toml 里的 mirrors，然后
    docker buildx rm nas-builder-cn
  再重新部署。临时绕过可用 --no-buildx（走 compose，用宿主机镜像缓存）。

示例:
  ./scripts/deploy-nas.sh dividend backend
  ./scripts/deploy-nas.sh dividend frontend
  ./scripts/deploy-nas.sh dividend both
  ./scripts/deploy-nas.sh douyin both
  ./scripts/deploy-nas.sh rss-relay both
  ./scripts/deploy-nas.sh macro both
  ./scripts/deploy-nas.sh macro backend
  ./scripts/deploy-nas.sh fund-select both
  ./scripts/deploy-nas.sh housing-map both
  ./scripts/deploy-nas.sh skill-manager both
  ./scripts/deploy-nas.sh kids-catalog both
  ./scripts/deploy-nas.sh index-trends both
  ./scripts/deploy-nas.sh task-web both      # 连带更新业务仓库 + 重建 stock-info:latest
  ./scripts/deploy-nas.sh nginx              # 同步 nginx/web.conf + reload（忽略 side）
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

# ---- nginx 同步（nginx 容器已 bind mount nginx/web.conf，需 restart 重挂载）----
# skill-manager 已合并到 docker-compose.nas.yml，与其他服务一起部署
case "$TARGET" in
esac

# bind mount 在文件 inode 层是同步的（同一路径），但 nginx master 进程
# 启动时 open() 拿到 fd 后不会重读，reload 也不重新挂载。所以
# 改完 web.conf 之后必须 docker compose restart nginx（3 秒）才能生效。
# 单纯 nginx -s reload 在「bind mount + nginx worker」这个组合下会
# 静默不生效，看起来 reload 成功但实际加载的是旧版本。
sync_nginx() {
    echo "==> nginx -t（测试配置，失败则中止，不会 reload）"
    docker exec "$NGINX_CONTAINER" nginx -t
    echo "==> docker compose -f $NGINX_COMPOSE_FILE restart $NGINX_CONTAINER（重新挂载 bind mount，加载新配置）"
    docker compose -f "$NGINX_COMPOSE_FILE" restart "$NGINX_CONTAINER"
    echo "============================================================"
    echo "nginx 配置已更新并 reload"
    echo "============================================================"
}

# ---- 服务映射 ----
get_services() {
    local target="$1" side="$2"
    case "$target" in
        dividend|douyin|rss-relay|macro|fund-select|housing-map|skill-manager|kids-catalog|index-trends|task-web)
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
            echo "dividend-backend dividend-frontend douyin-backend douyin-frontend rss-relay-backend rss-relay-frontend macro-backend macro-frontend fund-select-backend fund-select-frontend housing-map-backend housing-map-frontend skill-manager-backend skill-manager-frontend index-trends-backend index-trends-frontend task-web-backend task-web-frontend"
            ;;
        *)
            echo "错误: target 必须是 dividend | douyin | rss-relay | macro | fund-select | housing-map | skill-manager | kids-catalog | index-trends | task-web | all，实际 '$target'" >&2
            exit 1
            ;;
    esac
}

# ---- frontend buildx context 映射 ----
# USE_BUILDX=true 时前端走 docker buildx，pnpm install 走 Dockerfile cache mount 复用
# 格式 ctx:df:tag[:build_args]，build_args 段用 | 分隔多个 ARG=值（可省略）。
# buildx 不读 compose 的 build.args，需要 build-time inline 的 NEXT_PUBLIC_*
# 必须在这里显式传（值经顶部 .env 加载进入 shell 环境）
get_buildx_config() {
    local svc="$1"
    case "$svc" in
        dividend-frontend)  echo "apps/dividend:apps/dividend/Dockerfile:dividend-frontend" ;;
        douyin-frontend)    echo "apps/douyin:apps/douyin/Dockerfile:douyin-frontend" ;;
        rss-relay-frontend) echo "apps/rss-relay:apps/rss-relay/Dockerfile:rss-relay-frontend:NEXT_PUBLIC_RSS_TOKEN=${RSS_RELAY_TOKEN:-}" ;;
        macro-frontend) echo "apps/macro:apps/macro/Dockerfile:macro-frontend" ;;
        fund-select-frontend) echo "apps/fund-select:apps/fund-select/Dockerfile:fund-select-frontend" ;;
        housing-map-frontend) echo "apps/housing-map:apps/housing-map/Dockerfile:housing-map-frontend:NEXT_PUBLIC_GAODE_MAP_KEY=${GAODE_MAP_KEY:-${NEXT_PUBLIC_GAODE_MAP_KEY:-}}|NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY=${GAODE_MAP_SECURITY_KEY:-${NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY:-}}" ;;
        skill-manager-frontend) echo "apps/skill-manager:apps/skill-manager/Dockerfile:skill-manager-frontend" ;;
        kids-catalog-frontend) echo "apps/kids-catalog:apps/kids-catalog/Dockerfile:kids-catalog-frontend" ;;
        index-trends-frontend) echo "apps/index-trends:apps/index-trends/Dockerfile:index-trends-frontend" ;;
        task-web-frontend) echo "apps/task-web:apps/task-web/Dockerfile:task-web-frontend" ;;
        *) return 1 ;;
    esac
}

# ---- 确保 buildx builder 存在（docker-container + 国内 registry mirror） ----
ensure_buildx_builder() {
    local builder_name="${1:-$BUILDX_BUILDER}"
    local config_file="$BUILDKITD_CONFIG"

    # 清理旧 builder（无 mirror 配置，会直连 Docker Hub 超时）
    if docker buildx inspect nas-builder >/dev/null 2>&1; then
        echo ""
        echo "==> 移除旧 builder 'nas-builder'（无 registry mirror）"
        docker buildx rm nas-builder >/dev/null 2>&1 || true
    fi

    if docker buildx inspect "$builder_name" >/dev/null 2>&1; then
        return 0
    fi

    if [[ ! -f "$config_file" ]]; then
        echo "错误: 缺少 BuildKit 配置 $config_file" >&2
        exit 1
    fi

    echo ""
    echo "==> 创建 buildx builder '$builder_name'（docker-container + $config_file）"
    docker buildx create \
        --name "$builder_name" \
        --driver docker-container \
        --config "$config_file" \
        --bootstrap >/dev/null
    echo "    已创建 '$builder_name'（pnpm cache 持久 + Docker Hub 走国内 mirror）"
}

compose_build() {
    local svc="$1"
    local args=()
    if $COLD; then
        # --no-cache 清层；PNPM_CACHE_BUST 换新 id → cache mount 是空的，真正重下包
        args+=(--no-cache --build-arg "PNPM_CACHE_BUST=cold-$(date +%s)")
    fi
    docker compose "${COMPOSE_ARGS[@]}" build "$svc" "${args[@]}"
}

buildx_build_frontend() {
    local svc="$1"
    local cfg ctx df tag build_args
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
    # 第 4 段：build args（| 分隔），有 KEY=* 形态的 NEXT_PUBLIC_* 需要 build-time inline
    build_args=$(echo "$cfg" | cut -d: -f4)
    if [[ -n "$build_args" ]]; then
        local pair
        for pair in ${build_args//|/ }; do
            args+=(--build-arg "$pair")
        done
    fi
    if $COLD; then
        args+=(--no-cache --build-arg "PNPM_CACHE_BUST=cold-$(date +%s)")
    fi
    docker buildx build "${args[@]}" "$ctx"
}

# ---- task-web 业务仓库（stock-info-dingding）更新与就位校验 ----
# 方案 B 下业务代码不进本仓，但仍要「一条命令打包到位」：
# 镜像源码来自 STOCK_INFO_HOST_PATH 的 checkout，运行时 env_file 来自
# TASK_WEB_WORKSPACE_HOST_PATH 的 checkout —— 两者部署前都必须是最新的。
update_task_web_business_repo() {
    local path seen="" current
    for path in "$STOCK_INFO_HOST_PATH" "$TASK_WEB_WORKSPACE_HOST_PATH"; do
        # 默认两者同路径，去重避免 pull 两遍
        case " $seen " in *" $path "*) continue ;; esac
        seen="$seen $path"

        if [[ ! -d "$path" ]]; then
            echo "错误: task-web 业务仓库不存在: $path" >&2
            echo "  处理: 在根 .env 设置 STOCK_INFO_HOST_PATH / TASK_WEB_WORKSPACE_HOST_PATH 指向真实路径，" >&2
            echo "        或加 --no-pull 跳过业务仓库更新（仅用现有文件构建镜像）。" >&2
            exit 1
        fi
        if ! git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            echo "  提示: $path 不是 git 仓库，跳过 git pull（按现有文件构建镜像）"
            continue
        fi

        current=$(git -C "$path" rev-parse --short HEAD 2>/dev/null || echo "?")
        echo "  --- git pull 业务仓库 $(basename "$path") ($path, 当前 $current) ---"
        if ! git -C "$path" pull --ff-only; then
            echo "错误: $path 更新失败（本地改动、分支分叉或无远端凭据）。" >&2
            echo "  处理: cd $path && git status 查看；修好重跑，" >&2
            echo "        或加 --no-pull 用当前 checkout 直接构建（会打进旧代码）。" >&2
            exit 1
        fi
    done
}

# docker 任务靠 env_file 注入密钥：文件缺失时容器起不来，但镜像构建不受影响，
# 所以这里只告警，不阻断部署（历史镜像/无密钥环境仍可部署）。
check_task_web_business_env() {
    local name missing=()
    for name in .env .env.hermes-default; do
        [[ -f "$TASK_WEB_WORKSPACE_HOST_PATH/$name" ]] || missing+=("$TASK_WEB_WORKSPACE_HOST_PATH/$name")
    done
    if (( ${#missing[@]} > 0 )); then
        echo "  警告: 缺少 docker 任务的 env_file（对应任务运行时会失败）：" >&2
        printf '    - %s\n' "${missing[@]}" >&2
    else
        echo "  env_file 就位: $TASK_WEB_WORKSPACE_HOST_PATH/.env(.hermes-default)"
    fi
}

# ---- nginx target：只同步 web.conf + reload，不走 build/up ----
if [[ "$TARGET" == "nginx" ]]; then
    if $DO_PULL; then
        echo ""
        echo "==> git pull"
        git pull
    fi
    sync_nginx
    exit 0
fi

SERVICES=$(get_services "$TARGET" "$SIDE")
echo "============================================================"
echo "部署目标: $SERVICES"
echo "  pull:      $DO_PULL"
echo "  cold:      $COLD"
echo "  buildx:    $USE_BUILDX"
echo "  tail:      $DO_TAIL"
if [[ "$TARGET" == "task-web" && "$SIDE" != "frontend" ]]; then
    echo "  业务仓库:  $STOCK_INFO_HOST_PATH"
fi
echo "============================================================"

# ---- Step 1: git pull ----
if $DO_PULL; then
    echo ""
    echo "==> [1/3] git pull"
    git pull
fi

# ---- Step 2: build ----
# task-web 前置：业务仓库更新 + 业务镜像 stock-info（方案 B，脚本+依赖在业务仓库自维护）
# 前端不依赖业务镜像，side=frontend 时整段跳过。
if [[ "$TARGET" == "task-web" && "$SIDE" != "frontend" ]]; then
    echo ""
    if $DO_PULL; then
        echo "==> [2/3] 更新 task-web 业务仓库（stock-info-dingding）"
        update_task_web_business_repo
    else
        echo "==> [2/3] 跳过业务仓库 git pull（--no-pull，按当前 checkout 构建）"
    fi
    echo ""
    echo "  --- compose build stock-info-image（context=$STOCK_INFO_HOST_PATH）---"
    compose_build stock-info-image
    check_task_web_business_env
elif [[ "$TARGET" == "task-web" ]]; then
    echo ""
    echo "==> [2/3] side=frontend：跳过业务仓库更新与 stock-info 镜像构建"
fi
echo ""
if $USE_BUILDX; then
    ensure_buildx_builder "$BUILDX_BUILDER"
    if $COLD; then
        echo "==> [2/3] build（buildx frontend + compose backend，--cold）"
    else
        echo "==> [2/3] build（buildx frontend + compose backend，热构建）"
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
        echo "==> [2/3] docker compose build（--cold）"
    else
        echo "==> [2/3] docker compose build（热构建）"
    fi
    for svc in $SERVICES; do
        echo "  --- compose build $svc ---"
        compose_build "$svc"
    done
fi

# ---- Step 3: restart（--no-build：镜像已由上一步 buildx/compose 打好，禁止 compose 再用旧名偷偷重建） ----
echo ""
echo "==> [3/3] docker compose up -d --force-recreate --no-build"
docker compose "${COMPOSE_ARGS[@]}" up -d --force-recreate --no-build $SERVICES

# ---- 验证状态 ----
echo ""
echo "============================================================"
echo "部署完成。当前容器状态："
echo "============================================================"
docker compose "${COMPOSE_ARGS[@]}" ps $SERVICES

# ---- tail logs ----
if $DO_TAIL; then
    echo ""
    echo "============================================================"
    echo "tail logs（Ctrl+C 退出，不会停止容器）："
    echo "============================================================"
    docker compose "${COMPOSE_ARGS[@]}" logs -f --tail 50 $SERVICES
fi
