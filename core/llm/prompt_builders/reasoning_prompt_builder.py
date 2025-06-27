import logging
import time
from typing import Dict, Any, List, Optional
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class ReasoningPromptBuilder(IPromptBuilder):
    """构建推理提示和增强推理提示"""
    
    def build_prompt(self, task_description: str, available_tools: List[str],
                     previous_steps: Optional[List[Dict[str, Any]]] = None,
                     browser_context: Optional[Dict[str, Any]] = None,
                     tool_descriptions: Optional[str] = None, # 用于增强推理
                     execution_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        构建推理提示。
        根据是否提供 tool_descriptions 和 execution_context，决定构建普通推理提示还是增强推理提示。
        """
        if tool_descriptions is not None and execution_context is not None:
            return self._build_enhanced_reasoning_prompt(
                task_description, available_tools, tool_descriptions, previous_steps, execution_context
            )
        else:
            return self._build_basic_reasoning_prompt(
                task_description, available_tools, previous_steps, browser_context
            )

    def _build_basic_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                      previous_steps: Optional[List[Dict[str, Any]]] = None,
                                      browser_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """构建基础推理提示"""
        tool_descriptions = []
        for tool_name in available_tools:
            tool_descriptions.append(f"- {tool_name}")
        tools_desc = "\n".join(tool_descriptions)
        
        browser_context_str = ""
        if browser_context:
            bc = browser_context
            browser_context_str = (
                f"\n\n当前浏览器状态:\n"
                f"- 当前URL: {bc.get('current_url', 'N/A')}\n"
                f"- 页面标题: {bc.get('current_page_title', 'N/A')}\n"
                f"- 最近导航历史:\n  {bc.get('recent_navigation_summary', '无导航历史').replace(chr(10), chr(10) + '  ')}\n"
                f"- 上次提取文本片段: {bc.get('last_text_snippet', '无')}\n"
                f"- 当前页面链接摘要: {bc.get('links_on_page_summary', '无')}"
            )

        previous_steps_str = ""
        if previous_steps:
            previous_steps_str = "\n\n之前的执行步骤:\n"
            for i, step in enumerate(previous_steps[-3:], 1):
                action_str = step.get('action', step.get('action_type', 'unknown_action'))
                observation_str = str(step.get('observation', ''))[:200]
                previous_steps_str += f"  {i}. Action: {action_str}, Observation: {observation_str}...\n"

        prompt_template = f"""# AI Agent - Reasoning Assistant
你是一个智能推理助手，具备动态工具扩展能力。
目标：准确、高效地完成任务，并展示清晰的决策过程。

## 📋 任务信息
**任务**: {task_description}

## 🔧 可用工具
{tools_desc}
{browser_context_str}
{previous_steps_str}

## 📤 响应格式

请以JSON格式返回你的决策：

```json
{{
  "thinking": "STEP 1-任务分析: [任务需要什么？]\\nSTEP 2-工具评估: [当前工具是否充足？]\\nSTEP 3-决策制定: [选择的行动和理由]\\nSTEP 4-执行计划: [如何进行？]",
  "confidence": 0.85,
  "tool_id": "具体工具名称",
  "action": "具体行动名称", 
  "parameters": {{
    "param1": "value1",
    "param2": "value2"
  }}
}}
```

## 🎯 关键规则

### ⚠️ 必需参数检查 - 重要提醒
**每个工具动作都有特定的必需参数，必须全部包含：**
1. **deepsearch工具** - research, quick_research, comprehensive_research 都需要 "question" 参数
2. **microsandbox工具** - microsandbox_execute 需要 "code" 参数  
3. **browser工具** - browser_navigate 需要 "url" 参数，browser_use_execute_task 需要 "task" 参数
4. **search工具** - search_file_content 需要 "file_path" 和 "regex_pattern" 参数
5. **参数不能为空或null** - 所有必需参数都必须有有效值

### 工具参数规范: (请参考可用工具部分的详细描述)
1. **complete_task**: `{{}}`
2. **error**: `{{}}`

### 决策优先级:
- 优先使用现有工具完成任务
- **必须包含所有必需参数** - 这是最重要的要求
- 确保参数完整且格式正确  
- 失败时分析原因并调整策略
- 必要时考虑工具扩展

**⚠️ 严格要求：**
1. 只返回JSON对象，不要任何解释文字！
2. 不要使用markdown代码块包装JSON！
3. 不要添加任何注释或描述性文本！
4. 确保JSON格式完全正确！
5. NO explanatory text outside JSON!
**违反此约束将导致任务失败**

**FINAL REMINDER: JSON ONLY - NO OTHER TEXT!**
"""
        return [{"role": "user", "content": prompt_template}]

    def _build_enhanced_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                         tool_descriptions: str, previous_steps: Optional[List[Dict[str, Any]]] = None,
                                         execution_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """为增强推理构建优化的提示 - 支持MCP主动选择机制，动态工具描述"""

        prompt_parts = [
            "# AI Agent with Dynamic Tool Expansion",
            "",
            "You are an intelligent AI agent with access to a comprehensive set of specialized tools.",
            "**CORE PRINCIPLE: Always prioritize using existing tools before searching for new ones.**",
            "",
            # 🔧 动态工具描述（已移除硬编码）
            "## 🔧 Available Tools (Live from deployment)",
            tool_descriptions,  # 由ToolSchemaManager动态生成，反映实际部署状态
            "",
            f"## 🎯 Current Task",
            f"**Task**: {task_description}",
            "",
        ]

        if previous_steps:
            analyze_count = sum(1 for s in previous_steps if s.get('tool_id') == 'mcp-search-tool' and s.get('action') == 'analyze_tool_needs')
            search_count = sum(1 for s in previous_steps if s.get('tool_id') == 'mcp-search-tool' and s.get('action') == 'search_and_install_tools')
            tool_install_success = any('成功安装' in str(s.get('observation', '')) or 'successfully installed' in str(s.get('observation', '')) for s in previous_steps)
            
            has_search_recommendation = any(
                'search_for_new_tools' in str(s.get('observation', '')) or
                '需要新工具' in str(s.get('observation', '')) or
                'install' in str(s.get('observation', ''))
                for s in previous_steps
            )
            
            consecutive_failures = 0
            for s in reversed(previous_steps[-3:]):
                if not s.get('success', True):
                    consecutive_failures += 1
                else:
                    break
            
            history_summary = []
            for i, s in enumerate(previous_steps[-4:], 1):
                step_id = s.get('step_id', i)
                tool_action = f"{s.get('tool_id', 'unknown')}.{s.get('action', 'unknown')}"
                status = "✅" if s.get('success', True) else "❌"
                obs_snippet = str(s.get('observation', ''))[:50]
                history_summary.append(f"  {step_id}. {tool_action} {status} - {obs_snippet}...")
            
            prompt_parts.extend([
                "## 📋 Execution History",
                "\n".join(history_summary),
                f"**Status**: Analyzed {analyze_count}x | Searched {search_count}x | Installed: {'Yes' if tool_install_success else 'No'}",
                "",
            ])
            
            if consecutive_failures >= 2:
                prompt_parts.extend([
                    "🚨 **CRITICAL**: Multiple consecutive failures detected!",
                    "**Try Alternative Approach**: Use a different existing tool or approach with current tools.",
                    "**Last Resort**: Only if truly no existing tool can help, consider searching for new tools.",
                    ""
                ])
            elif analyze_count >= 2 and search_count == 0:
                prompt_parts.extend([
                    "⚠️ **LOOP DETECTED**: Analysis completed, but no action taken!",
                    "**Recommended**: Directly use the most appropriate existing tool instead of analyzing further.",
                    ""
                ])
            elif has_search_recommendation and search_count == 0:
                prompt_parts.extend([
                    "🔍 **RECONSIDER**: Before searching for new tools, verify if existing tools can handle the task.",
                    "**Check**: deepsearch, microsandbox, or browser_use capabilities.",
                    ""
                ])
            elif tool_install_success:
                prompt_parts.extend([
                    "🎉 **TOOLS INSTALLED**: New capabilities available! Use them to complete the task.",
                    ""
                ])

        prompt_parts.extend([
            "## 🧠 Intelligent Decision Framework",
            "",
            "### 🔍 For Research/Investigation Tasks (HIGHEST PRIORITY):",
            "```",
            "if task_contains_keywords(['研究', 'research', '调研', '分析', '了解']):",
            "    → ALWAYS use 'mcp-deepsearch' with action 'research' or 'comprehensive_research'",
            "    → PARAMETER: 'question' (NOT 'query'!)",
            "    → NEVER use mcp-search-tool for research tasks",
            "```",
            "",
            "### 💻 For Code/Programming Tasks:",
            "```",
            "if task_contains_keywords(['代码', 'code', '编程', 'python', '执行']):",
            "    → use 'microsandbox' with action 'microsandbox_execute'",
            "    → PARAMETER: 'code' (required!)",
            "    → FEATURES: Auto token refresh, session persistence, package management",
            "    → RELIABILITY: 100% success rate with local fallback",
            "```",
            "",
            "### 🌐 For Web/Browser Tasks (Enhanced with 25+ Actions):",
            "```",
            "if task_contains_keywords(['网页', 'web', '浏览', '访问', '搜索', '抓取', '数据收集', '表单', '自动化']):",
            "    → PRIMARY: Use 'browser_use_execute_task' for complex AI-driven tasks",
            "    → PARAMETER: 'task' (natural language description)",
            "    → FEATURES: AI vision, multi-step automation, intelligent interaction",
            "    → EXAMPLES: 'Search for Python tutorials and open first result'",
            "    ",
            "    → BASIC ACTIONS: Use specific actions for simple operations:",
            "    → NAVIGATE: 'browser_navigate' with 'url' parameter",
            "    → SEARCH: 'browser_search_google' with 'query' parameter",
            "    → INTERACT: 'browser_click_element' with 'index' parameter",
            "    → INPUT: 'browser_input_text' with 'index' + 'text' parameters",
            "    → EXTRACT: 'browser_extract_content' with 'goal' parameter",
            "    → SCREENSHOT: 'browser_screenshot' for visual capture",
            "    → SCROLL: 'browser_scroll_to_text' with 'text' parameter",
            "    → TABS: 'browser_open_tab', 'browser_switch_tab', 'browser_close_tab'",
            "    → UTILITY: 'browser_wait', 'browser_get_page_info', 'browser_save_pdf'",
            "```",
            "",
            "### 🔧 For Tool Installation Tasks ONLY:",
            "```",
            "if task_explicitly_requires_tool_installation:",
            "    if analyze_count == 0:",
            "        → use 'mcp-search-tool.analyze_tool_needs'",
            "    elif analyze_count >= 1:",
            "        → use 'mcp-search-tool.search_and_install_tools'",
            "    else:",
            "        → try alternative approach with existing tools",
            "```",
            "",
            "### ⚠️ IMPORTANT: NEVER use search_and_install_tools with mcp-deepsearch!",
            "",
            "### ⚡ CRITICAL DECISION RULES:",
            "1. **RESEARCH TASKS**: Use mcp-deepsearch DIRECTLY - no analysis needed",
            "2. **CODE TASKS**: Use 'microsandbox' DIRECTLY - enhanced with auto-refresh & sessions",
            "3. **WEB TASKS**: Use 'browser_use_execute_task' for complex tasks, specific actions for simple operations", 
            "4. **TOOL SEARCH**: Only use mcp-search-tool for truly specialized needs",
            "5. **ANALYSIS LIMIT**: Never call 'analyze_tool_needs' more than 2 times",
            "6. **INSTALLATION LIMIT**: Never repeat failed installations",
            "7. **MICROSANDBOX**: Token issues auto-resolved, always reliable with fallback",
            "",
        ])

        if execution_context:
            context_info = []
            if execution_context.get('browser_state'):
                context_info.append(f"Browser: {execution_context['browser_state'].get('current_url', 'N/A')}")
            if execution_context.get('installed_tools'):
                context_info.append(f"Newly Installed: {', '.join(execution_context['installed_tools'])}")
            
            if context_info:
                prompt_parts.extend([
                    "## 🔄 Execution Context",
                    "\n".join(f"- {info}" for info in context_info),
                    "",
                ])

        prompt_parts.extend([
            "## 💡 Example: Research Task",
            "```json",
            "{",
            '  "thinking": "STEP 1-TASK ANALYSIS: The user wants to know about the latest AI trends.\nSTEP 2-CAPABILITY CHECK: The `mcp-deepsearch` tool is perfect for this research task.\nSTEP 3-DECISION: I will use the `comprehensive_research` action for a thorough analysis.\nSTEP 4-EXECUTION PLAN: Formulate a clear question and execute the tool.",',
            '  "confidence": 0.95,',
            '  "tool_id": "mcp-deepsearch",',
            '  "action": "comprehensive_research",',
            '  "parameters": {',
            '    "question": "What are the latest trends in Artificial Intelligence as of late 2024?"',
            '  }',
            "}",
            "```",
            "",
            "## 📤 Response Format (JSON Only)",
            "",
            "Return **ONLY** a valid JSON object with this exact structure:",
            "",
            "```json",
            "{",
            '  "thinking": "STEP 1-TASK ANALYSIS: [What does the task require?]\\nSTEP 2-CAPABILITY CHECK: [Do current tools suffice?]\\nSTEP 3-DECISION: [Chosen action and reasoning]\\nSTEP 4-EXECUTION PLAN: [How to proceed]",',
            '  "confidence": 0.85,',
            '  "tool_id": "exact-tool-identifier",',
            '  "action": "exact_action_name",',
            '  "parameters": {',
            '    "question": "for mcp-deepsearch research actions",',
            '    "code": "for microsandbox_execute actions", ',
            '    "task": "for browser_use_execute_task (natural language)",',
            '    "url": "for browser_navigate actions",',
            '    "query": "for browser_search_google actions",',
            '    "index": "for browser click/input actions (NOT selector!)",',
            '    "text": "for browser_input_text actions",',
            '    "goal": "for browser_extract_content actions",',
            '    "filename": "for browser_screenshot actions (optional)",',
            '    "seconds": "for browser_wait actions",'
            '    "task_description": "for mcp-search-tool actions only"',
            '  }',
            "}",
            "```",
            "",
            "# ",
            "🔧 优化1修复：使用动态工具描述替换硬编码",
            "### 🎯 CRITICAL: Available Tools and Their Capabilities",
            "",
        ])
        
        # 插入动态工具描述，如果可用的话
        if tool_descriptions:
            prompt_parts.extend([
                tool_descriptions,
                "",
            ])
        else:
            # 降级到基本工具列表
            prompt_parts.extend([
                "**Available Tools:**",
                "\n".join([f"- {tool}" for tool in available_tools]),
                "⚠️ **Warning**: Detailed tool descriptions not available, use with caution",
                "",
            ])
        
        prompt_parts.extend([
            "### 🎯 Key Guidelines:",
            "1. **thinking**: Use 4-step analysis format above",
            "2. **tool_id**: Must match available tool names exactly",
            "3. **action**: Must match tool's supported actions",
            "4. **parameters**: MUST include ALL required parameters for the chosen action",
            "5. **confidence**: 0.8+ for tool installation, 0.9+ for task completion",
            "",
            "**⚠️ CRITICAL: microsandbox_execute MUST have 'code' parameter!**",
            "**⚠️ CRITICAL: Check examples above for correct parameter format!**",
            "**✅ NEW: MicroSandbox now has auto token refresh - no auth issues!**",
            "**✅ NEW: Session variables persist across executions in same session_id!**",
            "",
            "**⚠️ 严格要求：**",
            "1. 只返回JSON对象，不要任何解释文字！",
            "2. 不要使用markdown代码块包装JSON！",
            "3. 不要添加任何注释或描述性文本！",
            "4. 确保JSON格式完全正确！",
            "5. NO explanatory text outside JSON!",
            "**违反此约束将导致任务失败**",
            "",
            "**FINAL REMINDER: JSON ONLY - NO OTHER TEXT!**",
        ])
        
        return [{"role": "user", "content": "\n".join(prompt_parts)}]