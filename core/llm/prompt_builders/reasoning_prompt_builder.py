import logging
from typing import Dict, Any, List, Optional

from core.llm.prompt_builders.interfaces import IPromptBuilder
from core.unified_tool_manager import UnifiedToolManager
from .tool_info_formatter import ToolInfoFormatter

logger = logging.getLogger(__name__)


class ReasoningPromptBuilder(IPromptBuilder):
    """
    构建支持多轮、分步执行的推理提示。
    该构建器强制LLM遵循"思考->执行->观察"的循环，以消除幻觉。
    """
    
    def __init__(self, tool_manager: UnifiedToolManager, streaming_mode: bool = False):
        self.streaming_mode = streaming_mode
        self.tool_manager = tool_manager
        self.tool_formatter = ToolInfoFormatter(self.tool_manager)

    def build_prompt(self, task_description: str, history: Optional[List[str]] = None, 
                     **kwargs) -> List[Dict[str, Any]]:
        """
        构建核心的XML流式执行提示。

        Args:
            task_description: 用户的原始任务描述。
            history: 前几轮的对话历史，包含之前的思考、工具调用和结果。

        Returns:
            一个包含完整系统消息和用户任务的列表，用于发送给LLM。
        """
        history = history or []

        # 使用ToolInfoFormatter生成V4兼容的工具信息
        tools_info = self.tool_formatter.format_tools_for_prompt()

        system_prompt = f"""You are an expert AI assistant that solves tasks step-by-step using available services.

        **Primary Goal**: Solve the user's task by thinking and using the provided tools through our Orchestrator system.

        **XML Communication Format**:
        1. **Think First**: Always start with a `<think>` block to describe your reasoning and plan.
        2. **V4 Tool Call Format**: Use the format `<server_name><tool_name>content</tool_name></server_name>`. The `Available Services` section below provides the exact XML syntax for each tool.
            
            **Correct Example**:
            <microsandbox_server><execute_python>print("Hello V4!")</execute_python></microsandbox_server>

            **WRONG (Old) Example**:
            <service>microsandbox</service><tool>microsandbox_execute</tool>...

        3. **Execution Trigger**: You MUST end your tool calls with `<execute_tools />` to signal the system to execute them.
        4. **Execution Control**:
            - **Single Call**: A single tool call block followed by `<execute_tools />`.
            - **Parallel Calls**: Wrap multiple tool calls in `<parallel>...</parallel>`, then add `<execute_tools />`.
            - **Sequential Calls**: Wrap multiple tool calls in `<sequential>...</sequential>`, then add `<execute_tools />`.
        5. **Final Answer**: When the task is complete, using the `<answer>` tag is the VERY LAST step.

        **Available Services:**
{tools_info}
        **The question is:**
"""

        # 将历史记录格式化为字符串
        history_str = "\n".join(history)

        # 构建最终的提示内容
        # 注意：我们将历史直接注入到user content中，模拟一个持续的对话
        content = f"{system_prompt}\n\nUser: {task_description}\n{history_str}"

        # 返回与LLM客户端兼容的格式
        return [{"role": "user", "content": content}]
