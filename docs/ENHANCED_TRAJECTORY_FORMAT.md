# 增强轨迹记录格式 v2.0

## 概述

基于对 OpenHands 轨迹格式的深度分析，我们实施了轨迹记录系统的重大改进，在保持原有任务级别汇总优势的同时，增加了细粒度的元数据收集和分析能力。

## 主要改进

### 🔍 第一阶段：详细元数据收集

#### 1. LLM 交互元数据增强
```json
"llm_interactions": [
  {
    "interaction_id": "uuid",
    "timestamp": 1750431998.693,
    "provider": "gemini",
    "model": "gemini-1.5-pro",
    "context": "task_analysis",
    "token_usage": {
      "prompt_tokens": 10,
      "completion_tokens": 15,
      "total_tokens": 25
    },
    "cost_info": {
      "total_cost": 0.000125,
      "currency": "USD"
    },
    "response_time": 1.5,
    "success": true
  }
]
```

#### 2. 性能和资源使用追踪
```json
"resource_usage": {
  "cpu_usage_percent": 25.5,
  "memory_usage_mb": 128.0,
  "execution_time_ms": 1500
}
```

#### 3. 累积LLM指标
```json
"llm_metrics": {
  "total_interactions": 1,
  "accumulated_cost": 0.000125,
  "accumulated_token_usage": {
    "total_tokens": 25,
    "prompt_tokens": 10,
    "completion_tokens": 15
  },
  "average_response_time": 1.5,
  "providers_used": ["gemini"],
  "models_used": ["gemini-1.5-pro"]
}
```

### 🔗 第二阶段：事件因果关系和源归属

#### 1. 事件源归属
```json
"event_source": "agent",  // "agent" | "user" | "system" | "environment"
"caused_by_step": 1,      // 触发此步骤的前序步骤ID
"triggering_event": "user_request"  // 触发事件描述
```

#### 2. 子事件细粒度追踪
```json
"sub_events": [
  {
    "event_id": "uuid",
    "timestamp": 1640995200.0,
    "event_type": "tool_call_initiated",
    "description": "开始工具调用",
    "metadata": {}
  }
]
```

### 📊 第三阶段：错误处理和环境信息

#### 1. 错误处理统计
```json
"error_handling": {
  "errors_encountered": 0,
  "retry_attempts": 0,
  "error_types": [],
  "recovery_successful": true,
  "error_rate": 0.0
}
```

#### 2. 执行环境信息
```json
"execution_environment": {
  "platform": "Darwin",
  "python_version": "3.11.9",
  "cpu_count": 10,
  "total_memory_gb": 16.0,
  "session_start_time": 1750431998.693,
  "environment_id": "uuid"
}
```

## 完整轨迹格式示例

```json
{
  "task_id": "test_123",
  "task_name": "test_task", 
  "task_description": "这是一个测试任务",
  "runtime_id": "test_runtime",
  "success": true,
  "steps": [
    {
      "step_id": 1,
      "action_type": "tool_call",
      "tool_input": {"test_param": "test_value"},
      "tool_output": "测试观察结果",
      "success": true,
      "timestamp": 1750431998.693,
      "duration": 0.0,
      
      // 🔍 LLM交互详情
      "llm_interactions": [/* LLM交互记录 */],
      
      // 🔗 事件因果关系
      "event_source": "agent",
      "caused_by_step": null,
      "triggering_event": "user_request",
      
      // 📊 性能监控
      "resource_usage": {
        "cpu_usage_percent": 25.5,
        "memory_usage_mb": 128.0,
        "execution_time_ms": 1500
      },
      
      // 🔍 子事件追踪
      "sub_events": [/* 子事件列表 */]
    }
  ],
  "final_result": "测试任务成功完成",
  "total_duration": 5.0,
  
  // 🔍 累积LLM指标
  "llm_metrics": {
    "total_interactions": 1,
    "accumulated_cost": 0.000125,
    "accumulated_token_usage": {
      "total_tokens": 25,
      "prompt_tokens": 10,
      "completion_tokens": 15
    },
    "average_response_time": 1.5,
    "providers_used": ["gemini"],
    "models_used": ["gemini-1.5-pro"]
  },
  
  // 📋 执行环境
  "execution_environment": {
    "platform": "Darwin",
    "python_version": "3.11.9",
    "cpu_count": 10,
    "total_memory_gb": 16.0,
    "session_start_time": 1750431998.693,
    "environment_id": "uuid"
  },
  
  // ⚠️ 错误处理统计
  "error_handling": {
    "errors_encountered": 0,
    "retry_attempts": 0,
    "error_types": [],
    "recovery_successful": true,
    "error_rate": 0.0
  }
}
```

## 与 OpenHands 格式对比

| 特性 | OpenHands | 我们的增强格式 | 优势 |
|------|-----------|----------------|------|
| **粒度** | 事件级别 | 任务+步骤级别 | 更好的可读性和结构化 |
| **LLM元数据** | 详细 | 详细 | ✅ 同等水平 |
| **成本追踪** | 详细 | 详细 | ✅ 同等水平 |
| **因果关系** | 事件链接 | 步骤因果关系 | ✅ 更清晰的逻辑关系 |
| **性能监控** | 有限 | 系统级监控 | ✅ 更全面 |
| **错误处理** | 基础 | 统计分析 | ✅ 更智能 |
| **可读性** | 复杂 | 结构化 | ✅ 更易理解 |

## 使用场景

### 1. 调试和故障排除
- 通过 `llm_interactions` 分析LLM调用链
- 通过 `error_handling` 统计识别问题模式
- 通过 `sub_events` 定位具体失败点

### 2. 成本优化
- 监控 `accumulated_cost` 控制API开支
- 分析 `token_usage` 优化提示效率
- 对比 `providers_used` 选择最优模型

### 3. 性能分析
- 追踪 `resource_usage` 优化系统性能
- 分析 `response_time` 识别瓶颈
- 监控 `execution_environment` 确保一致性

### 4. 系统学习
- 分析成功轨迹的 `event_source` 和 `triggering_event` 模式
- 统计 `error_rate` 指导系统改进
- 追踪 `recovery_successful` 评估容错能力

## 实现组件

### 核心模块
1. **`TrajectoryEnhancer`** - 轨迹增强器，负责收集和计算元数据
2. **`EnhancedLLMClient`** - 增强LLM客户端，收集LLM交互详情
3. **增强的接口类** - `ExecutionStep`, `TrajectoryResult`, `LLMInteraction`

### 集成方式
- 在 `EnhancedReasoningRuntime` 中自动应用轨迹增强
- 保持向后兼容，现有代码无需修改
- 渐进式收集，不影响系统性能

## 未来扩展

### 第四阶段：高级分析功能
- **推理捕获**: 记录决策点和置信度
- **模式识别**: 自动识别成功和失败模式
- **预测分析**: 基于历史轨迹预测任务成功率
- **A/B测试**: 支持不同策略的效果对比

### 集成建议
- **数据分析平台**: 将轨迹数据导入BI工具进行深度分析
- **监控告警**: 基于错误率和成本阈值设置告警
- **自动优化**: 基于轨迹分析自动调整系统参数