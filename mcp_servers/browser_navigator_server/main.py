#!/usr/bin/env python3
"""
Browser Navigator MCP Server
独立的浏览器导航服务，通过MCP协议与toolscore通信
"""

import asyncio
import logging
import os
from typing import Dict, Any, List
from uuid import uuid4

from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from .browser_tool import BrowserTool
from core.config_manager import ConfigManager # 导入ConfigManager

logger = logging.getLogger(__name__)

class BrowserNavigatorMCPServer:
    """浏览器导航MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.browser_tool = BrowserTool()
        self.server_name = "browser_navigator_server"
        self.server_id = "browser-navigator-mcp-server"
        self.config_manager = config_manager
        
        # 从配置中获取端口，优先使用动态分配的端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查是否有动态分配的端口（由MCP启动器设置）
        dynamic_port = os.getenv('BROWSER_NAVIGATOR_SERVER_PORT')
        if dynamic_port:
            browser_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {browser_port}")
        else:
            browser_port = ports_config['mcp_servers']['browser_navigator']['port']
            logger.info(f"使用配置文件端口: {browser_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']

        # 监听地址使用 0.0.0.0 以接受所有网卡，但 **注册给 ToolScore 的地址** 必须是客户端可访问的
        listen_host = os.getenv("BROWSER_NAVIGATOR_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("BROWSER_NAVIGATOR_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{browser_port}/mcp"
        self._listen_host = listen_host
        self._listen_port = browser_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取浏览器工具的所有能力"""
        return [
            ToolCapability(
                name="browser_navigate",
                description="导航到指定URL",
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
                name="browser_click",
                description="点击页面元素",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器或XPath",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "button.search-btn"},
                    {"selector": "//input[@type='submit']"}
                ]
            ),
            ToolCapability(
                name="browser_type",
                description="在输入框中输入文本",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "输入框的CSS选择器",
                        "required": True
                    },
                    "text": {
                        "type": "string",
                        "description": "要输入的文本",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "input[name='q']", "text": "python tutorial"}
                ]
            ),
            ToolCapability(
                name="browser_scroll",
                description="滚动页面",
                parameters={
                    "direction": {
                        "type": "string",
                        "description": "滚动方向：up, down, left, right",
                        "required": False
                    },
                    "pixels": {
                        "type": "integer",
                        "description": "滚动像素数",
                        "required": False
                    }
                },
                examples=[
                    {"direction": "down", "pixels": 500}
                ]
            ),
            ToolCapability(
                name="browser_screenshot",
                description="截取当前页面截图",
                parameters={
                    "filename": {
                        "type": "string",
                        "description": "截图文件名",
                        "required": False
                    }
                },
                examples=[
                    {"filename": "current_page.png"}
                ]
            ),
            ToolCapability(
                name="browser_get_text",
                description="获取页面文本内容",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，如果为空则获取全页面文本",
                        "required": False
                    }
                },
                examples=[
                    {"selector": "h1"},
                    {}
                ]
            )
        ]
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            logger.info(f"Executing Browser tool action: {action} with params: {parameters}")
            
            if action == "browser_navigate":
                url = parameters.get("url", "")
                result = await self.browser_tool.navigate(url)
                
            elif action == "browser_click":
                selector = parameters.get("selector", "")
                result = await self.browser_tool.click(selector)
                
            elif action == "browser_type":
                selector = parameters.get("selector", "")
                text = parameters.get("text", "")
                result = await self.browser_tool.type_text(selector, text)
                
            elif action == "browser_scroll":
                direction = parameters.get("direction", "down")
                pixels = parameters.get("pixels", 500)
                result = await self.browser_tool.scroll(direction, pixels)
                
            elif action == "browser_screenshot":
                filename = parameters.get("filename", "screenshot.png")
                result = await self.browser_tool.screenshot(filename)
                
            elif action == "browser_get_text":
                selector = parameters.get("selector")
                # 如果selector是空字符串，将其转换为None
                if selector == "":
                    selector = None
                result = await self.browser_tool.get_text(selector)
                
            else:
                return {
                    "success": False,
                    "data": {
                        "error": f"Unsupported action: {action}",
                        "error_type": "UnsupportedAction"
                    }
                }
            
            return {
                "success": result.get("success", False),
                "data": result.get("output", {}),
                "error": result.get("output", {}).get("error"),
                "error_type": result.get("output", {}).get("error_type")
            }
                
        except Exception as e:
            logger.error(f"Browser tool execution failed for {action}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": "BrowserToolError"
            }

    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="浏览器导航和Web操作工具服务器",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 在启动之前，覆盖其监听地址，防止绑定到不可用端口
        os.environ["BROWSER_NAVIGATOR_BIND_HOST"] = self._listen_host
        await mcp_server.start()

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    server = BrowserNavigatorMCPServer(config_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())