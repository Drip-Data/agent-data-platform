# Memory & Multi-Step Reasoning Guide

## 🧠 记忆系统和多步推理使用指南

本指南介绍新增的记忆管理和多步推理功能，帮助您构建具备长期记忆和智能规划能力的AI Agent。

---

## 🚀 核心功能概览

### 1. MemoryManager - 记忆管理器
- **持久化会话记忆**：跨任务和跨会话的历史存储
- **上下文摘要**：为LLM提供简洁的历史上下文
- **跨会话洞察**：从历史数据中提取模式和经验
- **Redis支持**：生产环境的高性能持久化存储

### 2. StepPlanner - 步骤规划器
- **智能任务分解**：将复杂任务分解为可执行步骤
- **动态计划调整**：根据执行结果实时优化策略
- **多种规划策略**：顺序、自适应、并行、迭代执行
- **完成检查**：智能判断任务是否达成目标

### 3. Enhanced Runtime - 增强运行时
- **动态步骤数**：不再限制为2步，支持复杂长流程任务
- **记忆集成**：自动存储执行历史和会话摘要
- **上下文注入**：LLM决策时自动获得历史经验
- **会话管理**：统一的会话ID和记忆生命周期

---

## 📋 使用示例

### 基础用法 - 创建多步任务

```python
from core.interfaces import TaskSpec
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime

# 创建多步任务
task = TaskSpec(
    task_id="research_ai_trends_2024",
    description="深度调研2024年AI技术发展趋势，分析各领域进展并生成详细报告",
    max_steps=15,  # 允许最多15步执行
    priority="high"
)

# 执行任务 - 系统将自动进行多步规划和执行
runtime = EnhancedReasoningRuntime(config_manager, llm_client, toolscore_client, redis_manager)
result = await runtime.execute(task)
```

### 实际运行案例 - AI Agent研究任务

**真实案例**: 以下是系统实际执行的AI研究任务案例，展示了多步推理的完整过程。

```bash
# 实际提交的任务
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research",
       "input": "深度调研AI Agent开发领域的最新趋势，特别关注多模态Agent、LangGraph框架的发展现状，以及2024年下半年到2025年的主要技术突破",
       "max_steps": 15,
       "priority": "high"
     }'
```

**执行结果**:
```json
{
  "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
  "success": true,
  "total_duration": 207.987,
  "steps_completed": 2,
  "max_steps_used": 15,
  "final_result": "任务完成。生成结果：基于您提供的搜索结果，以下是一份关于AI Agent领域当前趋势、多模态Agent状态、LangGraph框架发展与采用，以及2024年末至2025年预期重大技术突破的全面、专业的深度分析报告...",
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

**系统智能决策过程**:
1. **Step 1**: 自动暴露可用工具给LLM进行规划
2. **Step 2**: 基于任务复杂度选择深度研究工具，执行全面调研
3. **智能终止**: 任务目标达成后提前结束，未使用完全部15步

### 高级用法 - 直接使用记忆管理器

```python
from core.memory_manager import MemoryManager

# 初始化记忆管理器
memory_manager = MemoryManager(redis_manager=redis_manager)

# 存储会话步骤
step_id = await memory_manager.store_conversation_step(
    task_id="analysis_task",
    session_id="user_session_001",
    user_input="分析这份财务报表",
    agent_output="已完成财务分析，发现以下关键指标...",
    thinking_summary="基于财务数据进行了比率分析和趋势分析",
    tools_used=["excel-analyzer", "chart-generator"],
    success=True,
    metadata={"analysis_type": "financial", "file_size": "2.5MB"}
)

# 获取会话上下文
context = await memory_manager.get_conversation_context(
    session_id="user_session_001",
    max_steps=10
)

# 生成上下文摘要用于LLM
summary = await memory_manager.generate_context_summary("user_session_001")
print(summary)
```

### 专家用法 - 自定义步骤规划

```python
from core.step_planner import StepPlanner, PlanningStrategy

# 创建步骤规划器
step_planner = StepPlanner(llm_client, memory_manager)

# 生成执行计划
plan = await step_planner.generate_initial_plan(
    task=task,
    available_tools=["web-search", "python-executor", "data-analyzer"],
    session_id="expert_session_001"
)

print(f"计划包含 {len(plan.planned_steps)} 个步骤")
print(f"预估耗时: {plan.estimated_total_duration:.1f} 秒")
print(f"策略: {plan.strategy.value}")
print(f"置信度: {plan.confidence:.2%}")

# 逐步执行计划
for step_idx in range(len(plan.planned_steps)):
    next_step = await step_planner.plan_next_step(
        task, executed_steps, available_tools, session_id
    )
    
    if not next_step:
        print("任务完成或无需更多步骤")
        break
    
    print(f"执行步骤: {next_step.action} -> {next_step.tool_id}")
    # 执行步骤逻辑...
```

---

## ⚙️ 配置和集成

### 在现有系统中启用记忆功能

1. **更新Runtime初始化**
```python
# 传递redis_manager以启用持久化记忆
runtime = EnhancedReasoningRuntime(
    config_manager=config_manager,
    llm_client=llm_client, 
    toolscore_client=toolscore_client,
    redis_manager=redis_manager  # 新增参数
)
```

2. **配置Redis存储**
```python
from core.redis_manager import RedisManager

redis_manager = RedisManager(
    redis_url="redis://localhost:6379",
    fallback_mode=False  # 生产环境设为False
)
```

3. **任务规范更新**
```python
# 现在支持动态max_steps
task = TaskSpec(
    task_id="complex_task",
    description="复杂的多步骤任务",
    max_steps=20,  # 新字段 - 最大执行步骤数
    priority="medium"
)
```

### OptimizedAgentController集成

```python
from core.optimized_agent_controller import OptimizedAgentController

# 控制器现在自动加载和保存学习数据
controller = OptimizedAgentController(toolscore_client, mcp_client)
await controller.initialize()  # 自动加载 data/learning_data.json

# 执行任务
result = await controller.execute_task(
    "分析市场趋势并预测未来6个月走向",
    task_type="research"
)

# 系统会话结束时自动保存学习数据
await controller.shutdown()
```

---

## 🔧 最佳实践

### 1. 会话管理
- **使用有意义的session_id**：如`user_${user_id}_${date}`
- **定期清理旧会话**：避免记忆存储无限增长
- **合理设置max_steps**：根据任务复杂度设定（建议5-20步）

### 2. 记忆优化
- **生产环境使用Redis**：确保记忆持久化和高性能
- **控制上下文长度**：避免LLM输入过长影响性能
- **定期获取跨会话洞察**：帮助系统持续学习优化

### 3. 错误处理
```python
try:
    result = await runtime.execute(task)
except Exception as e:
    # 系统会自动记录失败原因到记忆中
    logger.error(f"任务执行失败: {e}")
    
    # 可以查看记忆中的错误模式
    insights = await memory_manager.get_cross_session_insights()
    for insight in insights:
        if "失败" in insight or "错误" in insight:
            print(f"历史失败模式: {insight}")
```

---

## 📊 监控和调试

### 记忆系统状态
```python
# 获取记忆统计
stats = await memory_manager.get_memory_stats()
print(f"缓存大小: {stats['cache_size']}")
print(f"总步骤数: {stats['total_steps']}")
print(f"Redis状态: {stats['redis_available']}")

# 健康检查
health = await memory_manager.health_check()
print(f"系统状态: {health['status']}")
```

### 步骤规划统计
```python
# 获取规划器性能指标
planning_stats = step_planner.get_planning_stats()
print(f"生成计划数: {planning_stats['total_plans_generated']}")
print(f"成功率: {planning_stats['success_rate']:.2%}")
print(f"自适应调整次数: {planning_stats['adaptive_adjustments']}")
```

### 学习数据查看
```python
# 查看持久化的学习数据
import json
with open("data/learning_data.json", "r") as f:
    learning_data = json.load(f)
    
print(f"系统指标: {learning_data['system_metrics']}")
print(f"决策权重: {learning_data['decision_weights']}")
print(f"模式记忆条目: {len(learning_data['pattern_memory'])}")
```

---

## 🧪 测试

运行完整的测试套件：

```bash
# 测试记忆管理器
python3 -m pytest tests/test_memory_manager.py -v

# 测试多步推理（如果需要）
python3 -m pytest tests/ -k "multistep" -v

# 测试整体集成
python3 -m pytest tests/test_system_integration.py -v
```

---

## 🔮 未来扩展

### 已实现功能 ✅
1. **记忆持久化存储**：Redis + 内存降级模式
2. **多步推理规划**：动态1-100步执行能力
3. **学习数据持久化**：决策权重和模式记忆自动保存
4. **跨会话洞察**：历史数据分析和经验提取

### 计划中的功能 🔮
1. **记忆压缩算法**：自动压缩长期记忆，保留关键信息
2. **个性化学习**：基于用户行为模式的个性化推理策略
3. **分布式记忆**：支持多实例间的记忆共享和同步
4. **可视化界面**：Web界面查看和管理记忆数据

### 扩展接口
- **自定义规划策略**：实现StepPlanner的策略接口
- **记忆过滤器**：自定义记忆存储和检索规则
- **学习算法插件**：增强系统的学习和适应能力

---

## 🆘 常见问题

**Q: 如何迁移现有任务到新的多步模式？**  
A: 只需在TaskSpec中添加`max_steps`字段，系统向后兼容。

**Q: 记忆数据会占用多少存储空间？**  
A: 每个会话步骤约1-5KB，可通过max_memory_entries控制。

**Q: 如何在无Redis环境中使用？**  
A: 系统自动降级为内存模式，功能完整但重启后丢失记忆。

**Q: 多步执行会显著增加响应时间吗？**  
A: 步骤规划器经过优化，通常增加不超过10%的执行时间。

---

更多详细信息请参考源码注释和架构分析文档。