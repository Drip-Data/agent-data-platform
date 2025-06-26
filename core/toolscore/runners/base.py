from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseRunner(ABC):
    """可插拔运行器接口：负责安装、启动、停止、健康检查 MCP Server。"""

    @abstractmethod
    async def install_server(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """安装并启动服务器。

        返回示例::
            {
              "success": True,
              "endpoint": "ws://localhost:8123/mcp",
              "server_id": "python-executor",
              "pid": 12345,
              "error_msg": None
            }
        """

    @abstractmethod
    async def stop_server(self, server_id: str) -> bool:
        """停止并清理指定服务器。"""

    @abstractmethod
    async def health_check(self, endpoint: str) -> bool:
        """检查端点是否健康。""" 