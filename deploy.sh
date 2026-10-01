#!/usr/bin/env bash
# ==============================================================================
# NexusDesk 后端一键部署与管理脚本
# 支持：
#   1. 生产级全栈容器化部署 (Docker Compose: 后端 + PostgreSQL + Milvus 向量库)
#   2. 本地轻量级部署 (Python 虚拟环境直启)
#   3. 状态探针、日志监控与容器停止
# ==============================================================================

set -e

# 定位脚本所在根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"

# 控制台彩色输出定义
GREEN="\033[32m"
BLUE="\033[34m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
BOLD="\033[1m"
RESET="\033[0m"

log_info() {
    echo -e "${BLUE}[INFO]${RESET} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${RESET} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${RESET} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${RESET} $1"
}

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "========================================================"
    echo "   🚀 NexusDesk AI Desktop Agent 后端一键部署工具       "
    echo "========================================================"
    echo -e "${RESET}"
}

# 确保配置文件存在
check_env_file() {
    if [ ! -f "${BACKEND_DIR}/.env" ]; then
        log_warn "未检测到 backend/.env 配置文件，正在从模板 .env.example 自动创建..."
        if [ -f "${BACKEND_DIR}/.env.example" ]; then
            cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
            log_success "已创建 backend/.env！"
            echo -e "${YELLOW}提示: 请根据需要编辑 backend/.env 填入您的 DEFAULT_API_KEY (如 DeepSeek / OpenAI 等)${RESET}\n"
        fi
    fi
}

# 模式 1：Docker Compose 生产级一键全栈部署
deploy_docker() {
    log_info "正在检查 Docker 运行环境..."
    if ! command -v docker &> /dev/null; then
        log_error "未检测到 Docker，请先安装 Docker Desktop 或 Docker Engine！"
        echo "官方下载地址: https://www.docker.com/products/docker-desktop"
        exit 1
    fi

    # 兼容 docker compose (v2) 与 docker-compose (v1)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        log_error "未检测到 Docker Compose 插件，请升级 Docker！"
        exit 1
    fi

    check_env_file

    log_info "正在通过 Docker Compose 构建并启动后端全栈容器集群..."
    echo -e "${CYAN}包括: FastAPI 后端服务 + PostgreSQL 检查点存储 + Milvus 向量库 + MinIO + Etcd${RESET}\n"

    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} up -d --build

    log_info "正在等待服务完成健康自检 (约 15~30 秒)..."
    local retries=15
    local success=false

    for i in $(seq 1 $retries); do
        sleep 2
        if curl -s -f http://localhost:8000/health > /dev/null 2>&1 || curl -s -f http://localhost:8000/api/health > /dev/null 2>&1; then
            success=true
            break
        fi
        echo -n "."
    done
    echo ""

    if [ "$success" = true ]; then
        echo ""
        log_success "🎉 NexusDesk 后端服务已成功一键部署并上线！"
        echo -e "${BOLD}服务仪表盘与访问入口:${RESET}"
        echo -e "  🌐 后端 API 接口:     ${GREEN}http://localhost:8000${RESET}"
        echo -e "  📚 交互式文档 (Swagger): ${GREEN}http://localhost:8000/docs${RESET}"
        echo -e "  🩺 健康探活地址:       ${GREEN}http://localhost:8000/api/health${RESET}"
        echo -e "  🐘 PostgreSQL 端口:   ${GREEN}5432${RESET} (用户: nexusdesk, 库: nexusdesk)"
        echo -e "  ⚡ Milvus 向量服务:   ${GREEN}19530${RESET}"
        echo -e "  🗄️  MinIO 控制台:      ${GREEN}http://localhost:9001${RESET} (用户/密码: minioadmin)"
        echo ""
        echo -e "💡 提示: 您现在可以启动前端桌面客户端，它将无缝直连本地服务。"
    else
        log_warn "服务正在后台启动初始化中，请运行 './deploy.sh logs' 查看实时日志。"
    fi
}

# 模式 2：本地 Python 虚拟环境直启
deploy_local() {
    log_info "正在准备本地 Python 运行环境..."
    
    # 优先使用现有 venv
    PYTHON_BIN=""
    if [ -f "${BACKEND_DIR}/venv/bin/python3" ]; then
        PYTHON_BIN="${BACKEND_DIR}/venv/bin/python3"
    elif command -v python3 &> /dev/null; then
        PYTHON_BIN="python3"
    elif command -v python &> /dev/null; then
        PYTHON_BIN="python"
    else
        log_error "系统中未找到 Python，请安装 Python 3.10+！"
        exit 1
    fi

    # 检查虚拟环境
    if [ ! -d "${BACKEND_DIR}/venv" ]; then
        log_info "未检测到虚拟环境，正在创建 backend/venv..."
        cd "${BACKEND_DIR}"
        $PYTHON_BIN -m venv venv
        PYTHON_BIN="${BACKEND_DIR}/venv/bin/python3"
    fi

    check_env_file

    log_info "正在检查并安装 Python 依赖库..."
    cd "${BACKEND_DIR}"
    "${BACKEND_DIR}/venv/bin/pip" install --upgrade pip -q
    "${BACKEND_DIR}/venv/bin/pip" install -r requirements.txt -q

    log_success "依赖检查完成！"
    log_info "正在启动 NexusDesk FastAPI 后端服务..."
    echo -e "${CYAN}访问地址: http://127.0.0.1:8000${RESET}\n"

    exec "${BACKEND_DIR}/venv/bin/python" main.py --host 127.0.0.1 --port 8000
}

# 检查运行状态
show_status() {
    print_banner
    log_info "正在检查服务状态..."
    
    # 检查端口监听
    if command -v lsof &> /dev/null; then
        PID=$(lsof -ti :8000 || true)
        if [ -n "$PID" ]; then
            log_success "端口 8000 正在运行 (PID: $PID)"
        else
            log_warn "端口 8000 未被监听"
        fi
    fi

    # 探针请求 (优先探测 /health，兼容 /api/health)
    HEALTH_RES=$(curl -s -f http://localhost:8000/health 2>/dev/null || curl -s -f http://localhost:8000/api/health 2>/dev/null || true)
    if [ -n "$HEALTH_RES" ]; then
        log_success "后端服务健康探针响应正常: $HEALTH_RES"
    else
        log_warn "后端 HTTP 服务探活无响应 (请检查服务是否就绪)"
    fi

    # 检查 Docker 容器
    if command -v docker &> /dev/null; then
        echo ""
        log_info "Docker 容器状态:"
        docker ps --filter "name=nexusdesk" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    fi
}

# 停止容器
stop_services() {
    log_info "正在停止 NexusDesk 容器集群..."
    cd "${PROJECT_ROOT}"
    if docker compose version &> /dev/null; then
        docker compose down
    elif command -v docker-compose &> /dev/null; then
        docker-compose down
    fi
    log_success "服务已停止！"
}

# 查看日志
show_logs() {
    cd "${PROJECT_ROOT}"
    if docker compose version &> /dev/null; then
        docker compose logs -f --tail=100 backend
    elif command -v docker-compose &> /dev/null; then
        docker-compose logs -f --tail=100 backend
    fi
}

# 打印帮助指南
show_help() {
    print_banner
    echo -e "${BOLD}使用方式:${RESET}"
    echo "  ./deploy.sh [命令]"
    echo ""
    echo -e "${BOLD}可用命令:${RESET}"
    echo -e "  ${GREEN}docker${RESET}   一键全栈容器化部署 (推荐: 后端 + PostgreSQL + Milvus 向量库)"
    echo -e "  ${GREEN}local${RESET}    本地轻量启动 (使用本地 Python 虚拟环境与 SQLite / Milvus-Lite)"
    echo -e "  ${GREEN}status${RESET}   查看服务运行与健康探活状态"
    echo -e "  ${GREEN}logs${RESET}     查看后端容器实时日志流"
    echo -e "  ${GREEN}stop${RESET}     停止所有部署的容器"
    echo -e "  ${GREEN}help${RESET}     查看此帮助信息"
    echo ""
    echo "如果不传任何参数，默认执行 'docker' 一键全栈部署。"
}

# 主入口调度
COMMAND="${1:-docker}"

case "$COMMAND" in
    docker)
        print_banner
        deploy_docker
        ;;
    local)
        print_banner
        deploy_local
        ;;
    status)
        show_status
        ;;
    stop)
        stop_services
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "未知命令: $COMMAND"
        show_help
        exit 1
        ;;
esac
