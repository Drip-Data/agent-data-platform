#!/bin/bash

# Agent Data Platform 启动脚本 - 无Docker版本
# 用于在Python虚拟环境中启动平台

set -e

# 颜色定义
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

# 检查Python版本
check_python() {
    log_info "检查Python版本..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装，请先安装Python 3.10+"
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    required_version="3.10"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        log_error "Python版本过低，需要3.10+，当前版本: $python_version"
        exit 1
    fi
    
    log_success "Python版本检查通过: $python_version"
}

# 检查Redis
check_redis() {
    log_info "检查Redis服务..."
    
    if ! command -v redis-cli &> /dev/null; then
        log_warning "Redis CLI 未安装，请确保Redis服务可用"
        return 0
    fi
    
    if redis-cli ping &> /dev/null; then
        log_success "Redis服务正常"
    else
        log_warning "Redis服务未运行，某些功能可能受限"
    fi
}

# 创建虚拟环境
setup_venv() {
    log_info "设置Python虚拟环境..."
    
    if [ ! -d "venv" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv
    fi
    
    log_info "激活虚拟环境..."
    source venv/bin/activate
    
    log_info "升级pip..."
    pip install --upgrade pip
    
    log_success "虚拟环境设置完成"
}

# 安装依赖
install_dependencies() {
    log_info "安装Python依赖..."
    
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        log_success "依赖安装完成"
    else
        log_error "requirements.txt 文件不存在"
        exit 1
    fi
}

# 检查环境变量
check_env() {
    log_info "检查环境变量配置..."
    
    if [ ! -f ".env" ]; then
        if [ -f "env.example" ]; then
            log_info "复制环境变量模板..."
            cp env.example .env
            log_warning "请编辑 .env 文件，填入必要的API密钥"
        else
            log_error "环境变量配置文件不存在"
            exit 1
        fi
    fi
    
    # 检查关键环境变量
    source .env
    
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$OPENAI_API_KEY" ] && [ -z "$DEEPSEEK_API_KEY" ]; then
        log_warning "未配置AI API密钥，请在.env文件中配置至少一个API密钥"
    fi
    
    log_success "环境变量检查完成"
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    
    mkdir -p logs
    mkdir -p output/trajectories
    mkdir -p config
    mkdir -p data
    
    log_success "目录创建完成"
}

# 启动服务
start_services() {
    log_info "启动Agent Data Platform..."
    
    # 检查端口占用
    if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
        log_error "端口8080已被占用，请检查是否有其他服务在运行"
        exit 1
    fi
    
    # 启动主服务
    log_info "启动ToolScore核心服务..."
    python main.py &
    MAIN_PID=$!
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 5
    
    # 健康检查
    if curl -s http://localhost:8080/health > /dev/null; then
        log_success "服务启动成功！"
        log_info "服务地址: http://localhost:8080"
        log_info "WebSocket地址: ws://localhost:8081"
        log_info "监控地址: http://localhost:8082"
    else
        log_error "服务启动失败，请检查日志"
        kill $MAIN_PID 2>/dev/null || true
        exit 1
    fi
    
    # 保存PID
    echo $MAIN_PID > .platform.pid
    log_info "服务PID已保存到 .platform.pid"
}

# 显示状态
show_status() {
    log_info "=== Agent Data Platform 状态 ==="
    
    if [ -f ".platform.pid" ]; then
        PID=$(cat .platform.pid)
        if ps -p $PID > /dev/null; then
            log_success "主服务运行中 (PID: $PID)"
        else
            log_error "主服务未运行"
        fi
    else
        log_error "未找到PID文件"
    fi
    
    # 检查端口
    if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
        log_success "端口8080正在监听"
    else
        log_error "端口8080未监听"
    fi
    
    # 检查Redis
    if redis-cli ping &> /dev/null; then
        log_success "Redis服务正常"
    else
        log_warning "Redis服务未运行"
    fi
}

# 停止服务
stop_services() {
    log_info "停止Agent Data Platform..."
    
    if [ -f ".platform.pid" ]; then
        PID=$(cat .platform.pid)
        if ps -p $PID > /dev/null; then
            log_info "停止主服务 (PID: $PID)..."
            kill $PID
            sleep 2
            
            if ps -p $PID > /dev/null; then
                log_warning "强制停止服务..."
                kill -9 $PID
            fi
        fi
        rm -f .platform.pid
    fi
    
    # 清理其他可能的进程
    pkill -f "python main.py" 2>/dev/null || true
    
    log_success "服务已停止"
}

# 重启服务
restart_services() {
    log_info "重启Agent Data Platform..."
    stop_services
    sleep 2
    start_services
}

# 查看日志
show_logs() {
    if [ -f "logs/toolscore.log" ]; then
        tail -f logs/toolscore.log
    else
        log_error "日志文件不存在"
    fi
}

# 主函数
main() {
    case "${1:-start}" in
        "start")
            log_info "启动Agent Data Platform..."
            check_python
            check_redis
            setup_venv
            install_dependencies
            check_env
            create_directories
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs
            ;;
        "setup")
            log_info "设置开发环境..."
            check_python
            setup_venv
            install_dependencies
            check_env
            create_directories
            log_success "开发环境设置完成"
            ;;
        *)
            echo "用法: $0 {start|stop|restart|status|logs|setup}"
            echo ""
            echo "命令说明:"
            echo "  start   - 启动平台服务"
            echo "  stop    - 停止平台服务"
            echo "  restart - 重启平台服务"
            echo "  status  - 查看服务状态"
            echo "  logs    - 查看实时日志"
            echo "  setup   - 设置开发环境"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 