import os
import time
import logging
from typing import Dict, List, Any
import httpx

logger = logging.getLogger(__name__)

class MCPToolRegistry:
    """管理从 MCP Server 获取的工具信息, 提供搜索与注册接口"""

    def __init__(self, server_url: str | None = None, ttl: int = 300) -> None:
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:8080")
        self.ttl = ttl
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._last_refresh = 0.0
        self._client = httpx.Client(timeout=10)

    def _need_refresh(self) -> bool:
        return time.time() - self._last_refresh > self.ttl

    def refresh(self) -> None:
        """从 MCP Server 拉取最新工具列表"""
        try:
            resp = self._client.get(f"{self.server_url}/tools")
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._tools = {t.get("name"): t for t in tools if t.get("name")}
            self._last_refresh = time.time()
            logger.info("MCP tool registry refreshed: %d tools", len(self._tools))
        except Exception as e:
            logger.warning("Failed to refresh MCP tools: %s", e)

    def list_tool_names(self) -> List[str]:
        if self._need_refresh():
            self.refresh()
        return list(self._tools.keys())

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """按名称或描述搜索工具"""
        if self._need_refresh():
            self.refresh()
        key = keyword.lower()
        return [info for name, info in self._tools.items() if key in name.lower() or key in info.get("description", "").lower()]

    def get(self, name: str) -> Dict[str, Any] | None:
        if self._need_refresh():
            self.refresh()
        return self._tools.get(name)

    def register(self, tool_info: Dict[str, Any]) -> bool:
        """向 MCP Server 注册新工具"""
        try:
            resp = self._client.post(f"{self.server_url}/tools", json=tool_info)
            resp.raise_for_status()
            self.refresh()
            return True
        except Exception as e:
            logger.error("Failed to register tool %s: %s", tool_info.get("name"), e)
            return False

    def remove(self, name: str) -> bool:
        try:
            resp = self._client.delete(f"{self.server_url}/tools/{name}")
            resp.raise_for_status()
            self._tools.pop(name, None)
            return True
        except Exception as e:
            logger.error("Failed to remove tool %s: %s", name, e)
            return False
