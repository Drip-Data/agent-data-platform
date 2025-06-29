import logging
import time
from typing import Dict, Any, List, Optional
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class ReasoningPromptBuilder(IPromptBuilder):
    """构建推理提示和增强推理提示，支持XML流式执行模式"""
    
    def __init__(self, streaming_mode: bool = True):
        """
        初始化推理提示构建器
        
        Args:
            streaming_mode: 是否启用XML流式执行模式
        """
        self.streaming_mode = streaming_mode
    
    def build_prompt(self, task_description: str, available_tools: List[str],
                     previous_steps: Optional[List[Dict[str, Any]]] = None,
                     browser_context: Optional[Dict[str, Any]] = None,
                     tool_descriptions: Optional[str] = None, # 用于增强推理
                     execution_context: Optional[Dict[str, Any]] = None,
                     streaming_mode: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        构建推理提示。
        根据是否提供 tool_descriptions 和 execution_context，决定构建普通推理提示还是增强推理提示。
        支持XML流式模式。
        """
        # 确定是否使用流式模式
        use_streaming = streaming_mode if streaming_mode is not None else self.streaming_mode
        
        if use_streaming:
            # XML流式模式 - 多步骤推理和工具组合
            return self._build_streaming_xml_prompt(
                task_description, available_tools, tool_descriptions, previous_steps, execution_context
            )
        elif tool_descriptions is not None and execution_context is not None:
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
        """构建基础推理提示 - 简化版本"""
        tools_desc = "\n".join([f"- {tool}" for tool in available_tools])
        
        context_info = ""
        if browser_context:
            context_info += f"\n\nBrowser: {browser_context.get('current_url', 'N/A')}"
        if previous_steps:
            context_info += f"\n\nPrevious steps: {len(previous_steps)} completed"
        
        prompt_template = f"""Task: {task_description}

Available tools:
{tools_desc}
{context_info}

Respond with JSON format:
{{
  "thinking": "Analysis and reasoning",
  "confidence": 0.8,
  "tool_id": "tool_name",
  "action": "action_name",
  "parameters": {{"param": "value"}}
}}

JSON only, no explanatory text!"""
        return [{"role": "user", "content": prompt_template}]

    def _build_enhanced_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                         tool_descriptions: str, previous_steps: Optional[List[Dict[str, Any]]] = None,
                                         execution_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """构建增强推理提示 - 简化版本"""
        
        # 基础信息
        context_info = ""
        if previous_steps:
            recent_steps = [f"{s.get('tool_id', 'unknown')}.{s.get('action', 'unknown')}" for s in previous_steps[-3:]]
            context_info += f"\n\nRecent steps: {', '.join(recent_steps)}"
        
        if execution_context and execution_context.get('browser_state'):
            context_info += f"\nBrowser: {execution_context['browser_state'].get('current_url', 'N/A')}"
        
        # 工具描述
        tools_info = tool_descriptions if tool_descriptions else "\n".join([f"- {tool}" for tool in available_tools])
        
        prompt_template = f"""You are an AI agent with access to specialized tools.

Task: {task_description}

Available Tools:
{tools_info}
{context_info}

Key Guidelines:
- Use existing tools before searching for new ones
- For research: use mcp-deepsearch with 'question' parameter
- For code: use microsandbox with 'code' parameter
- For web: use browser_use_execute_task with 'task' parameter

Response Format (JSON only):
{{
  "thinking": "Step-by-step analysis",
  "confidence": 0.85,
  "tool_id": "exact-tool-name",
  "action": "exact-action-name",
  "parameters": {{"required_param": "value"}}
}}

JSON only, no explanatory text!"""
        
        return [{"role": "user", "content": prompt_template}]
    
    def _build_streaming_xml_prompt(self, task_description: str, available_tools: List[str],
                                   tool_descriptions: Optional[str] = None,
                                   previous_steps: Optional[List[Dict[str, Any]]] = None,
                                   execution_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """构建支持分层工具选择的XML流式执行提示"""
        
        # 构建工具能力展示（只展示高层级的Server）
        tools_capabilities = self._build_tool_capabilities_section(available_tools, tool_descriptions)
        
        # 构建执行历史
        execution_history = ""
        if previous_steps:
            execution_history = "\n\nPrevious steps:\n"
            for i, step in enumerate(previous_steps[-3:], 1):
                tool_action = f"{step.get('tool_id', 'unknown')}.{step.get('action', 'unknown')}"
                status = "✅" if step.get('success', True) else "❌"
                result_snippet = str(step.get('observation', ''))[:100]
                execution_history += f"  {i}. {tool_action} {status} - {result_snippet}...\n"
        
        # 构建上下文信息
        context_info = ""
        if execution_context:
            memory_context = execution_context.get('memory_context')
            if memory_context and isinstance(memory_context, str):
                context_info = f"\n\nContext from Memory:\n{memory_context}\n"

        prompt_template = f"""You are an expert AI assistant that solves tasks by generating a plan using a sequence of tools in XML format.

**Primary Goal**: Solve the user's task by thinking step-by-step and using the available services.

**XML Rules**:
1.  **Think First**: Always start with a `<think>` block to describe your reasoning and plan.
2.  **Hierarchical Tools**: You must use a two-level nested structure for tool calls. First, select a high-level service (e.g., `<microsandbox>`), then inside it, specify the exact action (e.g., `<execute_code>`).
3.  **Provide Full Context**: The content inside the inner action tag is the complete input for that action.
4.  **Sequential & Parallel**: Place tool calls sequentially for dependent tasks. Use a `<parallel>` block to wrap independent tool calls that can run simultaneously.
5.  **Final Answer**: Conclude your work with an `<answer>` tag containing the final, user-facing result.

**Available Services**:
{tools_capabilities}
{execution_history}
{context_info}
**Execution Example**:

<think>First, I need to see what files are in the current directory to understand the project structure. Then, I will read the `main.py` file.</think>
<microsandbox>
  <list_files>
    .
  </list_files>
</microsandbox>
<result>
  - main.py
  - README.md
</result>
<think>Okay, I see the main file. Now I will read its content.</think>
<microsandbox>
  <read_file>
    main.py
  </read_file>
</microsandbox>
<result>
  # content of main.py
  ...
</result>
<think>I have analyzed the file. The task is complete.</think>
<answer>I have successfully analyzed the project structure by listing files and reading the content of main.py.</answer>

---
Now, begin solving the following task.

**Task**: {task_description}
"""

        return [{"role": "user", "content": prompt_template}]
    
    def _build_tool_capabilities_section(self, available_tools: List[str], tool_descriptions: Optional[str] = None) -> str:
        """构建简洁的工具能力展示"""
        
        if tool_descriptions:
            return tool_descriptions
        
        # 简洁的工具描述
        tool_map = {
            'microsandbox': 'Code execution sandbox with Python, package management, session persistence',
            'mcp-deepsearch': 'Research and information gathering with comprehensive analysis',
            'browser_use': 'AI-powered web browsing and automation with 25+ actions',
            'mcp-search-tool': 'File searching, code analysis, and definition finding'
        }
        
        capabilities = []
        for tool in available_tools:
            tool_lower = tool.lower()
            for key, description in tool_map.items():
                if key in tool_lower:
                    capabilities.append(f"- **{tool}**: {description}")
                    break
            else:
                capabilities.append(f"- **{tool}**: Available tool")
        
        return '\n'.join(capabilities) if capabilities else f"Available tools: {', '.join(available_tools)}"