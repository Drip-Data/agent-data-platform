import logging
from typing import Dict, Any, List, Optional

from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)


class ReasoningPromptBuilder(IPromptBuilder):
    """
    构建支持多轮、分步执行的推理提示。
    该构建器强制LLM遵循“思考->执行->观察”的循环，以消除幻觉。
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

        system_prompt = f"""You are a helpful assistant that can solve the given question step by step using the provided tools.

**CRITICAL ANTI-HALLUCINATION RULES:**
1. **Think First**: Start with a `<think>` block to analyze the task
2. **Use ONE Tool**: After thinking, use exactly ONE tool with format `<tool_name>input_content</tool_name>`
3. **STOP IMMEDIATELY**: After using a tool, you MUST STOP generating. Do NOT continue.
4. **NEVER Generate Fake Results**: Do NOT write `<result>` tags yourself. Only the system provides real results.
5. **Wait for Real Results**: The system will execute your tool and provide actual output in `<result>` tags
6. **Continue Only After Results**: Only after seeing real `<result>`, continue with new `<think>` block

**Available Tools:**
{tools_info}

**Correct Usage Examples:**
- Research: `<deepsearch>search query here</deepsearch>`
- Python Code: `<microsandbox>python code here</microsandbox>`
- Web Browsing: `<browser_use>search query or task</browser_use>`

**FORBIDDEN - These Will Cause Errors:**
- Calling tools inside other tools: `<microsandbox>print(browser_use.search(...))</microsandbox>` ❌
- Generating fake results: `<result>fake content</result>` ❌
- Continuing after tool call without waiting for results ❌

**Correct Flow Example:**
<think>I need to search for information about Python's creator</think>
<deepsearch>who invented Python programming language</deepsearch>

[SYSTEM WILL EXECUTE TOOL AND PROVIDE REAL RESULT HERE]

<result>
Guido van Rossum invented Python in 1991...
</result>

<think>Now I have the information. Let me write some Python code to demonstrate.</think>
<microsandbox>
print("Python was created by Guido van Rossum")
result = 2 + 3
print(f"Example calculation: 2 + 3 = {{result}}")
</microsandbox>

[SYSTEM WILL EXECUTE CODE AND PROVIDE REAL OUTPUT HERE]

<result>
Python was created by Guido van Rossum
Example calculation: 2 + 3 = 5
</result>

<think>Perfect! I now have all the information needed.</think>
<answer>
Python was invented by **Guido van Rossum** in 1991. As demonstrated by the code execution, basic calculations work as expected: 2 + 3 = 5.
</answer>

**Remember: Use tools ONE AT A TIME, STOP after each tool call, and WAIT for real results!**"""

        # 将历史记录格式化为字符串
        history_str = "\n".join(history)

        # 构建最终的提示内容
        # 注意：我们将历史直接注入到user content中，模拟一个持续的对话
        content = f"{system_prompt}\n\nUser: {task_description}\n{history_str}"

        # 返回与LLM客户端兼容的格式
        return [{"role": "user", "content": content}]