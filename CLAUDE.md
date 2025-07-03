# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 核心开发原则 (CRITICAL DEVELOPMENT PRINCIPLES)

### 🚨 第一要务：代码质量至上
**严禁屎山代码！** 优先做减法或者在不新增大量代码的情况下完成bug修复。精简、高效、高可读性与维护性是第一要义。避免不知节制的增加补丁，导致屎山代码。

### 💪 专家级问题解决
Don't hold back. Give it your all. 你是一个顶级的黑客兼程序员，对于这种问题你很拿手。请给我一个解决方案。

### 🖥️ 系统环境要求
- **操作系统**: macOS 15.5 - 运行命令时请注意兼容性
- **Python版本**: 使用 `python3` 而不是 `python`
- **必读文档**: 首先阅读 `agent-data-platform/docs/` 下的文档和 `agent-data-platform/README.md` 快速了解系统基本架构和文件功能

### 🔧 根本性问题解决
任何修改和debug的目标均应该是**彻底从根本上解决问题**，而不是采用"降低验证标准"和"简化检查"的方式。
- **根本解决**: 所有修改和调试都应该从根本上解决问题，绝不采用"降低验证标准"或"简化检查"的方式掩盖问题
- **彻底修复**: 追求问题的本质原因，实施彻底的解决方案

### 📁 架构整洁性维护
- **避免文件污染**: 尽量避免在根目录和主目录下创建新的未归类文件
- **有意识维护**: 有意识地维护当前系统架构的清晰整洁性，便于后期维护

### 🏗️ 结构化开发
- **模块化优先**: 任何修改不应该只做简单的粘贴修补，最好是结构化的、模块化的补充和完善
- **清晰引用**: 提高系统引用之间的清晰与连贯，避免多跳引用、跨级引用等操作
- **降低维护难度**: 保持代码可读性与清晰性，减少维护困难

### 🧹 代码库清理
- **清理废弃代码**: 任何新功能对旧功能的替换操作，应该审阅并清理旧文件
- **防止冗余**: 防止废弃代码残留和代码库冗余
- **目标**: 保持代码库的清晰整洁与高度可维护性

### 🔒 反硬编码原则 (NEW!)
**严禁任何形式的硬编码！** 
- **常量化**: 所有固定字符串、状态判定标准、错误消息等均应定义为常量
- **配置化**: 可变的参数和阈值应通过配置文件管理
- **动态逻辑**: 状态判定、结果提取等逻辑应基于实际数据而非固定模式
- **可扩展性**: 设计时考虑未来变化，避免写死特定值或格式

### 📋 开发效率原则
**避免过度文档化！**
- **不要创建专门的修复报告**: 修复代码问题时，直接在代码中注释解释即可，无需单独创建 `.md` 报告文件
- **精简文档**: 只在 `CLAUDE.md` 和 `GEMINI.md` 中更新关键变更，避免冗余文档
- **重点在实现**: 优先完成功能修复和测试，而非详细的文档报告

**硬编码检查清单：**
- ❌ 硬编码的成功/失败判定条件
- ❌ 硬编码的错误消息文本
- ❌ 硬编码的XML标签名称
- ❌ 硬编码的状态值或枚举
- ❌ 硬编码的文件路径或URL
- ✅ 使用TaskExecutionConstants等常量类
- ✅ 基于配置文件的参数管理
- ✅ 动态的结果提取和状态判定

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
- 具有状态持久性的会话管理
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

## 核心配置文件

**核心配置**
- `config/llm_config.yaml`: LLM提供商设置 (Gemini, OpenAI等)
- `config/routing_config.yaml`: 任务路由和队列配置
- `requirements.txt`: Python依赖 (MicroSandbox需单独安装)

**环境变量**
```bash
# 必需
GEMINI_API_KEY=your_gemini_api_key

# 可选
OPENAI_API_KEY=your_openai_api_key
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
MICROSANDBOX_TIMEOUT=30
```

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

### 任务类型
- `code`: 代码生成和执行任务
- `reasoning`: 多步分析任务
- `research`: 信息收集和分析
- `web`: 基于浏览器的交互

### 内存管理
- 在任务上下文中使用session_id实现持久内存
- MemoryManager自动存储/检索上下文
- 上下文被注入到LLM提示中以保持连续性

### 错误处理
- 带恢复建议的结构化错误对象
- 针对瞬时故障的自动重试机制
- 针对复杂错误恢复的LLM反思
- 全面的错误分类和严重性级别

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

## 常见故障排除

**端口冲突**: 启动前运行`python3 utility/cleanup_ports.py`

**MicroSandbox问题**: 确保`pip install microsandbox`成功完成

**Redis连接**: 用`redis-cli ping`验证Redis正在运行

**API密钥**: 检查环境变量是否正确设置

**服务健康**: 使用`curl http://localhost:8000/health`进行状态检查

## 安全考虑

- 所有代码执行都限制在MicroSandbox容器中
- API密钥从日志和错误消息中过滤
- 整个管道的输入验证和清理
- 资源限制和超时强制执行
- 所有工具执行的审计日志