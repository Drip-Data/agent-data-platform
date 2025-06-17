#!/usr/bin/env python3
"""
Search Tool MCP Server
独立的搜索服务，通过MCP协议与toolscore通信
"""

import asyncio
import logging
import os
from typing import Dict, Any, List
from uuid import uuid4

from core.toolscore.interfaces import ToolCapability, ToolType
from core.toolscore.mcp_server import MCPServer
from .search_tool import SearchTool
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SearchToolMCPServer:
    """搜索工具MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.search_tool = SearchTool()
        self.server_name = "search_tool_server"
        self.server_id = "mcp-search-tool" # 使用用户指定的ID
        self.config_manager = config_manager
        
        # 从配置中获取端口，优先使用动态分配的端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查是否有动态分配的端口（由MCP启动器设置）
        dynamic_port = os.getenv('SEARCH_TOOL_SERVER_PORT')
        if dynamic_port:
            search_tool_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {search_tool_port}")
        else:
            search_tool_port = ports_config['mcp_servers']['search_tool']['port']
            logger.info(f"使用配置文件端口: {search_tool_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']

        # 监听地址使用 0.0.0.0 以接受所有网卡，但 **注册给 ToolScore 的地址** 必须是客户端可访问的
        listen_host = os.getenv("SEARCH_TOOL_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("SEARCH_TOOL_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{search_tool_port}/mcp"
        self._listen_host = listen_host
        self._listen_port = search_tool_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取搜索工具的所有能力"""
        return [
            ToolCapability(
                name="search_file_content",
                description="在指定文件中搜索匹配正则表达式的内容",
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "要搜索的文件路径",
                        "required": True
                    },
                    "regex_pattern": {
                        "type": "string",
                        "description": "要匹配的正则表达式",
                        "required": True
                    }
                },
                examples=[
                    {"file_path": "src/main.py", "regex_pattern": "def\\s+\\w+"}
                ]
            ),
            ToolCapability(
                name="list_code_definitions",
                description="列出指定文件或目录中Python代码的类、函数和方法定义",
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "要解析的Python文件路径",
                        "required": False
                    },
                    "directory_path": {
                        "type": "string",
                        "description": "要解析的目录路径",
                        "required": False
                    }
                },
                examples=[
                    {"file_path": "src/utils.py"},
                    {"directory_path": "src/models"}
                ]
            )
        ]
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            logger.info(f"Executing Search tool action: {action} with params: {parameters}")

            result = {}
            if action == "search_file_content":
                file_path = parameters.get("file_path", "")
                regex_pattern = parameters.get("regex_pattern", "")
                result = await self.search_tool.search_file_content(file_path, regex_pattern)
                
            elif action == "list_code_definitions":
                file_path = parameters.get("file_path")
                directory_path = parameters.get("directory_path")
                result = await self.search_tool.list_code_definitions(file_path, directory_path)
                
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }

            return {
                "success": result.get("success", False),
                "data": result.get("output", {}),
                "error_message": result.get("error_message", ""),
                "error_type": result.get("error_type", "")
            }
                
        except Exception as e:
            logger.error(f"Search tool execution failed for {action}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "SearchToolError"
            }

    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="文件内容搜索和代码定义搜索工具服务器",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 在启动之前，覆盖其监听地址，防止绑定到不可用端口
        os.environ["SEARCH_TOOL_BIND_HOST"] = self._listen_host
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
    
    server = SearchToolMCPServer(config_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())