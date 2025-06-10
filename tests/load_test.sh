#!/bin/bash

# 🚀 Agent数据平台负载测试脚本
# 生成混合类型测试任务，监控系统性能

set -e

echo "🔥 开始负载测试..."

# 配置参数
CODE_TASKS=50
WEB_TASKS=20
TEST_DURATION=300  # 5分钟
MONITOR_INTERVAL=10

# 清理旧测试结果
echo "🧹 清理旧测试结果..."
rm -f load_test_tasks.jsonl
rm -rf output/trajectories/load_test_*

# 生成代码执行任务
echo "📝 生成 $CODE_TASKS 个代码任务..."
for i in $(seq 1 $CODE_TASKS); do
    cat >> load_test_tasks.jsonl << EOF
{"task_id":"load_test_code_$i","task_type":"code","description":"计算第 $i 个斐波那契数","expected_tools":["python_executor"],"max_steps":5}
EOF
done

# 生成Web导航任务
echo "🌐 生成 $WEB_TASKS 个Web任务..."
for i in $(seq 1 $WEB_TASKS); do
    cat >> load_test_tasks.jsonl << EOF
{"task_id":"load_test_web_$i","task_type":"web","description":"搜索并获取第 $i 个技术文档","expected_tools":["browser"],"max_steps":8}
EOF
done

echo "✅ 生成了 $((CODE_TASKS + WEB_TASKS)) 个测试任务"

# 备份原始任务文件
if [ -f tasks.jsonl ]; then
    cp tasks.jsonl tasks.jsonl.backup
fi

# 替换任务文件
cp load_test_tasks.jsonl tasks.jsonl

# 启动完整服务栈
echo "🚀 启动完整服务栈..."
docker-compose up -d

# 等待服务就绪
echo "⏳ 等待服务启动..."
sleep 30

# 检查服务健康状态
echo "🏥 检查服务健康状态..."
for service in redis dispatcher sandbox-runtime web-runtime; do
    if docker-compose ps $service | grep -q "Up"; then
        echo "✅ $service 运行正常"
    else
        echo "❌ $service 启动失败"
        docker-compose logs $service
        exit 1
    fi
done

# 开始监控
echo "📊 开始负载测试监控 (持续 ${TEST_DURATION}s)..."
START_TIME=$(date +%s)
INITIAL_COMPLETED=0

# 获取初始完成数
if [ -d "output/trajectories" ]; then
    INITIAL_COMPLETED=$(ls output/trajectories/*.json 2>/dev/null | wc -l)
fi

echo "初始完成任务数: $INITIAL_COMPLETED"
echo "目标任务数: $((CODE_TASKS + WEB_TASKS))"
echo "开始时间: $(date)"
echo "预计结束时间: $(date -d "+${TEST_DURATION} seconds")"
echo ""

# 监控循环
while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    if [ $ELAPSED -ge $TEST_DURATION ]; then
        break
    fi
    
    # 获取当前指标
    CURRENT_COMPLETED=0
    if [ -d "output/trajectories" ]; then
        CURRENT_COMPLETED=$(ls output/trajectories/*.json 2>/dev/null | wc -l)
    fi
    
    TASKS_PROCESSED=$((CURRENT_COMPLETED - INITIAL_COMPLETED))
    THROUGHPUT=$(echo "scale=2; $TASKS_PROCESSED / ($ELAPSED / 60)" | bc -l 2>/dev/null || echo "0")
    
    # 获取队列大小
    CODE_QUEUE_SIZE=$(docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:code 2>/dev/null || echo "0")
    WEB_QUEUE_SIZE=$(docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:web 2>/dev/null || echo "0")
    
    # 获取错误统计
    ERRORS=$(curl -s http://localhost:8001/metrics 2>/dev/null | grep "tasks_failed_total" | awk '{print $2}' || echo "0")
    
    # 计算成功率
    if [ $TASKS_PROCESSED -gt 0 ]; then
        SUCCESS_RATE=$(echo "scale=2; (($TASKS_PROCESSED - $ERRORS) * 100) / $TASKS_PROCESSED" | bc -l 2>/dev/null || echo "100")
    else
        SUCCESS_RATE="100"
    fi
    
    # 显示实时统计
    echo "[$(date +'%H:%M:%S')] 已运行: ${ELAPSED}s | 完成: $TASKS_PROCESSED/$((CODE_TASKS + WEB_TASKS)) | 吞吐量: ${THROUGHPUT}/min | 队列: C:$CODE_QUEUE_SIZE W:$WEB_QUEUE_SIZE | 成功率: ${SUCCESS_RATE}% | 错误: $ERRORS"
    
    sleep $MONITOR_INTERVAL
done

echo ""
echo "🏁 负载测试完成！"

# 最终统计
FINAL_COMPLETED=0
if [ -d "output/trajectories" ]; then
    FINAL_COMPLETED=$(ls output/trajectories/*.json 2>/dev/null | wc -l)
fi

FINAL_PROCESSED=$((FINAL_COMPLETED - INITIAL_COMPLETED))
FINAL_THROUGHPUT=$(echo "scale=2; $FINAL_PROCESSED / ($TEST_DURATION / 60)" | bc -l 2>/dev/null || echo "0")

# 分析成功失败情况
SUCCESS_COUNT=0
FAILED_COUNT=0

if [ -d "output/trajectories" ]; then
    for file in output/trajectories/load_test_*.json; do
        if [ -f "$file" ]; then
            if jq -r '.success' "$file" 2>/dev/null | grep -q "true"; then
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            else
                FAILED_COUNT=$((FAILED_COUNT + 1))
            fi
        fi
    done
fi

FINAL_SUCCESS_RATE=$(echo "scale=2; ($SUCCESS_COUNT * 100) / $FINAL_PROCESSED" | bc -l 2>/dev/null || echo "0")

echo "📈 === 负载测试结果摘要 ==="
echo "测试时长: ${TEST_DURATION}s ($(echo "scale=1; $TEST_DURATION / 60" | bc -l)分钟)"
echo "目标任务: $((CODE_TASKS + WEB_TASKS)) (代码:$CODE_TASKS, Web:$WEB_TASKS)"
echo "完成任务: $FINAL_PROCESSED"
echo "成功任务: $SUCCESS_COUNT"
echo "失败任务: $FAILED_COUNT"
echo "完成率: $(echo "scale=1; ($FINAL_PROCESSED * 100) / ($CODE_TASKS + $WEB_TASKS)" | bc -l)%"
echo "成功率: ${FINAL_SUCCESS_RATE}%"
echo "平均吞吐量: ${FINAL_THROUGHPUT} 任务/分钟"
echo ""

# 性能分析
echo "🔍 === 性能分析 ==="

# 检查资源使用
echo "Docker容器资源使用:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""
echo "Redis队列状态:"
echo "代码队列剩余: $(docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:code 2>/dev/null || echo "N/A")"
echo "Web队列剩余: $(docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:web 2>/dev/null || echo "N/A")"

echo ""
echo "系统Metrics:"
curl -s http://localhost:8001/metrics 2>/dev/null | grep -E "(tasks_completed_total|tasks_failed_total|queue_size|cache_hits_total)" || echo "无法获取metrics"

# 清理测试文件
echo ""
echo "🧹 清理测试环境..."
rm -f load_test_tasks.jsonl

# 恢复原始任务文件
if [ -f tasks.jsonl.backup ]; then
    mv tasks.jsonl.backup tasks.jsonl
    echo "✅ 已恢复原始任务文件"
fi

echo ""
echo "🎉 负载测试完成！查看详细轨迹: output/trajectories/load_test_*"
echo "💡 提示: 使用 'docker-compose logs' 查看详细日志"
echo "🛑 停止服务: docker-compose down"