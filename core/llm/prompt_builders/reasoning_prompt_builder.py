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

        **Primary Goal**: Solve the user's task efficiently by thinking and using the provided tools through our Orchestrator system.

        **CRITICAL: Answer Tag Usage Protocol**

        The `<answer>` tag is reserved ONLY for the final, complete deliverable for the user. It signals that the entire task is finished. Adhere strictly to the following checklist.

        **Checklist for Using the `<answer>` Tag:**
        You MUST satisfy ALL of the following conditions to use the `<answer>` tag:

        *   [ ] **Condition 1: Execution Phase Completed.** You have already called at least one tool using `<execute_tools />`.
        *   [ ] **Condition 2: Meaningful Result Received.** The tool execution has returned actual, tangible data or a successful status. It was NOT an error, a timeout, or an empty response.
        *   [ ] **Condition 3: User's Goal Achieved.** The information you received from the tool(s) is sufficient to fully and finally resolve the user's original request. No more steps are needed.

        **FORBIDDEN USAGE:**
        *   ❌ **DO NOT** use `<answer>` to wrap your internal thoughts or your plan.
        *   ❌ **DO NOT** use `<answer>` if you are about to call a tool. The answer comes AFTER the result.
        *   ❌ **DO NOT** use `<answer>` if the last tool call resulted in an error.

        **Correct Workflow Examples:**

        **Example 1 (English Query):**
        User: "What is the capital of France?"
        
        1. **THINK & PLAN:**
           `<think>`
           The user wants to know the capital of France. I need to use the search tool to find this information.
           `</think>`
           `<deepsearch><research>Capital of France</research></deepsearch>`
           `<execute_tools />`

        2. **RECEIVE RESULT & PROVIDE ANSWER:**
           `<result>`
           The capital of France is Paris.
           `</result>`
           `<answer>`
           \\boxed{{The capital of France is Paris.}}
           `</answer>`

        **Example 2 (Chinese Query):**
        User: "苹果公司的股票价格是多少？"
        
        1. **THINK & PLAN:**
           `<think>`
           用户想知道苹果公司的股票价格。我需要使用浏览器搜索最新的苹果股票价格信息。
           `</think>`
           `<browser_use><browser_search_google>苹果公司股票价格</browser_search_google></browser_use>`
           `<execute_tools />`

        2. **RECEIVE RESULT & PROVIDE ANSWER:**
           `<result>`
           苹果公司(AAPL)当前股价为 $195.32
           `</result>`
           `<answer>`
           \\boxed{{苹果公司(AAPL)当前股价为 $195.32}}
           `</answer>`

        **LANGUAGE CONSISTENCY RULE:**
        🌐 **CRITICAL**: Your response language MUST match the user's query language.
        - If user asks in Chinese (中文) → respond in Chinese
        - If user asks in English → respond in English  
        - If user asks in other languages → respond in the same language
        - Mixed language queries → use the primary language of the query

        **FINAL ANSWER FORMAT REQUIREMENT:**
        📦 **MANDATORY**: All final answers must be wrapped in \\boxed{{}} for clean extraction:
        - ✅ Correct: `<answer>\\boxed{{Your final answer here}}</answer>`
        - ❌ Wrong: `<answer>Your final answer here</answer>`
        - ✅ Example: `<answer>\\boxed{{计算结果: 9.43×10⁻⁷ A}}</answer>`
        - ✅ Example: `<answer>\\boxed{{IORA stands for Institute of Operations Research and Analytics at NUS}}</answer>`

        **XML Communication Format**:
        1. **Think First**: Always start with a `<think>` block to describe your reasoning and plan.
        2. **V4 Tool Call Format**: Use the EXACT format shown below. Server names and tool names must match precisely.

        **Available Services:**
{tools_info}
        **ADAPTIVE EXECUTION GUIDELINES**:
        - 🎯 **Normal Tasks**: Analyze → Select tools → Execute directly
        - 🔧 **Tool Errors**: Analyze error message → Check tool definitions → Retry with correct parameters
        - 🧮 **Scientific Results**: Perform sanity checks on numerical results before concluding
        - 🔍 **Error Recovery**: If a tool fails repeatedly, examine the error details and try alternative approaches

        **TOOL USAGE GUIDELINES**:
        - 🔧 **MicroSandbox**: Use `<microsandbox><microsandbox_execute>your_python_code</microsandbox_execute></microsandbox>` (NOT execute_python)
        - 🔧 **Browser**: Use `<browser_use><browser_search_google>your_query</browser_search_google></browser_use>` with proper query format
        - 🔧 **DeepSearch**: Use `<deepsearch><research>your_question</research></deepsearch>` for research tasks

        3. **Execution Trigger**: You MUST end your tool calls with `<execute_tools />` to signal the system to execute them.
        4. **Execution Control**:
            - **Single Call**: A single tool call block followed by `<execute_tools />`.
            - **Parallel Calls**: Wrap multiple tool calls in `<parallel>...</parallel>`, then add `<execute_tools />`.
            - **Sequential Calls**: Wrap multiple tool calls in `<sequential>...</sequential>`, then add `<execute_tools />`.

        5. **Task Completion - Use the Protocol Above**: 
           🔒 **REMEMBER**: You MUST follow the Answer Tag Usage Protocol checklist above.
           🔒 **MANDATORY**: Execute tools first, receive meaningful results, THEN provide answer.
           🔒 **FORBIDDEN**: Never use `<answer>` for plans, thoughts, or before tool execution.
           

        **Error Recovery**:
        - If a tool call fails with parameter errors, check the EXACT parameter names in the tool definitions above
        - If a tool times out, try an alternative approach rather than repeating the same call
        - If multiple approaches fail, provide a partial answer based on available information

        **The question is:**
"""

        # 将历史记录格式化为字符串
        history_str = "\n".join(history)

        # 构建最终的提示内容
        # 注意：我们将历史直接注入到user content中，模拟一个持续的对话
        content = f"{system_prompt}\n\nUser: {task_description}\n{history_str}"

        # 返回与LLM客户端兼容的格式
        return [{"role": "user", "content": content}]
