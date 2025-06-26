# Agent Data Platform 功能演示指南

## 🎯 新功能亮点展示

本文档通过实际案例演示Agent Data Platform的核心新功能：**持久化记忆管理**、**多步推理能力**和**智能学习系统**。

---

## 🧠 演示1：持久化记忆管理

### 场景：跨任务的上下文保持
展示系统如何在多个任务间保持和利用会话记忆。

#### 步骤1：建立用户画像和研究方向
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "reasoning",
       "input": "我是一名AI研究员，专注于大语言模型的推理能力研究，特别关注Chain-of-Thought和Tree-of-Thought等推理技术",
       "context": {"session_id": "ai_researcher_session"},
       "priority": "medium"
     }'
```

**预期结果**: 系统记录用户的专业背景和研究兴趣

#### 步骤2：基于记忆的代码生成请求
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "基于我的研究方向，帮我生成一个实现Chain-of-Thought推理的Python示例代码",
       "context": {"session_id": "ai_researcher_session"},
       "priority": "high"
     }'
```

**系统行为**:
- 自动加载会话历史
- 识别用户的AI研究员身份
- 结合专业背景生成针对性代码
- 上下文注入到LLM提示词中

#### 步骤3：深化研究的后续任务
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research", 
       "input": "请深入分析我刚才提到的推理技术在实际应用中的性能对比",
       "context": {"session_id": "ai_researcher_session"},
       "max_steps": 12,
       "priority": "high"
     }'
```

**记忆效果展示**:
```json
{
  "memory_context": {
    "session_id": "ai_researcher_session",
    "context_applied": true,
    "previous_tasks_referenced": 2,
    "user_profile": "AI研究员，专注LLM推理技术",
    "research_focus": ["Chain-of-Thought", "Tree-of-Thought"],
    "context_summary": "=== 会话历史摘要 ===\n用户是AI研究员，已讨论CoT和ToT推理技术，生成了相关代码示例..."
  }
}
```

---

## 🔄 演示2：多步推理能力

### 场景：复杂研究任务的智能分解
展示系统如何将复杂任务分解为多个步骤，并动态调整执行策略。

#### 提交复杂研究任务
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research",
       "input": "深度调研AI Agent开发领域的最新趋势，特别关注多模态Agent、LangGraph框架的发展现状，以及2024年下半年到2025年的主要技术突破",
       "max_steps": 15,
       "context": {
         "session_id": "research_deep_dive",
         "timeout": 600
       },
       "priority": "high"
     }'
```

#### 系统自动规划执行
**步骤分解过程**:
```
Step 1: 工具暴露 (Tool Exposure)
├─ 向LLM暴露可用工具信息
├─ 持续时间: 0.1秒
└─ 状态: ✅ 成功

Step 2: 深度研究执行 (Research Execution)  
├─ 使用 mcp-deepsearch.comprehensive_research
├─ 查询: "AI Agent发展趋势、多模态Agent、LangGraph框架..."
├─ 持续时间: 162.5秒
├─ LLM交互: Gemini-1.5-pro (2.3秒响应)
└─ 状态: ✅ 成功
```

#### 实际执行结果
```json
{
  "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
  "success": true,
  "steps": 2,
  "max_steps_allowed": 15,
  "total_duration": 207.987,
  "reasoning_trace": {
    "decision_points": [
      {
        "step": 2,
        "decision": "选择comprehensive_research而非quick_research", 
        "reasoning": "任务要求深度调研，需要全面的研究能力",
        "confidence": 0.9
      }
    ],
    "tool_selection_log": [
      {
        "available_tools": ["mcp-deepsearch", "browser-use-mcp-server", "microsandbox-mcp-server", "mcp-search-tool"],
        "selected_tool": "mcp-deepsearch",
        "selection_reason": "最适合深度研究任务的工具"
      }
    ]
  }
}
```

---

## 🎯 演示3：智能学习和优化

### 场景：系统从执行历史中学习优化

#### 查看学习数据积累
```bash
# 检查学习数据文件
cat data/learning_data.json | jq '.'
```

**学习数据结构**:
```json
{
  "system_metrics": {
    "total_tasks_processed": 42,
    "successful_tasks": 40,
    "failed_tasks": 2,
    "average_execution_time": 145.3,
    "last_updated": "2025-06-20T19:29:21Z"
  },
  "decision_weights": {
    "tool_selection": {
      "mcp-deepsearch": 0.85,
      "microsandbox-mcp-server": 0.78,
      "browser-use-mcp-server": 0.72
    },
    "strategy_preference": {
      "comprehensive_research": 0.9,
      "quick_research": 0.6
    }
  },
  "pattern_memory": [
    {
      "pattern_id": "research_task_success",
      "description": "深度研究任务的成功执行模式",
      "success_rate": 0.95,
      "typical_tools": ["mcp-deepsearch"],
      "average_steps": 2.3,
      "context_factors": ["复杂查询", "长时间执行"]
    }
  ],
  "performance_cache": {
    "tool_performance": {
      "mcp-deepsearch": {
        "average_duration": 162.5,
        "success_rate": 1.0,
        "last_used": "2025-06-20T19:28:47Z"
      }
    }
  }
}
```

#### 展示学习效果的任务
```bash
# 提交类似的研究任务，观察系统优化效果
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research",
       "input": "分析2024年机器学习模型的最新突破和应用趋势",
       "max_steps": 10,
       "priority": "medium"
     }'
```

**学习效果体现**:
- 系统根据历史成功率优先选择 `mcp-deepsearch`
- 基于模式记忆预估需要2-3步完成
- 利用性能缓存数据优化执行策略

---

## 📊 演示4：记忆系统状态监控

### 实时记忆状态查询
```bash
# 通过健康检查查看记忆系统状态
curl http://localhost:8000/health | jq '.memory_stats'
```

**输出示例**:
```json
{
  "memory_stats": {
    "cached_sessions": 12,
    "total_stored_steps": 156,
    "redis_available": true,
    "cache_hit_rate": 0.89,
    "average_retrieval_time": 45
  }
}
```

### Redis中的记忆数据检查
```bash
# 连接Redis查看存储的记忆数据
redis-cli

# 查看会话列表
KEYS "memory:session:*"

# 查看特定会话的步骤
LRANGE "memory:session:ai_researcher_session:steps" 0 -1

# 查看跨会话洞察缓存
GET "memory:insights:cross_session"
```

---

## 🔧 演示5：错误恢复和记忆保持

### 场景：任务失败时的记忆管理

#### 提交一个可能失败的任务
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "在microsandbox中执行一个故意有错误的代码：print(undefined_variable)",
       "context": {"session_id": "error_demo_session"},
       "priority": "low"
     }'
```

#### 查看失败任务的记忆记录
**系统行为**:
- 记录失败原因和错误类型
- 保存失败任务的上下文信息
- 为后续任务提供错误避免经验

#### 提交修复任务
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "请修复刚才的代码错误，并重新执行",
       "context": {"session_id": "error_demo_session"},
       "priority": "medium"
     }'
```

**记忆辅助效果**:
- 系统记住上次失败的原因
- 在新任务中避免相同错误
- 提供更准确的代码修复建议

---

## 📈 演示6：性能和扩展性展示

### 批量任务处理
```bash
# 创建批量测试脚本
cat > demo_batch_tasks.sh << 'EOF'
#!/bin/bash

# 模拟多用户、多会话的并发场景
for i in {1..5}; do
  echo "提交任务 $i ..."
  curl -X POST "http://localhost:8000/api/v1/tasks" \
       -H "Content-Type: application/json" \
       -d "{
         \"task_type\": \"code\",
         \"input\": \"计算数字 ${i} 的阶乘并显示过程\",
         \"context\": {\"session_id\": \"batch_session_${i}\"},
         \"max_steps\": 5,
         \"priority\": \"medium\"
       }" &
done

wait
echo "所有任务已提交"
EOF

chmod +x demo_batch_tasks.sh
./demo_batch_tasks.sh
```

### 记忆系统压力测试
```bash
# 测试记忆系统在高负载下的表现
python3 << 'EOF'
import asyncio
import aiohttp
import json

async def test_memory_load():
    """测试记忆系统在高并发下的性能"""
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # 创建100个并发任务，每个使用不同的session_id
        for i in range(100):
            task_data = {
                "task_type": "reasoning",
                "input": f"这是测试任务 {i}，请记住这个序号",
                "context": {"session_id": f"stress_test_session_{i % 10}"},
                "priority": "low"
            }
            
            task = session.post(
                "http://localhost:8000/api/v1/tasks",
                json=task_data,
                headers={"Content-Type": "application/json"}
            )
            tasks.append(task)
        
        # 等待所有任务完成
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in responses if not isinstance(r, Exception))
        print(f"成功提交任务: {success_count}/100")

# 运行压力测试
asyncio.run(test_memory_load())
EOF
```

---

## 🎓 高级功能演示

### 自定义记忆策略
```python
# 演示如何通过代码直接操作记忆系统
from core.memory_manager import MemoryManager
from core.redis_manager import RedisManager

async def custom_memory_demo():
    # 初始化记忆管理器
    redis_manager = RedisManager("redis://localhost:6379")
    memory_manager = MemoryManager(redis_manager=redis_manager)
    
    # 手动存储重要的会话步骤
    await memory_manager.store_conversation_step(
        task_id="demo_task_001",
        session_id="custom_demo_session",
        user_input="我需要学习深度学习的最佳实践",
        agent_output="我将为您提供一个全面的深度学习最佳实践指南...",
        thinking_summary="用户想学习深度学习，需要提供系统性的指导",
        tools_used=["knowledge_base", "tutorial_generator"],
        success=True,
        metadata={
            "learning_stage": "beginner",
            "preferred_format": "step_by_step",
            "domains": ["computer_vision", "nlp"]
        }
    )
    
    # 获取上下文摘要
    summary = await memory_manager.generate_context_summary("custom_demo_session")
    print(f"生成的上下文摘要: {summary}")
    
    # 获取跨会话洞察
    insights = await memory_manager.get_cross_session_insights()
    for insight in insights:
        print(f"洞察: {insight}")

# 运行演示
import asyncio
asyncio.run(custom_memory_demo())
```

### 步骤规划定制
```python
# 演示自定义步骤规划策略
from core.step_planner import StepPlanner, PlanningStrategy
from core.interfaces import TaskSpec

async def custom_planning_demo():
    # 创建自定义规划器
    step_planner = StepPlanner(llm_client, memory_manager)
    
    # 定义复杂任务
    complex_task = TaskSpec(
        task_id="complex_analysis_task",
        description="分析一个大型数据集，生成可视化报告，并提供业务建议",
        max_steps=20,
        priority="high"
    )
    
    # 生成初始执行计划
    plan = await step_planner.generate_initial_plan(
        task=complex_task,
        available_tools=["data_analyzer", "chart_generator", "report_writer"],
        session_id="analysis_session",
        strategy=PlanningStrategy.ADAPTIVE
    )
    
    print(f"计划包含 {len(plan.planned_steps)} 个步骤")
    print(f"预估总耗时: {plan.estimated_total_duration:.1f} 秒")
    print(f"使用策略: {plan.strategy.value}")
    
    for i, step in enumerate(plan.planned_steps):
        print(f"步骤 {i+1}: {step.action} -> {step.tool_id}")

# 运行规划演示
asyncio.run(custom_planning_demo())
```

---

## 🔍 故障排除演示

### 记忆系统诊断
```bash
# 检查记忆系统健康状态
echo "=== 记忆系统诊断 ==="

# 1. Redis连接测试
redis-cli ping && echo "✅ Redis连接正常" || echo "❌ Redis连接失败"

# 2. 记忆数据完整性检查
redis-cli KEYS "memory:*" | wc -l
echo "记忆键数量: $(redis-cli KEYS 'memory:*' | wc -l)"

# 3. 学习数据文件检查
if [ -f "data/learning_data.json" ]; then
    echo "✅ 学习数据文件存在"
    echo "文件大小: $(du -h data/learning_data.json | cut -f1)"
else
    echo "❌ 学习数据文件缺失"
fi

# 4. 系统API健康检查
curl -s http://localhost:8000/health | jq '.memory_stats // "记忆状态不可用"'
```

### 性能监控命令
```bash
# 实时监控系统性能
echo "=== 性能监控 ==="

# 监控Redis内存使用
redis-cli INFO memory | grep used_memory_human

# 监控任务队列长度
echo "队列长度: $(redis-cli XLEN tasks:reasoning)"

# 监控系统进程
ps aux | grep -E "(main.py|redis)" | grep -v grep

# 实时日志监控 (在新终端中运行)
tail -f logs/main_test.log | grep -E "(记忆|Memory|步骤|Step|成功|成功)"
```

---

## 📝 演示总结

通过以上演示，我们展示了Agent Data Platform的核心新功能：

### 🧠 记忆管理系统
- **跨任务上下文保持**: 系统能够记住用户的身份、偏好和历史交互
- **智能上下文摘要**: 为LLM提供精炼的历史背景，提高决策质量
- **Redis持久化**: 确保记忆数据在系统重启后仍然可用

### 🔄 多步推理能力  
- **智能任务分解**: 复杂任务自动分解为多个可执行步骤
- **动态步骤调整**: 根据执行结果实时优化后续步骤
- **执行轨迹记录**: 完整记录每个步骤的决策过程和执行结果

### 🎯 智能学习系统
- **决策权重优化**: 基于历史成功率调整工具选择权重
- **模式识别**: 从成功执行中提取可复用的模式
- **性能缓存**: 记录工具性能数据，优化未来选择

### 🚀 系统优势
- **向后兼容**: 现有API无需修改即可享受新功能
- **高性能**: 记忆检索和步骤规划开销最小化
- **高可用**: 支持Redis降级，确保核心功能始终可用
- **可扩展**: 模块化设计，易于添加新的记忆策略和规划算法

这些功能将Agent Data Platform从一个简单的任务执行引擎升级为具备学习能力的智能Agent基础平台。

---

**演示环境要求**: 
- 系统正常运行 (`python main.py`)
- Redis服务可用
- GEMINI_API_KEY已配置
- 所有MCP服务器正常启动

**获取更多信息**:
- 技术文档: `docs/MEMORY_AND_MULTISTEP_GUIDE.md`
- API规范: `docs/AGENT_API_PROTOCOL_SPECIFICATION.md`
- 系统状态: `docs/SYSTEM_STATUS_2025.md`