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
   - `tool` = specific action (execute_code, research, search_google)
   - `content` = parameters/input for the tool
3. **Stop Signal**: End your tool calls with `<execute_tools />` to signal the system to execute them.
4. **Execution Control**: You can specify:
   - **Single**: Just one tool call
   - **Parallel**: Wrap multiple tools in `<parallel>...</parallel>`
   - **Sequential**: Wrap multiple tools in `<sequential>...</sequential>` with `$result_of_step_N` placeholders
5. **Final Answer**: When task is complete, use `Final Answer: your response here`

**Available Services:**
{tools_info}

**Examples:**

Single tool:
```
<think>I need to run Python code to calculate this.</think>
<microsandbox><microsandbox_execute>print(2 + 2)</microsandbox_execute></microsandbox>
<execute_tools />
```

Parallel tools:
```
<think>I can search and analyze simultaneously.</think>
<parallel>
<deepsearch><research>Python history</research></deepsearch>
<browser_use><browser_search_google>Python creator</browser_search_google></browser_use>
</parallel>
<execute_tools />
```

Sequential tools:
```
<think>First search, then analyze the results.</think>
<sequential>
<deepsearch><research>machine learning trends</research></deepsearch>
<microsandbox><microsandbox_execute>analyze_data("$result_of_step_1")</microsandbox_execute></microsandbox>
</sequential>
<execute_tools />
```

Final Answer Example:
```
<think>I have now gathered all the necessary information and can provide the final answer.</think>
Final Answer: The creator of Python is Guido van Rossum, and 2 to the power of 5 is 32.
```

**Critical Rules:**
- ALWAYS end tool blocks with `<execute_tools />`.
- After using tools, THINK about the results. If the task is complete, you MUST use `Final Answer:`.
- `Final Answer:` is the VERY LAST step. Do not use any more tools after this.
```

Final Answer:
```
<think>I have now gathered all the necessary information and can provide the final answer.</think>
Final Answer: The creator of Python is Guido van Rossum, and 2 to the power of 5 is 32.
```

**Critical Rules:**
- ALWAYS end tool blocks with `<execute_tools />`.
- After using tools, THINK about the results. If the task is complete, provide the final answer.
- Use `Final Answer: your response here` as the VERY LAST step. Do not use any more tools after this.
```

**Critical Rules:**
- ALWAYS end tool blocks with `<execute_tools />`
- WAIT for `<result>` tags before continuing
- Use `Final Answer:` only when task is completely done"""

        # 将历史记录格式化为字符串
        history_str = "\n".join(history)

        # 构建最终的提示内容
        # 注意：我们将历史直接注入到user content中，模拟一个持续的对话
        content = f"{system_prompt}\n\nUser: {task_description}\n{history_str}"

        # 返回与LLM客户端兼容的格式
        return [{"role": "user", "content": content}]