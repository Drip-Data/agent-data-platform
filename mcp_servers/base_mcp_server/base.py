from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseMCPServer(ABC):
    """
    所有 MCP Server 都应继承的基类。
    定义了 MCP Server 必须实现的核心接口。
    """

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        返回 MCP Server 提供的工具能力列表。
        这些能力将用于注册到 Unified Tool Library。
        """
        pass

    @abstractmethod
    async def handle_tool_action(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理来自 MCP Client 的工具调用请求。
        
        Args:
            tool_name (str): 要调用的工具名称。
            arguments (Dict[str, Any]): 工具调用的参数。
            
        Returns:
            Dict[str, Any]: 工具执行结果。
        """
        pass

    @abstractmethod
    async def start(self):
        """启动 MCP Server"""
        pass

    @abstractmethod
    async def stop(self):
        """停止 MCP Server"""
        pass

    @property
    @abstractmethod
    def server_name(self) -> str:
        """返回 MCP Server 的名称"""
        pass

    @property
    @abstractmethod
    def host(self) -> str:
        """返回 MCP Server 的主机地址"""
        pass

    @property
    @abstractmethod
    def port(self) -> int:
        """返回 MCP Server 的端口号"""
        pass