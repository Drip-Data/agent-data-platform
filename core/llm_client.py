#!/usr/bin/env python3
"""
LLM客户端统一接口
支持多种API提供商：vLLM本地服务、OpenAI、Google Gemini、DeepSeek等
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
import httpx
import asyncio
import re

logger = logging.getLogger(__name__)

class MaxTokensExceededError(Exception):
    """自定义异常，用于表示LLM响应因达到最大token数而被截断"""
    pass

class LLMProvider(Enum):
    """LLM提供商枚举"""
    VLLM = "vllm"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

class LLMClient:
    """统一的LLM客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # 优先使用配置中指定的提供商，没有则进行自动检测
        if 'provider' in config:
            provider_name = config['provider'].lower()
            if provider_name == 'vllm':
                self.provider = LLMProvider.VLLM
            elif provider_name == 'openai':
                self.provider = LLMProvider.OPENAI
            elif provider_name == 'gemini':
                self.provider = LLMProvider.GEMINI
            elif provider_name == 'deepseek':
                self.provider = LLMProvider.DEEPSEEK
            else:
                logger.warning(f"Unknown provider in config: {provider_name}, falling back to auto-detection")
                self.provider = self._detect_provider()
        else:
            self.provider = self._detect_provider()
            
        self.client = httpx.AsyncClient(timeout=60.0)
        
        logger.info(f"Initialized LLM client with provider: {self.provider.value}")
    
    def _detect_provider(self) -> LLMProvider:
        """自动检测使用的LLM提供商"""
        # 优先级：Gemini > DeepSeek > OpenAI > vLLM
        if os.getenv('GEMINI_API_KEY'):
            return LLMProvider.GEMINI
        elif os.getenv('DEEPSEEK_API_KEY'):
            return LLMProvider.DEEPSEEK
        elif os.getenv('OPENAI_API_KEY'):
            return LLMProvider.OPENAI
        else:
            return LLMProvider.VLLM
    
    async def generate_code(self, description: str, language: str = "python") -> Dict[str, str]:
        """生成代码，并返回思考过程和代码"""
        logger.debug(f"LLMClient.generate_code called: description={description[:50]}...")
        prompt = self._build_code_prompt(description, language)
        
        response_text = None
        code = None
        thinking = None

        try:
            # Initial attempt
            response_text = await self._call_api(prompt)
            code = self._extract_code(response_text, language)
            thinking = response_text  # Initial thinking is the full response

        except MaxTokensExceededError:
            logger.warning(f"Code generation response truncated due to MAX_TOKENS on initial attempt. Attempting to simplify prompt and retry.")
            simplified_prompt = self._simplify_code_prompt_for_retry(prompt)
            try:
                # Retry attempt
                response_text = await self._call_api(simplified_prompt)
                code = self._extract_code(response_text, language)
                thinking = response_text  # Thinking from the retried call
            except MaxTokensExceededError:
                logger.error("Code generation still truncated after simplification and retry.")
                raise RuntimeError("无法生成代码: Code generation still truncated after simplification and retry.")
            except Exception as e_retry:
                logger.error(f"Failed to generate code on retry after simplification: {e_retry}")
                raise RuntimeError(f"无法生成代码: Retry after simplification failed with {e_retry}")
        
        except Exception as e_initial: # Catch any other exceptions during the initial API call
            logger.error(f"Failed to generate code on initial attempt: {e_initial}")
            raise RuntimeError(f"无法生成代码: Initial API call failed with {e_initial}")

        if code is None or thinking is None:
             # This case should ideally be covered by the exceptions above,
             # but as a safeguard if _call_api or _extract_code returns None without raising.
            logger.error("Code or thinking is None after generation attempts, indicating an unhandled issue.")
            raise RuntimeError("无法生成代码: Unknown error during code generation process.")

        # 保存原始思考过程
        if len(thinking) > 2000:  # 如果思考过程太长，截取前后部分
            thinking = thinking[:1000] + "\n... (内容过长，已截断) ...\n" + thinking[-1000:]
            
        return {
            "code": code,
            "thinking": thinking,
            "success": True
        }
    
    def _simplify_code_prompt_for_retry(self, original_prompt: str) -> str:
        """简化代码生成prompt，用于重试"""
        # import re # No need to import re here if it's already imported at the top of the file
        # 移除详细的思考过程要求，只保留核心代码生成指令
        simplified_prompt = original_prompt
        simplified_prompt = re.sub(r'==== 思考过程 ====.+?==== 代码实现 ====', '==== 代码实现 ====', simplified_prompt, flags=re.DOTALL)
        simplified_prompt = re.sub(r'首先，详细思考如何解决这个问题.+?。', '', simplified_prompt, flags=re.DOTALL)
        simplified_prompt = re.sub(r'分析不同的解决方案并选择最佳方案。', '', simplified_prompt, flags=re.DOTALL)
        
        # 缩短描述，如果原始描述很长
        desc_match = re.search(r'描述：(.+?)\n\n要求：', simplified_prompt, re.DOTALL)
        if desc_match:
            original_desc = desc_match.group(1).strip()
            if len(original_desc) > 200:
                simplified_desc = original_desc[:200].rsplit(' ', 1)[0] + "..."
                simplified_prompt = simplified_prompt.replace(original_desc, simplified_desc)
        
        logger.info(f"Simplified code generation prompt for retry. New length: {len(simplified_prompt)}")
        return simplified_prompt
    
    async def generate_web_actions(self, description: str, page_content: str = "") -> List[Dict]:
        """生成Web操作步骤"""
        prompt = self._build_web_prompt(description, page_content)
        
        try:
            response = await self._call_api(prompt)
            actions = self._extract_web_actions(response)
            return actions
        except Exception as e:
            logger.error(f"Failed to generate web actions: {e}")
            return self._fallback_web_actions(description)
    
    async def generate_reasoning(self, task_description: str, available_tools: List[str],
                                previous_steps: List[Dict] = None,
                                browser_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成推理步骤和工具调用"""
        prompt = self._build_reasoning_prompt(task_description, available_tools, previous_steps, browser_context)
        
        try:
            response = await self._call_api(prompt)
            return self._parse_reasoning_response(response)
        except Exception as e:
            logger.error(f"Failed to generate reasoning: {e}")
            return {
                "thinking": f"Error occurred while processing: {e}",
                "action": "error",
                "tool": None,
                "parameters": {},
                "confidence": 0.0
            }
    
    async def generate_task_summary(self, task_description: str, steps: List[Dict], 
                                   final_outputs: List[str]) -> str:
        """生成任务执行总结"""
        prompt = self._build_summary_prompt(task_description, steps, final_outputs)
        
        try:
            response = await self._call_api(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Task completed with {len(steps)} steps. Final outputs: {'; '.join(final_outputs[:3])}"
    
    async def check_task_completion(self, task_description: str, steps: List[Dict], 
                                   current_outputs: List[str]) -> Dict[str, Any]:
        """检查任务是否完成"""
        prompt = self._build_completion_check_prompt(task_description, steps, current_outputs)
        
        try:
            response = await self._call_api(prompt)
            return self._parse_completion_response(response)
        except Exception as e:
            logger.error(f"Failed to check completion: {e}")
            return {"completed": False, "confidence": 0.0, "reason": f"Error: {e}"}

    async def _call_api(self, prompt: str) -> str:
        """调用相应的API"""
        if self.provider == LLMProvider.VLLM:
            return await self._call_vllm(prompt)
        elif self.provider == LLMProvider.OPENAI:
            return await self._call_openai(prompt)
        elif self.provider == LLMProvider.GEMINI:
            return await self._call_gemini(prompt)
        elif self.provider == LLMProvider.DEEPSEEK:
            return await self._call_deepseek(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    async def _call_vllm(self, prompt: str) -> str:
        """调用vLLM本地服务"""
        vllm_url = self.config.get("vllm_url", "http://localhost:8000")
        
        payload = {
            "model": "default",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
        response = await self.client.post(
            f"{vllm_url}/v1/chat/completions",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_openai(self, prompt: str) -> str:
        """调用OpenAI API"""
        api_key = os.getenv('OPENAI_API_KEY')
        api_base = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.post(
            f"{api_base}/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_gemini(self, prompt: str) -> str:
        """调用Google Gemini API"""
        api_key = os.getenv('GEMINI_API_KEY')
        api_url = os.getenv('GEMINI_API_URL', 'https://generativelanguage.googleapis.com/v1beta')
        
        # 验证并使用有效的Gemini模型名称
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash') # Use a generally available model
        # Fallback to a known stable model if GEMINI_MODEL is not set or invalid
        # For this example, let's assume gemini-1.5-flash is a good default.
        # You might want a more sophisticated way to manage valid_models if they change frequently.

        max_output_tokens = int(os.getenv('GEMINI_MAX_TOKENS', 2048)) # Default to 2048 if not set

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": float(os.getenv('GEMINI_TEMPERATURE', 0.1)), # Allow temperature to be configured
                "maxOutputTokens": max_output_tokens
            }
        }
        
        try:
            response = await self.client.post(
                f"{api_url}/models/{model_name}:generateContent?key={api_key}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                
                finish_reason = candidate.get("finishReason", "")
                if finish_reason == "MAX_TOKENS":
                    logger.warning(f"Gemini response was truncated due to MAX_TOKENS limit for model {model_name}.")
                    raise MaxTokensExceededError(f"Gemini response truncated due to MAX_TOKENS limit for model {model_name}.")
                
                if "content" in candidate and "parts" in candidate["content"] and len(candidate["content"]["parts"]) > 0 and "text" in candidate["content"]["parts"][0]:
                    return candidate["content"]["parts"][0]["text"]
                elif "content" in candidate and "text" in candidate["content"]: # Some models might have text directly under content
                     return candidate["content"]["text"]
                elif "text" in candidate: # Or directly under candidate
                     return candidate["text"]

            logger.error(f"Unexpected Gemini API response structure: {result}")
            raise ValueError(f"Cannot extract text from Gemini response: {result}")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API call failed with status {e.response.status_code}: {e.response.text}")
            # Consider if a more specific model fallback is needed here or just raise
            raise RuntimeError(f"Gemini API call failed: {e.response.status_code} - {e.response.text}") from e
        except Exception as e: # Catch other potential errors like network issues, JSON parsing, etc.
            logger.error(f"Gemini API call failed with an unexpected error: {e}")
            raise RuntimeError(f"Gemini API call failed: {e}") from e

    async def _call_deepseek(self, prompt: str) -> str:
        """调用DeepSeek API"""
        api_key = os.getenv('DEEPSEEK_API_KEY')
        api_url = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
        
        payload = {
            "model": "deepseek-coder",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.post(
            f"{api_url}/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    def _build_code_prompt(self, description: str, language: str) -> str:
        """构建代码生成提示，增强思考过程捕获"""
        # More concise prompt
        return f"""Generate {language} code for the following task.
Task: {description}

Provide your thought process first, then the code.
Format:
==== THOUGHTS ====
(Your detailed thought process, algorithms, data structures, steps)

==== CODE ====
(Your complete, executable code with comments and error handling)
"""
    
    def _build_web_prompt(self, description: str, page_content: str) -> str:
        """构建Web操作提示，强化多步骤规划和数据提取"""
        return f"""请仔细分析以下任务描述和当前页面内容，生成一个详细的、多步骤的Web操作计划，以完成任务目标。
你需要提取任务描述中要求的具体信息。

任务描述：{description}

当前页面内容摘要（Markdown格式，可能包含URL、标题和主要文本）：
{page_content[:1500] if page_content else '无当前页面内容，这可能是任务的第一步。'}

重要指令：
1.  **理解任务目标**：明确任务要求你做什么，需要提取什么信息。
2.  **规划步骤**：将任务分解为一系列具体的浏览器操作。例如：导航到特定网址、在搜索框输入文字、点击按钮、等待页面加载、提取特定元素文本等。
3.  **数据提取**：如果任务要求提取信息，请确保你的操作计划中包含提取相关文本的步骤。可以使用 `extract_text` 动作配合CSS选择器。
4.  **完成任务**：当所有必要信息已提取或操作已完成时，最后一步应为 `{{"action": "finish", "description": "任务完成，已提取所需信息。"}}`。
5.  **结果导向**：确保生成的动作序列能够最终导向任务描述中要求的 `final_result`。

请返回一个JSON格式的操作步骤列表。每个步骤是一个JSON对象，包含以下字段：
- `action`: 字符串，操作类型。常见操作包括:
    - "navigate": 导航到新URL。参数: `{{"url": "目标网址"}}`
    - "fill": 在输入框中填写文本。参数: `{{"selector": "CSS选择器", "value": "要填写的文本"}}`
    - "click": 点击元素。参数: `{{"selector": "CSS选择器"}}`
    - "wait_for_selector": 等待某个元素出现。参数: `{{"selector": "CSS选择器", "state": "visible|hidden|attached|detached", "timeout": 毫秒数 (可选)}}`
    - "extract_text": 提取指定元素的文本内容。参数: `{{"selector": "CSS选择器 (可选, 若无则提取整个页面主要内容)"}}` (此动作的输出将作为下一步的页面内容或最终结果)
    - "finish": 结束任务。参数: `{{"reason": "任务完成原因或最终总结"}}`
- `selector`: 字符串，操作目标的CSS选择器 (如果action需要)。
- `value`: 字符串，操作所需的值 (例如，fill动作的输入文本，navigate动作的URL)。
- `description`: 字符串，对该步骤的简短描述。
- `thinking` (可选): 字符串，你执行此步骤的思考过程。

示例格式：
[
  {{"action": "navigate", "value": "https://www.google.com", "description": "打开Google搜索"}},
  {{"action": "fill", "selector": "input[name='q']", "value": "Python官方文档", "description": "在搜索框输入查询"}},
  {{"action": "click", "selector": "input[name='btnK']", "description": "点击搜索按钮"}},
  {{"action": "wait_for_selector", "selector": "#search", "timeout": 5000, "description": "等待搜索结果加载"}},
  {{"action": "click", "selector": "a[href*='python.org']", "description": "点击Python官网链接"}},
  {{"action": "extract_text", "selector": "article", "description": "提取文章主要内容"}},
  {{"action": "finish", "description": "已提取Python官方文档核心内容。"}}
]

请只返回JSON数组，不要包含其他文字或解释。确保JSON格式正确。
"""
    
    def _build_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                previous_steps: List[Dict] = None,
                                browser_context: Optional[Dict[str, Any]] = None) -> str:
        """构建推理提示, 动态生成工具和动作描述"""
        tool_specific_descriptions = []
        tool_action_parameter_details = []
        possible_actions = ["complete_task", "error"] # Base actions

        logger.debug(f"Building reasoning prompt with available_tools: {available_tools}")

        for tool_name in available_tools:
            logger.debug(f"Processing tool: {tool_name} for prompt generation.")
            if tool_name == 'browser': 
                desc = (
                    f"- browser: 用于与网页交互的工具。支持以下主要 ACTION:\n"
                    f"    - `browser_navigate`: 导航到指定URL。PARAMETERS: `{{ \"url\": \"<完整的HTTP/HTTPS URL>\" }}`\n"
                    f"    - `browser_get_text`: 提取页面文本。PARAMETERS: `{{ \"selector\": \"<CSS选择器(可选)>\" }}` (若无selector，则提取body文本)\n"
                    f"    - `browser_click`: 点击指定元素。PARAMETERS: `{{ \"selector\": \"<CSS选择器>\" }}`"
                )
                tool_specific_descriptions.append(desc)
                possible_actions.extend(["browser_navigate", "browser_get_text", "browser_click"])
                tool_action_parameter_details.append(
                    "  - **对于 `browser_navigate` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"url\": \"<完整的、有效的HTTP或HTTPS URL>\" }}` 的格式。\n"
                    "    - 示例: `{{ \"url\": \"https://www.google.com\" }}`\n"
                    "  - **对于 `browser_click` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"selector\": \"<CSS选择器>\" }}` 的格式。\n"
                    "    - 示例: `{{ \"selector\": \"button#submit\" }}`\n"
                    "  - **对于 `browser_get_text` ACTION**:\n"
                    "    - `PARAMETERS` 可以是 `{{ \"selector\": \"<CSS选择器>\" }}` (提取特定元素文本) 或 `{{}}` (提取整个body文本)。\n"
                    "    - 示例: `{{ \"selector\": \"div.article-content\" }}` 或 `{{}}`"
                )
            elif tool_name == 'python_executor':
                actions_for_python = [
                    "`python_execute`: 执行Python代码。PARAMETERS: `{{ \"code\": \"<Python代码字符串>\" }}`",
                    "`python_analyze`: 分析数据。PARAMETERS: `{{ \"data\": <数据>, \"operation\": \"<操作类型，如 describe, info, correlation>\" }}`",
                    "`python_visualize`: 创建数据可视化。PARAMETERS: `{{ \"data\": <数据>, \"plot_type\": \"<图表类型，如 line, bar, scatter>\", \"title\": \"<图表标题(可选)>\" }}`"
                ]
                desc = (
                    f"- python_executor: 用于执行Python代码和数据分析。支持以下主要 ACTION:\n" +
                    "\n".join([f"    - {action_def}" for action_def in actions_for_python])
                )
                tool_specific_descriptions.append(desc)
                possible_actions.extend(["python_execute", "python_analyze", "python_visualize"])
                tool_action_parameter_details.append(
                    "  - **对于 `python_execute` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"code\": \"<Python代码字符串>\" }}`。\n"
                    "  - **对于 `python_analyze` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"data\": <数据>, \"operation\": \"<操作类型，例如 'describe', 'info', 'correlation'>\" }}`。\n"
                    "  - **对于 `python_visualize` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"data\": <数据>, \"plot_type\": \"<图表类型，例如 'line', 'bar', 'scatter'>\", \"title\": \"<图表标题(可选)>\" }}`。"
                )
            elif tool_name == 'browser_use':
                desc = (
                    f"- browser_use: 用于执行复杂的、多步骤的浏览器自动化任务。主要 ACTION:\n"
                    f"    - `browser_task`: 执行一个基于自然语言的浏览器任务。PARAMETERS: `{{ \"task_description\": \"<任务的详细描述>\" }}`"
                )
                tool_specific_descriptions.append(desc)
                possible_actions.append("browser_task")
                tool_action_parameter_details.append(
                    "  - **对于 `browser_task` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"task_description\": \"<描述你希望浏览器完成的任务>\" }}`。"
                )
            elif tool_name == 'deep_research':
                desc = (
                    f"- deep_research: 用于进行深度研究和分析。主要 ACTION:\n"
                    f"    - `deep_research`: 执行深度研究。PARAMETERS: `{{ \"query\": \"<研究查询字符串>\" }}`"
                )
                tool_specific_descriptions.append(desc)
                possible_actions.append("deep_research")
                tool_action_parameter_details.append(
                    "  - **对于 `deep_research` ACTION**:\n"
                    "    - `PARAMETERS` 必须是 `{{ \"query\": \"<研究查询字符串>\" }}`。"
                )
            else:
                tool_specific_descriptions.append(f"- {tool_name}: (这是一个通用工具，请根据其功能和预期输入来决定 ACTION 和 PARAMETERS)")
                logger.warning(f"Tool '{tool_name}' does not have a detailed description for prompt generation.")

        tools_desc_str = "\n".join(tool_specific_descriptions)
        parameters_details_str = "\n".join(tool_action_parameter_details)
        action_list_str = ", ".join(sorted(list(set(possible_actions)))) 

        browser_context_str = ""
        if browser_context: 
            bc = browser_context
            browser_context_str = (
                f"\n\n当前浏览器状态 (仅当 'browser' 工具可用时相关):\n"
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

        logger.debug("Applying strict tool usage rules from AGENT_IMPROVEMENT_PLAN.md with dynamic actions/params.")
        prompt_template = f"""你是一个智能的、自主的AI助手，你的任务是使用可用工具来解决给定的问题。

**# 任务**
{task_description}

**# 可用工具**
{tools_desc_str}

**# 历史记录**
{previous_steps_str}

**# 思考与行动指南**

1.  **分析与规划**:
    *   仔细阅读任务描述，理解核心目标。
    *   将复杂任务分解为更小的、可管理的步骤。
    *   **智能工具选择**:
        *   **对于简单的、一次性的网页数据获取** (例如，通过API或直接请求URL)，优先使用 `python_executor` 和 `requests` 库。
        *   **对于需要多步骤交互的复杂网页任务** (例如，登录、填写表单、点击多个按钮)，请使用 `browser_use` 工具。
        *   **对于开放式的、需要探索和总结多个信息源的研究任务**，请使用 `deep_research` 工具。

2.  **工具使用**:
    *   严格按照上面“可用工具”部分描述的 `ACTION` 和 `PARAMETERS` 格式来调用工具。
    *   对于 `python_executor`，如果遇到 `ModuleNotFoundError`，系统会自动尝试安装任何缺失的依赖包。你无需手动编写 `pip install` 命令。只需重新提交相同的代码，系统会自动处理依赖问题。

3.  **错误处理**:
    *   如果一个步骤失败，仔细分析 `Observation` 中的错误信息。
    *   不要重复失败的操作。调整你的策略，尝试不同的方法或工具来解决问题。
    *   例如，如果网页抓取失败，可以尝试使用 `deep_research` 工具，它有更强的网络访问能力。

4.  **完成任务**:
    *   当你确信已经收集到所有必要信息并完成了任务的所有要求时，使用 `complete_task` 动作来结束任务。

**# 你的回应**

请严格按照以下格式提供你的回应，不要添加任何额外的解释或注释。

THINKING:
[在这里详细描述你的思考过程。分析任务需求，回顾之前的步骤和观察结果（如果有），评估当前状态，并解释你为什么选择下一步的行动和工具。如果之前的步骤失败，请分析失败原因并说明你将如何调整策略。]

ACTION: [从以下选项中选择一个: {action_list_str}]

TOOL: [如果ACTION需要工具，请指定工具名称。如果ACTION是 complete_task 或 error，则为 null]

PARAMETERS:
[提供一个JSON对象格式的工具参数。严格遵守“可用工具”部分描述的格式。]

CONFIDENCE: [0.0到1.0之间的小数，表示你对当前决策能够成功推进任务的信心。]
"""
        return prompt_template
    
    def _build_summary_prompt(self, task_description: str, steps: List[Dict], 
                             final_outputs: List[str]) -> str:
        """构建总结提示"""
        steps_summary = "\n".join([
            f"步骤{i+1}: {step.get('action', 'unknown')} - {step.get('observation', '')[:100]}..."
            for i, step in enumerate(steps)
        ])
        
        outputs_summary = "\n".join([f"- {output[:200]}..." for output in final_outputs])
        
        return f"""请为以下任务执行过程生成一个简洁的总结。

任务描述: {task_description}

执行步骤:
{steps_summary}

关键输出:
{outputs_summary}

请生成一个包含以下内容的总结:
1. 任务完成情况
2. 主要发现或结果
3. 使用的方法/工具
4. 遇到的挑战(如果有)

总结应该简洁明了，不超过200字。"""
    
    def _build_completion_check_prompt(self, task_description: str, steps: List[Dict],
                                     current_outputs: List[str]) -> str:
        """构建完成检查提示"""
        
        steps_summary = []
        deep_research_found = False
        final_answers = []
        
        for i, step in enumerate(steps[-5:], 1):  # 只看最近5个步骤
            action_type = step.get('action_type', 'UNKNOWN')
            success = step.get('success', False)
            observation = step.get('observation', '')
            
            if 'deep_research' in str(step.get('action_params', {})).lower():
                deep_research_found = True
                try:
                    # import json # Already imported at the top
                    obs_data = json.loads(observation) if observation.startswith('{') else {}
                    final_answer = obs_data.get('final_answer', '')
                    if final_answer:
                        final_answers.append(final_answer[:500] + '...' if len(final_answer) > 500 else final_answer)
                except:
                    pass
            
            status = "✓ 成功" if success else "✗ 失败"
            steps_summary.append(f"步骤{i}: {action_type} - {status}")
        
        steps_text = "\n".join(steps_summary) if steps_summary else "无有效步骤"
        
        answers_text = ""
        if final_answers:
            answers_text = f"\n深度研究结果摘要:\n" + "\n---\n".join(final_answers[:2]) 
        
        return f"""请判断以下任务是否已经完成。

任务描述: {task_description}

已执行步骤数: {len(steps)}
最近步骤概况:
{steps_text}
{answers_text}

判断标准：
1. 如果任务要求"研究"、"分析"、"调查"等，且已完成深度研究并获得详细结果，应判断为完成
2. 如果任务要求具体数据下载、文件操作等，需要实际完成操作才算完成
3. 如果已经有了充分的研究结果回答了用户的问题，应判断为完成

深度研究已执行: {'是' if deep_research_found else '否'}

请回答:
COMPLETED: [true/false]
CONFIDENCE: [0.0-1.0]
REASON: [判断原因]

格式要求严格按照上述格式。"""
    
    def _extract_code(self, response: str, language: str) -> str:
        """从响应中提取代码，支持分离思考过程和代码"""
        # import re # Already imported at the top
        
        code_section_pattern = r'==== CODE ====\s*(.*?)(?:$|==== THOUGHTS ====)' # Adjusted to avoid conflict with thoughts section if it comes after
        section_match = re.search(code_section_pattern, response, re.DOTALL | re.IGNORECASE)
        
        target_content = response # Default to full response if no specific section found
        if section_match:
            target_content = section_match.group(1).strip()
            
        # Try to find language-specific code blocks first
        code_pattern_lang = rf'```{language}\s*(.*?)```'
        match_lang = re.search(code_pattern_lang, target_content, re.DOTALL | re.IGNORECASE)
        if match_lang:
            return match_lang.group(1).strip()
            
        # Try to find generic code blocks
        code_pattern_generic = r'```\s*(.*?)```'
        match_generic = re.search(code_pattern_generic, target_content, re.DOTALL)
        if match_generic:
            return match_generic.group(1).strip()
            
        # If no code blocks are found within the CODE section (if it exists),
        # or if no CODE section was found, return the content of the CODE section or the whole response.
        # This handles cases where the LLM might not use markdown code blocks.
        return target_content.strip() # Return the content of the section or the full response if no blocks
    
    def _extract_web_actions(self, response: str) -> List[Dict]:
        """从响应中提取Web操作"""
        try:
            # import re # Already imported at the top
            
            json_pattern = r'\[(.*?)\]'
            match = re.search(json_pattern, response, re.DOTALL)
            if match:
                json_str = '[' + match.group(1) + ']'
                return json.loads(json_str)
            
            return json.loads(response)
        except:
            logger.warning(f"Failed to parse web actions from response: {response[:200]}...")
            return self._fallback_web_actions("")
    
    def _parse_reasoning_response(self, response: str) -> Dict[str, Any]:
        """解析推理响应"""
        result = {
            "thinking": "",
            "action": "error",
            "tool": None,
            "parameters": {},
            "confidence": 0.5
        }
        
        try:
            current_section = None
            thinking_lines = []
            parameters_lines = []
            
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('THINKING:'):
                    current_section = "thinking"
                    thinking_content = line[len('THINKING:'):].strip()
                    if thinking_content:
                        thinking_lines.append(thinking_content)
                elif line.startswith('ACTION:'):
                    current_section = "action"
                    result["action"] = line[len('ACTION:'):].strip()
                elif line.startswith('TOOL:'):
                    current_section = "tool"
                    tool_value = line[len('TOOL:'):].strip()
                    result["tool"] = tool_value if tool_value and tool_value.lower() != "none" else None
                elif line.startswith('PARAMETERS:'):
                    current_section = "parameters"
                    param_str = line[len('PARAMETERS:'):].strip()
                    if param_str:
                        parameters_lines.append(param_str)
                elif line.startswith('CONFIDENCE:'):
                    current_section = "confidence"
                    try:
                        result["confidence"] = float(line[len('CONFIDENCE:'):].strip())
                    except:
                        result["confidence"] = 0.5 # Default on parse error
                elif current_section == "thinking" and line:
                    thinking_lines.append(line)
                elif current_section == "parameters" and line:
                    parameters_lines.append(line)
            
            if thinking_lines:
                result["thinking"] = "\n".join(thinking_lines)
            
            if parameters_lines:
                parameters_text = "\n".join(parameters_lines)
                try:
                    result["parameters"] = json.loads(parameters_text)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse multi-line parameters JSON: {parameters_text}")
                    try:
                        cleaned_params = parameters_text.replace('```json', '').replace('```', '').strip()
                        result["parameters"] = json.loads(cleaned_params)
                    except json.JSONDecodeError:
                        logger.error(f"Could not parse parameters as JSON: {parameters_text}")
                        result["parameters"] = {"raw_parameters": parameters_text} # Store raw if unparseable
            
        except Exception as e:
            logger.error(f"Error parsing reasoning response: {e}")
            result["thinking"] = f"Failed to parse response: {response[:200]}..."
        
        return result
    
    def _parse_completion_response(self, response: str) -> Dict[str, Any]:
        """解析完成检查响应"""
        result = {"completed": False, "confidence": 0.5, "reason": "Unknown"}
        
        try:
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('COMPLETED:'):
                    completed_str = line[len('COMPLETED:'):].strip().lower()
                    result["completed"] = completed_str in ['true', 'yes', '1']
                elif line.startswith('CONFIDENCE:'):
                    try:
                        result["confidence"] = float(line[len('CONFIDENCE:'):].strip())
                    except:
                        result["confidence"] = 0.5
                elif line.startswith('REASON:'):
                    result["reason"] = line[len('REASON:'):].strip()
        except Exception as e:
            logger.error(f"Error parsing completion response: {e}")
            result["reason"] = f"Parse error: {e}"
        
        return result

    def _fallback_web_actions(self, description: str) -> List[Dict]:
        """Web操作生成失败时的回退操作"""
        return [
            {
                "action": "navigate",
                "url": "https://www.google.com",
                "description": f"执行任务: {description}"
            }
        ]
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()