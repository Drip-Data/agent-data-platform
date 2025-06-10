#!/bin/bash

# MCP系统状态检查脚本
# 检查所有组件的运行状态和健康度

echo "🔍 MCP主动选择机制状态检查"
echo "========================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "\n${BLUE}📋 $1${NC}"
    echo "----------------------------------------"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 1. 检查Docker服务
print_header "Docker服务状态"

if ! docker info >/dev/null 2>&1; then
    print_error "Docker未运行或无权限访问"
    exit 1
else
    print_success "Docker服务正常"
fi

# 2. 检查容器状态
print_header "容器状态"

containers=("redis" "toolscore" "enhanced-reasoning-runtime")

for container in "${containers[@]}"; do
    if docker-compose ps $container | grep -q "running\|healthy"; then
        print_success "$container: 运行中"
    else
        print_error "$container: 未运行"
        echo "尝试启动 $container..."
        docker-compose up -d $container
    fi
done

# 3. 检查服务健康度
print_header "服务健康检查"

# Redis检查
echo "检查Redis连接..."
if docker-compose exec redis redis-cli ping 2>/dev/null | grep -q PONG; then
    print_success "Redis: 连接正常"
else
    print_error "Redis: 连接失败"
fi

# ToolScore检查
echo "检查ToolScore WebSocket..."
if docker-compose logs toolscore | tail -10 | grep -q "WebSocket\|WebSocket server\|listening"; then
    print_success "ToolScore: WebSocket服务正常"
else
    print_warning "ToolScore: WebSocket状态未知"
fi

# Enhanced Runtime检查
echo "检查Enhanced Runtime状态..."
if docker-compose logs enhanced-reasoning-runtime | tail -10 | grep -q "initialized\|ready\|listening"; then
    print_success "Enhanced Runtime: 服务正常"
else
    print_warning "Enhanced Runtime: 状态未知"
fi

# 4. 检查MCP组件
print_header "MCP组件检查"

# 创建检查脚本
cat > check_mcp_components.py << 'EOF'
import asyncio
import sys
sys.path.append('/app')

async def check_components():
    try:
        print("🔍 检查MCP组件...")
        
        # 检查模块导入
        try:
            from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
            from core.toolscore.mcp_search_tool import MCPSearchTool
            from core.toolscore.tool_gap_detector import ToolGapDetector
            print("✅ MCP模块导入成功")
        except Exception as e:
            print(f"❌ MCP模块导入失败: {e}")
            return False
        
        # 检查Runtime初始化
        try:
            from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
            runtime = EnhancedReasoningRuntime()
            await runtime.initialize()
            print("✅ Enhanced Runtime初始化成功")
        except Exception as e:
            print(f"❌ Enhanced Runtime初始化失败: {e}")
            return False
        
        # 检查MCP搜索工具注册
        try:
            tools = await runtime.tool_library.get_all_tools()
            mcp_tool = next((t for t in tools if t.tool_id == "mcp-search-tool"), None)
            
            if mcp_tool:
                print("✅ MCP搜索工具已注册")
                print(f"   能力数量: {len(mcp_tool.capabilities)}")
            else:
                print("❌ MCP搜索工具未注册")
                return False
        except Exception as e:
            print(f"❌ 工具注册检查失败: {e}")
            return False
        
        # 检查Docker连接
        try:
            import docker
            client = docker.from_env()
            info = client.info()
            print(f"✅ Docker连接正常 (版本: {info.get('ServerVersion', 'Unknown')})")
            client.close()
        except Exception as e:
            print(f"❌ Docker连接失败: {e}")
            return False
        
        await runtime.cleanup()
        print("✅ 所有MCP组件检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 组件检查异常: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(check_components())
    sys.exit(0 if success else 1)
EOF

# 运行组件检查
if docker-compose ps enhanced-reasoning-runtime | grep -q "running"; then
    docker cp check_mcp_components.py $(docker-compose ps -q enhanced-reasoning-runtime):/app/
    
    if docker-compose exec enhanced-reasoning-runtime python check_mcp_components.py; then
        print_success "MCP组件检查通过"
    else
        print_error "MCP组件检查失败"
    fi
    
    # 清理
    rm -f check_mcp_components.py
else
    print_error "Enhanced Runtime容器未运行，跳过组件检查"
fi

# 5. 检查动态MCP服务器
print_header "动态MCP服务器"

echo "检查动态安装的MCP服务器..."
dynamic_containers=$(docker ps --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}" | tail -n +2)

if [ -n "$dynamic_containers" ]; then
    echo "发现动态MCP服务器:"
    echo "$dynamic_containers"
else
    echo "暂无动态安装的MCP服务器"
fi

# 6. 检查端口使用情况
print_header "端口使用情况"

echo "检查MCP端口范围 (8100-8200)..."
used_ports=$(netstat -tuln 2>/dev/null | grep ":81[0-9][0-9]\|:82[0-9][0-9]" | wc -l || echo "0")
echo "已使用端口数量: $used_ports"

# 7. 资源使用情况
print_header "资源使用情况"

echo "Docker资源使用:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -10

# 8. 最近日志摘要
print_header "最近日志摘要"

echo "Enhanced Runtime 最近日志:"
docker-compose logs --tail=5 enhanced-reasoning-runtime

echo -e "\nToolScore 最近日志:"
docker-compose logs --tail=3 toolscore

# 9. 系统建议
print_header "系统建议"

# 检查环境变量
if [ -f ".env" ]; then
    if grep -q "your_.*_api_key_here" .env; then
        print_warning "检测到未配置的API密钥，请检查 .env 文件"
    else
        print_success "环境配置看起来正常"
    fi
else
    print_warning "未找到 .env 文件，请复制 env.example 并配置"
fi

# 检查磁盘空间
disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$disk_usage" -gt 80 ]; then
    print_warning "磁盘使用率较高 (${disk_usage}%)，可能影响容器运行"
else
    print_success "磁盘空间充足 (已用 ${disk_usage}%)"
fi

echo ""
echo "========================================"
echo "状态检查完成 $(date)"
echo ""
echo "🔧 常用管理命令:"
echo "   查看实时日志: docker-compose logs -f enhanced-reasoning-runtime"
echo "   重启服务: docker-compose restart enhanced-reasoning-runtime"
echo "   完整重启: docker-compose down && docker-compose up -d"
echo "   快速启动: ./scripts/quick_start_mcp.sh"
echo "   完整测试: ./scripts/test_mcp_complete.sh" 