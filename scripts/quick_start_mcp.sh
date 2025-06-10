#!/bin/bash

# MCP主动选择机制快速启动脚本
# 快速启动和验证系统

set -e

echo "🚀 MCP主动选择机制快速启动"
echo "=================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() {
    echo -e "\n${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# 检查环境变量
print_step "检查配置"

if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        print_warning ".env文件不存在，正在从env.example创建..."
        cp env.example .env
        echo "请编辑.env文件并填入你的API密钥，然后重新运行此脚本"
        echo "至少需要配置: GEMINI_API_KEY"
        exit 1
    else
        echo "❌ 未找到env.example文件"
        exit 1
    fi
fi

# 加载环境变量
source .env

if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_gemini_api_key_here" ]; then
    print_warning "请在.env文件中配置有效的GEMINI_API_KEY"
    exit 1
fi

print_success "环境配置检查通过"

# 快速启动
print_step "启动服务"

echo "停止现有服务..."
docker-compose down --remove-orphans || true

echo "启动核心服务..."
docker-compose up -d redis toolscore

echo "等待服务启动..."
sleep 15

echo "启动Enhanced Reasoning Runtime..."
docker-compose up -d enhanced-reasoning-runtime

echo "等待系统就绪..."
sleep 20

# 简单验证
print_step "验证系统状态"

if docker-compose ps enhanced-reasoning-runtime | grep -q "running"; then
    print_success "Enhanced Reasoning Runtime运行正常"
else
    echo "❌ Enhanced Reasoning Runtime启动失败"
    docker-compose logs enhanced-reasoning-runtime | tail -10
    exit 1
fi

# 创建简化测试
cat > quick_test.py << 'EOF'
import asyncio
import sys
sys.path.append('/app')

async def quick_test():
    try:
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        
        print("🧪 快速功能测试")
        runtime = EnhancedReasoningRuntime()
        await runtime.initialize()
        
        # 检查MCP搜索工具是否注册
        tools = await runtime.tool_library.get_all_tools()
        mcp_tool_found = any(tool.tool_id == "mcp-search-tool" for tool in tools)
        
        if mcp_tool_found:
            print("✅ MCP搜索工具已注册")
        else:
            print("❌ MCP搜索工具未找到")
            return False
        
        # 简单的工具分析测试
        result = await runtime.tool_library.execute_tool(
            tool_id="mcp-search-tool",
            action="analyze_tool_needs",
            parameters={"task_description": "generate an image"}
        )
        
        if result.success:
            print("✅ 工具分析功能正常")
        else:
            print(f"❌ 工具分析失败: {result.error_message}")
            return False
        
        await runtime.cleanup()
        print("✅ 快速测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)
EOF

# 在容器中运行快速测试
echo "执行快速功能测试..."
docker cp quick_test.py $(docker-compose ps -q enhanced-reasoning-runtime):/app/

if docker-compose exec enhanced-reasoning-runtime python quick_test.py; then
    print_success "🎉 系统启动成功！"
    
    echo ""
    echo "✅ MCP主动选择机制已就绪:"
    echo "   - Enhanced Reasoning Runtime ✓"
    echo "   - MCP搜索工具 ✓" 
    echo "   - 动态安装能力 ✓"
    echo ""
    echo "🎯 现在你可以:"
    echo "   1. 向AI描述需要完成的任务"
    echo "   2. AI会自动分析工具需求"
    echo "   3. 如需新工具，AI会主动搜索安装"
    echo "   4. 系统能力持续扩展"
    echo ""
    echo "📖 管理命令:"
    echo "   查看日志: docker-compose logs -f enhanced-reasoning-runtime"
    echo "   重启服务: docker-compose restart enhanced-reasoning-runtime"
    echo "   停止服务: docker-compose down"
    echo "   完整测试: ./scripts/test_mcp_complete.sh"
    
    # 清理临时文件
    rm -f quick_test.py
    
else
    echo "❌ 快速测试失败"
    echo "请运行完整测试进行诊断: ./scripts/test_mcp_complete.sh"
    docker-compose logs enhanced-reasoning-runtime | tail -20
    exit 1
fi

echo ""
echo "=================================="
echo "快速启动完成 $(date)" 