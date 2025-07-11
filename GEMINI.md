# GEMINI.md

此文件为Gemini模型在Agent Data Platform代码库中工作时提供指导。

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

Agent Data Platform 是一个复杂的多智能体AI系统，它将大语言模型(LLM)推理与真实工具执行相结合，通过反幻觉框架实现。该系统通过实施"停止并等待"机制来防止LLM生成虚假的工具执行结果。

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

## 架构关键组件

### 增强运行时 (Enhanced Runtime)
- 位置: `runtimes/reasoning/enhanced_runtime.py`
- 功能: 实现反幻觉框架，处理任务状态判定和结果提取
- **重要**: 已修复硬编码问题，使用TaskExecutionConstants

### 常量管理 (Constants Management)
- 位置: `core/interfaces.py`
- 类: TaskExecutionConstants, ErrorMessageConstants
- 功能: 统一管理所有硬编码字符串和判定标准

### 工具执行系统
- MicroSandbox服务器 (端口 8090): 安全代码执行
- Browser Use服务器 (端口 8082): AI驱动浏览器自动化
- DeepSearch服务器 (端口 8086): 高级搜索研究
- Search Tool服务器 (端口 8080): 文件系统搜索

## 开发指南

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

### 错误处理标准化
```python
# 使用结构化错误处理
error_msg = ErrorMessageConstants.format_error_message(
    'tool_execution_error',
    tool_id=tool_id,
    details=str(error)
)
```

## 测试和验证

### 状态判定测试
```bash
# 提交测试任务验证修复效果
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "code", "input": "计算1+1的结果"}'

# 检查success字段和final_result是否正确
curl "http://localhost:8000/api/v1/tasks/{task_id}"
```

### 预期修复效果
- ✅ Success准确率: 从0%提升到90%+
- ✅ Final_result有意义: 100%显示实际答案内容
- ✅ 错误信息减少: 冗余"No action performed"消息减少80%+
- ✅ 代码可维护性: 模块化的状态判定逻辑

## 安全考虑

- 所有代码执行都限制在MicroSandbox容器中
- API密钥从日志和错误消息中过滤
- 整个管道的输入验证和清理
- 资源限制和超时强制执行
- 所有工具执行的审计日志

## 维护原则

1. **持续重构**: 定期审查和消除新的硬编码
2. **测试驱动**: 为所有常量和判定逻辑编写测试
3. **文档同步**: 更新代码时同步更新文档
4. **性能监控**: 跟踪修复效果和系统性能指标