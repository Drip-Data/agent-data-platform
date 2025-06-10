#!/bin/bash

# Agent Data Platform 启动脚本
# 一键启动完整的智能Agent平台

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境
check_environment() {
    log_info "检查运行环境..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi
    
    # 检查必要的环境变量
    if [ -z "$GEMINI_API_KEY" ]; then
        log_warning "GEMINI_API_KEY 环境变量未设置，某些功能可能无法正常工作"
    fi
    
    log_success "环境检查通过"
}

# 清理旧容器
cleanup_containers() {
    log_info "清理旧容器..."
    
    # 停止并删除旧的容器
    docker-compose down --remove-orphans 2>/dev/null || true
    
    # 清理未使用的镜像（可选）
    if [ "$1" = "--clean-images" ]; then
        log_info "清理未使用的Docker镜像..."
        docker image prune -f
    fi
    
    log_success "容器清理完成"
}

# 构建镜像
build_images() {
    log_info "构建Docker镜像..."
    
    # 构建所有必要的镜像
    docker-compose build --parallel \
        redis \
        toolscore \
        python-executor-server \
        browser-navigator-server \
        enhanced-reasoning-runtime \
        dispatcher \
        synthesis
    
    log_success "镜像构建完成"
}

# 启动核心服务
start_core_services() {
    log_info "启动核心基础设施服务..."
    
    # 启动Redis
    docker-compose up -d redis
    
    # 等待Redis就绪
    log_info "等待 Redis 就绪..."
    for i in {1..60}; do
        if docker-compose exec redis redis-cli ping 2>/dev/null | grep -q PONG; then
            break
        fi
        sleep 1
    done
    
    log_success "Redis 服务启动完成"
}

# 启动工具服务
start_tool_services() {
    log_info "启动工具管理服务..."
    
    # 启动ToolScore
    docker-compose up -d toolscore
    
    # 等待ToolScore就绪
    log_info "等待 ToolScore 就绪..."
    sleep 10
    
    log_success "ToolScore 服务启动完成"
    
    # 启动MCP工具服务器
    log_info "启动 MCP 工具服务器..."
    docker-compose up -d python-executor-server browser-navigator-server
    
    # 等待MCP服务器就绪
    log_info "等待 MCP 服务器就绪..."
    sleep 15
    
    log_success "MCP 工具服务器启动完成"
}

# 启动运行时服务
start_runtime_services() {
    log_info "启动运行时服务..."
    
    # 启动增强推理运行时
    docker-compose up -d enhanced-reasoning-runtime
    
    # 等待运行时就绪
    log_info "等待运行时服务就绪..."
    sleep 10
    
    log_success "运行时服务启动完成"
}

# 启动任务管理服务
start_task_services() {
    log_info "启动任务管理服务..."
    
    # 启动任务分发器
    docker-compose up -d dispatcher
    
    log_success "任务管理服务启动完成"
}

# 启动学习服务
start_synthesis_services() {
    log_info "启动任务合成学习服务..."
    
    # 启动合成服务（现在在主compose文件中）
    docker-compose up -d synthesis
    
    log_success "任务合成学习服务启动完成"
}

# 启动监控服务
start_monitoring_services() {
    log_info "启动监控服务..."
    
    # 启动Prometheus和Grafana
    docker-compose up -d prometheus grafana
    
    log_success "监控服务启动完成"
}

# 显示服务状态
show_status() {
    log_info "检查服务状态..."
    
    echo ""
    echo "=== 服务状态 ==="
    docker-compose ps
    
    echo ""
    echo "=== 服务访问地址 ==="
    echo "🌐 任务分发器 API:      http://localhost:8000"
    echo "🔧 ToolScore MCP:       ws://localhost:8080/websocket"
    echo "🐍 Python执行器:       ws://localhost:8081/mcp"
    echo "🌍 浏览器导航器:       ws://localhost:8082/mcp"
    echo "📊 任务合成服务:       http://localhost:9000"
    echo "📈 Prometheus监控:     http://localhost:9090"
    echo "📊 Grafana仪表板:      http://localhost:3000 (admin/admin)"
    
    echo ""
    echo "=== 健康检查 ==="
    
    # 检查关键服务健康状态
    services=("redis" "toolscore" "python-executor-server" "browser-navigator-server" "enhanced-reasoning-runtime" "dispatcher" "synthesis")
    
    for service in "${services[@]}"; do
        if docker-compose ps "$service" | grep -q "Up (healthy)\|Up"; then
            echo "✅ $service: 运行中"
        else
            echo "❌ $service: 异常"
        fi
    done
}

# 显示日志
show_logs() {
    if [ -n "$1" ]; then
        log_info "显示 $1 服务日志..."
        docker-compose logs -f "$1"
    else
        log_info "显示所有服务日志..."
        docker-compose logs -f
    fi
}

# 主函数
main() {
    echo ""
    echo "🚀 Agent Data Platform 启动器"
    echo "=================================="
    
    case "${1:-start}" in
        "start")
            check_environment
            cleanup_containers
            build_images
            start_core_services
            start_tool_services  
            start_runtime_services
            start_task_services
            start_synthesis_services
            start_monitoring_services
            
            echo ""
            log_success "🎉 Agent Data Platform 启动完成！"
            show_status
            ;;
        "stop")
            log_info "停止 Agent Data Platform..."
            docker-compose down
            log_success "平台已停止"
            ;;
        "restart")
            log_info "重启 Agent Data Platform..."
            docker-compose down
            sleep 2
            # 强制重新构建所有镜像并重启服务
            docker-compose up -d --build
            log_success "平台已重启并更新"
            show_status
            ;;
        "rebuild")
            log_info "强制重建并启动 Agent Data Platform..."
            check_environment
            cleanup_containers --clean-images
            docker-compose down --volumes --remove-orphans
            docker system prune -f
            build_images
            start_core_services
            start_tool_services  
            start_runtime_services
            start_task_services
            start_synthesis_services
            start_monitoring_services
            
            echo ""
            log_success "🎉 Agent Data Platform 启动完成！"
            show_status
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "$2"
            ;;
        "clean")
            log_info "清理 Agent Data Platform..."
            cleanup_containers --clean-images
            docker-compose down --volumes --remove-orphans
            docker system prune -f
            log_success "清理完成"
            ;;
        "help"|"-h"|"--help")
            echo "用法: $0 [命令] [参数]"
            echo ""
            echo "命令:"
            echo "  start      启动完整平台 (默认)"
            echo "  stop       停止平台"
            echo "  restart    重启平台"
            echo "  rebuild    强制重建并启动平台"
            echo "  status     显示服务状态"
            echo "  logs [服务] 显示日志（可指定特定服务）"
            echo "  clean      清理所有容器、镜像和数据"
            echo "  help       显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0 start                    # 启动平台"
            echo "  $0 logs toolscore          # 查看toolscore服务日志"
            echo "  $0 status                  # 查看服务状态"
            ;;
        *)
            log_error "未知命令: $1"
            echo "使用 '$0 help' 查看可用命令"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 