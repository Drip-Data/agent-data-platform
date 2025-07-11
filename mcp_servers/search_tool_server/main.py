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
from mcp_servers.search_tool_server.search_tool import SearchTool
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

from core.unified_tool_manager import UnifiedToolManager

class SearchToolMCPServer:
    """搜索工具MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager, tool_manager: UnifiedToolManager):
        self.search_tool = SearchTool()
        self.server_name = "search_tool_server"
        self.server_id = "mcp-search-tool" # 使用用户指定的ID
        self.config_manager = config_manager
        self.tool_manager = tool_manager
        
        # 从配置中获取端口，优先使用动态分配的端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查是否有动态分配的端口（由MCP启动器设置）
        dynamic_port = os.getenv('SEARCH_TOOL_SERVER_PORT')
        if dynamic_port:
            search_tool_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {search_tool_port}")
        else:
            search_tool_port = ports_config['mcp_servers']['search_tool_server']['port']
            logger.info(f"使用配置文件端口: {search_tool_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']

        # 监听地址使用 0.0.0.0 以接受所有网卡，但 **注册给 ToolScore 的地址** 必须是客户端可访问的
        listen_host = os.getenv("SEARCH_TOOL_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("SEARCH_TOOL_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{search_tool_port}/mcp"
        self._listen_host = listen_host
        self._listen_port = search_tool_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')

        # 动作分发映射
        self._action_handlers = {
            "search_file_content": self._search_file_content_wrapper,
            "list_code_definitions": self._list_code_definitions_wrapper,
            "analyze_tool_needs": lambda params: self.search_tool.analyze_tool_needs(params.get("task_description", "")),
            "search_and_install_tools": lambda params: self.search_tool.search_and_install_tools(params.get("task_description", ""), params.get("reason", "")),
        }
        self._validate_actions()

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

    async def _search_file_content_wrapper(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        file_path = parameters.get("file_path", "")
        regex_pattern = parameters.get("regex_pattern", "")
        return await self.search_tool.search_file_content(file_path, regex_pattern)

    async def _list_code_definitions_wrapper(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        file_path = parameters.get("file_path")
        directory_path = parameters.get("directory_path")
        return await self.search_tool.list_code_definitions(file_path, directory_path)

    def get_capabilities(self) -> List[ToolCapability]:
        """获取搜索��具的所有能力"""
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
        logger.info(f"Executing Search tool action: {action} with params: {parameters}")
        handler = self._action_handlers.get(action)
        if handler:
            try:
                result = await handler(parameters)
                return {
                    "success": result.get("success", False),
                    "data": result.get("output", {}),
                    "error_message": result.get("error_message", ""),
                    "error_type": result.get("error_type", "")
                }
            except Exception as e:
                logger.error(f"Search tool execution failed for {action}: {e}", exc_info=True)
                return {"success": False, "data": None, "error_message": str(e), "error_type": "SearchToolError"}
        else:
            return {"success": False, "data": None, "error_message": f"Unsupported action: {action}", "error_type": "UnsupportedAction"}

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
    
    # 初始化ConfigManager和UnifiedToolManager
    from core.config_manager import ConfigManager
    from core.unified_tool_manager import UnifiedToolManager
    config_manager = ConfigManager()
    tool_manager = UnifiedToolManager()
    
    server = SearchToolMCPServer(config_manager, tool_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())