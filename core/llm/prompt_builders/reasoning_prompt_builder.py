import logging
from typing import Dict, Any, List, Optional

from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)


class ReasoningPromptBuilder(IPromptBuilder):
    """
    构建支持多轮、分步执行的推理提示。
    该构建器强制LLM遵循"思考->执行->观察"的循环，以消除幻觉。
    """
    
    def __init__(self, streaming_mode: bool = False):
        self.streaming_mode = streaming_mode

    def build_prompt(self, task_description: str, available_tools: List[str] = None,
                     tool_descriptions: str = None, history: Optional[List[str]] = None, 
                     streaming_mode: bool = None, execution_context: dict = None,
                     **kwargs) -> List[Dict[str, Any]]:
        """
        构建核心的XML流式执行提示。

        Args:
            task_description: 用户的原始任务描述。
            tool_descriptions: 动态生成的可用工具XML描述。
            history: 前几轮的对话历史，包含之前的思考、工具调用和结果。

        Returns:
            一个包含完整系统消息和用户任务的列表，用于发送给LLM。
        """
        history = history or []

        # 构建工具信息
        if tool_descriptions:
            tools_info = tool_descriptions
        else:
            tools_info = "\n".join([f"- {tool}" for tool in (available_tools or [])])

        system_prompt = f"""You are an expert AI assistant that solves tasks step-by-step using available services.

        **Primary Goal**: Solve the user's task by thinking and using the provided tools through our Orchestrator system.

        **XML Communication Format**:
        1. **Think First**: Always start with a `<think>` block to describe your reasoning and plan.
        2. **Hierarchical Tools**: Use the format `<service><tool>content</tool></service>` where:
        - `service` = MCP server name (microsandbox, deepsearch, browser_use)  
        - `tool` = specific action on that service (microsandbox_execute,browser_search_googlee.t.c)
        - `content` = parameters/input for the tool
        3. **Stop Signal**: End your tool calls with `<execute_tools />` to signal the system to execute them.
        4. **Execution Control**: You can specify:
        - **Single**: Just one tool call
        - **Parallel**: Wrap multiple tools in `<parallel>...</parallel>`
        - **Sequential**: Wrap multiple tools in `<sequential>...</sequential>`
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