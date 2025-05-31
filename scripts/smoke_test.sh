#!/bin/bash
# scripts/smoke_test.sh

set -e

echo "🔍 Starting comprehensive smoke test..."

# 清理之前的测试结果
echo "🧹 Cleaning up previous test results..."
rm -rf output/trajectories/test_*
rm -f test_tasks.jsonl

# 创建测试任务
echo "📝 Creating test tasks..."
cat > test_tasks.jsonl << 'EOF'
{"task_id": "test_fib_smoke", "task_type": "code", "description": "Calculate fibonacci(5)", "expected_tools": ["python_executor"], "constraints": {}, "max_steps": 3}
{"task_id": "test_fact_smoke", "task_type": "code", "description": "Calculate factorial(4)", "expected_tools": ["python_executor"], "constraints": {}, "max_steps": 3}
EOF

# 备份原tasks.jsonl
if [ -f "tasks.jsonl" ]; then
    cp tasks.jsonl tasks.jsonl.bak
fi

# 使用测试任务
cp test_tasks.jsonl tasks.jsonl

# 启动最小配置
echo "🚀 Starting minimal services..."
docker-compose -f docker-compose.minimal.yml down
docker-compose -f docker-compose.minimal.yml up -d

# 健康检查函数
check_service() {
    local service=$1
    local url=$2
    local max_attempts=30
    
    echo "Checking $service..."
    for i in $(seq 1 $max_attempts); do
        if curl -f -s "$url" > /dev/null 2>&1; then
            echo "✅ $service is healthy"
            return 0
        fi
        sleep 2
    done
    
    echo "❌ $service failed health check"
    return 1
}

# 等待服务启动
echo "⏳ Waiting for services to initialize..."
sleep 45

# 健康检查
echo "🏥 Performing health checks..."
check_service "Redis" "http://localhost:6379" || (echo "Note: Redis check via HTTP not available, assuming healthy")
check_service "Sandbox Runtime" "http://localhost:8001/metrics"

# 检查Redis连接
echo "🔗 Testing Redis connection..."
if docker exec $(docker-compose -f docker-compose.minimal.yml ps -q redis) redis-cli ping | grep -q PONG; then
    echo "✅ Redis connection successful"
else
    echo "❌ Redis connection failed"
    exit 1
fi

# 等待任务执行
echo "⏳ Waiting for task execution (60 seconds)..."
for i in $(seq 1 12); do
    completed=$(ls output/trajectories/test_*.json 2>/dev/null | wc -l)
    echo "Progress: $completed/2 tasks completed"
    if [ "$completed" -eq 2 ]; then
        break
    fi
    sleep 5
done

# 检查结果
echo "🔍 Checking test results..."
completed_tasks=$(ls output/trajectories/test_*.json 2>/dev/null | wc -l)

if [ "$completed_tasks" -eq 2 ]; then
    echo "✅ All test tasks completed successfully"
    
    # 验证轨迹文件内容
    for file in output/trajectories/test_*.json; do
        if jq -e '.success' "$file" > /dev/null 2>&1; then
            task_id=$(jq -r '.task_id' "$file")
            success=$(jq -r '.success' "$file")
            echo "✅ Task $task_id: success=$success"
        else
            echo "❌ Invalid trajectory file: $file"
            exit 1
        fi
    done
else
    echo "❌ Only $completed_tasks/2 tasks completed"
    echo "📋 Checking logs for errors..."
    
    echo "=== Dispatcher Logs ==="
    docker-compose -f docker-compose.minimal.yml logs dispatcher | tail -20
    
    echo "=== Sandbox Runtime Logs ==="
    docker-compose -f docker-compose.minimal.yml logs sandbox-runtime | tail -20
    
    exit 1
fi

# 检查metrics
echo "📊 Checking metrics..."
if curl -s http://localhost:8001/metrics | grep -q "tasks_completed_total"; then
    echo "✅ Metrics are working"
    
    # 显示一些关键指标
    echo "📈 Key metrics:"
    curl -s http://localhost:8001/metrics | grep -E "(tasks_completed_total|tasks_failed_total|task_duration)" | head -5
else
    echo "❌ Metrics not found"
    exit 1
fi

# 恢复原tasks.jsonl
if [ -f "tasks.jsonl.bak" ]; then
    mv tasks.jsonl.bak tasks.jsonl
else
    rm -f tasks.jsonl
fi

# 清理测试文件
rm -f test_tasks.jsonl

echo ""
echo "🎉 Smoke test completed successfully!"
echo ""
echo "📊 Test summary:"
echo "  - Services: ✅ Healthy"
echo "  - Tasks: ✅ $completed_tasks/2 completed"
echo "  - Metrics: ✅ Working"
echo ""
echo "🛑 To stop test services:"
echo "  docker-compose -f docker-compose.minimal.yml down"