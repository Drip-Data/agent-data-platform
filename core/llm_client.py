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
import time

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
                                         execution_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成增强推理步骤和工具调用 - 使用丰富的工具描述和执行上下文"""
        prompt = self._build_enhanced_reasoning_prompt(
            task_description, available_tools, tool_descriptions, previous_steps, execution_context
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

    async def analyze_task_requirements(self, task_description: str) -> Dict[str, Any]:
        """分析任务描述，总结需要的功能和能力 - 帮助LLM更好地在mcp_tools.json中找到合适工具"""
        prompt = self._build_task_analysis_prompt(task_description)
        
        try:
            response = await self._call_api(prompt)
            return self._parse_task_requirements_response(response)
        except Exception as e:
            logger.error(f"Failed to analyze task requirements: {e}")
            return {
                "task_type": "unknown",
                "required_capabilities": [],
                "tools_needed": [],
                "reasoning": f"分析失败: {str(e)}",
                "confidence": 0.0
            }

    async def get_next_action(self, task_description: str, available_tools: List[str],
                              tool_descriptions: str, previous_steps: List[Dict] = None,
                              execution_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取LLM的下一个行动决策。
        这是一个统一的接口，用于在增强推理模式下获取LLM的决策。
        它将直接调用 generate_enhanced_reasoning 方法。
        """
        logger.info("Calling get_next_action (unified LLM decision interface)")
        return await self.generate_enhanced_reasoning(
            task_description=task_description,
            available_tools=available_tools,
            tool_descriptions=tool_descriptions,
            previous_steps=previous_steps,
            execution_context=execution_context
        )

    async def _call_api(self, prompt: str) -> str:
        """调用相应的API，并记录完整的交互信息"""
        # 🔍 新增：记录API调用信息
        logger.info("🚀 LLM API调用开始")
        logger.info(f"   提供商: {self.provider.value}")
        logger.info(f"   Prompt长度: {len(prompt)} 字符")
        
        # 记录prompt内容（调试模式下记录更多详情）
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"   完整Prompt内容:\n{prompt}")
        else:
            # 生产模式下只记录前后片段
            prompt_preview = prompt[:200] + "..." + prompt[-100:] if len(prompt) > 300 else prompt
            logger.info(f"   Prompt预览: {prompt_preview}")
        
        start_time = time.time()
        
        try:
            # 根据提供商调用相应API
            if self.provider == LLMProvider.VLLM:
                response = await self._call_vllm(prompt)
            elif self.provider == LLMProvider.OPENAI:
                response = await self._call_openai(prompt)
            elif self.provider == LLMProvider.GEMINI:
                response = await self._call_gemini(prompt)
            elif self.provider == LLMProvider.DEEPSEEK:
                response = await self._call_deepseek(prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            # 🔍 新增：记录API响应信息
            duration = time.time() - start_time
            logger.info("✅ LLM API调用成功")
            logger.info(f"   响应时间: {duration:.2f}秒")
            logger.info(f"   响应长度: {len(response)} 字符")
            
            # 记录响应内容
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   完整响应内容:\n{response}")
            else:
                # 生产模式下只记录前后片段
                response_preview = response[:200] + "..." + response[-100:] if len(response) > 300 else response
                logger.info(f"   响应预览: {response_preview}")
            
            return response
            
        except Exception as e:
            # 🔍 新增：记录API错误信息
            duration = time.time() - start_time
            logger.error("❌ LLM API调用失败")
            logger.error(f"   失败时间: {duration:.2f}秒")
            logger.error(f"   错误类型: {type(e).__name__}")
            logger.error(f"   错误信息: {str(e)}")
            
            # 记录更多错误细节（如果有的话）
            if hasattr(e, 'response') and e.response:
                logger.error(f"   HTTP状态码: {getattr(e.response, 'status_code', 'Unknown')}")
                logger.error(f"   响应内容: {getattr(e.response, 'text', 'No response text')}")
            
            raise
    
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
                "maxOutputTokens": 4096,  # 🔍 增加token限制，确保完整响应
                "candidateCount": 1,
                "stopSequences": [],
                "topP": 0.9,
                "topK": 40
            }
        }
        
        try:
            # 🔧 添加DNS解析重试机制
            from httpx._config import Timeout
            import asyncio
            
            # 创建一个临时客户端，配置更长的超时和重试
            temp_client = httpx.AsyncClient(
                timeout=Timeout(timeout=120.0, connect=30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                trust_env=False  # 不使用环境代理设置
            )
            
            response = await temp_client.post(
                f"{api_url}/models/{model_name}:generateContent?key={api_key}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 检查响应格式
            if "candidates" not in result:
                raise ValueError(f"Invalid Gemini response format: missing 'candidates' field")
            
            if not result["candidates"]:
                raise ValueError(f"Empty candidates in Gemini response")
                
            candidate = result["candidates"][0]
            if "content" not in candidate:
                raise ValueError(f"Invalid candidate format: missing 'content' field")
                
            content = candidate["content"]
            if "parts" not in content:
                raise ValueError(f"Invalid content format: missing 'parts' field")
                
            if not content["parts"]:
                raise ValueError(f"Empty parts in content")
                
            part = content["parts"][0]
            if "text" not in part:
                raise ValueError(f"Invalid part format: missing 'text' field")
                
            await temp_client.aclose()
            return part["text"]
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            
            # 🔧 强化的重试机制：使用稳定模型+直接IP
            if "name resolution" in str(e).lower() or "connection" in str(e).lower():
                logger.info("尝试使用备用网络配置重试...")
                try:
                    # 使用备用DNS配置
                    backup_client = httpx.AsyncClient(
                        timeout=Timeout(timeout=180.0, connect=60.0),
                        limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
                        trust_env=False
                    )
                    
                    # 使用稳定模型重试
                    stable_model = 'gemini-1.5-flash'
                    response = await backup_client.post(
                        f"{api_url}/models/{stable_model}:generateContent?key={api_key}",
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    # 同样的格式检查
                    if ("candidates" in result and result["candidates"] and 
                        "content" in result["candidates"][0] and
                        "parts" in result["candidates"][0]["content"] and
                        result["candidates"][0]["content"]["parts"] and
                        "text" in result["candidates"][0]["content"]["parts"][0]):
                        await backup_client.aclose()
                        logger.info("✅ 使用备用网络配置成功恢复")
                        return result["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        raise ValueError(f"Invalid backup response format")
                        
                except Exception as backup_e:
                    logger.error(f"备用网络配置也失败: {backup_e}")
                    raise e
            else:
                raise e
    
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

        # 构建优化的基础推理提示
        logger.debug("Applying strict tool usage rules from AGENT_IMPROVEMENT_PLAN.md")
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

### 工具参数规范:
1. **browser_navigate**: `{{"url": "完整HTTP/HTTPS URL"}}`
2. **browser_click**: `{{"selector": "CSS选择器"}}`
3. **browser_get_text**: `{{"selector": "CSS选择器"}}` 或 `{{}}`
4. **python_execute**: `{{"code": "Python代码字符串"}}`
5. **complete_task**: `{{}}`
6. **error**: `{{}}`

### 决策优先级:
- 优先使用现有工具完成任务
- 确保参数完整且格式正确  
- 失败时分析原因并调整策略
- 必要时考虑工具扩展

**只返回JSON对象，不要其他文字！**
"""
        return prompt_template
    
    def _build_enhanced_reasoning_prompt(self, task_description: str, available_tools: List[str],
                                        tool_descriptions: str, previous_steps: List[Dict] = None,
                                        execution_context: Optional[Dict[str, Any]] = None) -> str:
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

        # 智能历史分析和状态检测
        if previous_steps:
            # 统计关键操作
            analyze_count = sum(1 for s in previous_steps if s.get('tool_id') == 'mcp-search-tool' and s.get('action') == 'analyze_tool_needs')
            search_count = sum(1 for s in previous_steps if s.get('tool_id') == 'mcp-search-tool' and s.get('action') == 'search_and_install_tools')
            tool_install_success = any('成功安装' in str(s.get('observation', '')) or 'successfully installed' in str(s.get('observation', '')) for s in previous_steps)
            
            # 检查推荐信号
            has_search_recommendation = any(
                'search_for_new_tools' in str(s.get('observation', '')) or
                '需要新工具' in str(s.get('observation', '')) or
                'install' in str(s.get('observation', ''))
                for s in previous_steps
            )
            
            # 检查失败模式
            consecutive_failures = 0
            for s in reversed(previous_steps[-3:]):
                if not s.get('success', True):
                    consecutive_failures += 1
                else:
                    break
            
            # 构建智能历史摘要
            history_summary = []
            for i, s in enumerate(previous_steps[-4:], 1):  # 显示最近4步
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
            
            # 智能决策指导
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

        # 增强的决策逻辑 - 基于任务类型的智能判断
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
            "### ⚡ OPTIMIZATION RULES:",
            "- **Never** call 'analyze_tool_needs' more than 2 times",
            "- **Always** follow analysis recommendations",
            "- **Prefer** using newly installed tools over workarounds",
            "- **Complete task** once capabilities are sufficient",
            "",
        ])

        # 执行上下文信息
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

        # 严格的响应格式
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
        
        return "\n".join(prompt_parts)
    
    def _build_summary_prompt(self, task_description: str, steps: List[Dict], 
                                   final_outputs: List[str]) -> str:
        """生成任务执行总结"""
        # 安全地提取步骤描述
        step_descriptions = []
        for step in steps:
            if isinstance(step, dict):
                # 尝试不同的可能字段名
                desc = step.get('description') or step.get('observation') or step.get('action_type', 'Unknown step')
                step_descriptions.append(str(desc))
            else:
                step_descriptions.append(str(step))
        
        prompt = f"""请根据以下描述生成任务执行总结：

任务描述：{task_description}

步骤：
{'; '.join(step_descriptions)}

最终输出：{'; '.join(final_outputs[:3])}
"""
        return prompt
    
    def _build_completion_check_prompt(self, task_description: str, steps: List[Dict], 
                                   current_outputs: List[str]) -> str:
        """检查任务是否完成"""
        # 安全地提取步骤描述
        step_descriptions = []
        for step in steps:
            if isinstance(step, dict):
                # 尝试不同的可能字段名
                desc = step.get('description') or step.get('observation') or step.get('action_type', 'Unknown step')
                step_descriptions.append(str(desc))
            else:
                step_descriptions.append(str(step))
        
        prompt = f"""请根据以下描述检查任务是否完成：

任务描述：{task_description}

步骤：
{'; '.join(step_descriptions)}

当前输出：{'; '.join(current_outputs[:3])}
"""
        return prompt
    
    def _extract_code(self, response: str, language: str) -> str:
        """从响应中提取代码"""
        # 这里需要实现从响应中提取代码的逻辑
        return response
    
    def _extract_web_actions(self, response: str) -> List[Dict]:
        """从响应中提取Web操作步骤"""
        # 这里需要实现从响应中提取Web操作步骤的逻辑
        return []
    
    def _fallback_web_actions(self, description: str) -> List[Dict]:
        """生成备用Web操作步骤"""
        # 这里需要实现生成备用Web操作步骤的逻辑
        return []
    
    def _parse_reasoning_response(self, response: str) -> Dict[str, Any]:
        """解析推理响应 - 支持增强的MCP主动选择机制"""
        import re
        
        logger.info(f"🔍 解析LLM响应 (长度: {len(response)})")
        
        try:
            # 首先尝试直接解析JSON
            response_clean = response.strip()
            
            # 🔍 增强的JSON提取 - 处理各种格式
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',  # markdown代码块
                r'```\s*(\{.*?\})\s*```',      # 普通代码块  
                r'(\{[^{}]*"thinking"[^{}]*\})', # 包含thinking的JSON
                r'(\{.*?\})',                  # 任何JSON对象
            ]
            
            json_text = None
            for pattern in json_patterns:
                match = re.search(pattern, response_clean, re.DOTALL)
                if match:
                    json_text = match.group(1)
                    logger.info(f"✅ 使用模式提取到JSON: {pattern}")
                    break
            
            # 如果没有找到JSON块，尝试直接解析
            if not json_text:
                # 移除可能的markdown代码块包装
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                if response_clean.endswith('```'):
                    response_clean = response_clean[:-3]
                json_text = response_clean.strip()
            
            # 🔍 修复常见的JSON格式问题
            if json_text:
                # 修复被截断的JSON
                if not json_text.endswith('}') and json_text.count('{') > json_text.count('}'):
                    missing_braces = json_text.count('{') - json_text.count('}')
                    json_text += '}' * missing_braces
                    logger.warning(f"🔧 修复了 {missing_braces} 个缺失的右括号")
                
                # 修复常见的格式问题
                json_text = json_text.replace('\n', '\\n').replace('\r', '\\r')
                
                # 尝试解析JSON
                try:
                    parsed = json.loads(json_text)
                    logger.info("✅ JSON解析成功")
                    
                    # 🔍 智能字段补全和验证
                    result = self._validate_and_complete_parsed_response(parsed)
                    
                    logger.info(f"🎯 最终解析结果: action={result.get('action')}, tool_id={result.get('tool_id')}, confidence={result.get('confidence')}")
                    return result
                    
                except json.JSONDecodeError as json_error:
                    logger.warning(f"❌ JSON解析失败: {json_error}")
                    # 继续使用备用解析方法
            
        except Exception as e:
            logger.error(f"❌ 响应解析过程中出错: {e}")
        
        # 🔍 增强的备用解析方法
        logger.warning("🔄 使用备用解析方法")
        return self._fallback_parse_response(response)
    
    def _validate_and_complete_parsed_response(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """验证并补全解析后的响应"""
        result = {}
        
        # 补全thinking字段
        result['thinking'] = parsed.get('thinking', f"LLM响应缺少thinking字段: {str(parsed)[:200]}")
        
        # 补全并验证action字段
        action = parsed.get('action', 'error')
        result['action'] = action
        
        # 补全并验证tool_id字段
        tool_id = parsed.get('tool_id') or parsed.get('tool')
        
        # 🔍 智能推断工具ID
        if not tool_id:
            if action in ['search_and_install_tools', 'analyze_tool_needs']:
                tool_id = 'mcp-search-tool'
                logger.info(f"🔧 自动推断工具ID: {tool_id} (基于action: {action})")
            elif 'search' in result['thinking'].lower() or 'install' in result['thinking'].lower():
                tool_id = 'mcp-search-tool'
                logger.info(f"🔧 基于thinking内容推断工具ID: {tool_id}")
        
        result['tool_id'] = tool_id
        result['tool'] = tool_id  # 向后兼容
        
        # 补全parameters字段
        parameters = parsed.get('parameters', {})
        
        # 🔍 基于action智能补全参数
        if action in ['search_and_install_tools', 'analyze_tool_needs'] and not parameters.get('task_description'):
            # 从thinking中提取任务描述
            thinking = result['thinking']
            if 'TASK ANALYSIS:' in thinking:
                task_desc_start = thinking.find('TASK ANALYSIS:') + len('TASK ANALYSIS:')
                task_desc_end = thinking.find('STEP 2', task_desc_start)
                if task_desc_end > task_desc_start:
                    task_desc = thinking[task_desc_start:task_desc_end].strip()
                    parameters['task_description'] = task_desc[:200]  # 限制长度
        
        result['parameters'] = parameters
        
        # 补全并验证confidence字段
        confidence = parsed.get('confidence', 0.5)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            confidence = 0.5
        result['confidence'] = confidence
        
        return result
    
    def _fallback_parse_response(self, response: str) -> Dict[str, Any]:
        """增强的备用解析方法"""
        import re
        
        logger.info("🔄 执行增强备用解析")
        
        # 🔍 增强的字段提取
        result = {
            'thinking': self._extract_thinking_field(response),
            'action': self._extract_action_field(response),
            'tool_id': self._extract_tool_id_field(response),
            'parameters': self._extract_parameters_field(response),
            'confidence': self._extract_confidence_field(response)
        }
        
        # 🔍 智能推断和修正
        result = self._smart_inference_and_correction(result, response)
        
        # 向后兼容
        result['tool'] = result['tool_id']
        
        logger.info(f"🎯 备用解析结果: action={result['action']}, tool_id={result['tool_id']}")
        return result
    
    def _extract_thinking_field(self, response: str) -> str:
        """提取thinking字段"""
        import re
        patterns = [
            r'"thinking":\s*"([^"]*(?:\\.[^"]*)*)"',
            r'thinking["\']?\s*[:=]\s*["\']([^"\']*)["\']',
            r'STEP 1[^:]*:([^"]*?)(?:STEP 2|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果都找不到，返回响应的前500字符
        return response[:500]
    
    def _extract_action_field(self, response: str) -> str:
        """提取action字段"""
        import re
        patterns = [
            r'"action":\s*"([^"]+)"',
            r'action["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 🔍 基于内容推断action
        if any(keyword in response.lower() for keyword in ['search', 'install', 'tool']):
            return 'search_and_install_tools'
        elif any(keyword in response.lower() for keyword in ['analyze', 'need']):
            return 'analyze_tool_needs'
        elif any(keyword in response.lower() for keyword in ['complete', 'finish', 'done']):
            return 'complete_task'
        
        return 'error'
    
    def _extract_tool_id_field(self, response: str) -> str:
        """提取tool_id字段"""
        import re
        patterns = [
            r'"tool_id":\s*"([^"]+)"',
            r'"tool":\s*"([^"]+)"',
            r'tool_id["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_parameters_field(self, response: str) -> Dict[str, Any]:
        """提取parameters字段"""
        import re
        
        # 尝试提取完整的parameters对象
        params_match = re.search(r'"parameters":\s*(\{[^}]*\})', response, re.DOTALL)
        if params_match:
            try:
                return json.loads(params_match.group(1))
            except:
                pass
        
        # 备用方案：提取常见参数
        params = {}
        
        # 提取task_description
        task_desc_patterns = [
            r'"task_description":\s*"([^"]*)"',
            r'task_description["\']?\s*[:=]\s*["\']([^"\']*)["\']',
        ]
        
        for pattern in task_desc_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                params['task_description'] = match.group(1)
                break
        
        return params
    
    def _extract_confidence_field(self, response: str) -> float:
        """提取confidence字段"""
        import re
        
        patterns = [
            r'"confidence":\s*([0-9.]+)',
            r'confidence["\']?\s*[:=]\s*([0-9.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    confidence = float(match.group(1))
                    return max(0.0, min(1.0, confidence))
                except:
                    pass
        
        return 0.5
    
    def _smart_inference_and_correction(self, result: Dict[str, Any], response: str) -> Dict[str, Any]:
        """智能推断和修正结果"""
        
        # 如果action是error但响应中包含工具相关内容，尝试修正
        if result['action'] == 'error':
            if any(keyword in response.lower() for keyword in ['mcp-search', 'search_and_install', 'tool']):
                result['action'] = 'search_and_install_tools'
                logger.info("🔧 修正action为: search_and_install_tools")
        
        # 如果没有tool_id但action需要工具，自动设置
        if not result['tool_id'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            result['tool_id'] = 'mcp-search-tool'
            logger.info("🔧 自动设置tool_id为: mcp-search-tool")
        
        # 如果parameters为空但action需要参数，尝试生成
        if not result['parameters'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            # 从thinking中提取任务相关信息
            thinking = result['thinking']
            params = {}
            
            if '任务' in thinking or 'task' in thinking.lower():
                # 提取可能的任务描述
                lines = thinking.split('\n')
                for line in lines:
                    if '任务' in line or 'task' in line.lower():
                        # 简化的任务描述提取
                        task_desc = line.strip()[:100]
                        params['task_description'] = task_desc
                        break
            
            if params:
                result['parameters'] = params
                logger.info(f"🔧 生成参数: {params}")
        
        return result
    
    def _parse_completion_response(self, response: str) -> Dict[str, Any]:
        """解析完成检查响应"""
        # 这里需要实现解析完成检查响应的逻辑
        return {"completed": True, "confidence": 1.0}

    def _build_task_analysis_prompt(self, task_description: str) -> str:
        """构建任务需求分析提示词"""
        prompt = f"""你是一个专业的任务分析助手。请仔细分析以下任务描述，总结完成这个任务需要什么样的功能和能力。

任务描述: {task_description}

请从以下维度分析这个任务：

1. **任务类型分类** (task_type):
   - reasoning: 需要复杂推理、多工具协同、分析对比
   - web: 主要涉及网页操作、信息搜索、网站导航  
   - code: 主要是编程、算法、计算、数据处理
   - image: 图像生成、图像处理、视觉相关
   - file: 文件操作、文档处理、格式转换
   - data: 数据分析、统计、可视化
   - communication: 通信、发送消息、API调用

2. **核心能力需求** (required_capabilities):
   分析任务需要哪些具体的技术能力，例如：
   - image_generation (图像生成)
   - web_scraping (网页抓取)
   - data_analysis (数据分析)
   - file_processing (文件处理)
   - code_execution (代码执行)
   - search (搜索功能)
   - browser_automation (浏览器自动化)
   - database_access (数据库访问)
   - api_calls (API调用)
   - text_processing (文本处理)

3. **具体工具类型** (tools_needed):
   基于能力需求，推测可能需要的工具类型，例如：
   - 图像生成工具 (如DALL-E, Stable Diffusion相关)
   - 浏览器操作工具 (如Selenium, Playwright相关)
   - 数据分析工具 (如pandas, numpy相关)
   - 文件处理工具 (如PDF, Excel处理相关)
   - API调用工具 (如HTTP客户端相关)

4. **关键特征识别** (key_features):
   识别任务描述中的关键特征，帮助匹配工具

请严格按照以下JSON格式返回分析结果，不要包含任何其他文字：

{{
  "task_type": "...",
  "required_capabilities": ["capability1", "capability2", "..."],
  "tools_needed": ["tool_type1", "tool_type2", "..."],
  "key_features": ["feature1", "feature2", "..."],
  "reasoning": "详细的分析推理过程，说明为什么需要这些能力和工具",
  "confidence": 0.9
}}

要求：
- 分析要准确且具体
- 不要猜测不存在的需求
- 重点关注任务的核心功能需求
- 确保JSON格式正确"""
        
        return prompt

    def _parse_task_requirements_response(self, response: str) -> Dict[str, Any]:
        """解析任务需求分析响应"""
        try:
            import re
            import json
            
            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # 确保所有必需字段存在，设置默认值
                result = {
                    "task_type": parsed.get("task_type", "unknown"),
                    "required_capabilities": parsed.get("required_capabilities", []),
                    "tools_needed": parsed.get("tools_needed", []),
                    "key_features": parsed.get("key_features", []),
                    "reasoning": parsed.get("reasoning", "无分析过程"),
                    "confidence": float(parsed.get("confidence", 0.7))
                }
                
                logger.info(f"✅ 任务需求分析完成:")
                logger.info(f"   任务类型: {result['task_type']}")
                logger.info(f"   所需能力: {result['required_capabilities']}")
                logger.info(f"   工具类型: {result['tools_needed']}")
                logger.info(f"   置信度: {result['confidence']}")
                
                return result
            else:
                logger.error("无法从响应中提取有效的JSON格式")
                return self._create_fallback_requirements_analysis(response)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return self._create_fallback_requirements_analysis(response)
        except Exception as e:
            logger.error(f"解析任务需求响应时出错: {e}")
            return self._create_fallback_requirements_analysis(response)

    def _create_fallback_requirements_analysis(self, response: str) -> Dict[str, Any]:
        """创建备用的需求分析结果"""
        # 基于响应内容的简单关键词分析
        response_lower = response.lower()
        
        capabilities = []
        tools_needed = []
        task_type = "unknown"
        
        # 简单的关键词匹配逻辑
        if any(word in response_lower for word in ['图', '图片', '图像', 'image', 'picture', '生成']):
            capabilities.append("image_generation")
            tools_needed.append("图像生成工具")
            task_type = "image"
        
        if any(word in response_lower for word in ['网页', 'web', 'browser', '浏览', '搜索']):
            capabilities.append("web_scraping")
            capabilities.append("browser_automation")
            tools_needed.append("浏览器操作工具")
            if task_type == "unknown":
                task_type = "web"
        
        if any(word in response_lower for word in ['代码', 'code', 'python', '编程', '算法']):
            capabilities.append("code_execution")
            tools_needed.append("代码执行工具")
            if task_type == "unknown":
                task_type = "code"
        
        if any(word in response_lower for word in ['数据', 'data', '分析', 'analysis']):
            capabilities.append("data_analysis")
            tools_needed.append("数据分析工具")
            if task_type == "unknown":
                task_type = "data"
        
        if any(word in response_lower for word in ['文件', 'file', '文档', 'document']):
            capabilities.append("file_processing")
            tools_needed.append("文件处理工具")
            if task_type == "unknown":
                task_type = "file"
        
        return {
            "task_type": task_type,
            "required_capabilities": list(set(capabilities)),
            "tools_needed": list(set(tools_needed)),
            "key_features": [],
            "reasoning": f"基于响应内容的简单分析: {response[:100]}...",
            "confidence": 0.6
        }
