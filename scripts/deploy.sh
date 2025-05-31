#!/bin/bash
# scripts/deploy.sh

set -e

echo "🚀 Deploying Agent Data Platform..."

# 检查tasks.jsonl
if [ ! -f "tasks.jsonl" ]; then
    echo "📝 Creating sample tasks.jsonl..."
    cat > tasks.jsonl << 'EOF'
{"task_id": "demo_fib", "task_type": "code", "description": "写一个Python函数计算斐波那契数列第10项", "expected_tools": ["python_executor"], "constraints": {}, "max_steps": 5}
{"task_id": "demo_search", "task_type": "web", "description": "搜索Python编程教程", "expected_tools": ["web_search"], "constraints": {"start_url": "https://www.google.com"}, "max_steps": 3}
{"task_id": "demo_prime", "task_type": "code", "description": "找出100以内的所有质数", "expected_tools": ["python_executor"], "constraints": {}, "max_steps": 5}
EOF
    echo "✅ Sample tasks created"
fi

# 部署模式选择
MODE=${1:-"minimal"}

if [ "$MODE" = "full" ]; then
    echo "🎯 Deploying full production stack..."
    docker-compose up -d
else
    echo "🎯 Deploying minimal stack for testing..."
    docker-compose -f docker-compose.minimal.yml up -d
fi

# 等待服务启动
echo "⏳ Waiting for services to start..."
sleep 30

# 检查服务状态
echo "🔍 Checking service status..."
docker-compose ps

# 显示访问信息
echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📊 Monitoring URLs:"
if [ "$MODE" = "full" ]; then
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
fi
echo "  - Sandbox Metrics: http://localhost:8001/metrics"
if [ "$MODE" = "full" ]; then
    echo "  - Web Runtime Metrics: http://localhost:8002/metrics"
fi
echo ""
echo "📁 Output directory: ./output/trajectories/"
echo ""
echo "🔍 Monitor progress:"
echo "  watch -n5 'ls output/trajectories | wc -l'"
echo ""
echo "🛑 Stop all services:"
echo "  docker-compose down"