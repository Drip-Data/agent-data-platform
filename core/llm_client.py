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

logger = logging.getLogger(__name__)

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
        disable_cache = os.getenv("DISABLE_CACHE") or self.config.get("disable_cache", False)
        logger.debug(f"LLMClient.generate_code called: disable_cache={disable_cache}, description={description[:50]}")
        prompt = self._build_code_prompt(description, language)
        
        try:
            response = await self._call_api(prompt)
            code = self._extract_code(response, language)
            # 保存原始思考过程
            thinking = response
            if len(thinking) > 2000:  # 如果思考过程太长，截取前后部分
                thinking = thinking[:1000] + "\n... (内容过长，已截断) ...\n" + thinking[-1000:]
            
            return {
                "code": code,
                "thinking": thinking,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to generate code: {e}")
            # 不再使用备用模板，而是直接报告错误
            raise RuntimeError(f"无法生成代码: {e}") from e
    
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
    
    async def generate_enhanced_reasoning(self, task_description: str, available_tools: List[str],
                                         tool_descriptions: str,
                                         previous_steps: List[Dict] = None,
                                         browser_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成增强推理步骤和工具调用 - 使用丰富的工具描述"""
        prompt = self._build_enhanced_reasoning_prompt(
            task_description, available_tools, tool_descriptions, previous_steps, browser_context
        )
        
        try:
            response = await self._call_api(prompt)
            return self._parse_reasoning_response(response)
        except Exception as e:
            logger.error(f"Failed to generate enhanced reasoning: {e}")
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
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-preview-05-20')  # 更新默认模型
        valid_models = [
            'gemini-2.5-flash-preview-05-20',  # 添加新的预览模型
            'gemini-2.0-flash', 'gemini-2.0-pro', 
            'gemini-1.0-pro', 'gemini-pro'
        ]
        
        if model_name not in valid_models:
            logger.warning(f"Invalid Gemini model '{model_name}', using default 'gemini-2.5-flash-preview-05-20'")
            model_name = 'gemini-2.5-flash-preview-05-20'
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024
            }
        }
        
        try:
            response = await self.client.post(
                f"{api_url}/models/{model_name}:generateContent?key={api_key}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            # 如果使用了不稳定的模型，尝试回退到稳定版本
            if model_name != 'gemini-2.0-flash':
                logger.info("Retrying with stable model 'gemini-2.0-flash'")
                response = await self.client.post(
                    f"{api_url}/models/gemini-1.5-flash:generateContent?key={api_key}",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise
    
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
        return f"""请根据以下描述生成{language}代码。

首先，详细思考如何解决这个问题，包括可能的算法、数据结构以及实现步骤。
在你的思考过程中，分析不同的解决方案并选择最佳方案。

描述：{description}

要求：
1. 先详细描述你的思考过程，包括你考虑的不同方法
2. 代码应该完整且可执行
3. 包含必要的注释
4. 处理可能的异常情况
5. 输出结果到控制台

==== 思考过程 ====
(请在这里详细写出你的思考过程，包括算法选择、数据结构、实现思路等)

==== 代码实现 ====
(在此处生成最终代码)
"""
    
    def _build_web_prompt(self, description: str, page_content: str) -> str:
        """构建Web操作提示"""
        return f"""请根据以下描述生成Web操作步骤：

任务描述：{description}

当前页面内容：
{page_content[:1000] if page_content else '无'}

请返回JSON格式的操作步骤列表，每个步骤包含：
- action: 操作类型（navigate, click, fill, wait等）
- selector: CSS选择器（如果需要）
- value: 输入值（如果需要）
- description: 操作描述

示例格式：
[
  {{"action": "navigate", "url": "https://example.com", "description": "打开网站"}},
  {{"action": "fill", "selector": "#search", "value": "搜索内容", "description": "填写搜索框"}},
  {{"action": "click", "selector": "button[type=submit]", "description": "点击搜索按钮"}}
]

请只返回JSON数组，不要包含其他文字："""
    
    def _build_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                previous_steps: List[Dict] = None,
                                browser_context: Optional[Dict[str, Any]] = None) -> str:
        """构建推理提示"""
        tool_descriptions = []
        for tool_name in available_tools:
            # 强制使用严格的工具调用格式和示例，详见 docs/AGENT_IMPROVEMENT_PLAN.md
            logger.debug("构建推理提示：应用严格的工具使用规则和示例")
            if tool_name == 'browser':
                browser_desc = (
                    f"- browser: 用于与网页交互的工具。支持以下主要 ACTION:\n"
                    f"    - `browser_navigate`: 导航到指定URL。PARAMETERS: `{{ \"url\": \"<完整的HTTP/HTTPS URL>\" }}`\n"
                    f"    - `browser_get_text`: 提取页面文本。PARAMETERS: `{{ \"selector\": \"<CSS选择器(可选)>\" }}` (若无selector，则提取body文本)\n"
                    f"    - `browser_click`: 点击指定元素。PARAMETERS: `{{ \"selector\": \"<CSS选择器>\" }}`\n"
                    f"    (更多操作如 browser_fill_form, browser_extract_links 等请参考工具文档，并确保 PARAMETERS 格式正确)"
                )
                tool_descriptions.append(browser_desc)
            elif tool_name == 'python_executor':
                python_desc = (
                    f"- python_executor: 用于执行Python代码。主要 ACTION:\n"
                    f"    - `python_execute`: 执行Python代码。PARAMETERS: `{{ \"code\": \"<Python代码字符串>\" }}`"
                )
                tool_descriptions.append(python_desc)
            else:
                tool_descriptions.append(f"- {tool_name}")
        tools_desc = "\n".join(tool_descriptions)
        
        browser_context_str = ""
        if browser_context:
            bc = browser_context # shortcut
            # Ensuring consistent indentation for the f-string block
            browser_context_str = (
                f"\n\n当前浏览器状态:\n"
                f"- 当前URL: {bc.get('current_url', 'N/A')}\n"
                f"- 页面标题: {bc.get('current_page_title', 'N/A')}\n"
                f"- 最近导航历史:\n  {bc.get('recent_navigation_summary', '无导航历史').replace(chr(10), chr(10) + '  ')}\n" # Indent multi-line summary
                f"- 上次提取文本片段: {bc.get('last_text_snippet', '无')}\n"
                f"- 当前页面链接摘要: {bc.get('links_on_page_summary', '无')}"
            )

        previous_steps_str = ""
        if previous_steps:
            previous_steps_str = "\n\n之前的执行步骤:\n"
            for i, step in enumerate(previous_steps[-3:], 1):  # 只显示最近3步
                action_str = step.get('action', step.get('action_type', 'unknown_action'))
                observation_str = str(step.get('observation', ''))[:200]
                previous_steps_str += f"  {i}. Action: {action_str}, Observation: {observation_str}...\n"

        # The f-string for prompt_template starts here.
        # All lines of the f-string content should be at least at this indentation level or further indented.
        logger.debug("Applying strict tool usage rules from AGENT_IMPROVEMENT_PLAN.md")
        prompt_template = f"""你是一个智能推理助手，需要逐步解决用户的任务。
你的目标是准确、高效地完成任务，并清晰地展示你的决策过程。

任务描述: {task_description}

可用工具:
{tools_desc}
{browser_context_str}
{previous_steps_str}
请分析当前情况（包括任务描述、可用工具、浏览器状态和之前的步骤），输出你的思考过程和下一步行动。格式如下:

THINKING:
[在这里详细描述你的思考过程。分析任务需求，回顾之前的步骤和观察结果（如果有），评估当前状态，并解释你为什么选择下一步的行动和工具。如果之前的步骤失败，请分析失败原因并说明你将如何调整策略。]

ACTION: [选择一个行动类型。可用行动包括: browser_navigate, browser_click, browser_get_text, python_execute, python_analyze, python_visualize, complete_task, error]

TOOL: [如果你选择的ACTION需要工具，请指定使用的具体工具名称，例如：browser, python_executor。如果ACTION是 complete_task 或 error，则TOOL应为 None 或留空。]

PARAMETERS:
[提供一个JSON对象格式的工具参数。严格遵守以下规则：
1.  **对于 `browser_navigate` ACTION**:
    -   `PARAMETERS` 必须是 `{{ \"url\": \"<完整的、有效的HTTP或HTTPS URL>\" }}` 的格式。
    -   示例: `{{ \"url\": \"https://www.google.com\" }}`
2.  **对于 `browser_click` ACTION**:
    -   `PARAMETERS` 必须是 `{{ \"selector\": \"<CSS选择器>\" }}` 的格式。
    -   示例: `{{ \"selector\": \"button#submit\" }}`
3.  **对于 `browser_get_text` ACTION**:
    -   `PARAMETERS` 可以是 `{{ \"selector\": \"<CSS选择器>\" }}` (提取特定元素文本) 或 `{{}}` (提取整个body文本)。
    -   示例: `{{ \"selector\": \"div.article-content\" }}` 或 `{{}}`
4.  **对于 `python_execute` ACTION**:
    -   `PARAMETERS` 必须是 `{{ \"code\": \"<Python代码字符串>\" }}`。
5.  **对于其他 ACTION**: 请根据工具的具体需求提供参数。
6.  **如果ACTION是 `complete_task` 或 `error`**: `PARAMETERS` 应为 `{{}}`。
7.  **绝对禁止使用 `{{\"raw\": ...}}` 作为 `PARAMETERS` 的主要结构。所有参数都应该有明确的键名。**
8.  在生成参数前，请在THINKING中确认所有必需的参数值（尤其是URL）已经从任务描述、之前的步骤或你的分析中获取。如果缺少关键参数，你的ACTION应该是error，并在THINKING中说明原因。
]

CONFIDENCE: [提供一个0.0到1.0之间的小数，表示你对当前决策能够成功推进任务的信心。]

请确保你的输出严格遵循上述格式的每一部分。
"""
        return prompt_template # This return must be at the same indentation level as the start of the method body.
    
    def _build_enhanced_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                        tool_descriptions: str, previous_steps: List[Dict] = None,
                                        browser_context: Optional[Dict[str, Any]] = None) -> str:
        """构建增强推理提示 - 使用丰富的工具描述"""
        
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

        prompt_template = f"""你是一个智能推理助手，拥有丰富的工具库来解决复杂任务。
你的目标是通过自主选择和组合工具，高效准确地完成用户任务。

任务描述: {task_description}

🔧 **你的工具库** (按类型组织，选择最适合的工具):
{tool_descriptions}

**工具使用策略建议**:
1. **分析任务本质**: 理解任务的核心需求和最终目标
2. **工具能力映射**: 将任务需求映射到具体的工具能力
3. **执行路径规划**: 设计最优的工具使用顺序
4. **动态调整策略**: 根据执行结果调整后续行动

**LLM自主决策原则**:
- 你完全自主决定使用哪些工具以及如何使用
- 可以创新性地组合多个工具来解决复杂问题
- 如果某个工具不满足需求，主动寻找替代方案
- 基于工具执行结果，动态调整策略
{browser_context_str}
{previous_steps_str}

请深入分析当前情况，展示你的推理过程，并自主选择最适合的工具和行动。

输出格式:

THINKING:
[详细分析任务需求，评估可用工具，制定执行策略。展示你的推理过程：
- 任务分析：核心目标是什么？
- 工具评估：哪些工具最适合？为什么？
- 策略制定：计划如何使用工具？
- 如果有之前的步骤，分析执行结果并调整策略]

ACTION: [选择的具体行动，如：browser_navigate, python_execute, browser_get_text等]

TOOL: [执行该ACTION需要的工具名称，如：browser, python_executor等]

PARAMETERS:
[JSON格式的参数，必须符合所选工具的参数要求。例如：
- browser_navigate: {{"url": "完整的HTTP/HTTPS URL"}}
- python_execute: {{"code": "Python代码字符串"}}
- browser_get_text: {{"selector": "CSS选择器"}} 或 {{}}
严格按照工具描述中的参数格式要求]

CONFIDENCE: [0.0-1.0的数值，表示对当前决策的信心]

注意：
- 你拥有完全的工具选择自主权，无需外部推荐
- 基于工具的详细描述和示例，做出最佳决策
- 如果遇到问题，展示你的适应性和问题解决能力
- 让工具为你的智能决策服务，而不是被工具限制
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
        return f"""请判断以下任务是否已经完成。

任务描述: {task_description}

已执行步骤数: {len(steps)}

当前输出:
{chr(10).join(current_outputs[-3:]) if current_outputs else '无输出'}

请回答:
COMPLETED: [true/false]
CONFIDENCE: [0.0-1.0]
REASON: [判断原因]

格式要求严格按照上述格式。"""
    
    def _extract_code(self, response: str, language: str) -> str:
        """从响应中提取代码，支持分离思考过程和代码"""
        import re
        
        # 首先查找是否有专用的"代码实现"部分
        code_section_pattern = r'==== 代码实现 ====\s*(.*?)(?:$|==== )'
        section_match = re.search(code_section_pattern, response, re.DOTALL)
        if section_match:
            # 在找到的代码实现部分中寻找代码块
            section_content = section_match.group(1).strip()
            
            # 查找带有语言标记的代码块
            code_pattern = rf'```{language}\s*(.*?)```'
            match = re.search(code_pattern, section_content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
            # 查找通用代码块
            code_pattern = r'```\s*(.*?)```'
            match = re.search(code_pattern, section_content, re.DOTALL)
            if match:
                return match.group(1).strip()
                
            # 如果代码部分没有用代码块标记，直接返回该部分内容
            return section_content
        
        # 传统方式：直接在整个响应中寻找代码块
        # 查找带有语言标记的代码块
        code_pattern = rf'```{language}\s*(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 查找通用代码块
        code_pattern = r'```\s*(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    def _extract_web_actions(self, response: str) -> List[Dict]:
        """从响应中提取Web操作"""
        try:
            # 尝试解析JSON
            import re
            
            # 查找JSON数组
            json_pattern = r'\[(.*?)\]'
            match = re.search(json_pattern, response, re.DOTALL)
            if match:
                json_str = '[' + match.group(1) + ']'
                return json.loads(json_str)
            
            # 尝试直接解析整个响应
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
            # 更好的解析策略：处理多行内容和JSON参数
            current_section = None
            thinking_lines = []
            parameters_lines = []
            
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('THINKING:'):
                    current_section = "thinking"
                    thinking_content = line[9:].strip()
                    if thinking_content:
                        thinking_lines.append(thinking_content)
                elif line.startswith('ACTION:'):
                    current_section = "action"
                    result["action"] = line[7:].strip()
                elif line.startswith('TOOL:'):
                    current_section = "tool"
                    tool_value = line[5:].strip()
                    result["tool"] = tool_value if tool_value and tool_value.lower() != "none" else None
                elif line.startswith('PARAMETERS:'):
                    current_section = "parameters"
                    param_str = line[11:].strip()
                    if param_str:
                        parameters_lines.append(param_str)
                elif line.startswith('CONFIDENCE:'):
                    current_section = "confidence"
                    try:
                        result["confidence"] = float(line[11:].strip())
                    except:
                        result["confidence"] = 0.5
                elif current_section == "thinking" and line:
                    # 继续收集thinking的多行内容
                    thinking_lines.append(line)
                elif current_section == "parameters" and line:
                    # 收集多行PARAMETERS内容
                    parameters_lines.append(line)
            
            # 组装thinking内容
            if thinking_lines:
                result["thinking"] = "\n".join(thinking_lines)
            
            # 解析PARAMETERS (支持多行JSON)
            if parameters_lines:
                parameters_text = "\n".join(parameters_lines)
                try:
                    result["parameters"] = json.loads(parameters_text)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse multi-line parameters JSON: {parameters_text}")
                    # 尝试修复常见的JSON格式问题
                    try:
                        # 移除可能的markdown代码块标记
                        cleaned_params = parameters_text.replace('```json', '').replace('```', '').strip()
                        result["parameters"] = json.loads(cleaned_params)
                    except json.JSONDecodeError:
                        logger.error(f"Could not parse parameters as JSON: {parameters_text}")
                        result["parameters"] = {"raw": parameters_text}
            
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
                    completed_str = line[10:].strip().lower()
                    result["completed"] = completed_str in ['true', 'yes', '1']
                elif line.startswith('CONFIDENCE:'):
                    try:
                        result["confidence"] = float(line[11:].strip())
                    except:
                        result["confidence"] = 0.5
                elif line.startswith('REASON:'):
                    result["reason"] = line[7:].strip()
        except Exception as e:
            logger.error(f"Error parsing completion response: {e}")
            result["reason"] = f"Parse error: {e}"
        
        return result

    # 备注: 我们不再需要备用代码模板，所有的代码生成都应该由LLM完成
    # 如果LLM调用失败，应当抛出异常，而不是使用备用代码模板
    
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