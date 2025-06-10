"""
ToolScore监控API
提供HTTP接口查看工具注册状态和统计信息
"""

import asyncio
import json
import logging
from typing import Optional
from aiohttp import web
from .unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

class ToolScoreMonitoringAPI:
    """ToolScore监控API服务器"""
    
    def __init__(self, tool_library: Optional[UnifiedToolLibrary] = None, port: int = 8080):
        self.tool_library = tool_library
        self.port = port
        self.app = web.Application()
        self._setup_routes()
    
    def _setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.get_status)
        self.app.router.add_get('/tools', self.list_tools)
        self.app.router.add_get('/tools/{tool_id}', self.get_tool_detail)
        self.app.router.add_get('/stats', self.get_stats)
        self.app.router.add_get('/mcp/persistent', self.get_persistent_storage)
        self.app.router.add_post('/mcp/search', self.search_mcp_servers)
        self.app.router.add_post('/mcp/install', self.install_mcp_server)
    
    async def health_check(self, request):
        """健康检查"""
        return web.json_response({"status": "healthy", "message": "ToolScore monitoring API is running"})
    
    async def get_status(self, request):
        """获取整体状态"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            stats = await self.tool_library.get_library_stats()
            return web.json_response({
                "status": "healthy",
                "tool_library_initialized": stats.get("initialized", False),
                "stats": stats
            })
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return web.json_response({
                "status": "error", 
                "message": str(e)
            }, status=500)
    
    async def list_tools(self, request):
        """列出所有工具"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            tools = await self.tool_library.get_all_tools()
            tools_data = []
            for tool in tools:
                tools_data.append({
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "description": tool.description,
                    "tool_type": tool.tool_type.value,
                    "enabled": tool.enabled,
                    "capabilities_count": len(tool.capabilities),
                    "capabilities": [cap.to_dict() for cap in tool.capabilities]
                })
            
            return web.json_response({
                "status": "success",
                "tools": tools_data,
                "total_count": len(tools_data)
            })
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def get_tool_detail(self, request):
        """获取工具详情"""
        tool_id = request.match_info['tool_id']
        
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            tool = await self.tool_library.get_tool_by_id(tool_id)
            if not tool:
                return web.json_response({
                    "status": "error",
                    "message": f"Tool {tool_id} not found"
                }, status=404)
            
            tool_data = {
                "tool_id": tool.tool_id,
                "name": tool.name,
                "description": tool.description,
                "tool_type": tool.tool_type.value,
                "enabled": tool.enabled,
                "tags": tool.tags,
                "capabilities": [cap.to_dict() for cap in tool.capabilities]
            }
            
            # 添加特定类型的额外信息
            if hasattr(tool, 'endpoint'):
                tool_data['endpoint'] = tool.endpoint
            if hasattr(tool, 'module_path'):
                tool_data['module_path'] = tool.module_path
            if hasattr(tool, 'class_name'):
                tool_data['class_name'] = tool.class_name
                
            return web.json_response({
                "status": "success",
                "tool": tool_data
            })
        except Exception as e:
            logger.error(f"Error getting tool detail for {tool_id}: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def get_stats(self, request):
        """获取详细统计信息"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            stats = await self.tool_library.get_library_stats()
            return web.json_response({
                "status": "success",
                "stats": stats
            })
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def start(self):
        """启动HTTP服务器"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"ToolScore monitoring API started on port {self.port}")
        return runner

    async def get_persistent_storage(self, request):
        """获取持久化存储状态"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            # 获取动态MCP管理器的持久化状态
            stats = await self.tool_library.get_library_stats()
            dynamic_mcp_stats = stats.get("dynamic_mcp", {})
            
            return web.json_response({
                "status": "success",
                "total_servers": dynamic_mcp_stats.get("installed_servers_count", 0),
                "servers": dynamic_mcp_stats.get("installed_servers", {}),
                "storage_stats": dynamic_mcp_stats.get("storage_stats", {}),
                "redis_connected": dynamic_mcp_stats.get("storage_stats", {}).get("redis_connected", False)
            })
        except Exception as e:
            logger.error(f"Error getting persistent storage: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def search_mcp_servers(self, request):
        """搜索MCP服务器"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            data = await request.json()
            query = data.get("query", "")
            max_candidates = data.get("max_candidates", 5)
            
            # 获取动态MCP管理器
            dynamic_mcp = getattr(self.tool_library, 'dynamic_mcp_manager', None)
            if not dynamic_mcp:
                return web.json_response({
                    "status": "error",
                    "message": "Dynamic MCP manager not available"
                }, status=500)
            
            # 执行搜索
            candidates = await dynamic_mcp.search_mcp_candidates(query, max_candidates)
            
            return web.json_response({
                "status": "success",
                "candidates": candidates,
                "total_found": len(candidates)
            })
        except Exception as e:
            logger.error(f"Error searching MCP servers: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def install_mcp_server(self, request):
        """安装MCP服务器"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            data = await request.json()
            
            # 获取动态MCP管理器
            dynamic_mcp = getattr(self.tool_library, 'dynamic_mcp_manager', None)
            if not dynamic_mcp:
                return web.json_response({
                    "status": "error",
                    "message": "Dynamic MCP manager not available"
                }, status=500)
            
            # 执行安装
            success = await dynamic_mcp.install_and_register_mcp_server(data)
            
            return web.json_response({
                "status": "success" if success else "error",
                "success": success,
                "message": "Installation completed" if success else "Installation failed"
            })
        except Exception as e:
            logger.error(f"Error installing MCP server: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

async def start_monitoring_api(tool_library: UnifiedToolLibrary, port: int = 8080):
    """启动监控API的便捷函数"""
    api = ToolScoreMonitoringAPI(tool_library, port)
    return await api.start() 