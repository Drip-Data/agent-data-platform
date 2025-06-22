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
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from browser_use import Agent, Browser, BrowserConfig, Controller, ActionModel, ActionResult
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.outputs import LLMResult, Generation
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

try:
    from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
    from core.toolscore.mcp_server import MCPServer
    from core.config_manager import ConfigManager
except ImportError as e:
    print(f'Import error: {e}')
    sys.exit(1)
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class BrowserUseLLMAdapter(BaseLanguageModel):
    """
    Adapter to make our LLMClient compatible with browser-use's LangChain interface
    """
    
    def __init__(self, llm_client: LLMClient, **kwargs):
        super().__init__(**kwargs)
        # Use object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, 'llm_client', llm_client)
    
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
    ) -> LLMResult:
        """Generate LLM result from messages."""
        # Convert LangChain messages to our format
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": msg.content})
            else:
                # Handle other message types as system messages
                formatted_messages.append({"role": "system", "content": str(msg.content)})
        
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
        
        # Return LangChain format result
        generation = Generation(text=response)
        return LLMResult(generations=[[generation]])
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Async generate LLM result from messages."""
        # Convert LangChain messages to our format
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": msg.content})
            else:
                # Handle other message types as system messages
                formatted_messages.append({"role": "system", "content": str(msg.content)})
        
        try:
            response = await self.llm_client._call_api(formatted_messages)
        except Exception as e:
            logger.error(f"LLM adapter async call failed: {e}")
            response = f"Error: {e}"
        
        # Return LangChain format result
        generation = Generation(text=response)
        return LLMResult(generations=[[generation]])
    
    # Required abstract methods from BaseLanguageModel
    def generate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        """Generate completions for multiple prompts."""
        generations = []
        for prompt in prompts:
            messages = prompt.to_messages()
            result = self._generate(messages, stop=stop, **kwargs)
            generations.append(result.generations[0])
        return LLMResult(generations=generations)
    
    async def agenerate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        """Async generate completions for multiple prompts."""
        generations = []
        for prompt in prompts:
            messages = prompt.to_messages()
            result = await self._agenerate(messages, stop=stop, **kwargs)
            generations.append(result.generations[0])
        return LLMResult(generations=generations)
    
    def predict(self, text: str, *, stop: Optional[List[str]] = None, **kwargs) -> str:
        """Predict text completion."""
        messages = [HumanMessage(content=text)]
        result = self._generate(messages, stop=stop, **kwargs)
        return result.generations[0][0].text
    
    async def apredict(self, text: str, *, stop: Optional[List[str]] = None, **kwargs) -> str:
        """Async predict text completion."""
        messages = [HumanMessage(content=text)]
        result = await self._agenerate(messages, stop=stop, **kwargs)
        return result.generations[0][0].text
    
    def predict_messages(self, messages: List[BaseMessage], *, stop: Optional[List[str]] = None, **kwargs) -> BaseMessage:
        """Predict message response."""
        result = self._generate(messages, stop=stop, **kwargs)
        return AIMessage(content=result.generations[0][0].text)
    
    async def apredict_messages(self, messages: List[BaseMessage], *, stop: Optional[List[str]] = None, **kwargs) -> BaseMessage:
        """Async predict message response."""
        result = await self._agenerate(messages, stop=stop, **kwargs)
        return AIMessage(content=result.generations[0][0].text)
    
    def invoke(self, input_data, config=None, **kwargs):
        """Invoke the language model."""
        if isinstance(input_data, str):
            return self.predict(input_data, **kwargs)
        elif isinstance(input_data, list):
            return self.predict_messages(input_data, **kwargs)
        else:
            raise ValueError(f"Unsupported input type: {type(input_data)}")


class BrowserUseMCPServer:
    """Browser-Use AI浏览器MCP服务器 - 完整实现browser-use功能"""
    
    def __init__(self, config_manager: ConfigManager):
        self.server_name = "browser_use_server"
        self.server_id = "browser-use-mcp-server"
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
        
        # 初始化browser和controller
        self.browser = None
        self.controller = None
        
        logger.info(f"BrowserUseMCPServer initialized:")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")
    
    async def _ensure_browser_session(self):
        """确保browser已初始化"""
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
                await self.browser.start()
                logger.info("Browser initialized with enhanced configuration")
                
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                # 回退到基本配置
                browser_config = BrowserConfig(
                    headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
                    disable_security=True
                )
                self.browser = Browser(config=browser_config)
                await self.browser.start()
                logger.info("Browser initialized with basic configuration")
            
        if self.controller is None:
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
            logger.info(f"Executing Browser-Use action: {action} with params: {parameters}")
            
            # 确保browser session已初始化
            await self._ensure_browser_session()
            
            # 高级AI任务执行
            if action == "browser_use_execute_task":
                return await self._execute_task(parameters)
            
            # 基础导航功能
            elif action == "browser_navigate":
                return await self._execute_action("go_to_url", {"url": parameters["url"]})
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
                browser_llm = BrowserUseLLMAdapter(self.llm_client)
                return await self._execute_action("extract_content", {
                    "goal": parameters["goal"],
                    "include_links": parameters.get("include_links", False)
                }, page_extraction_llm=browser_llm)
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
            result = await self.controller.act(
                action=action_model,
                browser=self.browser,
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
                browser=self.browser,
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
            page = await self.browser.get_current_page()
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
            if not self.browser:
                return {
                    "success": False,
                    "data": None,
                    "error_message": "Browser session not initialized",
                    "error_type": "SessionError"
                }
            
            page = await self.browser.get_current_page()
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
            if not self.browser:
                return {
                    "success": False,
                    "data": None,
                    "error_message": "Browser session not initialized",
                    "error_type": "SessionError"
                }
            
            page = await self.browser.get_current_page()
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
    
    async def _close_session(self) -> Dict[str, Any]:
        """关闭浏览器会话"""
        try:
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