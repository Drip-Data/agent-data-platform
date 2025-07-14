#!/usr/bin/env python3
"""
LLM客户端统一接口
支持多种API提供商：vLLM本地服务、OpenAI、Google Gemini、DeepSeek等
"""

import os
import logging
import json
from typing import Dict, Any, Optional, List
from enum import Enum
import time
import httpx # 重新引入httpx，因为_call_api中的异常处理需要它

from core.llm_providers.interfaces import ILLMProvider
from core.llm_providers.openai_provider import OpenAIProvider
from core.llm_providers.gemini_provider import GeminiProvider
from core.llm_providers.deepseek_provider import DeepSeekProvider
from core.llm_providers.vllm_provider import VLLMProvider

# 导入提示构建器
from core.llm.prompt_builders.interfaces import IPromptBuilder
from core.llm.prompt_builders.code_prompt_builder import CodePromptBuilder
from core.llm.prompt_builders.web_prompt_builder import WebPromptBuilder
from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder
from core.llm.prompt_builders.summary_prompt_builder import SummaryPromptBuilder
from core.llm.prompt_builders.completion_check_prompt_builder import CompletionCheckPromptBuilder
from core.llm.prompt_builders.task_analysis_prompt_builder import TaskAnalysisPromptBuilder

# 导入响应解析器
from core.llm.response_parsers.interfaces import IResponseParser
from core.llm.response_parsers.reasoning_response_parser import ReasoningResponseParser
from core.llm.response_parsers.code_response_parser import CodeResponseParser
from core.llm.response_parsers.web_actions_response_parser import WebActionsResponseParser
from core.llm.response_parsers.completion_check_response_parser import CompletionCheckResponseParser
from core.llm.response_parsers.task_analysis_response_parser import TaskAnalysisResponseParser


logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    """LLM提供商枚举"""
    VLLM = "vllm"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

from core.unified_tool_manager import UnifiedToolManager

class LLMClient:
    """统一的LLM客户端"""
    
    def __init__(self, config: Dict[str, Any], tool_manager: UnifiedToolManager):
        self.config = config
        self.provider_instance: Optional[ILLMProvider] = None # 初始化为None
        
        # 确保环境变量传递到配置中
        self._enrich_config_with_env_vars()
        
        # 实例化提示构建器
        streaming_mode = config.get('streaming_mode', True)  # 默认启用XML流式模式
        self.code_prompt_builder: IPromptBuilder = CodePromptBuilder()
        self.web_prompt_builder: IPromptBuilder = WebPromptBuilder()
        self.reasoning_prompt_builder: IPromptBuilder = ReasoningPromptBuilder(tool_manager=tool_manager, streaming_mode=streaming_mode)
        self.summary_prompt_builder: IPromptBuilder = SummaryPromptBuilder()
        self.completion_check_prompt_builder: IPromptBuilder = CompletionCheckPromptBuilder()
        self.task_analysis_prompt_builder: IPromptBuilder = TaskAnalysisPromptBuilder()

        # 实例化响应解析器
        self.reasoning_response_parser: IResponseParser = ReasoningResponseParser()
        self.code_response_parser: IResponseParser = CodeResponseParser()
        self.web_actions_response_parser: IResponseParser = WebActionsResponseParser()
        self.completion_check_response_parser: IResponseParser = CompletionCheckResponseParser()
        self.task_analysis_response_parser: IResponseParser = TaskAnalysisResponseParser()

        # 优先使用配置中指定的提供商，没有则进行自动检测
        provider_name = config.get('provider') or config.get('default_provider')
        if provider_name:
            provider_name = provider_name.lower()
            if provider_name == 'vllm':
                self.provider = LLMProvider.VLLM
                self.provider_instance = VLLMProvider(config)
            elif provider_name == 'openai':
                self.provider = LLMProvider.OPENAI
                self.provider_instance = OpenAIProvider(config)
            elif provider_name == 'gemini':
                self.provider = LLMProvider.GEMINI
                # 从嵌套配置中提取 Gemini 特定配置并合并到根级别
                gemini_config = config.copy()
                if 'providers' in config and 'gemini' in config['providers']:
                    gemini_provider_config = config['providers']['gemini']
                    gemini_config.update(gemini_provider_config)
                self.provider_instance = GeminiProvider(gemini_config)
            elif provider_name == 'deepseek':
                self.provider = LLMProvider.DEEPSEEK
                self.provider_instance = DeepSeekProvider(config)
            else:
                logger.warning(f"Unknown provider in config: {provider_name}, falling back to auto-detection")
                self.provider = self._detect_provider()
                self._initialize_provider_instance()
        else:
            self.provider = self._detect_provider()
            self._initialize_provider_instance()
            
        logger.info(f"Initialized LLM client with provider: {self.provider.value}")

    def _enrich_config_with_env_vars(self):
        """将环境变量添加到配置中以确保providers能正确访问"""
        env_vars = {
            'gemini_api_key': os.getenv('GEMINI_API_KEY'),
            'gemini_api_url': os.getenv('GEMINI_API_URL'),
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'openai_base_url': os.getenv('OPENAI_BASE_URL'),
            'deepseek_api_key': os.getenv('DEEPSEEK_API_KEY'),
            'deepseek_base_url': os.getenv('DEEPSEEK_BASE_URL'),
            'vllm_base_url': os.getenv('VLLM_BASE_URL')
        }
        
        # 只添加非空的环境变量
        for key, value in env_vars.items():
            if value:
                self.config[key] = value
        
        logger.debug(f"Enriched config with environment variables: {list(self.config.keys())}")

    def _initialize_provider_instance(self):
        """根据检测到的提供商初始化具体的LLM提供商实例"""
        try:
            if self.provider == LLMProvider.VLLM:
                self.provider_instance = VLLMProvider(self.config)
            elif self.provider == LLMProvider.OPENAI:
                self.provider_instance = OpenAIProvider(self.config)
            elif self.provider == LLMProvider.GEMINI:
                # 从嵌套配置中提取 Gemini 特定配置并合并到根级别
                gemini_config = self.config.copy()
                if 'providers' in self.config and 'gemini' in self.config['providers']:
                    gemini_provider_config = self.config['providers']['gemini']
                    gemini_config.update(gemini_provider_config)
                self.provider_instance = GeminiProvider(gemini_config)
            elif self.provider == LLMProvider.DEEPSEEK:
                self.provider_instance = DeepSeekProvider(self.config)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            # 🔍 验证provider_instance不是Mock对象
            if self.provider_instance and "Mock" in type(self.provider_instance).__name__:
                logger.error(f"❌ Provider初始化后发现Mock对象: {type(self.provider_instance)}")
                raise ValueError(f"Provider初始化失败：返回了Mock对象 {type(self.provider_instance)}")
            
            logger.debug(f"✅ Provider实例初始化成功: {type(self.provider_instance).__name__}")
            
        except Exception as e:
            logger.error(f"❌ Provider初始化失败: {e}")
            self.provider_instance = None
            raise
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取当前LLM配置"""
        return {
            "provider": self.provider.value,
            "config": self.config,
            "provider_instance": str(type(self.provider_instance).__name__) if self.provider_instance else None
        }
    
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
    
    async def generate_code(self, description: str, language: str = "python") -> Dict[str, Any]:
        """生成代码，并返回思考过程和代码"""
        disable_cache = os.getenv("DISABLE_CACHE") or self.config.get("disable_cache", False)
        logger.debug(f"LLMClient.generate_code called: disable_cache={disable_cache}, description={description[:50]}")
        messages = self.code_prompt_builder.build_prompt(description=description, language=language)
        
        try:
            response = await self._call_api(messages)
            return self.code_response_parser.parse_response(response, language=language)
        except Exception as e:
            logger.error(f"Failed to generate code: {e}")
            raise RuntimeError(f"无法生成代码: {e}") from e
    
    async def generate_web_actions(self, description: str, page_content: str = "") -> Dict[str, Any]:
        """生成Web操作步骤"""
        messages = self.web_prompt_builder.build_prompt(description=description, page_content=page_content)
        
        try:
            response = await self._call_api(messages)
            return self.web_actions_response_parser.parse_response(response, description=description)
        except Exception as e:
            logger.error(f"Failed to generate web actions: {e}")
            # 备用逻辑现在由解析器内部处理
            return self.web_actions_response_parser.parse_response("", description=description) # 传入空字符串触发备用
    
    async def generate_reasoning(self, task_description: str, available_tools: List[str],
                                previous_steps: Optional[List[Dict[str, Any]]] = None,
                                browser_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成推理步骤和工具调用"""
        messages = self.reasoning_prompt_builder.build_prompt(
            task_description=task_description,
            available_tools=available_tools,
            previous_steps=previous_steps,
            browser_context=browser_context
        )
        
        try:
            response = await self._call_api(messages)
            return self.reasoning_response_parser.parse_response(response)
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
                                         previous_steps: Optional[List[Dict[str, Any]]] = None,
                                         execution_context: Optional[Dict[str, Any]] = None,
                                         streaming_mode: Optional[bool] = None) -> Dict[str, Any]:
        """生成增强推理步骤和工具调用 - 使用丰富的工具描述和执行上下文，支持XML流式模式"""
        messages = self.reasoning_prompt_builder.build_prompt(
            task_description=task_description,
            available_tools=available_tools,
            tool_descriptions=tool_descriptions,
            previous_steps=previous_steps,
            execution_context=execution_context,
            streaming_mode=streaming_mode
        )
        
        try:
            response = await self._call_api(messages)
            return self.reasoning_response_parser.parse_response(response)
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
        messages = self.summary_prompt_builder.build_prompt(
            task_description=task_description,
            steps=steps,
            final_outputs=final_outputs
        )
        
        try:
            response = await self._call_api(messages)
            return response.strip() # 总结通常是纯文本，直接返回
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Task completed with {len(steps)} steps. Final outputs: {'; '.join(final_outputs[:3])}"
    
    async def check_task_completion(self, task_description: str, steps: List[Dict],
                                   current_outputs: List[str]) -> Dict[str, Any]:
        """检查任务是否完成"""
        messages = self.completion_check_prompt_builder.build_prompt(
            task_description=task_description,
            steps=steps,
            current_outputs=current_outputs
        )
        
        try:
            response = await self._call_api(messages)
            return self.completion_check_response_parser.parse_response(response)
        except Exception as e:
            logger.error(f"Failed to check completion: {e}")
            return {"completed": False, "confidence": 0.0, "reason": f"Error: {e}"}

    async def analyze_task_requirements(self, task_description: str) -> Dict[str, Any]:
        """分析任务描述，总结需要的功能和能力 - 帮助LLM更好地在mcp_tools.json中找到合适工具"""
        messages = self.task_analysis_prompt_builder.build_prompt(task_description=task_description)
        
        try:
            response = await self._call_api(messages)
            return self.task_analysis_response_parser.parse_response(response)
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
                                tool_descriptions: str, previous_steps: Optional[List[Dict[str, Any]]] = None, # 修改类型提示
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

    async def _call_api(self, messages: List[Dict[str, Any]], timeout: int = 120, stop_sequences: Optional[List[str]] = None) -> Dict[str, Any]:
        """调用相应的API，并记录完整的交互信息"""
        # 🔧 新增：预调用数据验证 - 防止数据类型错误传播
        try:
            validated_messages = self._validate_input_messages(messages)
        except Exception as validation_error:
            logger.error(f"输入消息验证失败: {validation_error}")
            raise ValueError(f"LLM API调用参数无效: {validation_error}")
        
        # 🔍 新增：记录API调用信息
        logger.info("🚀 LLM API调用开始")
        logger.info(f"   提供商: {self.provider.value}")
        logger.info(f"   消息数量: {len(validated_messages)}")
        
        # 记录prompt内容（调试模式下记录更多详情）
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"   完整Messages内容:\n{json.dumps(validated_messages, ensure_ascii=False, indent=2)}")
        else:
            # 生产模式下记录消息概览
            msg_summary = []
            for i, msg in enumerate(validated_messages):
                role = msg.get("role", "unknown")
                content_len = len(str(msg.get("content", "")))
                msg_summary.append(f"{role}({content_len}字符)")
            logger.info(f"   消息概览: {' -> '.join(msg_summary)}")
        
        start_time = time.time()
        
        try:
            if self.provider_instance is None:
                raise ValueError("LLM provider instance is not initialized.")
            
            # 🔍 新增：检查provider_instance类型，防止AsyncMock泄露
            provider_type = type(self.provider_instance).__name__
            if "Mock" in provider_type:
                logger.error(f"❌ 检测到Mock对象被用作LLM provider: {provider_type}")
                logger.error(f"   重新初始化provider...")
                self._initialize_provider_instance()
                if "Mock" in type(self.provider_instance).__name__:
                    raise ValueError(f"LLM provider被意外设置为Mock对象: {type(self.provider_instance)}")
            
            # 获取默认模型并传递给 generate_response
            model_name = self.provider_instance.get_default_model()
            
            # 准备参数，包含stop_sequences（如果支持）
            params = {
                "messages": validated_messages,
                "model": model_name,
                "timeout": timeout
            }
            
            # 如果提供了stop_sequences，添加到参数中
            if stop_sequences:
                params["stop_sequences"] = stop_sequences
                logger.info(f"🔧 使用stop_sequences: {stop_sequences}")
            
            response = await self.provider_instance.generate_response(**params)
            
            # 🔍 新增：检查响应类型，处理不同的返回格式
            duration = time.time() - start_time
            
            # 如果provider返回字符串（旧格式），转换为新格式
            if isinstance(response, str):
                response_data = {
                    'content': response,
                    'usage': None,  # 旧格式没有usage信息
                    'metadata': {
                        'response_time': duration,
                        'provider': self.provider.value,
                        'model': model_name
                    }
                }
                logger.warning(f"⚠️ Provider返回旧格式(string)，已转换为新格式")
            elif isinstance(response, dict):
                # 新格式：字典包含content和metadata
                response_data = response
                response_data.setdefault('metadata', {})
                response_data['metadata'].update({
                    'response_time': duration,
                    'provider': self.provider.value,
                    'model': model_name
                })
            elif hasattr(response, '_mock_name') or "Mock" in type(response).__name__:
                logger.error(f"❌ LLM provider返回了Mock对象: {type(response)}")
                raise ValueError(f"LLM provider返回了Mock对象: {type(response)}")
            else:
                logger.error(f"❌ LLM provider返回了意外类型: {type(response)}")
                raise ValueError(f"LLM provider返回了意外类型: {type(response)}")
            
            # 验证响应内容
            content = response_data.get('content', '')
            if not isinstance(content, str):
                logger.warning(f"⚠️ 响应内容类型异常: {type(content)}, 尝试转换为字符串")
                content = str(content) if content is not None else ""
                response_data['content'] = content
            
            # 🔍 新增：记录API响应信息和数据流追踪
            logger.info("✅ LLM API调用成功")
            logger.info(f"   响应时间: {duration:.2f}秒")
            logger.info(f"   响应长度: {len(content)} 字符")
            logger.info(f"   包含usage信息: {response_data.get('usage') is not None}")
            
            # 检查响应是否为空或异常
            if not content or content.strip() == "":
                logger.warning("⚠️ LLM API返回空响应")
            elif len(content) > 10000:
                logger.warning(f"⚠️ LLM API返回响应过长: {len(content)} 字符")
            
            # 记录响应内容
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   完整响应内容:\n{content}")
            else:
                # 生产模式下只记录前后片段
                response_preview = content[:200] + "..." + content[-100:] if len(content) > 300 else content
                logger.info(f"   响应预览: {response_preview}")
            
            return response_data
            
        except httpx.HTTPStatusError as e: # 捕获更具体的HTTP错误
            # 🔍 新增：记录API错误信息
            duration = time.time() - start_time
            logger.error("❌ LLM API调用失败")
            logger.error(f"   失败时间: {duration:.2f}秒")
            logger.error(f"   错误类型: {type(e).__name__}")
            logger.error(f"   错误信息: {str(e)}")
            logger.error(f"   HTTP状态码: {e.response.status_code}")
            logger.error(f"   响应内容: {e.response.text}")
            raise
        except Exception as e:
            # 🔍 新增：记录API错误信息
            duration = time.time() - start_time
            logger.error("❌ LLM API调用失败")
            logger.error(f"   失败时间: {duration:.2f}秒")
            logger.error(f"   错误类型: {type(e).__name__}")
            logger.error(f"   错误信息: {str(e)}")
            # 对于非HTTPStatusError，可能没有response属性
            raise

    def _validate_input_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证和清理输入消息，防止数据类型错误传播"""
        if not isinstance(messages, list):
            raise ValueError(f"messages必须是列表类型，实际类型: {type(messages)}")
        
        validated_messages = []
        for i, msg in enumerate(messages):
            try:
                # 确保每个消息都是字典
                if not isinstance(msg, dict):
                    logger.warning(f"消息 {i} 不是字典类型: {type(msg)}, 尝试转换")
                    if hasattr(msg, '__dict__'):
                        msg = msg.__dict__
                    else:
                        raise ValueError(f"消息 {i} 无法转换为字典")
                
                # 验证必需字段
                if "role" not in msg:
                    raise ValueError(f"消息 {i} 缺少'role'字段")
                if "content" not in msg:
                    raise ValueError(f"消息 {i} 缺少'content'字段")
                
                # 清理和验证字段值
                validated_msg = {
                    "role": str(msg["role"]).strip(),
                    "content": self._validate_and_clean_content(msg["content"], i)
                }
                
                # 验证role值
                valid_roles = {"user", "assistant", "system"}
                if validated_msg["role"] not in valid_roles:
                    logger.warning(f"消息 {i} 的role无效: {validated_msg['role']}, 设置为'user'")
                    validated_msg["role"] = "user"
                
                validated_messages.append(validated_msg)
                
            except Exception as e:
                logger.error(f"验证消息 {i} 失败: {e}, 消息内容: {msg}")
                # 跳过无效消息，但如果所有消息都无效则抛出异常
                continue
        
        if not validated_messages:
            raise ValueError("所有输入消息都无效，无法进行API调用")
        
        logger.debug(f"消息验证完成: {len(messages)} -> {len(validated_messages)}")
        return validated_messages
    
    def _validate_and_clean_content(self, content: Any, msg_index: int) -> str:
        """验证和清理消息内容"""
        if content is None:
            return ""
        
        if isinstance(content, str):
            return content
        
        if isinstance(content, (dict, list)):
            try:
                # 将复杂对象转换为JSON字符串
                json_str = json.dumps(content, ensure_ascii=False, indent=2)
                logger.debug(f"消息 {msg_index} 的复杂content已转换为JSON字符串")
                return json_str
            except Exception as e:
                logger.warning(f"消息 {msg_index} 的content JSON序列化失败: {e}")
                return str(content)
        
        # 其他类型直接转换为字符串
        return str(content)
