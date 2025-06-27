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

logger = logging.getLogger(__name__)


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
            
            # Try to parse as JSON for structured output
            import json
            import re
            try:
                # First try to parse directly
                parsed = json.loads(content)
                return StructuredResponse(parsed)
            except (json.JSONDecodeError, TypeError):
                # Try to extract JSON from markdown code blocks
                try:
                    # Look for JSON wrapped in markdown code blocks
                    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
                    if json_match:
                        json_content = json_match.group(1).strip()
                        parsed = json.loads(json_content)
                        return StructuredResponse(parsed)
                    else:
                        # Try to find JSON-like content without code blocks
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            json_content = json_match.group(0)
                            parsed = json.loads(json_content)
                            return StructuredResponse(parsed)
                        else:
                            raise ValueError("No JSON content found")
                except (json.JSONDecodeError, ValueError):
                    # If not valid JSON, wrap the string response
                    return StructuredResponse({"response": content})
                
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
            
            # Try to parse as JSON for structured output
            import json
            import re
            try:
                # First try to parse directly
                parsed = json.loads(content)
                structured_resp = StructuredResponse(parsed)
                logger.info(f"Created StructuredResponse with keys: {list(structured_resp.keys())}")
                return structured_resp
            except (json.JSONDecodeError, TypeError):
                # Try to extract JSON from markdown code blocks
                try:
                    # Look for JSON wrapped in markdown code blocks
                    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
                    if json_match:
                        json_content = json_match.group(1).strip()
                        parsed = json.loads(json_content)
                        structured_resp = StructuredResponse(parsed)
                        logger.info(f"Extracted JSON from markdown, created StructuredResponse with keys: {list(structured_resp.keys())}")
                        logger.info(f"StructuredResponse type: {type(structured_resp)}, has action: {hasattr(structured_resp, 'action')}")
                        if hasattr(structured_resp, 'action'):
                            logger.info(f"Action attribute type: {type(structured_resp.action)}, value: {structured_resp.action}")
                        return structured_resp
                    else:
                        # Try to find JSON-like content without code blocks
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            json_content = json_match.group(0)
                            parsed = json.loads(json_content)
                            structured_resp = StructuredResponse(parsed)
                            logger.info(f"Extracted JSON pattern, created StructuredResponse with keys: {list(structured_resp.keys())}")
                            return structured_resp
                        else:
                            raise ValueError("No JSON content found")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse JSON even after extraction: {e}, returning raw content")
                    # If not valid JSON, wrap the string response
                    return StructuredResponse({"response": content})
                
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
        import json
        import re
        try:
            # First try to parse directly
            parsed = json.loads(content)
            structured_resp = StructuredResponse(parsed)
            logger.info(f"Direct JSON parse successful, created StructuredResponse with keys: {list(structured_resp.keys())}")
            return structured_resp
        except (json.JSONDecodeError, TypeError):
            # Try to extract JSON from markdown code blocks
            try:
                # Look for JSON wrapped in markdown code blocks
                json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
                if json_match:
                    json_content = json_match.group(1).strip()
                    parsed = json.loads(json_content)
                    structured_resp = StructuredResponse(parsed)
                    logger.info(f"Extracted JSON from markdown, created StructuredResponse with keys: {list(structured_resp.keys())}")
                    logger.info(f"StructuredResponse type: {type(structured_resp)}, has action: {hasattr(structured_resp, 'action')}")
                    if hasattr(structured_resp, 'action'):
                        logger.info(f"Action attribute type: {type(structured_resp.action)}, value: {structured_resp.action}")
                    return structured_resp
                else:
                    # Try to find JSON-like content without code blocks
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        json_content = json_match.group(0)
                        parsed = json.loads(json_content)
                        structured_resp = StructuredResponse(parsed)
                        logger.info(f"Extracted JSON pattern, created StructuredResponse")
                        return structured_resp
                    else:
                        logger.warning("No JSON content found in response")
                        return None
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON even after extraction: {e}")
                return None


class BrowserUseMCPServer:
    """Browser-Use AI浏览器MCP服务器 - 完整实现browser-use功能"""
    
    def __init__(self, config_manager: ConfigManager):
        self.server_name = "browser_use_server"
        self.server_id = "browser_use"
        self.config_manager = config_manager
        
        # 初始化统一LLM客户端
        llm_config = config_manager.get_llm_config()
        self.llm_client = LLMClient(llm_config)
        logger.info(f"Browser-Use server initialized with LLM provider: {self.llm_client.provider.value}")
        
        # 从配置中获取端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查动态分配的端口
        dynamic_port = os.getenv('BROWSER_USE_SERVER_PORT')
        if dynamic_port:
            browser_use_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {browser_use_port}")
        else:
            browser_use_port = ports_config['mcp_servers'].get('browser_use', {}).get('port', 8003)
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
        
        logger.info(f"BrowserUseMCPServer initialized:")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")
    
    async def _ensure_browser_session(self):
        """确保browser和context已初始化"""
        if self.browser is None:
            try:
                # 增强的浏览器配置 - 移除不支持的chrome_path参数
                browser_config = BrowserConfig(
                    headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
                    disable_security=True,     # 允许跨域访问
                    extra_chromium_args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage", 
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-extensions",
                        "--no-first-run",
                        "--disable-default-apps",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding"
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
        return [
            # 高级AI任务执行
            ToolCapability(
                name="browser_use_execute_task",
                description="使用AI执行复杂的浏览器任务，支持自然语言描述",
                parameters={
                    "task": {
                        "type": "string",
                        "description": "要执行的任务描述，使用自然语言",
                        "required": True
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "最大执行步骤数，默认50",
                        "required": False
                    },
                    "use_vision": {
                        "type": "boolean",
                        "description": "是否使用视觉理解，默认true",
                        "required": False
                    }
                },
                examples=[
                    {"task": "搜索Python教程并打开第一个结果"},
                    {"task": "在GitHub上搜索browser-use项目并查看README"},
                    {"task": "登录网站并填写表单", "use_vision": True}
                ]
            ),
            
            # 基础导航功能
            ToolCapability(
                name="browser_navigate",
                description="导航到指定网址",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "要访问的URL地址",
                        "required": True
                    }
                },
                examples=[
                    {"url": "https://www.google.com"},
                    {"url": "https://github.com"}
                ]
            ),
            
            ToolCapability(
                name="browser_search_google",
                description="在Google中搜索指定查询",
                parameters={
                    "query": {
                        "type": "string",
                        "description": "搜索查询词",
                        "required": True
                    }
                },
                examples=[
                    {"query": "Python machine learning tutorial"},
                    {"query": "browser automation tools"}
                ]
            ),
            
            ToolCapability(
                name="browser_go_back",
                description="返回上一页",
                parameters={},
                examples=[{}]
            ),
            
            # 元素交互功能
            ToolCapability(
                name="browser_click_element",
                description="通过索引点击页面元素",
                parameters={
                    "index": {
                        "type": "integer",
                        "description": "要点击的元素索引",
                        "required": True
                    }
                },
                examples=[
                    {"index": 1},
                    {"index": 5}
                ]
            ),
            
            ToolCapability(
                name="browser_input_text",
                description="在指定元素中输入文本",
                parameters={
                    "index": {
                        "type": "integer",
                        "description": "要输入文本的元素索引",
                        "required": True
                    },
                    "text": {
                        "type": "string",
                        "description": "要输入的文本",
                        "required": True
                    }
                },
                examples=[
                    {"index": 2, "text": "hello world"},
                    {"index": 0, "text": "test@example.com"}
                ]
            ),
            
            ToolCapability(
                name="browser_send_keys",
                description="发送特殊键或快捷键",
                parameters={
                    "keys": {
                        "type": "string",
                        "description": "要发送的键，如Enter、Escape、Control+c等",
                        "required": True
                    }
                },
                examples=[
                    {"keys": "Enter"},
                    {"keys": "Control+c"},
                    {"keys": "Escape"}
                ]
            ),
            
            # 滚动功能
            ToolCapability(
                name="browser_scroll_down",
                description="向下滚动页面",
                parameters={
                    "amount": {
                        "type": "integer",
                        "description": "滚动像素数，不指定则滚动一页",
                        "required": False
                    }
                },
                examples=[
                    {},
                    {"amount": 500}
                ]
            ),
            
            ToolCapability(
                name="browser_scroll_up",
                description="向上滚动页面",
                parameters={
                    "amount": {
                        "type": "integer",
                        "description": "滚动像素数，不指定则滚动一页",
                        "required": False
                    }
                },
                examples=[
                    {},
                    {"amount": 300}
                ]
            ),
            
            ToolCapability(
                name="browser_scroll_to_text",
                description="滚动到包含指定文本的元素",
                parameters={
                    "text": {
                        "type": "string",
                        "description": "要滚动到的文本内容",
                        "required": True
                    }
                },
                examples=[
                    {"text": "Sign up"},
                    {"text": "Contact us"}
                ]
            ),
            
            # 标签管理
            ToolCapability(
                name="browser_switch_tab",
                description="切换到指定标签",
                parameters={
                    "page_id": {
                        "type": "integer",
                        "description": "要切换到的标签ID",
                        "required": True
                    }
                },
                examples=[
                    {"page_id": 0},
                    {"page_id": 1}
                ]
            ),
            
            ToolCapability(
                name="browser_open_tab",
                description="在新标签中打开URL",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "要在新标签中打开的URL",
                        "required": True
                    }
                },
                examples=[
                    {"url": "https://www.example.com"}
                ]
            ),
            
            ToolCapability(
                name="browser_close_tab",
                description="关闭指定标签",
                parameters={
                    "page_id": {
                        "type": "integer",
                        "description": "要关闭的标签ID",
                        "required": True
                    }
                },
                examples=[
                    {"page_id": 1}
                ]
            ),
            
            # 内容提取
            ToolCapability(
                name="browser_extract_content",
                description="从页面提取特定内容",
                parameters={
                    "goal": {
                        "type": "string",
                        "description": "提取目标描述",
                        "required": True
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "是否包含链接，默认false",
                        "required": False
                    }
                },
                examples=[
                    {"goal": "提取所有公司名称"},
                    {"goal": "获取产品价格信息", "include_links": True}
                ]
            ),
            
            ToolCapability(
                name="browser_get_content",
                description="获取页面内容",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，空则获取全部内容",
                        "required": False
                    }
                },
                examples=[
                    {"selector": "h1, p"},
                    {}
                ]
            ),
            
            ToolCapability(
                name="browser_get_ax_tree",
                description="获取页面的可访问性树结构",
                parameters={
                    "number_of_elements": {
                        "type": "integer",
                        "description": "返回的元素数量",
                        "required": True
                    }
                },
                examples=[
                    {"number_of_elements": 50}
                ]
            ),
            
            # 下拉菜单操作
            ToolCapability(
                name="browser_get_dropdown_options",
                description="获取下拉菜单的所有选项",
                parameters={
                    "index": {
                        "type": "integer",
                        "description": "下拉菜单元素的索引",
                        "required": True
                    }
                },
                examples=[
                    {"index": 3}
                ]
            ),
            
            ToolCapability(
                name="browser_select_dropdown_option",
                description="选择下拉菜单中的选项",
                parameters={
                    "index": {
                        "type": "integer",
                        "description": "下拉菜单元素的索引",
                        "required": True
                    },
                    "text": {
                        "type": "string",
                        "description": "要选择的选项文本",
                        "required": True
                    }
                },
                examples=[
                    {"index": 3, "text": "Option 1"}
                ]
            ),
            
            # 拖拽操作
            ToolCapability(
                name="browser_drag_drop",
                description="执行拖拽操作",
                parameters={
                    "element_source": {
                        "type": "string",
                        "description": "源元素选择器",
                        "required": False
                    },
                    "element_target": {
                        "type": "string",
                        "description": "目标元素选择器",
                        "required": False
                    },
                    "coord_source_x": {
                        "type": "integer",
                        "description": "源坐标X",
                        "required": False
                    },
                    "coord_source_y": {
                        "type": "integer",
                        "description": "源坐标Y",
                        "required": False
                    },
                    "coord_target_x": {
                        "type": "integer",
                        "description": "目标坐标X",
                        "required": False
                    },
                    "coord_target_y": {
                        "type": "integer",
                        "description": "目标坐标Y",
                        "required": False
                    },
                    "steps": {
                        "type": "integer",
                        "description": "拖拽步骤数，默认10",
                        "required": False
                    }
                },
                examples=[
                    {"element_source": ".item1", "element_target": ".dropzone"}
                ]
            ),
            
            # 文件操作
            ToolCapability(
                name="browser_save_pdf",
                description="将当前页面保存为PDF",
                parameters={},
                examples=[{}]
            ),
            
            ToolCapability(
                name="browser_screenshot",
                description="截取当前页面截图",
                parameters={
                    "filename": {
                        "type": "string",
                        "description": "截图文件名，可选",
                        "required": False
                    }
                },
                examples=[
                    {"filename": "current_page.png"},
                    {}
                ]
            ),
            
            # 等待功能
            ToolCapability(
                name="browser_wait",
                description="等待指定秒数",
                parameters={
                    "seconds": {
                        "type": "number",
                        "description": "等待的秒数，默认3",
                        "required": False
                    }
                },
                examples=[
                    {"seconds": 5},
                    {}
                ]
            ),
            
            # 任务完成
            ToolCapability(
                name="browser_done",
                description="标记任务完成",
                parameters={
                    "text": {
                        "type": "string",
                        "description": "完成描述",
                        "required": True
                    },
                    "success": {
                        "type": "boolean",
                        "description": "是否成功完成",
                        "required": True
                    }
                },
                examples=[
                    {"text": "任务已完成", "success": True}
                ]
            ),
            
            # 新增页面信息获取功能
            ToolCapability(
                name="browser_get_page_info",
                description="获取当前页面信息",
                parameters={},
                examples=[{}]
            ),
            
            ToolCapability(
                name="browser_get_current_url",
                description="获取当前页面URL",
                parameters={},
                examples=[{}]
            ),
            
            ToolCapability(
                name="browser_close_session",
                description="关闭浏览器会话",
                parameters={},
                examples=[{}]
            )
        ]
    
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            # 记录工具使用统计（用于修复元数据记录问题）
            if not hasattr(self, '_tool_usage_stats'):
                self._tool_usage_stats = {}
            self._tool_usage_stats[action] = self._tool_usage_stats.get(action, 0) + 1
            
            logger.info(f"Executing Browser-Use action: {action} with params: {parameters}")
            
            # 🔥 强化通用参数校验
            if not isinstance(parameters, dict):
                logger.error(f"❌ 参数必须是字典类型，收到: {type(parameters).__name__}")
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"参数必须是字典类型，收到: {type(parameters).__name__}",
                    "error_type": "InvalidParameterType",
                    "received_type": type(parameters).__name__
                }
            
            # 检查是否包含元数据污染
            contaminated_fields = [key for key in parameters.keys() 
                                 if key in ['action', 'tool_id', 'tool']]
            if contaminated_fields:
                logger.error(f"❌ 检测到参数元数据污染: {contaminated_fields}")
                logger.error(f"❌ 完整参数: {parameters}")
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"检测到无效的元数据字段: {contaminated_fields}。这些字段不应该出现在业务参数中。",
                    "error_type": "ParameterContamination",
                    "contaminated_fields": contaminated_fields,
                    "action": action,
                    "diagnostic_info": "这通常表示参数构建逻辑存在bug，将元数据混入了业务参数"
                }
            
            # 确保browser session已初始化
            await self._ensure_browser_session()
            
            # 执行前记录开始时间（用于性能监控）
            start_time = time.time()
            
            # 高级AI任务执行
            if action == "browser_use_execute_task":
                result = await self._execute_task_with_retry(parameters)
                result['execution_time'] = time.time() - start_time
                return result
            
            # 基础导航功能
            elif action == "browser_navigate":
                # 🔥 强化参数校验：必须包含有效的url参数
                if "url" not in parameters:
                    logger.error(f"❌ browser_navigate缺少必需参数'url'，收到参数: {parameters}")
                    return {
                        "success": False,
                        "data": None,
                        "error_message": "browser_navigate动作缺少必需参数'url'",
                        "error_type": "MissingRequiredParameter",
                        "received_parameters": list(parameters.keys()),
                        "expected_parameters": ["url"]
                    }
                
                url = parameters["url"]
                if not isinstance(url, str) or not url.strip():
                    logger.error(f"❌ browser_navigate的url参数无效: {url}")
                    return {
                        "success": False,
                        "data": None,
                        "error_message": f"browser_navigate的url参数必须是非空字符串，收到: {type(url).__name__}",
                        "error_type": "InvalidParameterValue",
                        "received_url": str(url)[:100] if url else "None"
                    }
                
                # 增加日志去重逻辑，防止重复记录
                request_id = f"navigate:{url}"
                if self._is_recent_request(request_id):
                    logger.info(f"Debouncing duplicate navigation request for {url}")
                    return {
                        "success": True,
                        "data": {"message": "Request debounced"},
                        "error_message": "",
                        "error_type": "Debounced"
                    }
                self._record_request(request_id)
                
                return await self._navigate_to_url(url)
            elif action == "browser_search_google":
                return await self._execute_action("search_google", {"query": parameters["query"]})
            elif action == "browser_go_back":
                return await self._execute_action("go_back", {})
            
            # 元素交互功能
            elif action == "browser_click_element":
                return await self._execute_action("click_element_by_index", {"index": parameters["index"]})
            elif action == "browser_input_text":
                return await self._execute_action("input_text", {
                    "index": parameters["index"],
                    "text": parameters["text"]
                })
            elif action == "browser_send_keys":
                return await self._execute_action("send_keys", {"keys": parameters["keys"]})
            
            # 滚动功能
            elif action == "browser_scroll_down":
                return await self._execute_action("scroll_down", {"amount": parameters.get("amount")})
            elif action == "browser_scroll_up":
                return await self._execute_action("scroll_up", {"amount": parameters.get("amount")})
            elif action == "browser_scroll_to_text":
                return await self._execute_action("scroll_to_text", {"text": parameters["text"]})
            
            # 标签管理
            elif action == "browser_switch_tab":
                return await self._execute_action("switch_tab", {"page_id": parameters["page_id"]})
            elif action == "browser_open_tab":
                return await self._execute_action("open_tab", {"url": parameters["url"]})
            elif action == "browser_close_tab":
                return await self._execute_action("close_tab", {"page_id": parameters["page_id"]})
            
            # 内容提取
            elif action == "browser_extract_content":
                return await self._extract_page_content(parameters)
            elif action == "browser_get_ax_tree":
                return await self._execute_action("get_ax_tree", {
                    "number_of_elements": parameters["number_of_elements"]
                })
            
            # 下拉菜单操作
            elif action == "browser_get_dropdown_options":
                return await self._execute_action("get_dropdown_options", {"index": parameters["index"]})
            elif action == "browser_select_dropdown_option":
                return await self._execute_action("select_dropdown_option", {
                    "index": parameters["index"],
                    "text": parameters["text"]
                })
            
            # 拖拽操作
            elif action == "browser_drag_drop":
                drag_params = {}
                for key in ["element_source", "element_target", "coord_source_x", "coord_source_y", 
                           "coord_target_x", "coord_target_y", "steps"]:
                    if key in parameters:
                        drag_params[key] = parameters[key]
                return await self._execute_action("drag_drop", drag_params)
            
            # 文件操作
            elif action == "browser_save_pdf":
                return await self._execute_action("save_pdf", {})
            elif action == "browser_screenshot":
                return await self._screenshot(parameters)
            
            # 等待功能
            elif action == "browser_wait":
                return await self._execute_action("wait", {"seconds": parameters.get("seconds", 3)})
            
            # 任务完成
            elif action == "browser_done":
                return await self._execute_action("done", {
                    "text": parameters["text"],
                    "success": parameters["success"]
                })
            
            # 新增高级功能
            elif action == "browser_get_page_info":
                return await self._get_page_info()
            elif action == "browser_get_current_url":
                return await self._get_current_url()
            elif action == "browser_close_session":
                return await self._close_session()
            
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }
                
        except Exception as e:
            logger.error(f"Browser-Use tool execution failed for {action}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "BrowserUseError"
            }
    
    async def _execute_action(self, action_name: str, params: dict, **kwargs) -> Dict[str, Any]:
        """执行browser-use控制器的具体动作"""
        try:
            # 创建动作模型
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
        """执行AI浏览器任务"""
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
            
            # 执行任务
            result = await agent.run(max_steps=max_steps)
            
            # 提取结果
            if hasattr(result, 'history') and result.history:
                last_step = result.history[-1]
                success = getattr(last_step, 'success', True)
                content = getattr(last_step, 'extracted_content', '')
                
                return {
                    "success": success,
                    "data": {
                        "task": task,
                        "result": content,
                        "steps_taken": len(result.history),
                        "max_steps": max_steps
                    },
                    "error_message": "",
                    "error_type": ""
                }
            else:
                return {
                    "success": True,
                    "data": {
                        "task": task,
                        "result": "任务执行完成",
                        "steps_taken": 0,
                        "max_steps": max_steps
                    },
                    "error_message": "",
                    "error_type": ""
                }
                
        except Exception as e:
            logger.error(f"Browser-Use task execution failed: {e}", exc_info=True)
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
    
    async def _extract_page_content(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """提取页面内容"""
        goal = parameters.get("goal", "提取页面主要内容")
        include_links = parameters.get("include_links", False)
        
        try:
            page = await self.browser_context.get_current_page()
            
            # 获取页面基本信息
            url = page.url
            title = await page.title()
            
            # 提取页面文本内容
            # 获取主要内容元素
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
            
            # 获取主要段落内容
            try:
                # 尝试常见的主内容选择器
                content_selectors = [
                    "main", "article", ".content", "#content", 
                    ".main-content", ".page-content", ".intro-text"
                ]
                
                found_content = False
                for selector in content_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            for element in elements[:2]:  # 最多获取2个主要元素
                                text = await element.text_content()
                                if text and len(text.strip()) > 50:  # 只获取有意义的内容
                                    main_content += f"{text.strip()}\n\n"
                                    found_content = True
                                    break
                            if found_content:
                                break
                    except:
                        continue
                
                # 如果没有找到主内容，获取所有段落
                if not found_content:
                    p_elements = await page.query_selector_all("p")
                    for p in p_elements[:5]:  # 最多5个段落
                        text = await p.text_content()
                        if text and len(text.strip()) > 20:
                            main_content += f"{text.strip()}\n\n"
                            
            except Exception as e:
                logger.warning(f"获取段落内容失败: {e}")
                
            # 获取链接信息（如果需要）
            links_content = ""
            if include_links:
                try:
                    link_elements = await page.query_selector_all("a[href]")
                    links = []
                    for link in link_elements[:10]:  # 最多10个链接
                        href = await link.get_attribute("href")
                        text = await link.text_content()
                        if href and text and text.strip():
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
                        # 简单清理和截取
                        lines = body_text.strip().split('\n')
                        meaningful_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 10]
                        main_content = '\n'.join(meaningful_lines[:10])  # 最多10行
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
                    "extraction_method": "direct_playwright"
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
    
    # 初始化ConfigManager
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    server = BrowserUseMCPServer(config_manager)
    
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