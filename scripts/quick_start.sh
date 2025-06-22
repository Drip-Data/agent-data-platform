#!/bin/bash

# Agent Data Platform 快速启动脚本

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 切换到项目根目录
cd "$PROJECT_ROOT"

echo "🚀 Agent Data Platform 快速启动脚本"
echo "=================================="
echo "📁 工作目录: $PROJECT_ROOT"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未找到，请先安装Python3"
    exit 1
fi

# 检查Redis
if ! command -v redis-cli &> /dev/null; then
    echo "⚠️  Redis CLI 未找到，请确保Redis已安装并运行"
fi

# 检查Redis服务状态
if ! redis-cli ping &> /dev/null; then
    echo "⚠️  Redis服务未运行，尝试启动..."
    if command -v brew &> /dev/null; then
        brew services start redis
    else
        echo "❌ 请手动启动Redis服务"
        exit 1
    fi
fi

echo "✅ 环境检查完成"
echo ""

# 显示选项
echo "请选择运行模式:"
echo "1) 交互式模式 (启动服务 + 交互式命令)"
echo "2) 批处理模式 (启动服务 + 自动注入测试任务)"
echo "3) 仅启动服务"
echo "4) 仅注入任务 (需要服务已运行)"
echo "5) 运行基础测试"

read -p "请输入选择 (1-5): " choice

case $choice in
    1)
        echo "🎮 启动交互式模式..."
        python3 scripts/run_system.py --mode interactive
        ;;
    2)
        echo "🔄 启动批处理模式..."
        python3 scripts/run_system.py --mode batch --tasks-file data/test_tasks.jsonl
        ;;
    3)
        echo "⚙️  启动服务..."
        python3 main.py
        ;;
    4)
        echo "📋 注入测试任务..."
        python3 scripts/run_system.py --no-start --mode batch --tasks-file data/test_tasks.jsonl
        ;;
    5)
        echo "🧪 运行基础测试..."
        python3 -m pytest tests/test_mcp_server_startup.py -v
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac