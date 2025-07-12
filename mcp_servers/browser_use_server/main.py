#!/usr/bin/env python3
"""
Browser-Use MCP Server
基于browser-use的AI浏览器自动化服务，完整实现browser-use的所有功能
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import logging
import os
import json
import time
import re  # 🔧 修复：将re模块移到全局导入，避免作用域问题
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from browser_use import Agent, Browser, BrowserConfig, Controller, ActionModel, ActionResult
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.outputs import LLMResult, Generation, ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

# Custom generation class that behaves like both Generation and ChatGeneration
class BrowserUseGeneration(ChatGeneration):
    """Custom generation class for browser-use compatibility"""
    
    def __getitem__(self, key):
        """Support subscript access for compatibility"""
        if isinstance(key, int):
            if key == 0:
                return self
            else:
                raise IndexError("Generation index out of range")
        elif key == "text":
            return self.text
        else:
            return getattr(self, key, None)
    
    def __iter__(self):
        """Support iteration"""
        yield self
    
    def __len__(self):
        """Support len()"""
        return 1

try:
    from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
    from core.toolscore.mcp_server import MCPServer
    from core.config_manager import ConfigManager
except ImportError as e:
    print(f'Import error: {e}')
    sys.exit(1)
from core.llm_client import LLMClient
from core.unified_tool_manager import UnifiedToolManager
from core.shared_workspace import get_workspace_manager

# 导入本地工具模块，解决重复导入问题
try:
    from utils import JSONExtractor, ResponseValidator, ConfigHelper
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    from mcp_servers.browser_use_server.utils import JSONExtractor, ResponseValidator, ConfigHelper

logger = logging.getLogger(__name__)


def safe_tool_execution(func):
    """安全的工具执行装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            import traceback
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(f"TRACEBACK: {traceback.format_exc()}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "tool_execution_error"
            }
    return wrapper


class StructuredOutputWrapper:
    """Wrapper to provide structured output interface for browser-use compatibility"""
    
    def __init__(self, llm_adapter, schema):
        self.llm_adapter = llm_adapter
        self.schema = schema
    
    def invoke(self, input_data, config=None, **kwargs):
        """Invoke the wrapped LLM and return structured response"""
        try:
            # Get response from the LLM
            response = self.llm_adapter.invoke(input_data, config, **kwargs)
            
            # If response is an AIMessage, get its content
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            # 使用工具类解析结构化内容，避免重复导入
            parsed = JSONExtractor.parse_structured_content(content)
            return StructuredResponse(parsed)
                
        except Exception as e:
            logger.error(f"Structured output wrapper error: {e}")
            # Return a fallback structured response
            return StructuredResponse({"error": str(e), "response": ""})
    
    async def ainvoke(self, input_data, config=None, **kwargs):
        """Async invoke the wrapped LLM and return structured response"""
        try:
            # Get response from the LLM using apredict_messages if available
            if hasattr(self.llm_adapter, 'apredict_messages') and isinstance(input_data, list):
                response = await self.llm_adapter.apredict_messages(input_data, **kwargs)
            elif hasattr(self.llm_adapter, 'apredict'):
                if isinstance(input_data, list):
                    # Convert messages to text
                    text_input = "\n".join([str(msg.content) if hasattr(msg, 'content') else str(msg) for msg in input_data])
                else:
                    text_input = str(input_data)
                response = await self.llm_adapter.apredict(text_input, **kwargs)
            else:
                # Fallback to sync invoke
                response = self.llm_adapter.invoke(input_data, config, **kwargs)
            
            # If response is an AIMessage, get its content
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            logger.info(f"Structured wrapper response content: {content[:200]}...")
            
            # 使用工具类解析结构化内容，避免重复导入
            parsed = JSONExtractor.parse_structured_content(content)
            structured_resp = StructuredResponse(parsed)
            logger.info(f"Created StructuredResponse with keys: {list(structured_resp.keys())}")
            
            if hasattr(structured_resp, 'action'):
                logger.info(f"Action attribute type: {type(structured_resp.action)}, value: {structured_resp.action}")
            
            return structured_resp
                
        except Exception as e:
            logger.error(f"Structured output wrapper async error: {e}")
            # Return a fallback structured response
            return StructuredResponse({"error": str(e), "response": ""})


class MockActionModel:
    """Mock ActionModel to satisfy browser-use expectations"""
    def __init__(self, action_data):
        self.action_data = action_data
        # Set the action as an attribute
        for key, value in action_data.items():
            setattr(self, key, value)
    
    def model_dump(self, exclude_unset=True):
        """Mimic Pydantic model_dump method"""
        return self.action_data
    
    def get_index(self):
        """Get index from action parameters"""
        for action_params in self.action_data.values():
            if isinstance(action_params, dict) and 'index' in action_params:
                return action_params['index']
        return None
    
    def set_index(self, index):
        """Set index in action parameters"""
        for action_params in self.action_data.values():
            if isinstance(action_params, dict):
                action_params['index'] = index


class BrowserUseResultAnalyzer:
    """Browser-Use风格的结果分析器 - 模仿AgentHistoryList的功能"""
    
    def __init__(self, agent_history):
        self.history = agent_history
    
    def extract_comprehensive_result(self, task: str) -> Dict[str, Any]:
        """全面的结果提取 - 模仿Browser-Use的逻辑"""
        
        # 1. 基础状态检查
        if not self.history or not hasattr(self.history, 'history') or not self.history.history:
            return self._create_error_result("No execution history found", task)
        
        # 2. 获取Browser-Use的原生方法结果
        final_result = self._get_final_result()
        is_done = self._is_done()
        is_successful = self._is_successful()
        has_errors = self._has_errors()
        
        # 3. 提取执行统计
        steps_taken = len(self.history.history)
        total_duration = self._get_total_duration()
        error_list = self._get_errors()
        
        # 4. 获取最后一步的详细信息
        last_step = self.history.history[-1] if self.history.history else None
        
        # 5. 构建综合结果
        result_data = {
            "success": self._determine_overall_success(is_done, is_successful, has_errors),
            "data": {
                "task": task,
                "result": final_result or self._extract_fallback_content(),
                "is_done": is_done,
                "is_successful": is_successful,
                "steps_taken": steps_taken,
                "total_duration_seconds": total_duration,
                "has_errors": has_errors,
                "error_count": len([e for e in error_list if e is not None]),
                "last_action": self._get_last_action(),
                "extracted_contents": self._get_extracted_content(),
                "urls_visited": self._get_unique_urls(),
                "attachments": self._extract_attachments(),
                "execution_summary": self._create_execution_summary(),
                "action_breakdown": self._get_action_breakdown()
            },
            "error_message": self._get_primary_error_message(),
            "error_type": self._classify_error_type(),
            "debug_info": {
                "browser_use_version": getattr(self.history, 'version', 'unknown'),
                "raw_final_result": final_result,
                "history_length": steps_taken,
                "last_step_details": self._get_last_step_debug_info()
            }
        }
        
        # 确保结果是JSON可序列化的
        return self._ensure_json_serializable(result_data)
    
    def _get_final_result(self):
        """模仿Browser-Use的final_result()方法"""
        try:
            return self.history.final_result() if hasattr(self.history, 'final_result') else None
        except Exception as e:
            logger.debug(f"Error getting final_result: {e}")
            return None
    
    def _is_done(self):
        """模仿Browser-Use的is_done()方法"""
        try:
            return self.history.is_done() if hasattr(self.history, 'is_done') else False
        except Exception as e:
            logger.debug(f"Error checking is_done: {e}")
            return False
    
    def _is_successful(self):
        """模仿Browser-Use的is_successful()方法"""
        try:
            return self.history.is_successful() if hasattr(self.history, 'is_successful') else None
        except Exception as e:
            logger.debug(f"Error checking is_successful: {e}")
            return None
    
    def _has_errors(self):
        """模仿Browser-Use的has_errors()方法"""
        try:
            return self.history.has_errors() if hasattr(self.history, 'has_errors') else False
        except Exception as e:
            logger.debug(f"Error checking has_errors: {e}")
            return False
    
    def _get_total_duration(self):
        """获取总执行时间"""
        try:
            return self.history.total_duration_seconds() if hasattr(self.history, 'total_duration_seconds') else 0.0
        except Exception as e:
            logger.debug(f"Error getting total_duration: {e}")
            return 0.0
    
    def _get_errors(self):
        """获取错误列表"""
        try:
            return self.history.errors() if hasattr(self.history, 'errors') else []
        except Exception as e:
            logger.debug(f"Error getting errors: {e}")
            return []
    
    def _get_last_action(self):
        """获取最后一个动作"""
        try:
            if hasattr(self.history, 'last_action'):
                action = self.history.last_action()
                # 确保action是可序列化的
                if hasattr(action, 'model_dump'):
                    return action.model_dump()
                elif isinstance(action, dict):
                    return action
                else:
                    return str(action) if action is not None else None
            return None
        except Exception as e:
            logger.debug(f"Error getting last_action: {e}")
            return None
    
    def _get_extracted_content(self):
        """获取所有提取的内容"""
        try:
            return self.history.extracted_content() if hasattr(self.history, 'extracted_content') else []
        except Exception as e:
            logger.debug(f"Error getting extracted_content: {e}")
            return []
    
    def _get_unique_urls(self):
        """获取访问的URL列表"""
        try:
            urls = self.history.urls() if hasattr(self.history, 'urls') else []
            return list(set([url for url in urls if url]))
        except Exception as e:
            logger.debug(f"Error getting URLs: {e}")
            return []
    
    def _get_action_breakdown(self):
        """获取动作分解"""
        try:
            if hasattr(self.history, 'action_names'):
                action_names = self.history.action_names()
                action_counts = {}
                for action in action_names:
                    action_counts[action] = action_counts.get(action, 0) + 1
                return action_counts
            return {}
        except Exception as e:
            logger.debug(f"Error getting action breakdown: {e}")
            return {}
    
    def _determine_overall_success(self, is_done: bool, is_successful: bool | None, has_errors: bool) -> bool:
        """模仿Browser-Use的成功判断逻辑"""
        if not is_done:
            return False
        if is_successful is not None:
            return is_successful
        return not has_errors
    
    def _extract_fallback_content(self) -> str:
        """当没有final_result时的回退内容提取"""
        # 1. 尝试从提取内容获取
        contents = self._get_extracted_content()
        if contents:
            return contents[-1]
        
        # 2. 尝试从最后一步的结果获取
        if self.history.history:
            last_step = self.history.history[-1]
            if hasattr(last_step, 'result') and last_step.result:
                for result in reversed(last_step.result):
                    if hasattr(result, 'extracted_content') and result.extracted_content:
                        return result.extracted_content
        
        # 3. 尝试从model输出获取
        try:
            if hasattr(self.history, 'model_outputs'):
                model_outputs = self.history.model_outputs()
                if model_outputs:
                    last_output = model_outputs[-1]
                    if hasattr(last_output, 'next_goal') and hasattr(last_output, 'memory'):
                        return f"Goal: {last_output.next_goal}, Memory: {last_output.memory}"
        except Exception as e:
            logger.debug(f"Error extracting from model outputs: {e}")
        
        # 4. 最后的回退
        return "Task executed but no specific content extracted"
    
    def _extract_attachments(self) -> List[str]:
        """提取所有附件"""
        attachments = []
        try:
            if hasattr(self.history, 'action_results'):
                for result in self.history.action_results():
                    if hasattr(result, 'attachments') and result.attachments:
                        attachments.extend(result.attachments)
        except Exception as e:
            logger.debug(f"Error extracting attachments: {e}")
        return attachments
    
    def _create_execution_summary(self) -> Dict[str, Any]:
        """创建执行摘要"""
        action_counts = self._get_action_breakdown()
        return {
            "total_actions": sum(action_counts.values()),
            "action_breakdown": action_counts,
            "unique_actions": len(action_counts),
            "most_used_action": max(action_counts.items(), key=lambda x: x[1])[0] if action_counts else None
        }
    
    def _get_primary_error_message(self) -> str:
        """获取主要错误信息"""
        errors = self._get_errors()
        error_messages = [e for e in errors if e is not None]
        if error_messages:
            return error_messages[-1]
        return ""
    
    def _classify_error_type(self) -> str:
        """错误类型分类"""
        error_msg = self._get_primary_error_message().lower()
        if not error_msg:
            return ""
        
        if "network" in error_msg or "connection" in error_msg:
            return "NetworkError"
        elif "element" in error_msg or "selector" in error_msg:
            return "ElementError"
        elif "timeout" in error_msg:
            return "TimeoutError"
        elif "validation" in error_msg:
            return "ValidationError"
        elif "llm" in error_msg or "api" in error_msg:
            return "LLMError"
        else:
            return "UnknownError"
    
    def _get_last_step_debug_info(self) -> Dict[str, Any]:
        """获取最后一步的调试信息"""
        if not self.history.history:
            return {}
        
        try:
            last_step = self.history.history[-1]
            debug_info = {
                "has_model_output": hasattr(last_step, 'model_output') and last_step.model_output is not None,
                "has_result": hasattr(last_step, 'result') and bool(last_step.result),
                "result_count": len(last_step.result) if hasattr(last_step, 'result') and last_step.result else 0
            }
            
            if hasattr(last_step, 'result') and last_step.result:
                last_result = last_step.result[-1]
                debug_info.update({
                    "last_result_is_done": getattr(last_result, 'is_done', None),
                    "last_result_success": getattr(last_result, 'success', None),
                    "last_result_error": getattr(last_result, 'error', None),
                    "last_result_has_content": bool(getattr(last_result, 'extracted_content', None))
                })
            
            # 确保所有值都是JSON可序列化的
            serializable_debug_info = {}
            for key, value in debug_info.items():
                if value is None or isinstance(value, (bool, int, float, str)):
                    serializable_debug_info[key] = value
                else:
                    serializable_debug_info[key] = str(value)
            
            return serializable_debug_info
        except Exception as e:
            logger.debug(f"Error getting debug info: {e}")
            return {"debug_info_error": str(e)}
    
    def _create_error_result(self, error_msg: str, task: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "success": False,
            "data": {
                "task": task,
                "result": "",
                "is_done": False,
                "steps_taken": 0,
                "error_details": error_msg
            },
            "error_message": error_msg,
            "error_type": "SystemError"
        }
    
    def _ensure_json_serializable(self, data: Any) -> Any:
        """确保数据是JSON可序列化的"""
        try:
            if data is None:
                return None
            elif isinstance(data, (bool, int, float, str)):
                return data
            elif isinstance(data, (list, tuple)):
                return [self._ensure_json_serializable(item) for item in data]
            elif isinstance(data, dict):
                return {key: self._ensure_json_serializable(value) for key, value in data.items()}
            else:
                # 对于Mock对象或其他不可序列化的对象，转换为字符串
                return str(data)
        except Exception as e:
            logger.debug(f"Error serializing data: {e}")
            return str(data)


class StructuredResponse:
    """Response object that supports subscript access for browser-use compatibility"""
    
    def __init__(self, data):
        self.data = data if isinstance(data, dict) else {"response": str(data)}
        
        # Set attributes dynamically for direct attribute access
        for key, value in self.data.items():
            if key == 'action' and isinstance(value, list):
                # Convert action list to MockActionModel instances
                mock_actions = []
                for action_item in value:
                    if isinstance(action_item, dict):
                        mock_actions.append(MockActionModel(action_item))
                    else:
                        mock_actions.append(action_item)
                setattr(self, key, mock_actions)
            else:
                setattr(self, key, value)
    
    def __getitem__(self, key):
        """Support subscript access"""
        return self.data.get(key, "")
    
    def __setitem__(self, key, value):
        """Support subscript assignment"""
        self.data[key] = value
        setattr(self, key, value)
    
    def __contains__(self, key):
        """Support 'in' operator"""
        return key in self.data
    
    def get(self, key, default=None):
        """Support dictionary-like get method"""
        return self.data.get(key, default)
    
    def keys(self):
        """Support keys() method"""
        return self.data.keys()
    
    def values(self):
        """Support values() method"""
        return self.data.values()
    
    def items(self):
        """Support items() method"""
        return self.data.items()
    
    def __getattr__(self, name):
        """Support dynamic attribute access"""
        if name == 'data':
            return object.__getattribute__(self, name)
        if name in self.data:
            value = self.data[name]
            if name == 'action' and isinstance(value, list):
                # Return MockActionModel instances for actions
                mock_actions = []
                for action_item in value:
                    if isinstance(action_item, dict):
                        mock_actions.append(MockActionModel(action_item))
                    else:
                        mock_actions.append(action_item)
                return mock_actions
            return value
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    def __str__(self):
        """String representation"""
        return str(self.data)
    
    def __repr__(self):
        """Representation"""
        return f"StructuredResponse({self.data})"

class BrowserUseLLMAdapter(BaseChatModel):
    """
    Adapter to make our LLMClient compatible with browser-use's LangChain interface
    """
    
    def __init__(self, llm_client: LLMClient, **kwargs):
        super().__init__(**kwargs)
        # Use object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, 'llm_client', llm_client)
    
    def get(self, key: str, default=None):
        """Support for dictionary-like access needed by LangChain"""
        return getattr(self, key, default)
    
    @property
    def _llm_type(self) -> str:
        """Return identifier of LLM."""
        return f"browser_use_adapter_{self.llm_client.provider.value}"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat result from messages."""
        # Convert LangChain messages to our format with filtering
        formatted_messages = []
        for msg in messages:
            content = str(msg.content).strip() if msg.content else ""
            
            # Skip empty messages
            if not content:
                continue
                
            if isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": content})
            else:
                # For Gemini, convert system messages to user messages with prefix
                formatted_messages.append({"role": "user", "content": f"System: {content}"})
        
        # Ensure we have at least one message and merge consecutive user messages for Gemini
        if not formatted_messages:
            formatted_messages = [{"role": "user", "content": "Hello"}]
        else:
            # Merge consecutive user messages to avoid Gemini API issues
            merged_messages = []
            current_user_content = []
            
            for msg in formatted_messages:
                if msg["role"] == "user":
                    current_user_content.append(msg["content"])
                else:
                    # Flush any accumulated user content first
                    if current_user_content:
                        merged_messages.append({
                            "role": "user", 
                            "content": "\n\n".join(current_user_content)
                        })
                        current_user_content = []
                    merged_messages.append(msg)
            
            # Flush any remaining user content
            if current_user_content:
                merged_messages.append({
                    "role": "user", 
                    "content": "\n\n".join(current_user_content)
                })
            
            formatted_messages = merged_messages
        
        # Use our LLM client to get response (this needs to be synchronous for LangChain)
        import asyncio
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            response = loop.run_until_complete(self.llm_client._call_api(formatted_messages))
        except Exception as e:
            logger.error(f"LLM adapter call failed: {e}")
            response = f"Error: {e}"
        
        # Handle structured output if requested
        if hasattr(self, '_structured_schema') and self._structured_schema:
            logger.info("Processing structured output response (sync)")
            structured_response = self._parse_structured_response(response)
            if structured_response:
                # Return the structured response directly as the message content
                generation = BrowserUseGeneration(message=AIMessage(content=structured_response))
                return ChatResult(generations=[generation])
        
        # Return LangChain format result for chat models with browser-use compatibility
        generation = BrowserUseGeneration(message=AIMessage(content=response))
        return ChatResult(generations=[generation])
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate chat result from messages."""
        # Convert LangChain messages to our format with filtering
        formatted_messages = []
        for msg in messages:
            content = str(msg.content).strip() if msg.content else ""
            
            # Skip empty messages
            if not content:
                continue
                
            if isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": content})
            else:
                # For Gemini, convert system messages to user messages with prefix
                formatted_messages.append({"role": "user", "content": f"System: {content}"})
        
        # Ensure we have at least one message and merge consecutive user messages for Gemini
        if not formatted_messages:
            formatted_messages = [{"role": "user", "content": "Hello"}]
        else:
            # Merge consecutive user messages to avoid Gemini API issues
            merged_messages = []
            current_user_content = []
            
            for msg in formatted_messages:
                if msg["role"] == "user":
                    current_user_content.append(msg["content"])
                else:
                    # Flush any accumulated user content first
                    if current_user_content:
                        merged_messages.append({
                            "role": "user", 
                            "content": "\n\n".join(current_user_content)
                        })
                        current_user_content = []
                    merged_messages.append(msg)
            
            # Flush any remaining user content
            if current_user_content:
                merged_messages.append({
                    "role": "user", 
                    "content": "\n\n".join(current_user_content)
                })
            
            formatted_messages = merged_messages
        
        try:
            response = await self.llm_client._call_api(formatted_messages)
        except Exception as e:
            logger.error(f"LLM adapter async call failed: {e}")
            response = f"Error: {e}"
        
        # Handle structured output if requested
        if hasattr(self, '_structured_schema') and self._structured_schema:
            logger.info("Processing structured output response")
            structured_response = self._parse_structured_response(response)
            if structured_response:
                # Return the structured response directly as the message content
                generation = BrowserUseGeneration(message=AIMessage(content=structured_response))
                return ChatResult(generations=[generation])
        
        # Return LangChain format result for chat models with browser-use compatibility
        generation = BrowserUseGeneration(message=AIMessage(content=response))
        return ChatResult(generations=[generation])
    
    # Required abstract methods from BaseChatModel
    def generate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        """Generate completions for multiple prompts."""
        generations = []
        for prompt in prompts:
            messages = prompt.to_messages()
            result = self._generate(messages, stop=stop, **kwargs)
            generations.extend(result.generations)  # Use extend instead of append
        return ChatResult(generations=generations)
    
    async def agenerate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        """Async generate completions for multiple prompts."""
        generations = []
        for prompt in prompts:
            messages = prompt.to_messages()
            result = await self._agenerate(messages, stop=stop, **kwargs)
            generations.extend(result.generations)  # Use extend instead of append
        return ChatResult(generations=generations)
    
    def predict(self, text: str, *, stop: Optional[List[str]] = None, **kwargs) -> str:
        """Predict text completion."""
        messages = [HumanMessage(content=text)]
        result = self._generate(messages, stop=stop, **kwargs)
        return result.generations[0].message.content
    
    async def apredict(self, text: str, *, stop: Optional[List[str]] = None, **kwargs) -> str:
        """Async predict text completion."""
        messages = [HumanMessage(content=text)]
        result = await self._agenerate(messages, stop=stop, **kwargs)
        return result.generations[0].message.content
    
    def predict_messages(self, messages: List[BaseMessage], *, stop: Optional[List[str]] = None, **kwargs) -> BaseMessage:
        """Predict message response."""
        result = self._generate(messages, stop=stop, **kwargs)
        return result.generations[0].message
    
    async def apredict_messages(self, messages: List[BaseMessage], *, stop: Optional[List[str]] = None, **kwargs) -> BaseMessage:
        """Async predict message response."""
        result = await self._agenerate(messages, stop=stop, **kwargs)
        return result.generations[0].message
    
    def invoke(self, input_data, config=None, **kwargs):
        """Invoke the language model."""
        if isinstance(input_data, str):
            return self.predict(input_data, **kwargs)
        elif isinstance(input_data, list):
            return self.predict_messages(input_data, **kwargs)
        else:
            raise ValueError(f"Unsupported input type: {type(input_data)}")
    
    def with_structured_output(self, schema, **kwargs):
        """Return a new model with structured output capability."""
        logger.warning("with_structured_output called - returning direct adapter")
        # Instead of wrapping, modify the current instance to handle structured output
        self._structured_schema = schema
        self._structured_kwargs = kwargs
        return self
    
    def bind(self, **kwargs):
        """Bind additional parameters to the model."""
        # Return self for simplicity - browser-use may call this
        return self
    
    def _parse_structured_response(self, content):
        """Parse structured response from LLM content"""
        try:
            # 🔧 修复：使用JSONExtractor工具类，彻底避免re作用域问题
            parsed = JSONExtractor.parse_structured_content(content)
            structured_resp = StructuredResponse(parsed)
            logger.info(f"JSONExtractor parse successful, created StructuredResponse with keys: {list(structured_resp.keys())}")
            
            if hasattr(structured_resp, 'action'):
                logger.info(f"Action attribute type: {type(structured_resp.action)}, value: {structured_resp.action}")
            
            return structured_resp
        except Exception as e:
            logger.error(f"Error in structured response parsing: {e}")
            return StructuredResponse({"error": str(e), "response": content})


from core.unified_tool_manager import UnifiedToolManager

class BrowserUseMCPServer:
    """Browser-Use AI浏览器MCP服务器 - 完整实现browser-use功能"""
    
    def __init__(self, config_manager: ConfigManager, tool_manager: UnifiedToolManager):
        self.server_name = "browser_use_server"
        self.server_id = "browser_use"
        self.config_manager = config_manager
        self.tool_manager = tool_manager
        
        # 初始化统一LLM��户端
        llm_config = config_manager.get_llm_config()
        self.llm_client = LLMClient(llm_config, tool_manager=tool_manager)
        logger.info(f"Browser-Use server initialized with LLM provider: {self.llm_client.provider.value}")
        
        # 从配置中获取端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查动态分配的端口
        dynamic_port = os.getenv('BROWSER_USE_SERVER_PORT')
        if dynamic_port:
            browser_use_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {browser_use_port}")
        else:
            browser_use_port = ports_config['mcp_servers'].get('browser_use_server', {}).get('port', 8082)
            logger.info(f"使用配置文件端口: {browser_use_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
        
        # 配置监听地址
        listen_host = os.getenv("BROWSER_USE_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("BROWSER_USE_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{browser_use_port}"
        self._listen_host = listen_host
        self._listen_port = browser_use_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')
        
        # 初始化browser、context和controller
        self.browser = None
        self.browser_context = None
        self.controller = None

        # 动作分发映射
        self._action_handlers = {
            "browser_use_execute_task": self._execute_task_wrapper,
            "browser_navigate": self._navigate_wrapper,
            "browser_search_google": self._search_google_wrapper,
            "browser_go_back": lambda params: self._execute_action("go_back", {}),
            "browser_click_element": lambda params: self._execute_action("click_element_by_index", {"index": params["index"]}),
            "browser_input_text": lambda params: self._execute_action("input_text", {"index": params["index"], "text": params["text"]}),
            "browser_send_keys": lambda params: self._execute_action("send_keys", {"keys": params["keys"]}),
            "browser_scroll_down": lambda params: self._execute_action("scroll_down", {"amount": params.get("amount")}),
            "browser_scroll_up": lambda params: self._execute_action("scroll_up", {"amount": params.get("amount")}),
            "browser_scroll_to_text": lambda params: self._execute_action("scroll_to_text", {"text": params["text"]}),
            "browser_switch_tab": lambda params: self._execute_action("switch_tab", {"page_id": params["page_id"]}),
            "browser_open_tab": lambda params: self._execute_action("open_tab", {"url": params["url"]}),
            "browser_close_tab": lambda params: self._execute_action("close_tab", {"page_id": params["page_id"]}),
            "browser_extract_content": self._extract_page_content,
            "browser_get_content": self._get_content_wrapper,
            "browser_get_ax_tree": lambda params: self._execute_action("get_ax_tree", {"number_of_elements": params["number_of_elements"]}),
            "browser_get_dropdown_options": lambda params: self._execute_action("get_dropdown_options", {"index": params["index"]}),
            "browser_select_dropdown_option": lambda params: self._execute_action("select_dropdown_option", {"index": params["index"], "text": params["text"]}),
            "browser_drag_drop": self._drag_drop_wrapper,
            "browser_save_pdf": lambda params: self._execute_action("save_pdf", {}),
            "browser_screenshot": self._screenshot,
            "browser_wait": lambda params: self._execute_action("wait", {"seconds": params.get("seconds", 3)}),
            "browser_done": lambda params: self._execute_action("done", {"text": params["text"], "success": params["success"]}),
            "browser_get_page_info": self._get_page_info,
            "browser_get_current_url": self._get_current_url,
            "browser_close_session": self._close_session,
        }
        try:
            self._validate_actions()
        except Exception as e:
            logger.warning(f"Action validation failed: {e}, continuing with startup")
        
        logger.info(f"BrowserUseMCPServer initialized:")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")

    def _validate_actions(self):
        """验证所有在配置中声明的动作都有对应的处理函数。"""
        try:
            declared_actions = set(self.tool_manager.get_tool_actions(self.server_name))
            implemented_actions = set(self._action_handlers.keys())

            missing = declared_actions - implemented_actions
            if missing:
                raise NotImplementedError(f"服务器 {self.server_name} 在配置中声明了动作 {missing}，但没有实现对应的处理函数！")

            extra = implemented_actions - declared_actions
            if extra:
                logging.warning(f"服务器 {self.server_name} 实现了多余的动作 {extra}，这些动作未在配置中声明。")
            
            logger.info(f"✅ {self.server_name} 的所有动作已验证。")
        except Exception as e:
            logger.error(f"动作验证失败: {e}", exc_info=True)
            raise

    async def _execute_task_wrapper(self, parameters):
        result = await self._execute_task_with_retry(parameters)
        result['execution_time'] = time.time() - (result.get('start_time', time.time()))
        return result

    async def _navigate_wrapper(self, parameters):
        if "url" not in parameters:
            return {"success": False, "error_message": "Missing 'url' parameter."}
        url = parameters["url"]
        if not isinstance(url, str) or not url.strip():
            return {"success": False, "error_message": "Invalid 'url' parameter."}
        return await self._navigate_to_url(url)

    async def _search_google_wrapper(self, parameters):
        query = parameters.get("query", "")
        if not query:
            return {"success": False, "error_message": "Missing 'query' parameter."}
        return await self._handle_google_search(query)

    async def _drag_drop_wrapper(self, parameters):
        drag_params = {key: parameters[key] for key in ["element_source", "element_target", "coord_source_x", "coord_source_y", "coord_target_x", "coord_target_y", "steps"] if key in parameters}
        return await self._execute_action("drag_drop", drag_params)
    
    async def _get_content_wrapper(self, parameters):
        """获取页面内容，支持通过CSS选择器获取特定内容"""
        try:
            selector = parameters.get("selector", "")
            
            # 获取当前页面
            if not self.browser_context:
                return {"success": False, "error_message": "浏览器上下文不可用"}
            
            page = await self.browser_context.get_current_page()
            if not page:
                return {"success": False, "error_message": "当前没有活动页面"}
            
            # 根据选择器获取内容
            if not selector or selector == "entire page":
                # 获取整个页面的HTML内容
                content = await page.content()
            else:
                # 使用CSS选择器获取特定元素的内容
                try:
                    element = await page.query_selector(selector)
                    if element:
                        # 获取元素的文本内容
                        content = await element.text_content()
                        if not content:
                            # 如果没有文本内容，尝试获取innerHTML
                            content = await element.inner_html()
                    else:
                        return {"success": False, "error_message": f"未找到匹配选择器 '{selector}' 的元素"}
                except Exception as e:
                    return {"success": False, "error_message": f"选择器 '{selector}' 无效: {str(e)}"}
            
            return {
                "success": True, 
                "data": {
                    "content": content or "",
                    "selector": selector,
                    "url": page.url if hasattr(page, 'url') else "未知"
                }
            }
            
        except Exception as e:
            logger.error(f"获取页面内容失败: {e}")
            return {"success": False, "error_message": f"获取内容时发生错误: {str(e)}"}

    async def _handle_google_search(self, query: str):
        """增强的Google搜索处理 - 基于官方browser-use实现"""
        try:
            import urllib.parse
            import asyncio
            
            logger.info(f"🔍 Enhanced Google搜索: {query}")
            
            # 首先尝试Google搜索
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=en"
            
            # 导航到Google搜索页面
            navigate_result = await self._navigate_to_url(search_url)
            if not navigate_result.get('success', False):
                return {
                    "success": False,
                    "error_message": f"Google搜索导航失败: {navigate_result.get('error_message', 'Unknown error')}",
                    "query": query
                }
            
            # 等待页面完全加载
            await asyncio.sleep(4)
            
            # 检查是否遇到Google的反爬虫保护
            page = await self.browser_context.get_current_page()
            current_url = page.url
            
            if "/sorry/" in current_url or "google.com/sorry" in current_url:
                logger.warning(f"遇到Google反爬虫保护: {current_url}")
                return {
                    "success": False,
                    "error_message": f"Google搜索被阻止，请稍后重试。当前URL: {current_url}",
                    "query": query
                }
            
            # 使用专门的Google搜索结果提取
            extract_result = await self._extract_google_search_results(query)
            
            if extract_result.get('success', False):
                content = extract_result['data']['content']
                logger.info(f"✅ Enhanced Google搜索成功，结果数: {extract_result['data'].get('result_count', 0)}")
                return {
                    "success": True,
                    "data": {
                        "content": content,
                        "query": query,
                        "url": search_url,
                        "extraction_method": "enhanced_google_search",
                        "result_count": extract_result['data'].get('result_count', 0),
                        "is_done": True
                    }
                }
            else:
                return {
                    "success": False,
                    "error_message": f"Google搜索结果提取失败: {extract_result.get('error_message', 'Unknown error')}",
                    "query": query
                }
                
        except Exception as e:
            logger.error(f"Enhanced Google搜索处理出错: {e}")
            return {
                "success": False,
                "error_message": f"Enhanced Google搜索处理出错: {str(e)}",
                "query": query
            }
    
    async def _ensure_browser_session(self):
        """确保browser和context已初始化"""
        if self.browser is None:
            try:
                # 🔧 增强的反检测浏览器配置
                # 🚀 Enhanced Browser Config - 基于官方browser-use最佳实践
                # 关闭无头模式以减少反爬虫检测
                browser_config = BrowserConfig(
                    headless=False,  # 强制使用有头模式
                    disable_security=True,
                    extra_chromium_args=[
                        # 基础安全和性能参数
                        "--no-sandbox",
                        "--disable-dev-shm-usage", 
                        "--disable-gpu",
                        "--disable-extensions",
                        "--no-first-run",
                        "--disable-default-apps",
                        
                        # 🎯 核心反检测 - 基于官方browser-use
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-ipc-flooding-protection",
                        "--exclude-switches=enable-automation",
                        "--disable-client-side-phishing-detection",
                        
                        # 🔧 增强的用户代理和伪装 - 使用最新Chrome
                        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        
                        # 🚄 性能优化 - 更快的搜索体验
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows", 
                        "--disable-renderer-backgrounding",
                        "--disable-background-networking",
                        
                        # 🌐 网络和缓存优化
                        "--aggressive-cache-discard",
                        "--disable-back-forward-cache",
                        "--disable-prompt-on-repost",
                        
                        # 🎭 隐私和追踪保护
                        "--disable-component-extensions-with-background-pages",
                        "--disable-domain-reliability",
                        "--disable-sync",
                        "--disable-translate",
                        "--no-default-browser-check",
                        "--disable-plugins",
                        
                        # 🔍 搜索优化 - 提高Google搜索成功率  
                        "--disable-features=TranslateUI",
                        "--disable-features=Translate",
                        "--lang=en-US,en",
                        "--accept-lang=en-US,en;q=0.9",
                        
                        # 🎭 模拟真实用户行为
                        "--simulate-outdated-no-au",
                        "--disable-features=VizDisplayCompositor",
                        "--start-maximized"  # 有头模式时最大化窗口
                    ]
                )
                
                self.browser = Browser(config=browser_config)
                logger.info("Browser initialized with enhanced configuration")
                
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                # 回退到基本配置
                browser_config = BrowserConfig(
                    headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
                    disable_security=True
                )
                self.browser = Browser(config=browser_config)
                logger.info("Browser initialized with basic configuration")
        
        # 确保browser context已创建
        if self.browser_context is None:
            self.browser_context = await self.browser.new_context()
            logger.info("Browser context created")
            
        if self.controller is None:
            # Controller需要与当前页面关联
            page = await self.browser_context.get_current_page()
            self.controller = Controller()
            logger.info("Controller initialized")
    
    def get_capabilities(self) -> List[ToolCapability]:
        """获取Browser-Use工具的所有能力"""
        tool_info = self.tool_manager.get_tool_info(self.server_name)
        capabilities = []
        for action_name, action_def in tool_info.get('actions', {}).items():
            capabilities.append(ToolCapability(
                name=action_name,
                description=action_def.get('description', ''),
                parameters=action_def.get('parameters', {}),
                examples=action_def.get('examples', [])
            ))
        return capabilities
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        await self._ensure_browser_session()
        handler = self._action_handlers.get(action)
        if handler:
            try:
                return await handler(parameters)
            except Exception as e:
                logger.error(f"Browser-Use tool execution failed for {action}: {e}", exc_info=True)
                return {"success": False, "data": None, "error_message": str(e), "error_type": "BrowserUseError"}
        else:
            return {"success": False, "data": None, "error_message": f"Unsupported action: {action}", "error_type": "UnsupportedAction"}
    
    async def _execute_action(self, action_name: str, params: dict, **kwargs) -> Dict[str, Any]:
        """执行browser-use控制器的具体动作"""
        try:
            # 🔧 通用修复：统一处理空字典参数，保持接口一致性
            # 如果参数是空字典，则不传递参数给ActionModel，避免验证错误
            if not params or params == {}:
                # 对于空参数，创建只包含动作名的ActionModel
                action_model = ActionModel(**{action_name: None})
            else:
                # 对于有参数的动作，正常创建
                action_dict = {action_name: params}
                action_model = ActionModel(**action_dict)
            
            # 使用控制器执行动作
            # Controller.act()需要browser_context参数
            result = await self.controller.act(
                action=action_model,
                browser_context=self.browser_context,
                **kwargs
            )
            
            if isinstance(result, ActionResult):
                return {
                    "success": not bool(result.error),
                    "data": {
                        "content": result.extracted_content,
                        "is_done": result.is_done,
                        "include_in_memory": result.include_in_memory
                    },
                    "error_message": result.error or "",
                    "error_type": "ActionError" if result.error else ""
                }
            else:
                return {
                    "success": True,
                    "data": {"content": str(result)},
                    "error_message": "",
                    "error_type": ""
                }
                
        except Exception as e:
            logger.error(f"Action execution failed for {action_name}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": f"动作执行失败: {str(e)}",
                "error_type": "ActionExecutionError"
            }
    
    async def _execute_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行AI浏览器任务 - 使用增强版结果提取"""
        task = parameters.get("task", "")
        max_steps = parameters.get("max_steps", 50)
        use_vision = parameters.get("use_vision", True)
        
        if not task:
            return {
                "success": False,
                "data": None,
                "error_message": "任务描述不能为空",
                "error_type": "InvalidInput"
            }
        
        try:
            # 创建Browser-Use兼容的LLM包装器
            browser_llm = BrowserUseLLMAdapter(self.llm_client)
            
            # 使用Browser-Use执行任务
            agent = Agent(
                task=task,
                llm=browser_llm,
                browser_context=self.browser_context,
                use_vision=use_vision,
                max_failures=3,
                retry_delay=5
            )
            
            # 执行任务并获取完整的AgentHistoryList
            agent_history = await agent.run(max_steps=max_steps)
            
            # 使用Browser-Use风格的结果分析器
            analyzer = BrowserUseResultAnalyzer(agent_history)
            comprehensive_result = analyzer.extract_comprehensive_result(task)
            
            # 添加执行统计日志
            data = comprehensive_result.get('data', {})
            debug_info = comprehensive_result.get('debug_info', {})
            
            logger.info(f"✅ Browser-Use task execution completed:")
            logger.info(f"  📋 Task: {task[:50]}...")
            logger.info(f"  🎯 Success: {comprehensive_result['success']}")
            logger.info(f"  📊 Steps taken: {data.get('steps_taken', 0)}")
            logger.info(f"  ⏱️ Duration: {data.get('total_duration_seconds', 0):.2f}s")
            logger.info(f"  ✔️ Is done: {data.get('is_done', False)}")
            logger.info(f"  🏆 Is successful: {data.get('is_successful', None)}")
            logger.info(f"  ❌ Has errors: {data.get('has_errors', False)}")
            logger.info(f"  🔧 Error count: {data.get('error_count', 0)}")
            
            if data.get('action_breakdown'):
                logger.info(f"  📈 Actions: {data['action_breakdown']}")
            
            if comprehensive_result.get('error_message'):
                logger.warning(f"  ⚠️ Error: {comprehensive_result['error_message']}")
            
            # 调试信息
            logger.debug(f"Debug info: {debug_info}")
            
            # 将结果保存到共享工作区
            try:
                workspace = get_workspace_manager()
                session_id = parameters.get('session_id', f"browser_task_{int(time.time())}")
                
                # 保存浏览器任务结果
                workspace.save_data(
                    session_id=session_id,
                    data_key="browser_result",
                    data={
                        "task_description": task,
                        "execution_time": datetime.now().isoformat(),
                        "result": comprehensive_result,
                        "raw_content": data.get('result', ''),
                        "urls_visited": data.get('urls_visited', []),
                        "attachments": data.get('attachments', [])
                    },
                    file_format="json"
                )
                
                # 如果有具体的内容数据，也单独保存
                if data.get('result'):
                    workspace.save_data(
                        session_id=session_id,
                        data_key="extracted_content",
                        data=data['result'],
                        file_format="text"
                    )
                
                # 添加工作区信息到结果中
                comprehensive_result['workspace_info'] = {
                    "session_id": session_id,
                    "workspace_path": str(workspace.get_session_path(session_id)),
                    "saved_files": ["browser_result.json", "extracted_content.txt"]
                }
                
                logger.info(f"💾 浏览器结果已保存到共享工作区: {session_id}")
                
            except Exception as workspace_error:
                logger.warning(f"⚠️ 保存到共享工作区失败: {workspace_error}")
                # 不影响主要结果返回
            
            return comprehensive_result
                
        except Exception as e:
            logger.error(f"❌ Browser-Use task execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": f"任务执行失败: {str(e)}",
                "error_type": "TaskExecutionError"
            }
    
    async def _screenshot(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """截取页面截图"""
        filename = parameters.get("filename", "screenshot.png")
        
        try:
            page = await self.browser_context.get_current_page()
            await page.screenshot(path=filename)
            
            return {
                "success": True,
                "data": {
                    "filename": filename,
                    "message": f"Screenshot saved as {filename}"
                },
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": f"截图失败: {str(e)}",
                "error_type": "ScreenshotError"
            }
    
    async def _get_page_info(self) -> Dict[str, Any]:
        """获取当前页面信息"""
        try:
            if not self.browser_context:
                return {
                    "success": False,
                    "data": None,
                    "error_message": "Browser context not initialized",
                    "error_type": "SessionError"
                }
            
            page = await self.browser_context.get_current_page()
            url = page.url
            title = await page.title()
            
            return {
                "success": True,
                "data": {
                    "url": url,
                    "title": title,
                    "viewport": page.viewport_size
                },
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": f"获取页面信息失败: {str(e)}",
                "error_type": "PageInfoError"
            }
    
    async def _get_current_url(self) -> Dict[str, Any]:
        """获取当前URL"""
        try:
            if not self.browser_context:
                return {
                    "success": False,
                    "data": None,
                    "error_message": "Browser context not initialized",
                    "error_type": "SessionError"
                }
            
            page = await self.browser_context.get_current_page()
            url = page.url
            
            return {
                "success": True,
                "data": {"url": url},
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": f"获取URL失败: {str(e)}",
                "error_type": "URLError"
            }
    
    async def _extract_google_search_results(self, query: str) -> Dict[str, Any]:
        """专门提取Google搜索结果 - 基于官方browser-use最佳实践"""
        try:
            page = await self.browser_context.get_current_page()
            url = page.url
            
            # 等待搜索结果加载
            try:
                await page.wait_for_selector('.g, .tF2Cxc', timeout=10000)
            except:
                logger.warning("Google搜索结果选择器等待超时，继续尝试提取")
            
            search_results = []
            result_count = 0
            
            # 多种Google搜索结果选择器 - 适配不同版本的Google
            result_selectors = [
                '.g',  # 经典Google结果
                '.tF2Cxc',  # 新版Google结果
                '.g .rc',  # 备用选择器
                '[data-sokoban-container]'  # 另一个可能的选择器
            ]
            
            for selector in result_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        logger.info(f"找到 {len(elements)} 个搜索结果，使用选择器: {selector}")
                        
                        for i, element in enumerate(elements[:10]):  # 最多处理前10个结果
                            try:
                                # 提取标题
                                title_selectors = ['h3', '.LC20lb', '.DKV0Md']
                                title = ""
                                for title_sel in title_selectors:
                                    title_elem = await element.query_selector(title_sel)
                                    if title_elem:
                                        title = await title_elem.text_content() or ""
                                        if title.strip():
                                            break
                                
                                # 提取链接
                                link_selectors = ['a[href]', '.yuRUbf a', 'h3 a']
                                link = ""
                                for link_sel in link_selectors:
                                    link_elem = await element.query_selector(link_sel)
                                    if link_elem:
                                        link = await link_elem.get_attribute('href') or ""
                                        if link and not link.startswith('/search'):
                                            break
                                
                                # 提取摘要
                                snippet_selectors = ['.VwiC3b', '.s3v9rd', '.st', '.X5LH0c']
                                snippet = ""
                                for snippet_sel in snippet_selectors:
                                    snippet_elem = await element.query_selector(snippet_sel)
                                    if snippet_elem:
                                        snippet = await snippet_elem.text_content() or ""
                                        if snippet.strip():
                                            break
                                
                                if title.strip():  # 只有当有标题时才添加结果
                                    search_results.append({
                                        'title': title.strip(),
                                        'url': link.strip() if link else '',
                                        'snippet': snippet.strip(),
                                        'position': i + 1
                                    })
                                    result_count += 1
                                    
                            except Exception as e:
                                logger.warning(f"处理搜索结果 {i} 失败: {e}")
                                continue
                        
                        if search_results:
                            break  # 找到结果就退出循环
                            
                except Exception as e:
                    logger.warning(f"选择器 {selector} 失败: {e}")
                    continue
            
            if not search_results:
                # 如果所有专用选择器都失败，尝试通用方法
                logger.info("专用选择器失败，尝试通用内容提取")
                return await self._extract_page_content({
                    "goal": f"Google搜索结果: {query}",
                    "include_links": True
                })
            
            # 格式化搜索结果
            formatted_content = f"# Google搜索结果: {query}\n\n"
            formatted_content += f"找到 {result_count} 个相关结果\n\n"
            
            for i, result in enumerate(search_results, 1):
                formatted_content += f"## {i}. {result['title']}\n"
                if result['url']:
                    formatted_content += f"**链接**: {result['url']}\n"
                if result['snippet']:
                    formatted_content += f"**摘要**: {result['snippet']}\n"
                formatted_content += "\n"
            
            return {
                "success": True,
                "data": {
                    "content": formatted_content,
                    "url": url,
                    "result_count": result_count,
                    "raw_results": search_results,
                    "extraction_method": "enhanced_google_search"
                }
            }
            
        except Exception as e:
            logger.error(f"Google搜索结果提取失败: {e}")
            return {
                "success": False,
                "error_message": f"Google搜索结果提取失败: {str(e)}"
            }
    
    async def _extract_page_content(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """提取页面内容 - 增强版本"""
        goal = parameters.get("goal", "提取页面主要内容")
        include_links = parameters.get("include_links", False)
        
        try:
            page = await self.browser_context.get_current_page()
            
            # 获取页面基本信息
            url = page.url
            title = await page.title()
            
            # 检查是否是Google搜索页面
            if "google.com/search" in url:
                query = parameters.get("query", goal.replace("Google搜索结果: ", ""))
                return await self._extract_google_search_results(query)
            
            # 提取页面文本内容
            main_content = ""
            
            # 尝试获取标题
            try:
                h1_elements = await page.query_selector_all("h1")
                if h1_elements:
                    h1_text = await h1_elements[0].text_content()
                    if h1_text:
                        main_content += f"# {h1_text.strip()}\n\n"
            except:
                pass
            
            # 获取主要段落内容 - 增强选择器
            try:
                content_selectors = [
                    "main", "article", ".content", "#content", 
                    ".main-content", ".page-content", ".intro-text",
                    "[role='main']", ".post-content", ".entry-content"
                ]
                
                found_content = False
                for selector in content_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            for element in elements[:3]:  # 增加到3个主要元素
                                text = await element.text_content()
                                if text and len(text.strip()) > 30:  # 降低阈值
                                    main_content += f"{text.strip()}\n\n"
                                    found_content = True
                                    break
                            if found_content:
                                break
                    except:
                        continue
                
                # 如果没有找到主内容，获取所有段落和div
                if not found_content:
                    text_elements = await page.query_selector_all("p, div.text, .description")
                    for elem in text_elements[:8]:  # 增加到8个元素
                        text = await elem.text_content()
                        if text and len(text.strip()) > 15:  # 降低阈值
                            main_content += f"{text.strip()}\n\n"
                            
            except Exception as e:
                logger.warning(f"获取段落内容失败: {e}")
                
            # 获取链接信息（如果需要）
            links_content = ""
            if include_links:
                try:
                    link_elements = await page.query_selector_all("a[href]")
                    links = []
                    for link in link_elements[:15]:  # 增加到15个链接
                        href = await link.get_attribute("href")
                        text = await link.text_content()
                        if href and text and text.strip() and len(text.strip()) > 2:
                            # 过滤掉内部锚点和javascript链接
                            if not href.startswith('#') and not href.startswith('javascript:'):
                                links.append(f"- [{text.strip()}]({href})")
                    if links:
                        links_content = "\n\n## 相关链接\n" + "\n".join(links)
                except:
                    pass
            
            # 如果没有获取到任何内容，使用body文本
            if not main_content.strip():
                try:
                    body_text = await page.text_content("body")
                    if body_text:
                        # 改进的文本清理
                        lines = body_text.strip().split('\n')
                        meaningful_lines = []
                        for line in lines:
                            clean_line = line.strip()
                            if clean_line and len(clean_line) > 5 and not clean_line.isspace():
                                meaningful_lines.append(clean_line)
                        main_content = '\n'.join(meaningful_lines[:20])  # 增加到20行
                except:
                    main_content = "无法提取页面内容"
            
            # 组合最终内容
            final_content = f"# {title}\n\n{main_content}{links_content}".strip()
            
            return {
                "success": True,
                "data": {
                    "goal": goal,
                    "url": url,
                    "title": title,
                    "content": final_content,
                    "content_length": len(final_content),
                    "include_links": include_links,
                    "extraction_method": "enhanced_playwright"
                },
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            logger.error(f"内容提取失败: {e}")
            return {
                "success": False,
                "data": None,
                "error_message": f"内容提取失败: {str(e)}",
                "error_type": "ContentExtractionError"
            }

    async def _navigate_to_url(self, url: str) -> Dict[str, Any]:
        """直接导航到指定URL"""
        try:
            page = await self.browser_context.get_current_page()
            
            # 使用playwright的goto方法进行导航
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # 获取页面信息
            actual_url = page.url
            title = await page.title()
            
            # 记录导航成功日志（只记录一次）
            logger.info(f"Navigation successful: {url} -> {actual_url}")
            
            return {
                "success": True,
                "data": {
                    "navigation_successful": True,
                    "requested_url": url,
                    "current_url": actual_url,
                    "page_title": title,
                    "message": f"成功导航到 {actual_url}，页面标题: {title}",
                    "next_suggested_actions": [
                        "browser_extract_content - 提取页面内容",
                        "browser_get_page_info - 获取详细页面信息", 
                        "browser_use_execute_task - 使用AI执行复杂任务"
                    ]
                },
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return {
                "success": False,
                "data": None,
                "error_message": f"导航到 {url} 失败: {str(e)}",
                "error_type": "NavigationError"
            }

    async def _execute_task_with_retry(self, parameters: Dict[str, Any], max_retries: int = 2) -> Dict[str, Any]:
        """带重试逻辑的任务执行"""
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # 如果不是第一次尝试，添加延迟
                if attempt > 0:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    logger.info(f"任务执行重试 - 第{attempt + 1}次尝试")
                
                result = await self._execute_task(parameters)
                
                # 如果成功，记录重试次数并返回
                if result.get('success', False):
                    if attempt > 0:
                        result['retry_count'] = attempt
                        logger.info(f"任务执行成功 - 经过{attempt}次重试")
                    return result
                else:
                    last_error = result.get('error_message', 'Unknown error')
                    if attempt < max_retries:
                        logger.warning(f"任务执行失败，准备重试: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"任务执行异常 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries:
                    continue
                else:
                    break
        
        # 所有重试都失败了
        return {
            "success": False,
            "data": None,
            "error_message": f"任务执行失败，已重试{max_retries}次。最后错误: {last_error}",
            "error_type": "TaskExecutionFailure",
            "retry_count": max_retries
        }

    def _is_recent_request(self, request_id: str, timeout: int = 5) -> bool:
        """检查请求是否在近期内发生过"""
        if not hasattr(self, '_request_timestamps'):
            self._request_timestamps = {}
        
        last_time = self._request_timestamps.get(request_id)
        if last_time and (time.time() - last_time) < timeout:
            return True
        return False

    def _record_request(self, request_id: str):
        """记录请求时间"""
        if not hasattr(self, '_request_timestamps'):
            self._request_timestamps = {}
        self._request_timestamps[request_id] = time.time()

    async def _close_session(self) -> Dict[str, Any]:
        """关闭浏览器会话"""
        try:
            if self.browser_context:
                await self.browser_context.close()
                self.browser_context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
                self.controller = None
                logger.info("Browser session closed")
            
            return {
                "success": True,
                "data": {"message": "Browser session closed successfully"},
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": f"关闭会话失败: {str(e)}",
                "error_type": "SessionCloseError"
            }
    
    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="基于Browser-Use的AI浏览器自动化服务器，完整实现browser-use的所有功能",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 配置监听地址
        os.environ["BROWSER_USE_BIND_HOST"] = self._listen_host
        
        logger.info(f"Attempting to start MCPServer for {self.server_name} at {self.endpoint}...")
        try:
            await mcp_server.start()
            logger.info(f"MCPServer for {self.server_name} started successfully.")
        except Exception as e:
            logger.error(f"Failed to start MCPServer for {self.server_name}: {e}", exc_info=True)
            raise
        finally:
            # 清理资源
            if self.browser:
                try:
                    await self.browser.close()
                    logger.info("Browser session closed.")
                except Exception as e:
                    logger.warning(f"Error closing browser session: {e}")


async def main():
    """主函数"""
    import signal
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager和UnifiedToolManager
    from core.config_manager import ConfigManager
    from core.unified_tool_manager import UnifiedToolManager
    config_manager = ConfigManager()
    tool_manager = UnifiedToolManager()
    
    server = BrowserUseMCPServer(config_manager, tool_manager)
    
    # 设置信号处理器确保优雅退出
    def signal_handler():
        logger.info("收到停止信号，正在清理资源...")
        # 创建任务来异步清理
        asyncio.create_task(cleanup_and_exit(server))
    
    async def cleanup_and_exit(server):
        try:
            # 清理浏览器资源
            if hasattr(server, 'browser') and server.browser:
                await server.browser.close()
                logger.info("浏览器会话已关闭")
            
            # 清理其他资源
            if hasattr(server, 'cleanup'):
                await server.cleanup()
                
        except Exception as e:
            logger.error(f"清理过程中出错: {e}")
        finally:
            logger.info("Browser Use服务器已完全停止")
            # 强制退出
            os._exit(0)
    
    # 注册信号处理器
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda s, f: signal_handler())
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
        await cleanup_and_exit(server)
    except OSError as e:
        if "Address already in use" in str(e) or "Errno 48" in str(e):
            logger.error(f"端口冲突: {e}")
            logger.error("端口8084已被占用，请检查是否有其他Browser Use进程正在运行")
            sys.exit(1)
        else:
            logger.error(f"网络错误: {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        await cleanup_and_exit(server)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())