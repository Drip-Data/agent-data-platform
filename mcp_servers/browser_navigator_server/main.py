import logging
import asyncio
from typing import Dict, Any, List
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException
import websockets

from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from core.toolscore.mcp_client import MCPToolClient
from runtimes.reasoning.tools.browser_tool import BrowserTool # 导入原始的 BrowserTool

logger = logging.getLogger(__name__)

class BrowserNavigatorMCPServer:
    """
    浏览器导航 MCP Server，提供网页导航、点击、文本提取、表单填写、截图和链接提取能力。
    """
    
    def __init__(self, toolscore_url: str):
        self.browser_tool = BrowserTool()
        self.toolscore_client = MCPToolClient(toolscore_url)
        self.server_name = "browser_navigator_server"
        self.server_url = "http://localhost:8082" # 假设此服务运行在8082端口
        self.server_id = str(uuid4()) # 为 MCP Server 生成一个唯一的 ID
        self.mcp_server_instance = None # 用于存储 MCPServer 实例
        
    async def _execute_tool(self, action: str, params: Dict[str, Any]) -> ExecutionResult:
        """
        内部工具执行逻辑，根据 action 调用相应的 BrowserTool 方法。
        """
        try:
            result = {}
            if action == "browser_navigate":
                url = params.get("url", "")
                result = await self.browser_tool.navigate(url)
                
            elif action == "browser_click":
                selector = params.get("selector", "")
                result = await self.browser_tool.click(selector)
                
            elif action == "browser_get_text":
                selector = params.get("selector")
                result = await self.browser_tool.get_text(selector)
                
            elif action == "browser_fill_form":
                selector = params.get("selector", "")
                value = params.get("value", "")
                result = await self.browser_tool.fill_form(selector, value)
                
            elif action == "browser_screenshot":
                path = params.get("path")
                result = await self.browser_tool.screenshot(path)
                
            elif action == "browser_extract_links":
                result = await self.browser_tool.extract_links()
                
            else:
                return ExecutionResult(
                    success=False,
                    error_message=f"Unsupported action: {action}",
                    error_type="UnsupportedAction"
                )
            
            return ExecutionResult(
                success=result.get("success", False),
                data=result.get("output", ""),
                error_message=result.get("error", ""),
                error_type=result.get("error_type", "")
            )
                
        except Exception as e:
            logger.error(f"Browser tool execution failed for {action}: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                error_type="BrowserToolError"
            )

    async def wait_for_server_instance(self):
        """等待 MCPServer 实例被初始化"""
        while self.mcp_server_instance is None:
            await asyncio.sleep(0.1) # 短暂等待
        logger.info("MCPServer instance is ready.")

    def get_capabilities(self) -> List[ToolCapability]:
        """获取浏览器工具的所有能力，用于注册到 toolscore。"""
        return [
            ToolCapability(
                name="browser_navigate",
                description="导航到指定URL",
                parameters={
                    "url": {
                        "type": "string",
                        "description": "要导航到的完整HTTP/HTTPS URL",
                        "required": True
                    }
                },
                examples=[
                    {"url": "https://www.google.com"},
                    {"url": "https://github.com/search?q=python"}
                ]
            ),
            ToolCapability(
                name="browser_click",
                description="点击页面上的指定元素",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，用于定位要点击的元素",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "button#submit"},
                    {"selector": "a[href='/login']"},
                    {"selector": ".search-button"}
                ]
            ),
            ToolCapability(
                name="browser_get_text",
                description="提取页面或指定元素的文本内容",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，留空则提取整个页面文本",
                        "required": False
                    }
                },
                examples=[
                    {},  # 提取整页文本
                    {"selector": ".article-content"},
                    {"selector": "h1"}
                ]
            ),
            ToolCapability(
                name="browser_fill_form",
                description="填写表单字段",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "表单字段的CSS选择器",
                        "required": True
                    },
                    "value": {
                        "type": "string",
                        "description": "要填入的值",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "input[name='email']", "value": "test@example.com"},
                    {"selector": "#password", "value": "password123"}
                ]
            ),
            ToolCapability(
                name="browser_screenshot",
                description="截取当前页面截图",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "截图保存路径，留空则自动生成",
                        "required": False
                    }
                },
                examples=[
                    {},
                    {"path": "/app/output/screenshot.png"}
                ]
            ),
            ToolCapability(
                name="browser_extract_links",
                description="提取页面上的所有链接",
                parameters={},
                examples=[{}]
            )
        ]

    async def run(self):
        """
        启动 MCP Server 并注册到 toolscore。
        """
        logging.basicConfig(level=logging.INFO)
        logger.info(f"Starting {self.server_name} MCP Server...")
        
        # 创建并启动 MCP Server
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description=f"MCP Server for {self.server_name}",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.server_url,
            toolscore_endpoint=self.toolscore_client.toolscore_endpoint
        )
        
        # 注册工具动作处理函数
        mcp_server.register_tool_action_handler(self._execute_tool)
        
        # 启动 MCP Server
        await mcp_server.start()
        self.mcp_server_instance = mcp_server # 存储 MCPServer 实例

# 全局 FastAPI 应用实例
app = FastAPI()

# 在应用启动时初始化并运行 MCP Server
@app.on_event("startup")
async def startup_event():
    toolscore_url = "ws://toolscore:8080/websocket" # 假设 toolscore 运行在 8080 端口
    global browser_navigator_mcp_server
    browser_navigator_mcp_server = BrowserNavigatorMCPServer(toolscore_url)
    app.state.browser_navigator_mcp_server = browser_navigator_mcp_server
    asyncio.create_task(browser_navigator_mcp_server.run())
    # 等待 MCPServer 实例初始化完成
    await browser_navigator_mcp_server.wait_for_server_instance()

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# MCP Server 的 WebSocket 端点
@app.websocket("/mcp")
async def websocket_endpoint(websocket: websockets.WebSocket):
    if hasattr(app.state, 'browser_navigator_mcp_server') and \
       app.state.browser_navigator_mcp_server.mcp_server_instance:
        await app.state.browser_navigator_mcp_server.mcp_server_instance.websocket_handler(websocket, "/mcp")
    else:
        raise HTTPException(status_code=503, detail="Browser Navigator MCP Server not initialized.")