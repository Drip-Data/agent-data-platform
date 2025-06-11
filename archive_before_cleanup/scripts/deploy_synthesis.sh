#!/bin/bash

# ============================================================================
# 任务合成器独立部署脚本
# 可以选择性地部署合成器模块，不影响原有系统
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="docker-compose.yml"
SYNTHESIS_COMPOSE_FILE="docker-compose.synthesis.yml"

print_banner() {
    echo -e "${BLUE}"
    echo "========================================================"
    echo "         任务合成器模块独立部署工具"
    echo "========================================================"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_step "检查部署要求..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi
    
    echo "✅ Docker 和 Docker Compose 已安装"
}

setup_environment() {
    print_step "设置环境变量..."
    
    # 创建 .env 文件（如果不存在）
    if [ ! -f "$BASE_DIR/.env" ]; then
        cat > "$BASE_DIR/.env" << EOF
# ============================================================================
# 任务合成器环境配置
# ============================================================================

# 基础配置
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379

# 合成器配置
SYNTHESIS_ENABLED=true
SYNTHESIS_DB=/app/output/synthesis.db

# LLM API配置（根据需要配置）
# GEMINI_API_KEY=your_gemini_key
# GEMINI_API_URL=https://generativelanguage.googleapis.com
# DEEPSEEK_API_KEY=your_deepseek_key
# DEEPSEEK_API_URL=https://api.deepseek.com
# OPENAI_API_KEY=your_openai_key
# OPENAI_API_BASE=https://api.openai.com

# VLLM配置（本地模型）
VLLM_URL=http://vllm:8000
EOF
        echo "✅ 已创建默认 .env 文件"
        print_warning "请编辑 .env 文件，配置必要的 API 密钥"
    else
        echo "✅ .env 文件已存在"
    fi
    
    # 创建输出目录
    mkdir -p "$BASE_DIR/output"
    echo "✅ 输出目录已创建"
}

deploy_base_system() {
    print_step "部署基础系统..."
    
    cd "$BASE_DIR"
    
    # 启动基础服务
    if [ -f "$COMPOSE_FILE" ]; then
        echo "启动基础服务..."
        docker-compose -f "$COMPOSE_FILE" up -d redis dispatcher
        echo "✅ 基础服务已启动"
    else
        print_warning "未找到基础 docker-compose.yml，跳过基础服务部署"
    fi
}

deploy_synthesis_module() {
    print_step "部署任务合成器模块..."
    
    cd "$BASE_DIR"
    
    # 启动合成器服务
    if [ -f "$SYNTHESIS_COMPOSE_FILE" ]; then
        echo "启动合成器服务..."
        docker-compose -f "$SYNTHESIS_COMPOSE_FILE" up -d
        echo "✅ 合成器服务已启动"
    else
        print_error "未找到 $SYNTHESIS_COMPOSE_FILE 文件"
        exit 1
    fi
}

deploy_integrated_system() {
    print_step "部署集成系统..."
    
    cd "$BASE_DIR"
    
    # 同时启动基础系统和合成器
    echo "启动完整系统..."
    if [ -f "$COMPOSE_FILE" ] && [ -f "$SYNTHESIS_COMPOSE_FILE" ]; then
        docker-compose -f "$COMPOSE_FILE" -f "$SYNTHESIS_COMPOSE_FILE" up -d
        echo "✅ 集成系统已启动"
    else
        print_error "缺少必要的配置文件"
        exit 1
    fi
}

check_deployment() {
    print_step "检查部署状态..."
    
    echo "正在运行的容器："
    docker ps --filter "label=com.docker.compose.project=agent-data-platform" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    echo "网络状态："
    docker network ls | grep agent-data-platform || echo "网络未创建"
    
    echo ""
    echo "卷状态："
    docker volume ls | grep synthesis || echo "合成器卷未创建"
}

show_logs() {
    print_step "显示服务日志..."
    
    echo "合成器服务日志："
    docker-compose -f "$SYNTHESIS_COMPOSE_FILE" logs --tail=20 synthesis
}

show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项："
    echo "  base       - 仅部署基础系统"
    echo "  synthesis  - 仅部署合成器模块"
    echo "  integrated - 部署完整集成系统（推荐）"
    echo "  status     - 检查部署状态"
    echo "  logs       - 显示服务日志"
    echo "  stop       - 停止所有服务"
    echo "  clean      - 清理所有资源"
    echo "  help       - 显示此帮助信息"
    echo ""
    echo "示例："
    echo "  $0 integrated  # 部署完整系统"
    echo "  $0 synthesis   # 仅部署合成器"
    echo "  $0 status      # 检查状态"
}

stop_services() {
    print_step "停止服务..."
    
    cd "$BASE_DIR"
    
    if [ -f "$SYNTHESIS_COMPOSE_FILE" ]; then
        docker-compose -f "$SYNTHESIS_COMPOSE_FILE" down
    fi
    
    if [ -f "$COMPOSE_FILE" ]; then
        docker-compose -f "$COMPOSE_FILE" down
    fi
    
    echo "✅ 所有服务已停止"
}

clean_resources() {
    print_step "清理资源..."
    
    stop_services
    
    echo "清理Docker镜像和卷..."
    docker system prune -f
    docker volume rm $(docker volume ls -q --filter "label=com.docker.compose.project=agent-data-platform") 2>/dev/null || true
    
    echo "✅ 资源清理完成"
}

main() {
    print_banner
    
    case "${1:-help}" in
        "base")
            check_requirements
            setup_environment
            deploy_base_system
            check_deployment
            ;;
        "synthesis")
            check_requirements
            setup_environment
            deploy_synthesis_module
            check_deployment
            ;;
        "integrated")
            check_requirements
            setup_environment
            deploy_integrated_system
            check_deployment
            ;;
        "status")
            check_deployment
            ;;
        "logs")
            show_logs
            ;;
        "stop")
            stop_services
            ;;
        "clean")
            clean_resources
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

main "$@" 