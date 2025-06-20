# Agent Data Platform API Protocol Specification

## 📋 协议规范版本：v1.0
**发布日期：** 2025-06-20  
**适用系统：** Agent Data Platform with Memory & Multi-Step Reasoning

---

## 📖 概述

本协议规范定义了Agent Data Platform系统的标准化输入输出JSON格式，确保客户端和系统之间的信息交换标准化、结构化和可扩展。

### 核心设计原则
- **标准化**：统一的字段命名和数据结构
- **可扩展性**：支持未来功能扩展
- **向后兼容**：保持API版本间的兼容性
- **类型安全**：明确的数据类型定义
- **错误处理**：完整的错误状态和消息

---

## 🔍 输入侧协议 (Query Input Specification)

### 1. 任务提交 (Task Submission)

#### 1.1 基础任务提交 API

**端点：** `POST /api/v1/tasks`

**请求格式：**
```json
{
  "protocol_version": "v1.0",
  "request_id": "req_20250620_001",
  "timestamp": "2025-06-20T19:30:00Z",
  "client_info": {
    "client_id": "client_web_001",
    "client_version": "1.2.0",
    "user_agent": "AgentPlatform-WebClient/1.2.0"
  },
  "task": {
    "task_id": "user_defined_task_001",
    "task_type": "research",
    "description": "深度调研AI Agent开发领域的最新趋势",
    "context": "用户是AI研究人员，需要了解2024-2025年的技术发展",
    "priority": "high",
    "max_steps": 15,
    "timeout": 600,
    "constraints": {
      "language": "zh-CN",
      "output_format": "detailed_report",
      "sources_required": true
    },
    "expected_tools": [
      "mcp-deepsearch",
      "browser-use-mcp-server"
    ]
  },
  "session": {
    "session_id": "session_20250620_user001",
    "continue_previous": true,
    "memory_context": "include_last_5_interactions"
  },
  "preferences": {
    "response_format": "structured",
    "include_reasoning": true,
    "include_tool_trace": true,
    "max_response_length": 10000
  }
}
```

#### 1.2 快速任务提交 API (简化版)

**端点：** `POST /api/v1/tasks/quick`

**请求格式：**
```json
{
  "query": "请分析当前AI Agent技术发展趋势",
  "task_type": "research",
  "session_id": "session_user001",
  "options": {
    "max_steps": 10,
    "priority": "medium"
  }
}
```

### 2. 任务状态查询

#### 2.1 任务状态查询 API

**端点：** `GET /api/v1/tasks/{task_id}/status`

**响应格式：**
```json
{
  "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
  "status": "completed",
  "progress": {
    "current_step": 2,
    "total_steps": 2,
    "completion_percentage": 100.0
  },
  "estimated_remaining_time": 0,
  "last_updated": "2025-06-20T19:29:21Z"
}
```

### 3. 流式查询 (Streaming Query)

#### 3.1 WebSocket 连接

**端点：** `WS /api/v1/stream/{session_id}`

**输入消息格式：**
```json
{
  "type": "task_submit",
  "data": {
    "task": {
      "description": "实时任务描述",
      "stream_updates": true
    }
  }
}
```

---

## 📤 输出侧协议 (Response Output Specification)

### 1. 标准任务执行响应

#### 1.1 完整响应格式

```json
{
  "protocol_version": "v1.0",
  "response_id": "resp_20250620_001",
  "request_id": "req_20250620_001",
  "timestamp": "2025-06-20T19:29:21Z",
  "status": "success",
  "task_result": {
    "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
    "task_name": "AI Agent趋势调研",
    "task_description": "请深度调研当前AI Agent开发领域的最新趋势...",
    "runtime_id": "enhanced-reasoning-1",
    "success": true,
    "execution_summary": {
      "total_steps": 2,
      "successful_steps": 2,
      "total_duration": 207.987,
      "start_time": "2025-06-20T19:26:33Z",
      "end_time": "2025-06-20T19:29:21Z"
    },
    "final_result": "任务完成。生成结果：...",
    "confidence_score": 0.95,
    "steps": [
      {
        "step_id": 1,
        "step_type": "tool_exposure",
        "action_type": "tool_call",
        "success": true,
        "timestamp": "2025-06-20T19:26:33Z",
        "duration": 0.1,
        "description": "向LLM暴露可用工具信息",
        "tool_input": {
          "tools_snapshot": "# 已注册的工具\\n- microsandbox-mcp-server: 可用工具..."
        },
        "tool_output": "Tools exposed to LLM for planning",
        "metadata": {
          "internal_step": true,
          "tool_count": 4
        }
      },
      {
        "step_id": 2,
        "step_type": "research_execution",
        "action_type": "tool_call",
        "success": true,
        "timestamp": "2025-06-20T19:26:35Z",
        "duration": 162.482,
        "description": "执行深度研究任务",
        "thinking": "STEP 1-TASK ANALYSIS: 任务需要深入调研AI Agent开发的最新趋势...",
        "tool_input": {
          "query": "Current trends in AI Agent development...",
          "action": "comprehensive_research",
          "tool_id": "mcp-deepsearch"
        },
        "tool_output": "工具执行成功: {'answer': '## Comprehensive Analysis of AI Agent Development...'",
        "execution_code": "{\"action\": \"comprehensive_research\", \"tool_id\": \"mcp-deepsearch\", \"parameters\": {...}}",
        "llm_interactions": [
          {
            "provider": "gemini",
            "model": "gemini-1.5-pro",
            "context": "step_2_reasoning",
            "prompt_type": "task_execution",
            "prompt_length": 1250,
            "response_length": 850,
            "response_time": 2.3
          }
        ]
      }
    ],
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
    },
    "memory_context": {
      "session_id": "session_20250620_user001",
      "context_summary": "=== 会话历史摘要 (最近5步) ===\\n成功步骤: 5, 失败步骤: 0...",
      "cross_session_insights": [
        "最常用工具: mcp-deepsearch(3次), browser-use-mcp-server(2次)",
        "整体成功率: 95.2% (20/21)"
      ],
      "memory_stats": {
        "total_stored_steps": 25,
        "session_duration": "45min",
        "key_topics": ["AI Agent", "技术趋势", "LangGraph"]
      }
    },
    "tool_usage": {
      "available_tools": [
        {
          "server_id": "microsandbox-mcp-server",
          "server_name": "MicroSandbox",
          "description": "可用工具 (操作: microsandbox_execute, microsandbox_install_package...)",
          "available_actions": ["microsandbox_execute", "microsandbox_install_package", "microsandbox_list_sessions", "microsandbox_close_session", "microsandbox_cleanup_expired"]
        },
        {
          "server_id": "mcp-search-tool",
          "server_name": "MCP Search Tool",
          "description": "可用工具 (操作: analyze_tool_needs, search_and_install_tools)",
          "available_actions": ["analyze_tool_needs", "search_and_install_tools"]
        },
        {
          "server_id": "browser-use-mcp-server",
          "server_name": "Browser Use Mcp Server",
          "description": "可用工具 (操作: navigate_to_url, get_page_content, click_element, fill_form)",
          "available_actions": ["navigate_to_url", "get_page_content", "click_element", "fill_form"]
        },
        {
          "server_id": "mcp-deepsearch",
          "server_name": "Mcp Deepsearch",
          "description": "可用工具 (操作: research, quick_research, comprehensive_research)",
          "available_actions": ["research", "quick_research", "comprehensive_research"]
        }
      ],
      "used_tools": {
        "mcp-deepsearch.comprehensive_research": {
          "used": true,
          "call_count": 1,
          "total_duration": 162.482,
          "success_rate": 1.0
        }
      },
      "usage_statistics": {
        "available_tools_count": 4,
        "used_servers_count": 1,
        "total_tool_calls": 2,
        "successful_calls": 2,
        "total_execution_time": 132.097,
        "tool_usage_rate": 0.25
      }
    },
    "quality_metrics": {
      "completion_quality": 0.95,
      "reasoning_coherence": 0.92,
      "tool_efficiency": 0.88,
      "response_relevance": 0.96
    }
  },
  "metadata": {
    "processing_time": 207.987,
    "tokens_used": {
      "input_tokens": 1250,
      "output_tokens": 850,
      "total_tokens": 2100
    },
    "cost_info": {
      "estimated_cost": 0.0315,
      "currency": "USD"
    },
    "system_info": {
      "runtime_version": "enhanced-reasoning-v1.2",
      "model_provider": "gemini",
      "model_version": "gemini-1.5-pro"
    }
  }
}
```

#### 1.2 简化响应格式 (用于快速查询)

```json
{
  "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
  "status": "success",
  "result": "任务完成。生成结果：...",
  "duration": 207.987,
  "steps_count": 2,
  "tools_used": ["mcp-deepsearch"]
}
```

### 2. 错误响应格式

#### 2.1 标准错误响应

```json
{
  "protocol_version": "v1.0",
  "response_id": "resp_error_001",
  "request_id": "req_20250620_001",
  "timestamp": "2025-06-20T19:30:00Z",
  "status": "error",
  "error": {
    "error_code": "TASK_EXECUTION_FAILED",
    "error_type": "TOOL_ERROR",
    "error_message": "工具调用失败：mcp-deepsearch服务不可用",
    "error_details": {
      "failed_step": 2,
      "failed_tool": "mcp-deepsearch",
      "retry_attempted": true,
      "retry_count": 1
    },
    "suggested_actions": [
      "检查mcp-deepsearch服务状态",
      "使用替代工具browser-use-mcp-server",
      "稍后重试任务"
    ],
    "recovery_options": {
      "can_retry": true,
      "alternative_tools": ["browser-use-mcp-server", "mcp-search-tool"],
      "estimated_recovery_time": 30
    }
  },
  "partial_result": {
    "completed_steps": 1,
    "intermediate_outputs": ["Tools exposed to LLM for planning"],
    "execution_trace": "已完成工具暴露步骤，在执行研究步骤时失败"
  }
}
```

#### 2.2 错误代码定义

| 错误代码 | 错误类型 | 描述 |
|---------|---------|------|
| `INVALID_INPUT` | VALIDATION_ERROR | 输入参数验证失败 |
| `TASK_EXECUTION_FAILED` | TOOL_ERROR | 任务执行过程中工具调用失败 |
| `TIMEOUT_EXCEEDED` | TIMEOUT | 任务执行超时 |
| `MEMORY_ERROR` | SYSTEM_ERROR | 记忆管理系统错误 |
| `PLANNING_FAILED` | REASONING_ERROR | 步骤规划失败 |
| `RATE_LIMIT_EXCEEDED` | RATE_LIMIT | 请求频率超限 |
| `AUTHENTICATION_FAILED` | AUTH_ERROR | 身份认证失败 |
| `INSUFFICIENT_RESOURCES` | RESOURCE_ERROR | 系统资源不足 |

### 3. 流式响应格式

#### 3.1 WebSocket 流式输出

```json
{
  "type": "progress_update",
  "timestamp": "2025-06-20T19:27:00Z",
  "data": {
    "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
    "current_step": 2,
    "total_steps": 3,
    "progress_percentage": 66.7,
    "current_action": "执行深度研究",
    "estimated_remaining_time": 45,
    "step_output": "正在调用mcp-deepsearch进行comprehensive_research..."
  }
}
```

```json
{
  "type": "step_completed",
  "timestamp": "2025-06-20T19:29:00Z",
  "data": {
    "step_id": 2,
    "success": true,
    "duration": 162.482,
    "output": "研究完成，生成了详细的AI Agent发展趋势报告"
  }
}
```

```json
{
  "type": "task_completed",
  "timestamp": "2025-06-20T19:29:21Z",
  "data": {
    "task_id": "67929b7b-1bf0-48a3-98a3-d47a2fe5fb7f",
    "final_result": "完整的任务结果...",
    "success": true,
    "total_duration": 207.987
  }
}
```

---

## 🔧 系统状态和监控 API

### 1. 系统健康检查

#### 1.1 整体系统状态

**端点：** `GET /api/v1/system/health`

**响应格式：**
```json
{
  "system_status": "healthy",
  "timestamp": "2025-06-20T19:30:00Z",
  "components": {
    "redis": {
      "status": "healthy",
      "latency": 2.5,
      "memory_usage": "45%"
    },
    "toolscore": {
      "status": "healthy",
      "available_tools": 4,
      "active_connections": 12
    },
    "memory_manager": {
      "status": "healthy",
      "cached_sessions": 25,
      "total_stored_steps": 150
    },
    "step_planner": {
      "status": "healthy",
      "active_plans": 3,
      "success_rate": 0.95
    }
  },
  "performance_metrics": {
    "average_task_duration": 185.5,
    "tasks_completed_today": 47,
    "current_load": 0.65,
    "queue_length": 2
  }
}
```

### 2. 记忆系统状态

#### 2.1 会话记忆查询

**端点：** `GET /api/v1/memory/sessions/{session_id}`

**响应格式：**
```json
{
  "session_id": "session_20250620_user001",
  "session_summary": {
    "start_time": "2025-06-20T18:00:00Z",
    "last_activity": "2025-06-20T19:29:21Z",
    "total_steps": 15,
    "successful_steps": 14,
    "main_topics": ["AI Agent", "技术趋势", "LangGraph框架"],
    "key_insights": [
      "用户关注AI Agent的最新发展",
      "特别感兴趣多模态Agent技术"
    ]
  },
  "recent_context": "=== 会话历史摘要 (最近5步) ===...",
  "memory_stats": {
    "cache_size": 15,
    "total_tokens": 8500,
    "compression_ratio": 0.15
  }
}
```

---

## 📚 数据类型定义

### 1. 基础数据类型

```typescript
// 任务类型枚举
enum TaskType {
  RESEARCH = "research",
  CODE = "code",
  WEB = "web",
  ANALYSIS = "analysis",
  GENERAL = "general"
}

// 优先级枚举
enum Priority {
  LOW = "low",
  MEDIUM = "medium", 
  HIGH = "high",
  URGENT = "urgent"
}

// 任务状态枚举
enum TaskStatus {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled"
}

// 错误类型枚举
enum ErrorType {
  VALIDATION_ERROR = "validation_error",
  TOOL_ERROR = "tool_error",
  TIMEOUT = "timeout",
  SYSTEM_ERROR = "system_error",
  REASONING_ERROR = "reasoning_error",
  RATE_LIMIT = "rate_limit",
  AUTH_ERROR = "auth_error",
  RESOURCE_ERROR = "resource_error"
}
```

### 2. 复杂数据结构

```typescript
// 任务规范
interface TaskSpec {
  task_id?: string;
  task_type: TaskType;
  description: string;
  context?: string;
  priority: Priority;
  max_steps?: number;
  timeout?: number;
  constraints?: Record<string, any>;
  expected_tools?: string[];
}

// 执行步骤
interface ExecutionStep {
  step_id: number;
  step_type: string;
  action_type: string;
  success: boolean;
  timestamp: string;
  duration: number;
  description?: string;
  thinking?: string;
  tool_input?: Record<string, any>;
  tool_output?: string;
  execution_code?: string;
  llm_interactions?: LLMInteraction[];
  metadata?: Record<string, any>;
}

// LLM交互记录
interface LLMInteraction {
  provider: string;
  model: string;
  context: string;
  prompt_type: string;
  prompt_length: number;
  response_length: number;
  response_time: number;
}
```

---

## 🔒 安全和认证

### 1. API认证

所有API请求需要包含认证头：

```http
Authorization: Bearer <access_token>
X-API-Key: <api_key>
X-Client-ID: <client_id>
```

### 2. 请求限制

| 端点类型 | 频率限制 | 并发限制 |
|---------|---------|---------|
| 任务提交 | 100/小时 | 5 |
| 状态查询 | 1000/小时 | 20 |
| 流式连接 | 10/小时 | 2 |

---

## 📖 使用示例

### 1. 基础任务提交示例

```javascript
// 提交研究任务
const response = await fetch('/api/v1/tasks', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer your_token'
  },
  body: JSON.stringify({
    task: {
      task_type: "research",
      description: "分析2024年AI Agent发展趋势",
      priority: "high",
      max_steps: 10
    },
    session: {
      session_id: "user_session_001"
    }
  })
});

const result = await response.json();
console.log('任务结果:', result.task_result.final_result);
```

### 2. 流式任务监控示例

```javascript
// WebSocket连接监控任务进度
const ws = new WebSocket('ws://localhost:8000/api/v1/stream/user_session_001');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch(message.type) {
    case 'progress_update':
      console.log(`进度: ${message.data.progress_percentage}%`);
      break;
    case 'step_completed':
      console.log(`步骤完成: ${message.data.output}`);
      break;
    case 'task_completed':
      console.log(`任务完成: ${message.data.final_result}`);
      break;
  }
};
```

---

## 🔄 版本兼容性

### 当前版本：v1.0
- 首次发布版本
- 支持基础任务提交和执行
- 包含记忆管理和多步推理

### 向后兼容性承诺
- 在同一主版本内保持向后兼容
- 新增字段采用可选方式
- 废弃字段会提前通知并保留至少一个版本

---

## 📞 技术支持

如有协议相关问题，请参考：
- 📖 [完整API文档](./MEMORY_AND_MULTISTEP_GUIDE.md)
- 🐛 [问题报告](https://github.com/your-repo/issues)
- 💬 [技术讨论](https://github.com/your-repo/discussions)

---

**协议维护团队：** Agent Data Platform Development Team  
**最后更新：** 2025-06-20