#!/bin/bash

# MCP主动选择机制完整测试部署脚本
# 自动构建、部署和测试整个系统

set -e  # 遇到错误立即退出

echo "🚀 MCP主动选择机制完整测试部署"
echo "==============================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_step() {
    echo -e "\n${BLUE}📋 $1${NC}"
    echo "-----------------------------------------------"
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

# 检查环境
print_step "检查环境依赖"

if ! command -v docker &> /dev/null; then
    print_error "Docker未安装或不在PATH中"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose未安装或不在PATH中"
    exit 1
fi

print_success "Docker和Docker Compose检查通过"

# 检查必要的环境变量
print_step "检查环境变量"

if [ -z "$GEMINI_API_KEY" ]; then
    print_warning "GEMINI_API_KEY未设置，某些功能可能受限"
    read -p "是否继续？(y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    print_success "GEMINI_API_KEY已设置"
fi

# 清理旧容器和镜像
print_step "清理环境"

echo "停止现有容器..."
docker-compose down --remove-orphans || true

echo "清理未使用的镜像..."
docker image prune -f || true

print_success "环境清理完成"

# 构建镜像
print_step "构建Docker镜像"

echo "构建Enhanced Reasoning Runtime镜像..."
docker-compose build enhanced-reasoning-runtime

print_success "镜像构建完成"

# 启动基础服务
print_step "启动基础服务"

echo "启动Redis..."
docker-compose up -d redis

echo "等待Redis启动..."
sleep 10

echo "启动ToolScore..."
docker-compose up -d toolscore

echo "等待ToolScore启动..."
sleep 15

print_success "基础服务启动完成"

# 检查基础服务健康状态
print_step "检查基础服务状态"

echo "检查Redis状态..."
if docker-compose exec redis redis-cli ping | grep -q PONG; then
    print_success "Redis运行正常"
else
    print_error "Redis未正常运行"
    docker-compose logs redis
    exit 1
fi

echo "检查ToolScore状态..."
sleep 5
if docker-compose ps toolscore | grep -q "healthy\|running"; then
    print_success "ToolScore运行正常"
else
    print_warning "ToolScore可能还在启动中"
    docker-compose logs toolscore | tail -20
fi

# 启动Enhanced Reasoning Runtime
print_step "启动Enhanced Reasoning Runtime"

echo "启动Enhanced Reasoning Runtime容器..."
docker-compose up -d enhanced-reasoning-runtime

echo "等待容器完全启动..."
sleep 20

# 检查容器状态
if docker-compose ps enhanced-reasoning-runtime | grep -q "running"; then
    print_success "Enhanced Reasoning Runtime启动成功"
else
    print_error "Enhanced Reasoning Runtime启动失败"
    docker-compose logs enhanced-reasoning-runtime
    exit 1
fi

# 运行容器内测试
print_step "执行容器内测试"

echo "将测试脚本复制到容器..."
docker cp test_mcp_in_container.py $(docker-compose ps -q enhanced-reasoning-runtime):/app/

echo "在容器内执行测试..."
if docker-compose exec enhanced-reasoning-runtime python test_mcp_in_container.py; then
    print_success "容器内测试全部通过"
    TEST_SUCCESS=true
else
    print_error "容器内测试失败"
    TEST_SUCCESS=false
fi

# 显示服务状态
print_step "服务状态概览"

echo "当前运行的服务:"
docker-compose ps

echo -e "\n服务日志摘要:"
echo "Redis:"
docker-compose logs --tail=5 redis

echo -e "\nToolScore:"
docker-compose logs --tail=5 toolscore

echo -e "\nEnhanced Reasoning Runtime:"
docker-compose logs --tail=10 enhanced-reasoning-runtime

# 功能演示（如果测试通过）
if [ "$TEST_SUCCESS" = true ]; then
    print_step "功能演示"
    
    echo "演示MCP搜索工具的使用..."
    
    # 创建演示脚本
    cat > demo_mcp_usage.py << 'EOF'
import asyncio
import sys
sys.path.append('/app')

from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime

async def demo():
    print("🎭 MCP搜索工具使用演示")
    print("=" * 50)
    
    runtime = EnhancedReasoningRuntime()
    await runtime.initialize()
    
    # 演示工具需求分析
    print("📋 分析任务: 'Create a PDF report with charts'")
    
    result = await runtime.tool_library.execute_tool(
        tool_id="mcp-search-tool",
        action="analyze_tool_needs",
        parameters={
            "task_description": "Create a PDF report with charts and data visualization"
        }
    )
    
    if result.success:
        analysis = result.data.get("analysis", {})
        print(f"✅ 分析完成")
        print(f"   工具充足性: {analysis.get('has_sufficient_tools')}")
        print(f"   建议行动: {analysis.get('recommended_action')}")
        
        requirements = analysis.get('tool_requirements', [])
        if requirements:
            print(f"   识别到的工具需求:")
            for req in requirements:
                print(f"     - {req.get('description')}")
                
        print("\n🎯 演示: AI现在可以:")
        print("   ✅ 智能分析任务需求")
        print("   ✅ 识别工具缺口")
        print("   ✅ 主动选择搜索新工具")
        print("   ✅ 自动安装和注册MCP服务器")
    else:
        print(f"❌ 分析失败: {result.error_message}")
    
    await runtime.cleanup()

if __name__ == "__main__":
    asyncio.run(demo())
EOF

    docker cp demo_mcp_usage.py $(docker-compose ps -q enhanced-reasoning-runtime):/app/
    docker-compose exec enhanced-reasoning-runtime python demo_mcp_usage.py
fi

# 最终报告
print_step "部署测试报告"

if [ "$TEST_SUCCESS" = true ]; then
    print_success "🎉 MCP主动选择机制部署测试成功!"
    echo ""
    echo "✅ 功能验证完成:"
    echo "   - 多格式MCP服务器统一注册 ✓"
    echo "   - LLM驱动的工具缺口检测 ✓"
    echo "   - Docker容器化动态部署 ✓"
    echo "   - 主动工具选择机制 ✓"
    echo "   - 完整生命周期管理 ✓"
    echo ""
    echo "🚀 系统就绪! AI现在可以:"
    echo "   • 主动判断任务需要的工具"
    echo "   • 搜索和安装新的MCP服务器"
    echo "   • 扩展自己的能力范围"
    echo "   • 完成更复杂的任务"
    echo ""
    echo "📖 使用方法:"
    echo "   1. 向AI描述任务"
    echo "   2. AI将自动分析工具需求"
    echo "   3. 如需新工具，AI会主动搜索安装"
    echo "   4. 系统能力持续扩展"
else
    print_error "部署测试过程中发现问题"
    echo ""
    echo "🔍 故障排查建议:"
    echo "   1. 检查Docker和网络配置"
    echo "   2. 确认环境变量设置"
    echo "   3. 查看容器日志: docker-compose logs enhanced-reasoning-runtime"
    echo "   4. 重新运行测试: ./scripts/test_mcp_complete.sh"
fi

echo ""
echo "🔧 管理命令:"
echo "   查看日志: docker-compose logs enhanced-reasoning-runtime"
echo "   重启服务: docker-compose restart enhanced-reasoning-runtime"
echo "   停止服务: docker-compose down"
echo "   重新部署: $0"

echo ""
echo "==============================================="
echo "测试完成 $(date)"

exit $([ "$TEST_SUCCESS" = true ] && echo 0 || echo 1) 