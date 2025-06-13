#!/bin/bash

# Agent Data Platform 测试脚本 - 无Docker版本
# 用于验证平台功能是否正常

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

# 检查服务是否运行
check_service() {
    local url=$1
    local name=$2
    
    log_info "检查 $name 服务..."
    
    if curl -s "$url" > /dev/null; then
        log_success "$name 服务正常"
        return 0
    else
        log_error "$name 服务异常"
        return 1
    fi
}

# 测试API端点
test_api() {
    local endpoint=$1
    local method=${2:-GET}
    local data=${3:-}
    local name=$4
    
    log_info "测试 $name..."
    
    if [ -n "$data" ]; then
        response=$(curl -s -X "$method" -H "Content-Type: application/json" -d "$data" "$endpoint" || echo "ERROR")
    else
        response=$(curl -s -X "$method" "$endpoint" || echo "ERROR")
    fi
    
    if [ "$response" = "ERROR" ]; then
        log_error "$name 测试失败"
        return 1
    else
        log_success "$name 测试通过"
        echo "响应: $response" | head -c 200
        echo ""
        return 0
    fi
}

# 主测试函数
main() {
    log_info "开始测试 Agent Data Platform..."
    
    # 基础服务检查
    log_info "=== 基础服务检查 ==="
    
    # 检查主服务
    if ! check_service "http://localhost:8080/health" "ToolScore主服务"; then
        log_error "主服务未运行，请先启动平台"
        exit 1
    fi
    
    # 检查WebSocket服务
    if ! check_service "http://localhost:8081" "WebSocket服务"; then
        log_warning "WebSocket服务可能未启动"
    fi
    
    # 检查监控服务
    if ! check_service "http://localhost:8082" "监控服务"; then
        log_warning "监控服务可能未启动"
    fi
    
    # API功能测试
    log_info "=== API功能测试 ==="
    
    # 测试健康检查
    test_api "http://localhost:8080/health" "GET" "" "健康检查API"
    
    # 测试系统统计
    test_api "http://localhost:8080/api/v1/stats" "GET" "" "系统统计API"
    
    # 测试MCP服务器列表
    test_api "http://localhost:8080/api/v1/mcp/servers" "GET" "" "MCP服务器列表API"
    
    # 测试工具搜索
    test_api "http://localhost:8080/api/v1/tools/search?query=python" "GET" "" "工具搜索API"
    
    # 测试任务提交（如果支持）
    task_data='{"task_type": "reasoning", "input": "测试任务：计算1+1", "priority": "low"}'
    if test_api "http://localhost:8080/api/v1/tasks" "POST" "$task_data" "任务提交API"; then
        log_success "任务提交功能正常"
    else
        log_warning "任务提交功能可能未实现或需要配置"
    fi
    
    # 进程检查
    log_info "=== 进程状态检查 ==="
    
    if [ -f ".platform.pid" ]; then
        PID=$(cat .platform.pid)
        if ps -p $PID > /dev/null; then
            log_success "主进程运行正常 (PID: $PID)"
            
            # 检查内存使用
            memory_usage=$(ps -p $PID -o rss= | awk '{print $1/1024}')
            log_info "内存使用: ${memory_usage}MB"
            
            # 检查CPU使用
            cpu_usage=$(ps -p $PID -o %cpu= | awk '{print $1}')
            log_info "CPU使用: ${cpu_usage}%"
        else
            log_error "主进程未运行"
        fi
    else
        log_warning "未找到PID文件"
    fi
    
    # 检查端口占用
    log_info "=== 端口占用检查 ==="
    
    ports=(8080 8081 8082)
    for port in "${ports[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            log_success "端口 $port 正在监听"
        else
            log_warning "端口 $port 未监听"
        fi
    done
    
    # 日志检查
    log_info "=== 日志检查 ==="
    
    if [ -f "logs/toolscore.log" ]; then
        log_success "日志文件存在"
        
        # 检查最近的错误
        error_count=$(grep -c "ERROR" logs/toolscore.log 2>/dev/null || echo "0")
        warning_count=$(grep -c "WARNING" logs/toolscore.log 2>/dev/null || echo "0")
        
        log_info "错误数量: $error_count"
        log_info "警告数量: $warning_count"
        
        if [ "$error_count" -gt 0 ]; then
            log_warning "发现错误，最近的错误："
            tail -n 20 logs/toolscore.log | grep "ERROR" | tail -n 3
        fi
    else
        log_warning "日志文件不存在"
    fi
    
    # 配置检查
    log_info "=== 配置检查 ==="
    
    if [ -f ".env" ]; then
        log_success "环境配置文件存在"
        
        # 检查关键配置
        if grep -q "GEMINI_API_KEY" .env && ! grep -q "GEMINI_API_KEY=$" .env; then
            log_success "Gemini API密钥已配置"
        elif grep -q "OPENAI_API_KEY" .env && ! grep -q "OPENAI_API_KEY=$" .env; then
            log_success "OpenAI API密钥已配置"
        else
            log_warning "未配置AI API密钥"
        fi
    else
        log_warning "环境配置文件不存在"
    fi
    
    # 目录检查
    log_info "=== 目录结构检查 ==="
    
    directories=("logs" "output" "config" "data")
    for dir in "${directories[@]}"; do
        if [ -d "$dir" ]; then
            log_success "目录 $dir 存在"
        else
            log_warning "目录 $dir 不存在"
        fi
    done
    
    # 总结
    log_info "=== 测试总结 ==="
    log_success "Agent Data Platform 测试完成"
    log_info "如果发现问题，请检查日志文件: logs/toolscore.log"
    log_info "或使用以下命令查看实时日志: tail -f logs/toolscore.log"
}

# 执行测试
main "$@" 