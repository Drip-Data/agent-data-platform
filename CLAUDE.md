# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start for New Claude Code Instances

**Critical Dependencies:**
- MicroSandbox: `pip install microsandbox` (required for all code execution)
- Redis: Must be running for task queues and memory management
- Environment: `export GEMINI_API_KEY=your_key`

**Key Architecture Points:**
- All code execution MUST go through MicroSandbox server (port 8090)
- Anti-hallucination framework prevents fake tool results via XML streaming
- ToolScore system (port 8088/8089) manages all MCP server communications
- Enhanced Runtime (`runtimes/reasoning/enhanced_runtime.py`) is the main execution engine

**Most Important Files:**
- `main.py`: System entry point
- `core/interfaces.py`: Constants and data structures (avoid hardcoding)
- `runtimes/reasoning/enhanced_runtime.py`: Core execution logic
- `core/toolscore/`: Tool management system

## Essential Commands

### Start the platform
```bash
python3 main.py
```

### Run tests
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test suites  
python3 -m pytest tests/test_microsandbox_*.py -v
python3 -m pytest tests/test_system_validation.py -v

# Submit test tasks
python3 scripts/batch_test_tasks.py --tasks-file tasks.jsonl
python3 scripts/batch_test_tasks.py --tasks-file data/test_tasks.jsonl
```

### Health checks
```bash
curl http://localhost:8000/health
curl http://localhost:8088/health  # ToolScore service
```

### Dependency management
```bash
# Install core dependencies
pip install -r requirements.txt

# Install MicroSandbox (critical for code execution)
pip install microsandbox

# Verify MicroSandbox installation
python3 -c "from microsandbox import PythonSandbox; print('✅ MicroSandbox ready')"
```

## Architecture Overview

Agent Data Platform is a multi-agent AI system combining LLM reasoning with real tool execution through an anti-hallucination framework. The system prevents LLMs from generating fake tool results by implementing a "stop-and-wait" mechanism.

### Core Components

**Enhanced Runtime** (`runtimes/reasoning/enhanced_runtime.py`)
- Main execution engine with XML streaming and anti-hallucination
- Handles memory management and trajectory enhancement
- Coordinates LLM interactions with real tool execution

**ToolScore System** (`core/toolscore/`)
- Unified tool management with MCP server integration
- Dynamic tool discovery and session management
- HTTP API on port 8088, WebSocket on port 8089

**Memory & Planning**
- `MemoryManager`: Redis-based persistent session memory
- `StepPlanner`: Multi-step reasoning with adaptive planning
- Supports up to 100 execution steps for complex tasks

### MCP Tool Servers

**MicroSandbox Server** (port 8090) - Critical for code execution
- Secure Python code execution environment
- Session management with state persistence
- Package installation and dependency management

**Browser Use Server** (port 8082) - Web automation
- AI-driven browser automation with 25+ tools
- Web scraping and intelligent form filling

**DeepSearch Server** (port 8086) - Research capabilities
- Advanced search and multi-source information aggregation
- Intelligent query optimization with caching

**Search Tool Server** (port 8080) - File operations
- File system search and content pattern matching

### Data Synthesis Learning

The platform implements a "data flywheel" for continuous learning:

**Trajectory Monitoring**
- Real-time monitoring of `output/trajectories/` directory
- Automatic triggering on trajectory file modifications
- Synthesis processing delay of 2-5 minutes

**Synthesis Process**
1. Extract successful execution patterns
2. Generate atomic seed tasks from trajectories
3. Apply depth/breadth expansion for task variants
4. Multi-dimensional quality validation
5. Store validated tasks in `output/seed_tasks.jsonl`

**Output Files**
- `output/trajectories/trajectories_collection.json`: Raw execution data
- `output/seed_tasks.jsonl`: Auto-generated learning tasks
- `output/task_essences.json`: Extracted task patterns

## Development Principles

### System Requirements
- **Python**: Use `python3` not `python`
- **Platform**: macOS 15.5 compatible
- **Redis**: Required for task queues and memory management
- **MicroSandbox**: Critical dependency for secure code execution

### Code Quality Standards
- **No hardcoded values**: Use constants from `core.interfaces.TaskExecutionConstants`
- **Modular design**: Prefer editing existing files over creating new ones
- **Clean architecture**: Maintain clear separation between components
- **Anti-hallucination**: All tool execution must go through MCP servers

### Key Development Patterns
```python
# ✅ Correct: Use constants
from core.interfaces import TaskExecutionConstants
answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']

# ❌ Wrong: Hardcoded strings
if "Final Answer:" in response:
    success = True
```

### Testing Requirements
- Always run pytest before committing changes
- Test MicroSandbox integration for code execution tasks
- Verify anti-hallucination framework integrity
- Check all MCP server connections

## 系统概述

Agent Data Platform 是一个复杂的多智能体AI系统，它将大语言模型(LLM)推理与真实工具执行相结合，通过反幻觉框架实现。该系统通过实施"停止并等待"机制来防止LLM生成虚假的工具执行结果，LLM必须在每次工具调用后暂停并等待真实的执行结果。

## 核心开发命令

### 系统启动和管理
```bash
# 启动整个平台 (包含端口清理)
python3 main.py

# 检查系统健康状态
curl http://localhost:8000/health

# 手动清理端口 (如需要)
python3 utility/cleanup_ports.py
```

### 测试
```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行特定测试套件
python3 -m pytest tests/test_microsandbox_*.py -v  # MicroSandbox 测试
python3 -m pytest tests/test_system_validation.py  # 系统验证测试
python3 -m pytest tests/test_synthesis_focus.py    # 合成系统测试

# 运行性能测试
python3 scripts/batch_test_tasks.py --tasks-file data/test_tasks.jsonl

# 运行单个测试任务
python3 scripts/batch_test_tasks.py --tasks-file tasks.jsonl
```

### 开发工具
```bash
# 验证系统配置
python3 scripts/validate_paths.py

# 检查系统健康
python3 scripts/check_system_health.py

# 监控端口使用
python3 scripts/port_manager.py

# 验证工具映射
python3 scripts/verify_tool_id_mappings.py

# Token优化功能测试
python3 tests/test_token_optimization.py
```

## 架构概览

### 核心组件

**增强运行时** (`runtimes/reasoning/enhanced_runtime.py`)
- 实现带XML流的反幻觉框架
- 处理内存管理和轨迹增强
- 协调LLM交互与真实工具执行

**任务处理管道**
- `TaskLoader`: 从JSONL文件加载和验证任务
- `TaskEnhancer`: 用上下文和元数据丰富任务
- `TaskDistributor`: 将任务路由到适当的队列
- `TaskProcessingCoordinator`: 编排整个管道

**ToolScore系统** (`core/toolscore/`)
- 与MCP服务器集成的统一工具管理
- 动态工具发现和注册
- 会话管理和连接池

**内存与规划**
- `MemoryManager`: 基于Redis存储的持久会话内存
- `StepPlanner`: 具有自适应规划的多步推理
- 智能上下文注入以提高LLM性能

### MCP工具服务器

**MicroSandbox服务器** (端口 8090)
- 安全的Python代码执行环境
- 会话管理和状态持久性
- 包安装和依赖管理

**Browser Use服务器** (端口 8082) 
- AI驱动的浏览器自动化
- 网页抓取和交互能力
- 智能表单填写和导航

**DeepSearch服务器** (端口 8086)
- 高级搜索和研究能力
- 多源信息聚合
- 智能查询优化

**Search Tool服务器** (端口 8080)
- 文件系统搜索和索引
- 内容模式匹配和分析

### 数据流架构

1. **输入接收**: 通过REST API接收任务 (端口 8000)
2. **任务增强**: 上下文丰富和验证
3. **队列分发**: 基于Redis的任务路由 (`tasks:reasoning`)
4. **运行时执行**: 带反幻觉的增强运行时
5. **工具执行**: 通过MCP服务器进行真实工具调用
6. **结果存储**: 轨迹存储和合成学习

## Key Configuration Files

- `config/llm_config.yaml`: LLM provider settings (Gemini primary, OpenAI backup)
- `config/routing_config.yaml`: Task routing and queue configuration  
- `config/unified_tool_definitions.yaml`: Tool definitions and mappings
- `requirements.txt`: Python dependencies (MicroSandbox requires separate installation)

### Required Environment Variables
```bash
# Required
export GEMINI_API_KEY=your_gemini_api_key

# Optional
export OPENAI_API_KEY=your_openai_api_key
export REDIS_URL=redis://localhost:6379
export LOG_LEVEL=INFO
export MICROSANDBOX_TIMEOUT=30
```

### Port Configuration
- 8000: Task API Service
- 8088: ToolScore HTTP API
- 8089: ToolScore WebSocket
- 8090: MicroSandbox Server (critical)
- 8082: Browser Use Server
- 8086: DeepSearch Server
- 8080: Search Tool Server
- 6379: Redis

## 开发指南

### 反幻觉实现
- 始终通过MCP服务器实现真实工具执行
- 对工具调用使用带结果注入的XML流
- 在LLM继续之前验证所有工具输出
- 绝不允许LLM生成虚假的`<result>`标签

### 反硬编码实践
```python
# ❌ 错误的硬编码方式
if "Final Answer:" in response:
    success = True
    final_result = "Task execution completed."

# ✅ 正确的常量化方式
from core.interfaces import TaskExecutionConstants

answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
if f"</{answer_tag}>" in response:
    success = self._determine_task_success(response, trajectory)
    final_result = self._extract_final_result(response)
```

### Token优化与成本控制
```python
# 🆕 使用智能Token管理器进行成本优化
from core.intelligent_token_manager import IntelligentTokenManager
from core.context_cache_manager import CacheStrategy

# 初始化Token管理器
token_manager = IntelligentTokenManager(
    gemini_provider=gemini_provider,
    cache_strategy=CacheStrategy.BALANCED,
    token_budget_limit=1000000  # 100万token预算
)

# 精确Token计数（使用Gemini真实API）
token_count = await token_manager.count_tokens_accurately(text, model="gemini-2.5-flash")

# 智能消息优化（自动缓存与复用）
optimized_messages, optimization_info = await token_manager.optimize_messages_with_cache(
    messages, model="gemini-2.5-flash", session_id="user_session"
)

# 详细成本分析
cost_analysis = step_logger._calculate_cost_metrics(token_usage, duration)
print(f"成本: ${cost_analysis['estimated_cost_usd']:.6f}")
print(f"缓存节省: ${cost_analysis['cache_analysis']['cache_savings_usd']:.6f}")
```

### 状态判定最佳实践
- 使用`_determine_task_success()`进行智能状态判定
- 使用`_extract_final_result()`动态提取结果内容
- 避免简单的字符串匹配，采用多维度综合判断
- 参考: `runtimes/reasoning/enhanced_runtime.py` 中的修复实例

### 工具集成
```python
# 添加新的MCP服务器
1. 在 mcp_servers/{server_name}/ 中创建服务器
2. 实现 MCPServer 基类
3. 添加到 config/ports_config.yaml
4. 在 service_manager 中注册
```

### 服务管理
- 使用系统级重启来重启服务（重启main.py）
- 端口清理机制在启动时自动处理冲突进程

### Task Types
- `code`: Code generation and execution tasks
- `reasoning`: Multi-step analysis tasks  
- `research`: Information gathering and analysis
- `web`: Browser-based interactions

### Memory Management
- Use `session_id` in task context for persistent memory
- MemoryManager automatically stores/retrieves context
- Context injected into LLM prompts for continuity

### Error Handling
- Structured error objects with recovery suggestions
- Automatic retry mechanisms for transient failures
- LLM reflection for complex error recovery
- Comprehensive error classification and severity levels

## 数据合成学习

平台实现"数据飞轮"进行持续学习：

**轨迹监控**
- 实时监控`output/trajectories/`目录
- 轨迹文件修改时自动触发
- 合成处理延迟2-5分钟

**合成过程**
1. 提取成功的执行模式
2. 从轨迹生成原子种子任务
3. 应用深度/宽度扩展以获得任务变体
4. 多维度质量验证
5. 将验证的任务存储在`output/seed_tasks.jsonl`中

**输出文件**
- `output/trajectories/trajectories_collection.json`: 原始执行数据
- `output/seed_tasks.jsonl`: 自动生成的学习任务
- `output/task_essences.json`: 提取的任务模式

## 测试和验证

### 集成测试
```bash
# 提交测试任务
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "code", "input": "测试 MicroSandbox: print(\"Hello!\")"}'

# 检查任务状态
curl "http://localhost:8000/api/v1/tasks/{task_id}"
```

### 性能监控
- 通过ToolScore HTTP API的实时指标 (端口 8088)
- `logs/System.log`中的系统日志 (统一日志记录)
- 通过Redis CLI进行队列监控
- 执行模式的轨迹分析

## Troubleshooting

### Quick Diagnostics
```bash
# Check all critical services
curl http://localhost:8000/health           # Task API
curl http://localhost:8088/health           # ToolScore
redis-cli ping                              # Redis
python3 -c "from microsandbox import PythonSandbox; print('✅ MicroSandbox OK')"

# Port cleanup (if needed)
python3 utility/cleanup_ports.py

# Check task queue status
redis-cli XLEN tasks:reasoning

# Monitor system logs
tail -f logs/System.log
```

### Common Issues
- **Port conflicts**: `python3 utility/cleanup_ports.py` then restart
- **MicroSandbox missing**: `pip install microsandbox`
- **Redis down**: Start Redis service for your OS
- **Tasks stuck**: Check queue with `redis-cli XLEN tasks:reasoning`

## Security Considerations

- All code execution restricted to MicroSandbox containers
- API keys filtered from logs and error messages
- Input validation and sanitization throughout pipeline
- Resource limits and timeout enforcement
- Audit logging for all tool executions