#!/bin/bash

# 真实MCP服务器测试启动脚本

echo "🚀 启动真实MCP服务器测试环境"

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 检查Redis是否运行
if ! docker ps | grep -q redis; then
    echo "🔄 启动Redis..."
    docker run -d --name test-redis -p 6379:6379 redis:alpine
fi

# 检查Python环境
echo "🐍 检查Python环境..."
python3 -c "import aiohttp, docker, redis" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 安装缺少的Python包..."
    pip install aiohttp docker redis
fi

# 设置环境变量
export REDIS_URL="redis://localhost:6379"
export DOCKER_HOST="unix:///var/run/docker.sock"

echo "📋 当前配置:"
echo "  Redis URL: $REDIS_URL"
echo "  Docker Host: $DOCKER_HOST"

# 运行测试
echo "🧪 开始运行真实MCP服务器测试..."
cd "$(dirname "$0")/.."
python3 scripts/test_real_mcp_install.py

echo "✅ 测试完成!" 