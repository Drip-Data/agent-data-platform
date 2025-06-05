"""
工具注册中心
负责 Function Tool 和 MCP Server 的注册、发现和管理
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
import uuid
import json
from datetime import datetime

from .interfaces import (
    ToolSpec, FunctionToolSpec, MCPServerSpec,
    ToolType, RegistrationResult
)

logger = logging.getLogger(__name__)


@dataclass
class ToolRegistryEntry:
    """工具注册条目"""
    tool_spec: ToolSpec
    registration_time: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 0.0
    health_status: bool = True


class ToolRegistry:
    """统一工具注册中心"""
    
    def __init__(self):
        self._tools: Dict[str, ToolRegistryEntry] = {}
        self._function_tools: Dict[str, FunctionToolSpec] = {}
        self._mcp_servers: Dict[str, MCPServerSpec] = {}
        self._tags_index: Dict[str, Set[str]] = {}  # tag -> tool_ids
        
    async def initialize(self):
        """初始化注册中心"""
        logger.info("Tool registry initialized")
        
    async def register_function_tool(self, tool_spec: FunctionToolSpec) -> RegistrationResult:
        """注册 Function Tool"""
        try:
            tool_id = tool_spec.tool_id or f"func_{uuid.uuid4().hex[:8]}"
            tool_spec.tool_id = tool_id
            
            # 创建注册条目
            entry = ToolRegistryEntry(
                tool_spec=tool_spec,
                registration_time=datetime.now()
            )
            
            # 存储到各个索引
            self._tools[tool_id] = entry
            self._function_tools[tool_id] = tool_spec
            
            # 更新标签索引
            self._update_tags_index(tool_id, tool_spec.tags)
            
            logger.info(f"Successfully registered Function Tool: {tool_spec.name} (ID: {tool_id})")
            
            return RegistrationResult(
                success=True,
                tool_id=tool_id,
                deployment_info={
                    "type": "function_tool",
                    "module_path": tool_spec.module_path,
                    "class_name": tool_spec.class_name,
                    "tags": tool_spec.tags
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to register Function Tool {tool_spec.name}: {e}")
            return RegistrationResult(
                success=False,
                error=str(e)
            )
    
    async def register_mcp_server(self, server_spec: MCPServerSpec) -> RegistrationResult:
        """注册 MCP Server"""
        try:
            tool_id = server_spec.tool_id or f"mcp_{uuid.uuid4().hex[:8]}"
            server_spec.tool_id = tool_id
            
            # 创建注册条目
            entry = ToolRegistryEntry(
                tool_spec=server_spec,
                registration_time=datetime.now()
            )
            
            # 存储到各个索引
            self._tools[tool_id] = entry
            self._mcp_servers[tool_id] = server_spec
            
            # 更新标签索引
            self._update_tags_index(tool_id, server_spec.tags)
            
            logger.info(f"Successfully registered MCP Server: {server_spec.name} (ID: {tool_id})")
            
            return RegistrationResult(
                success=True,
                tool_id=tool_id,
                deployment_info={
                    "type": "mcp_server",
                    "endpoint": server_spec.endpoint,
                    "server_config": server_spec.server_config,
                    "tags": server_spec.tags
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to register MCP Server {server_spec.name}: {e}")
            return RegistrationResult(
                success=False,
                error=str(e)
            )
    
    async def unregister_tool(self, tool_id: str) -> bool:
        """注销工具"""
        try:
            if tool_id not in self._tools:
                logger.warning(f"Tool {tool_id} not found for unregistration")
                return False
            
            # 获取工具规范
            entry = self._tools[tool_id]
            tool_spec = entry.tool_spec
            
            # 从各个索引中移除
            del self._tools[tool_id]
            
            if tool_id in self._function_tools:
                del self._function_tools[tool_id]
            
            if tool_id in self._mcp_servers:
                del self._mcp_servers[tool_id]
            
            # 更新标签索引
            self._remove_from_tags_index(tool_id, tool_spec.tags)
            
            logger.info(f"Successfully unregistered tool: {tool_spec.name} (ID: {tool_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister tool {tool_id}: {e}")
            return False
    
    async def get_all_tools(self) -> List[ToolSpec]:
        """获取所有可用工具"""
        return [entry.tool_spec for entry in self._tools.values() if entry.tool_spec.enabled]
    
    async def get_tools_by_type(self, tool_type: ToolType) -> List[ToolSpec]:
        """按类型获取工具"""
        tools = []
        for entry in self._tools.values():
            if entry.tool_spec.tool_type == tool_type and entry.tool_spec.enabled:
                tools.append(entry.tool_spec)
        return tools
    
    async def get_tool_spec(self, tool_id: str) -> Optional[ToolSpec]:
        """获取工具规范"""
        entry = self._tools.get(tool_id)
        return entry.tool_spec if entry else None
    
    async def search_tools_by_tags(self, tags: List[str]) -> List[ToolSpec]:
        """按标签搜索工具（为将来扩展预留）"""
        if not tags:
            return await self.get_all_tools()
        
        # 查找包含任一标签的工具
        tool_ids = set()
        for tag in tags:
            if tag in self._tags_index:
                tool_ids.update(self._tags_index[tag])
        
        tools = []
        for tool_id in tool_ids:
            entry = self._tools.get(tool_id)
            if entry and entry.tool_spec.enabled:
                tools.append(entry.tool_spec)
        
        return tools
    
    async def get_all_function_tools(self) -> List[FunctionToolSpec]:
        """获取所有 Function Tools"""
        return [spec for spec in self._function_tools.values() if spec.enabled]
    
    async def get_all_mcp_servers(self) -> List[MCPServerSpec]:
        """获取所有 MCP Servers"""
        return [spec for spec in self._mcp_servers.values() if spec.enabled]
    
    async def update_tool_metrics(self, tool_id: str, success: bool, execution_time: float):
        """更新工具指标"""
        entry = self._tools.get(tool_id)
        if not entry:
            return
        
        entry.last_used = datetime.now()
        entry.usage_count += 1
        
        # 更新成功率（简单的滑动平均）
        if entry.usage_count == 1:
            entry.success_rate = 1.0 if success else 0.0
        else:
            # 加权平均，最近的执行权重更高
            weight = 0.3
            entry.success_rate = (1 - weight) * entry.success_rate + weight * (1.0 if success else 0.0)
    
    def _update_tags_index(self, tool_id: str, tags: List[str]):
        """更新标签索引"""
        for tag in tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = set()
            self._tags_index[tag].add(tool_id)
    
    def _remove_from_tags_index(self, tool_id: str, tags: List[str]):
        """从标签索引中移除"""
        for tag in tags:
            if tag in self._tags_index:
                self._tags_index[tag].discard(tool_id)
                # 如果标签下没有工具了，删除标签
                if not self._tags_index[tag]:
                    del self._tags_index[tag]
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息"""
        return {
            "total_tools": len(self._tools),
            "function_tools": len(self._function_tools),
            "mcp_servers": len(self._mcp_servers),
            "available_tags": list(self._tags_index.keys()),
            "tools_by_type": {
                "function": len(self._function_tools),
                "mcp_server": len(self._mcp_servers)
            }
        } 