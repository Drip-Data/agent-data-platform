#!/usr/bin/env python3
"""
工具验证器 - 验证工具是否存在并可用
防止调用不存在的工具导致循环
"""

import logging
from typing import List, Set, Dict, Any
from core.toolscore.mcp_client import MCPToolClient

logger = logging.getLogger(__name__)

class ToolValidator:
    """工具验证器"""
    
    def __init__(self, mcp_client: MCPToolClient = None):
        self.mcp_client = mcp_client
        self._available_tools_cache = None
        self._cache_timestamp = 0
        
        # 已知的可用工具列表（基于配置文件）
        self.known_available_tools = {
            'web_search',
            'deepsearch', 
            'browser_navigator',
            'python_executor',
            'search_tool',
            'microsandbox',
            'file_reader'
        }
        
        # 已知不存在的工具列表
        self.known_unavailable_tools = {
            'content_analyzer',  # 不存在
            'mcp-search-tool',   # 可能不存在
        }
    
    async def get_available_tools(self, force_refresh: bool = False) -> Set[str]:
        """获取可用工具列表"""
        import time
        current_time = time.time()
        
        # 如果缓存有效且不强制刷新，返回缓存
        if (not force_refresh and 
            self._available_tools_cache is not None and 
            current_time - self._cache_timestamp < 300):  # 5分钟缓存
            return self._available_tools_cache
        
        available_tools = set()
        
        if self.mcp_client:
            try:
                # 从MCP客户端获取实际可用工具
                tools_info = await self.mcp_client.list_tools()
                for tool in tools_info:
                    tool_name = tool.name if hasattr(tool, 'name') else tool.get('name', '')
                    if tool_name:
                        available_tools.add(tool_name)
                
                logger.info(f"✅ 从MCP获取到 {len(available_tools)} 个可用工具")
                
            except Exception as e:
                logger.warning(f"⚠️ 无法从MCP获取工具列表: {e}")
                # 回退到已知工具列表
                available_tools = self.known_available_tools.copy()
        else:
            # 没有MCP客户端，使用已知工具列表
            available_tools = self.known_available_tools.copy()
        
        # 更新缓存
        self._available_tools_cache = available_tools
        self._cache_timestamp = current_time
        
        return available_tools
    
    async def validate_tool_list(self, tool_list: List[str]) -> List[str]:
        """验证工具列表，返回实际可用的工具"""
        if not tool_list:
            return []
        
        available_tools = await self.get_available_tools()
        validated_tools = []
        
        for tool in tool_list:
            if tool in available_tools:
                validated_tools.append(tool)
            elif tool in self.known_unavailable_tools:
                logger.warning(f"⚠️ 跳过已知不可用工具: {tool}")
                # 提供替代工具
                replacement = self._get_replacement_tool(tool)
                if replacement and replacement in available_tools:
                    validated_tools.append(replacement)
                    logger.info(f"🔄 使用替代工具: {tool} -> {replacement}")
            else:
                logger.warning(f"⚠️ 工具 {tool} 可用性未知，保留")
                validated_tools.append(tool)
        
        return validated_tools
    
    def _get_replacement_tool(self, unavailable_tool: str) -> str:
        """为不可用工具提供替代"""
        replacements = {
            'content_analyzer': 'deepsearch',
            'mcp-search-tool': 'web_search',
        }
        return replacements.get(unavailable_tool)
    
    async def check_tool_exists(self, tool_name: str) -> bool:
        """检查单个工具是否存在"""
        if tool_name in self.known_unavailable_tools:
            return False
        
        available_tools = await self.get_available_tools()
        return tool_name in available_tools
    
    async def filter_available_tools(self, tool_suggestions: List[str]) -> List[str]:
        """过滤出实际可用的工具建议"""
        if not tool_suggestions:
            return ['web_search', 'deepsearch']  # 默认工具
        
        validated = await self.validate_tool_list(tool_suggestions)
        
        # 确保至少有一个工具
        if not validated:
            validated = ['web_search']
        
        return validated