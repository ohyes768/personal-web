#!/bin/bash
# 初始化宏观经济历史数据
# 调用 macro 服务的历史数据接口，从 2000 年开始获取全部历史数据

set -e

# 服务地址，可通过环境变量覆盖
MACRO_SERVICE_URL="${MACRO_SERVICE_URL:-http://localhost:8094}"

# 请求超时时间（秒），历史数据获取可能需要较长时间
TIMEOUT=300

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查服务是否可用
check_service() {
    log_info "检查 macro 服务状态: ${MACRO_SERVICE_URL}"
    if curl -s --connect-timeout 5 "${MACRO_SERVICE_URL}/api/macro/health" > /dev/null 2>&1; then
        log_info "服务可用"
        return 0
    else
        log_error "服务不可用，请确认 macro 服务已启动"
        return 1
    fi
}

# 调用历史数据接口
fetch_history() {
    local name=$1
    local endpoint=$2

    log_info "开始获取 ${name} 历史数据..."

    response=$(curl -s -w "\n%{http_code}" --max-time ${TIMEOUT} -X POST "${MACRO_SERVICE_URL}${endpoint}")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" -eq 200 ]; then
        if echo "$body" | grep -q '"success":true'; then
            log_info "${name} 历史数据获取成功"
            return 0
        else
            log_warn "${name} 历史数据获取返回异常: $(echo "$body" | head -c 200)"
            return 1
        fi
    else
        log_error "${name} 历史数据获取失败，HTTP 状态码: ${http_code}"
        return 1
    fi
}

# 主流程
main() {
    log_info "=========================================="
    log_info "开始初始化宏观经济历史数据"
    log_info "服务地址: ${MACRO_SERVICE_URL}"
    log_info "=========================================="

    # 检查服务
    if ! check_service; then
        exit 1
    fi

    echo ""

    # 顺序调用各历史数据接口（有并发锁，不能并行）
    local success_count=0
    local total=5

    # 1. 美国国债历史数据
    if fetch_history "美国国债" "/api/macro/fetch/us-treasuries/history"; then
        ((success_count++))
    fi
    echo ""

    # 2. 汇率历史数据
    if fetch_history "汇率" "/api/macro/fetch/exchange-rates/history"; then
        ((success_count++))
    fi
    echo ""

    # 3. 欧洲国债历史数据
    if fetch_history "欧洲国债" "/api/macro/fetch/eu-bonds/history"; then
        ((success_count++))
    fi
    echo ""

    # 4. 日本国债历史数据
    if fetch_history "日本国债" "/api/macro/fetch/jp-bonds/history"; then
        ((success_count++))
    fi
    echo ""

    # 5. VIX 历史数据
    if fetch_history "VIX恐慌指数" "/api/macro/fetch/vix/history"; then
        ((success_count++))
    fi
    echo ""

    # 汇总
    log_info "=========================================="
    log_info "初始化完成: ${success_count}/${total} 成功"
    log_info "=========================================="

    if [ "$success_count" -eq "$total" ]; then
        log_info "所有历史数据初始化成功！"
        exit 0
    else
        log_warn "部分数据初始化失败，请检查日志"
        exit 1
    fi
}

main "$@"
