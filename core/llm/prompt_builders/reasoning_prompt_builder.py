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

### 工具参数规范: (请参考可用工具部分的详细描述)
1. **complete_task**: `{{}}`
2. **error**: `{{}}`

### 决策优先级:
- 优先使用现有工具完成任务
- 确保参数完整且格式正确  
- 失败时分析原因并调整策略
- 必要时考虑工具扩展

**只返回JSON对象，不要其他文字！**
"""
        return [{"role": "user", "content": prompt_template}]

    def _build_enhanced_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                         tool_descriptions: str, previous_steps: Optional[List[Dict[str, Any]]] = None,
                                         execution_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """为增强推理构建优化的提示 - 支持MCP主动选择机制"""

        prompt_parts = [
            "# AI Agent with Dynamic Tool Expansion",
            "",
            "You are an intelligent AI agent capable of **self-evolution** through dynamic tool acquisition.",
            "Your core innovation: **PROACTIVELY identify tool gaps and install new MCP servers when needed**.",
            "",
            f"## 🎯 Current Task",
            f"**Task**: {task_description}",
            "",
            "## 🔧 Available Tools",
            tool_descriptions,
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
                    "**Action Required**: Use 'mcp-search-tool' → 'search_and_install_tools' to acquire new capabilities.",
                    ""
                ])
            elif analyze_count >= 2 and search_count == 0:
                prompt_parts.extend([
                    "⚠️ **LOOP DETECTED**: Analysis completed, but no action taken!",
                    "**Next Action MUST be**: 'mcp-search-tool' → 'search_and_install_tools'",
                    ""
                ])
            elif has_search_recommendation and search_count == 0:
                prompt_parts.extend([
                    "🔍 **SEARCH RECOMMENDED**: Previous analysis suggests tool installation needed.",
                    "**Proceed with**: 'mcp-search-tool' → 'search_and_install_tools'",
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
            "### 🎨 For Image/Chart Generation Tasks:",
            "```",
            "if no_image_tools_available:",
            "    if analyze_count == 0:",
            "        → use 'mcp-search-tool.analyze_tool_needs'",
            "    elif analyze_count >= 1:",
            "        → use 'mcp-search-tool.search_and_install_tools'",
            "    else:",
            "        → proceed with available tools",
            "```",
            "",
            "### 📄 For Document Processing Tasks:",
            "```",
            "if no_document_tools_available:",
            "    → follow same pattern as image generation",
            "```",
            "",
            "### 🌐 For Web Scraping/API Tasks:",
            "```",
            "if browser_tools_sufficient:",
            "    → use existing browser-navigator tools",
            "else:",
            "    → search for specialized API/scraping tools",
            "```",
            "",
            "### 🔍 For Research/Investigation Tasks:",
            "```",
            "if task_requires_deep_research:",
            "    if 'mcp-deepsearch' in available_tools:",
            "        → use 'mcp-deepsearch' with action 'research' or 'comprehensive_research'",
            "    else:",
            "        → search for professional research capabilities",
            "elif quick_info_needed:",
            "    → use basic search or browser tools",
            "```",
            "",
            "### ⚡ OPTIMIZATION RULES:",
            "- **Never** call 'analyze_tool_needs' more than 2 times",
            "- **Always** follow analysis recommendations",
            "- **Prefer** using newly installed tools over workarounds",
            "- **Complete task** once capabilities are sufficient",
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
            '    "task_description": "copy task exactly if using mcp-search-tool",',
            '    "reason": "explain why new tools are needed (for search actions)",',
            '    "other_params": "as required by specific tool"',
            '  }',
            "}",
            "```",
            "",
            "### 🎯 Key Guidelines:",
            "1. **thinking**: Use 4-step analysis format above",
            "2. **tool_id**: Must match available tool names exactly",
            "3. **action**: Must match tool's supported actions",
            "4. **parameters**: Include all required parameters for the chosen action",
            "5. **confidence**: 0.8+ for tool installation, 0.9+ for task completion",
            "",
            "**NO other text outside the JSON object!**",
        ])
        
        return [{"role": "user", "content": "\n".join(prompt_parts)}]