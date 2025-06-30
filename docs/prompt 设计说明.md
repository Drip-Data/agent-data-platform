# 关键Prompt设计快速参考

## 🎯 核心Prompt模板分析

### 1. 增强推理Prompt (Enhanced Reasoning)

**文件**: `core/llm/prompt_builders/reasoning_prompt_builder.py`
**用途**: 复杂任务的深度推理和工具选择

```python
# 核心结构模板
prompt_template = """
# AI Agent with Dynamic Tool Expansion

**CORE PRINCIPLE: Always prioritize using existing tools before searching for new ones.**

## 🧠 Intelligent Decision Framework

### 🔍 For Research/Investigation Tasks (HIGHEST PRIORITY):
if task_contains_keywords(['研究', 'research', '调研']):
    → ALWAYS use 'mcp-deepsearch' with action 'research'
    → This tool provides comprehensive research capabilities
    → Example: {{"tool_id": "mcp-deepsearch", "action": "research", "parameters": {{"question": "research_query"}}}}

### 💻 For Code/Programming Tasks:
if task_contains_keywords(['代码', 'code', '编程', 'programming', '开发']):
    → use 'microsandbox' with action 'microsandbox_execute'
    → For code execution, analysis, debugging
    → Example: {{"tool_id": "microsandbox", "action": "microsandbox_execute", "parameters": {{"code": "python_code"}}}}

### 🌐 For Web/Browser Tasks:
if task_contains_keywords(['网页', 'web', '浏览', 'browse', '网站']):
    → PRIMARY: Use 'browser_use_execute_task' for complex AI-driven tasks
    → SECONDARY: Use 'web_scraper' for simple data extraction
    → Example: {{"tool_id": "browser_use_execute_task", "action": "browser_use_execute_task", "parameters": {{"task": "web_task_description"}}}}

## 🚫 Loop Prevention & Efficiency Rules:
1. **NEVER** repeatedly search for the same tool name
2. **NEVER** repeatedly install the same tool that has failed  
3. If a tool installation fails twice, consider alternative approaches
4. Always check if an existing tool can handle the task before searching
5. **CRITICAL**: Avoid analysis loops - if you've analyzed the same content multiple times, take action

## 🔧 Available Tools:
{dynamic_tool_descriptions}

## 📤 Required JSON Response Format:
{{
  "thinking": "STEP 1-任务分析: [What does the task require?]\\nSTEP 2-工具评估: [Are current tools sufficient?]\\nSTEP 3-决策制定: [Chosen action and reasoning]\\nSTEP 4-执行计划: [How to proceed?]",
  "confidence": 0.85,
  "tool_id": "specific_tool_name",
  "action": "specific_action_name",
  "parameters": {{"key": "value"}}
}}
"""
```

**关键特性**:
- **智能决策框架**: 基于关键词的任务类型识别
- **循环预防机制**: 避免重复安装和分析循环
- **动态工具描述**: 实时反映工具部署状态
- **结构化思维**: 四步推理过程（分析→评估→决策→计划）

### 2. 基础推理Prompt (Basic Reasoning)

**用途**: 简单任务的快速推理

```python
prompt_template = f"""
# AI Agent - Reasoning Assistant
你是一个智能推理助手，具备动态工具扩展能力。
目标：准确、高效地完成任务，并展示清晰的决策过程。

## 📋 任务信息
**任务**: {task_description}

## 🔧 可用工具
{tools_desc}

## 📤 响应格式
请以JSON格式返回你的决策：
{{
  "thinking": "STEP 1-任务分析: [任务需要什么？]\\nSTEP 2-工具评估: [当前工具是否充足？]\\nSTEP 3-决策制定: [选择的行动和理由]\\nSTEP 4-执行计划: [如何进行？]",
  "confidence": 0.85,
  "tool_id": "具体工具名称",
  "action": "具体行动名称",
  "parameters": {{"key": "value"}}
}}
"""
```

### 3. 任务分析Prompt

**文件**: `core/llm/prompt_builders/task_analysis_prompt_builder.py`
**用途**: 分析任务需求和推荐工具

```python
analysis_prompt = f"""
# 任务需求分析专家

请分析以下任务的具体需求：

**任务描述**: {task_description}

## 分析维度

### 1. 任务类型分类
从以下类型中选择（可多选）:
- reasoning: 推理分析
- research: 研究调查  
- web: 网页浏览
- code: 代码编程
- image: 图像处理
- file: 文件操作
- data: 数据分析
- communication: 通信交流

### 2. 核心能力需求
- image_generation: 图像生成
- web_scraping: 网页抓取
- deep_research: 深度研究
- code_execution: 代码执行
- file_manipulation: 文件操作
- data_analysis: 数据分析

### 3. 推荐工具类型
- search_tools: 搜索工具
- browser_tools: 浏览器工具
- code_tools: 代码工具
- image_tools: 图像工具
- file_tools: 文件工具

请以JSON格式返回分析结果：
{{
  "task_types": ["type1", "type2"],
  "capabilities_needed": ["capability1", "capability2"],
  "recommended_tool_types": ["tool_type1", "tool_type2"],
  "complexity_assessment": "simple|medium|complex",
  "estimated_steps": 3,
  "key_challenges": ["challenge1", "challenge2"]
}}
"""
```

### 4. 错误恢复Prompt

**文件**: `core/recovery/intelligent_error_recovery.py`
**用途**: 智能错误分析和恢复策略生成

```python
recovery_prompt = f"""
# 智能错误恢复分析师

## 错误事件信息
- **组件**: {component}
- **错误类型**: {error_type}
- **错误信息**: {error_message}
- **上下文**: {context}
- **历史记录**: {error_history}

## 分析任务
请分析此错误并提供恢复建议：

### 1. 错误分类
- NETWORK_ERROR: 网络连接问题
- TOOL_ERROR: 工具执行错误
- TIMEOUT_ERROR: 超时错误
- RESOURCE_ERROR: 资源不足
- CONFIGURATION_ERROR: 配置错误

### 2. 严重程度评估
- LOW: 可忽略，不影响主流程
- MEDIUM: 需处理但不影响主流程
- HIGH: 影响功能但系统可继续
- CRITICAL: 系统需立即恢复

### 3. 恢复策略推荐
- RETRY: 重试操作
- FALLBACK: 使用替代方案
- RESTART: 重启组件
- ISOLATE: 隔离错误组件
- COMPENSATE: 补偿操作
- ESCALATE: 升级处理

请返回JSON格式的分析结果：
{{
  "error_category": "category",
  "severity": "severity_level",
  "root_cause_analysis": "分析结果",
  "recommended_strategy": "strategy",
  "recovery_steps": ["step1", "step2"],
  "prevention_measures": ["measure1", "measure2"],
  "confidence": 0.85
}}
"""
```

## 🔄 动态上下文注入机制

### 1. 浏览器上下文

```python
browser_context_template = """
## 🌐 当前浏览器状态
- **当前URL**: {current_url}
- **页面标题**: {current_page_title}  
- **最近导航历史**: {recent_navigation_summary}
- **上次提取文本片段**: {last_text_snippet}
- **当前页面链接摘要**: {links_on_page_summary}
- **页面交互状态**: {interaction_state}
"""
```

### 2. 执行历史上下文

```python
execution_history_template = """
## 📋 之前的执行步骤
{步骤序号}. **Action**: {action_name}
   **Tool**: {tool_id}
   **Parameters**: {parameters}
   **Result**: {observation}
   **Status**: {success/failure}
   **Duration**: {execution_time}s
---
"""
```

### 3. 工具状态上下文

```python
tool_status_template = """
## 🔧 工具生态状态
- **可用工具数**: {available_tools_count}
- **工具可用率**: {availability_rate}%
- **最近安装**: {recently_installed}
- **故障工具**: {failed_tools}
- **推荐工具**: {recommended_tools}
"""
```

## 🛡️ Prompt安全与验证

### 1. Guardrails中间件

```python
class GuardrailsMiddleware:
    # JSON格式验证和修复
    json_repair_patterns = [
        (r'```json\s*\n(.*?)\n```', r'\1'),  # 移除markdown代码块
        (r'```\s*\n(.*?)\n```', r'\1'),      # 移除普通代码块
        (r'\n\s*\n', r'\n'),                 # 移除多余换行
        (r'([^"]),(\s*[}\]])', r'\1\2'),     # 修复尾随逗号
    ]
    
    # 必需字段验证
    required_fields = ["thinking", "tool_id", "action", "parameters"]
    
    # 工具可用性验证
    def validate_tool_availability(self, tool_id: str, available_tools: List[str]) -> str:
        if tool_id not in available_tools:
            # 模糊匹配最相似的工具
            similar_tool = self.find_most_similar_tool(tool_id, available_tools)
            return similar_tool
        return tool_id
```

### 2. 参数完整性检查

```python
parameter_validation_rules = {
    "mcp-deepsearch": {
        "research": {"required": ["question"], "optional": ["research_depth"]},
        "quick_research": {"required": ["question"], "optional": []},
    },
    "browser_use_execute_task": {
        "browser_use_execute_task": {"required": ["task"], "optional": ["url"]},
    },
    "microsandbox": {
        "microsandbox_execute": {"required": ["code"], "optional": ["language"]},
    }
}
```

## 📊 Prompt效果监控

### 1. 成功率指标

```python
prompt_metrics = {
    "parsing_success_rate": "JSON解析成功率",
    "tool_selection_accuracy": "工具选择准确率", 
    "parameter_completeness": "参数完整性",
    "execution_success_rate": "执行成功率",
    "reasoning_quality_score": "推理质量评分"
}
```

### 2. A/B测试框架

```python
class PromptABTesting:
    test_variants = {
        "reasoning_v1": "基础推理Prompt",
        "reasoning_v2": "增强推理Prompt",
        "reasoning_v3": "简化推理Prompt"
    }
    
    async def run_ab_test(self, task_description: str, sample_size: int = 100):
        # 随机分配测试组
        # 收集执行结果
        # 统计成功率和性能指标
        # 推荐最优Prompt版本
```

## 🚀 最佳实践建议

### 1. Prompt设计原则
- **简洁明确**: 避免冗长复杂的指令
- **结构化输出**: 强制JSON格式确保解析可靠性
- **上下文感知**: 动态注入相关上下文信息
- **错误容忍**: 包含格式修复和验证机制

### 2. 性能优化技巧
- **模板复用**: 避免重复构建相似的Prompt
- **长度控制**: 限制上下文长度避免超出token限制
- **缓存机制**: 缓存常用的工具描述和模板
- **并行处理**: 批量处理多个Prompt构建请求

### 3. 可靠性保障
- **多层验证**: JSON格式→字段完整性→工具可用性→参数合理性
- **优雅降级**: 解析失败时的自动修复和重试
- **监控告警**: 实时监控Prompt效果和成功率
- **持续优化**: 基于执行反馈持续改进Prompt设计

这套Prompt设计系统通过**智能决策框架**、**动态上下文注入**和**多层验证机制**，确保了Agent能够准确理解任务需求，正确选择工具，并可靠执行任务，是整个Agent编排系统的核心大脑。