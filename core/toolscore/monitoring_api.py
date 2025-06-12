"""
ToolScore监控API
提供HTTP接口查看工具注册状态和统计信息
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional
from aiohttp import web
import aiohttp
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
        
        # 管理员工具注册接口 - 中央注册权威
        self.app.router.add_post('/admin/tools/register', self.register_tool_admin)
        self.app.router.add_delete('/admin/tools/{tool_id}', self.unregister_tool_admin)
        self.app.router.add_get('/admin/tools/lifecycle', self.get_tool_lifecycle)
        
        # 新增API端点 - 支持Enhanced Reasoning Runtime
        self.app.router.add_get('/api/v1/tools/available', self.get_available_tools_for_llm)
        self.app.router.add_post('/api/v1/tools/request-capability', self.request_tool_capability)
        self.app.router.add_post('/api/v1/tools/analyze-gap', self.analyze_tool_gap)
        
        # WebSocket实时事件端点 (Step 4.1)
        self.app.router.add_get('/api/v1/events/tools', self.websocket_tools_events)
    
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
            
            # 执行搜索 - 修复方法名
            if hasattr(dynamic_mcp, 'search_mcp_servers'):
                candidates = await dynamic_mcp.search_mcp_servers(query, [])
            else:
                # 降级处理：直接返回空结果
                logger.warning("DynamicMCPManager没有search_mcp_servers方法，返回空结果")
                candidates = []
            
            # 转换为API响应格式
            candidates_data = []
            for candidate in candidates[:max_candidates]:
                candidates_data.append({
                    "name": candidate.name,
                    "description": candidate.description,
                    "github_url": candidate.github_url,
                    "author": candidate.author,
                    "tags": candidate.tags,
                    "install_method": candidate.install_method,
                    "capabilities": candidate.capabilities,
                    "security_score": candidate.security_score,
                    "popularity_score": candidate.popularity_score
                })
            
            return web.json_response({
                "status": "success",
                "candidates": candidates_data,
                "total_found": len(candidates_data)
            })
        except Exception as e:
            logger.error(f"Error searching MCP servers: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def register_tool_admin(self, request):
        """管理员工具注册接口 - 中央注册权威"""
        if not self.tool_library:
            return web.json_response({
                "success": False,
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            data = await request.json()
            tool_spec_data = data.get("tool_spec")
            
            if not tool_spec_data:
                return web.json_response({
                    "success": False,
                    "message": "Missing tool_spec in request"
                }, status=400)
            
            # 验证和创建工具规范
            tool_spec = self._create_tool_spec_from_dict(tool_spec_data)
            
            # 注册到工具库
            result = await self.tool_library.register_function_tool(tool_spec)
            
            if result.success:
                # 发布工具注册事件到Redis Pub/Sub
                await self._publish_tool_registration_event(tool_spec_data, "register")
                
                logger.info(f"✅ 工具已成功注册并发布事件: {tool_spec.tool_id}")
            
            return web.json_response({
                "success": result.success,
                "tool_id": result.tool_id if result.success else None,
                "message": result.error if not result.success else "工具注册成功"
            })
            
        except Exception as e:
            logger.error(f"Admin tool registration failed: {e}")
            return web.json_response({
                "success": False,
                "message": f"注册失败: {str(e)}"
            }, status=400)
    
    async def unregister_tool_admin(self, request):
        """管理员工具注销接口"""
        if not self.tool_library:
            return web.json_response({
                "success": False,
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            tool_id = request.match_info.get('tool_id')
            if not tool_id:
                return web.json_response({
                    "success": False,
                    "message": "Missing tool_id in request"
                }, status=400)
            
            # 获取工具信息用于事件发布
            tool = await self.tool_library.get_tool_by_id(tool_id)
            
            # 注销工具
            result = await self.tool_library.unregister_tool(tool_id)
            
            if result.success and tool:
                # 发布工具注销事件
                await self._publish_tool_registration_event({
                    "tool_id": tool_id,
                    "name": tool.name
                }, "unregister")
                
                logger.info(f"✅ 工具已成功注销并发布事件: {tool_id}")
            
            return web.json_response({
                "success": result.success,
                "message": result.error if not result.success else "工具注销成功"
            })
            
        except Exception as e:
            logger.error(f"Admin tool unregistration failed: {e}")
            return web.json_response({
                "success": False,
                "message": f"注销失败: {str(e)}"
            }, status=400)
    
    async def _publish_tool_registration_event(self, tool_spec_data: dict, event_type: str):
        """发布工具注册事件到Redis Pub/Sub"""
        try:
            import redis.asyncio as redis
            
            redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379'))
            
            event_data = {
                "event_type": event_type,
                "tool_id": tool_spec_data.get("tool_id"),
                "tool_spec": tool_spec_data,
                "source_service": "toolscore",
                "timestamp": time.time()
            }
            
            await redis_client.publish('tool_events', json.dumps(event_data))
            logger.info(f"📢 已发布工具{event_type}事件: {tool_spec_data.get('tool_id')}")
            
            await redis_client.close()
            
        except Exception as e:
            logger.error(f"❌ 发布工具注册事件失败: {e}")
    
    async def get_tool_lifecycle(self, request):
        """获取工具生命周期管理信息"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            # 获取所有工具的生命周期信息
            tools = await self.tool_library.get_all_tools()
            lifecycle_info = []
            
            for tool in tools:
                tool_info = {
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "enabled": tool.enabled,
                    "registration_time": getattr(tool, 'registration_time', None),
                    "last_used": getattr(tool, 'last_used', None),
                    "usage_count": getattr(tool, 'usage_count', 0),
                    "success_rate": getattr(tool, 'success_rate', 0.0),
                    "health_status": getattr(tool, 'health_status', True)
                }
                lifecycle_info.append(tool_info)
            
            return web.json_response({
                "status": "success",
                "tools": lifecycle_info,
                "total_count": len(lifecycle_info)
            })
            
        except Exception as e:
            logger.error(f"Error getting tool lifecycle: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    def _create_tool_spec_from_dict(self, tool_spec_data):
        """从字典创建工具规范"""
        from .interfaces import FunctionToolSpec, ToolCapability, ToolType
        
        # 创建工具能力列表
        capabilities_data = tool_spec_data.get("capabilities", [])
        capabilities = []
        
        for cap_data in capabilities_data:
            if isinstance(cap_data, dict):
                capabilities.append(ToolCapability(**cap_data))
        
        # 创建Function Tool规范
        tool_spec = FunctionToolSpec(
            tool_id=tool_spec_data.get("tool_id"),
            name=tool_spec_data.get("name"),
            description=tool_spec_data.get("description"),
            tool_type=ToolType.FUNCTION,
            capabilities=capabilities,
            tags=tool_spec_data.get("tags", []),
            enabled=tool_spec_data.get("enabled", True),
            module_path=tool_spec_data.get("module_path"),
            class_name=tool_spec_data.get("class_name")
        )
        
        return tool_spec

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

    async def get_available_tools_for_llm(self, request):
        """获取LLM可用的工具列表 - Step 1.6 新增API"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            # 获取所有可用工具
            tools = await self.tool_library.get_all_tools()
            
            # 转换为LLM友好的格式
            available_tools = []
            for tool in tools:
                if tool.enabled:  # 只包含启用的工具
                    tool_info = {
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "tool_type": tool.tool_type.value,
                        "capabilities": [
                            {
                                "name": cap.name,
                                "description": cap.description,
                                "parameters": cap.parameters
                            } for cap in tool.capabilities
                        ],
                        "tags": tool.tags,
                        "usage_example": getattr(tool, 'usage_example', None)
                    }
                    
                    # 添加特定类型的额外信息
                    if hasattr(tool, 'endpoint'):
                        tool_info['endpoint'] = tool.endpoint
                    
                    available_tools.append(tool_info)
            
            return web.json_response({
                "status": "success",
                "available_tools": available_tools,
                "total_count": len(available_tools),
                "timestamp": time.time()
            })
            
        except Exception as e:
            logger.error(f"Error getting available tools for LLM: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def request_tool_capability(self, request):
        """请求工具能力 - 一站式搜索安装服务 - Step 1.6 新增API"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            data = await request.json()
            task_description = data.get('task_description', '')
            required_capabilities = data.get('required_capabilities', [])
            current_tools = data.get('current_tools', [])
            auto_install = data.get('auto_install', True)
            security_level = data.get('security_level', 'medium')
            
            if not task_description and not required_capabilities:
                return web.json_response({
                    "status": "error",
                    "message": "task_description or required_capabilities is required"
                }, status=400)
            
            # 获取MCP搜索工具
            mcp_search_tool = getattr(self.tool_library, 'mcp_search_tool', None)
            if not mcp_search_tool:
                return web.json_response({
                    "status": "error",
                    "message": "MCP search tool not available"
                }, status=500)
            
            start_time = time.time()
            
            # 如果启用自动安装，直接搜索和安装
            if auto_install and task_description:
                install_result = await mcp_search_tool.search_and_install_tools(
                    task_description=task_description,
                    current_available_tools=current_tools,
                    reason="API request for tool capability"
                )
                
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                if install_result.success:
                    # 获取更新后的工具列表
                    total_tools = len(await self.tool_library.get_all_tools())
                    
                    return web.json_response({
                        "success": True,
                        "action_taken": "installed_new_tools",
                        "installed_tools": install_result.installed_tools,
                        "total_available_tools": total_tools,
                        "processing_time_ms": processing_time_ms
                    })
                else:
                    return web.json_response({
                        "success": False,
                        "action_taken": "installation_failed",
                        "message": install_result.message,
                        "processing_time_ms": processing_time_ms
                    })
            
            # 如果不自动安装，只分析工具需求
            else:
                analysis_result = await mcp_search_tool.analyze_tool_needs(
                    task_description=task_description,
                    current_available_tools=current_tools
                )
                
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                return web.json_response({
                    "success": True,
                    "action_taken": "analysis_only",
                    "analysis": analysis_result,
                    "processing_time_ms": processing_time_ms
                })
                
        except Exception as e:
            logger.error(f"Error requesting tool capability: {e}")
            return web.json_response({
                "success": False,
                "action_taken": "error",
                "message": str(e)
            }, status=500)
    
    async def analyze_tool_gap(self, request):
        """分析工具缺口 - Step 1.6 新增API"""
        if not self.tool_library:
            return web.json_response({
                "status": "error",
                "message": "Tool library not initialized"
            }, status=500)
        
        try:
            data = await request.json()
            task_description = data.get('task_description', '')
            current_tools = data.get('current_tools', [])
            context = data.get('context', {})
            
            if not task_description:
                return web.json_response({
                    "status": "error",
                    "message": "task_description is required"
                }, status=400)
            
            # 获取工具缺口检测器
            tool_gap_detector = getattr(self.tool_library, 'tool_gap_detector', None)
            if not tool_gap_detector:
                return web.json_response({
                    "status": "error",
                    "message": "Tool gap detector not available"
                }, status=500)
            
            start_time = time.time()
            
            # 执行工具充分性分析
            analysis = await tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_tools
            )
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # 构建响应
            response_data = {
                "has_sufficient_tools": analysis.has_sufficient_tools,
                "gap_analysis": {
                    "missing_capabilities": [req.needed for req in analysis.tool_requirements if req.needed],
                    "confidence_score": analysis.confidence_score if hasattr(analysis, 'confidence_score') else 0.8,
                    "reasoning": analysis.overall_assessment
                },
                "recommendations": [
                    {
                        "capability": req.needed,
                        "priority": "high" if req.confidence_score > 0.8 else "medium",
                        "suggested_keywords": req.suggested_search_keywords
                    } for req in analysis.tool_requirements if req.needed
                ],
                "cache_info": {
                    "cached": False,  # 暂时不实现缓存
                    "cache_age_seconds": 0
                },
                "processing_time_ms": processing_time_ms
            }
            
            return web.json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error analyzing tool gap: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def websocket_tools_events(self, request):
        """WebSocket工具事件流 - Step 4.1 新增端点"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        client_ip = request.remote if request.remote else "unknown"
        logger.info(f"🔌 WebSocket连接建立: {client_ip}")
        
        try:
            # 获取实时注册器
            real_time_registry = getattr(self.tool_library, 'real_time_registry', None)
            if real_time_registry:
                # 将WebSocket连接添加到实时注册器管理
                real_time_registry.websocket_connections.add(ws)
                
                # 发送当前工具列表给新连接的客户端
                try:
                    current_tools = []
                    tools = await self.tool_library.get_all_tools()
                    for tool in tools:
                        if tool.enabled:
                            current_tools.append({
                                "tool_id": tool.tool_id,
                                "name": tool.name,
                                "capabilities": [cap.name for cap in tool.capabilities],
                                "type": tool.tool_type.value,
                                "enabled": tool.enabled
                            })
                    
                    welcome_message = {
                        "type": "welcome",
                        "tools": current_tools,
                        "total_count": len(current_tools),
                        "timestamp": time.time()
                    }
                    
                    await ws.send_str(json.dumps(welcome_message))
                    logger.debug(f"已向客户端 {client_ip} 发送当前工具列表")
                    
                except Exception as e:
                    logger.error(f"发送欢迎消息失败: {e}")
            
            # 处理客户端消息
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_websocket_message(ws, data, client_ip)
                    except json.JSONDecodeError:
                        logger.warning(f"收到无效JSON消息: {msg.data}")
                    except Exception as e:
                        logger.error(f"处理WebSocket消息失败: {e}")
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket错误: {ws.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket连接处理失败: {e}")
            
        finally:
            # 清理连接
            if real_time_registry:
                real_time_registry.websocket_connections.discard(ws)
            logger.info(f"🔌 WebSocket连接断开: {client_ip}")
        
        return ws
    
    async def _handle_websocket_message(self, ws, data: dict, client_ip: str):
        """处理WebSocket客户端消息"""
        message_type = data.get("type")
        
        if message_type == "ping":
            # 响应ping消息
            await ws.send_str(json.dumps({
                "type": "pong", 
                "timestamp": time.time()
            }))
            
        elif message_type == "subscribe":
            # 订阅特定事件
            events = data.get('events', [])
            logger.debug(f"客户端 {client_ip} 订阅事件: {events}")
            
        elif message_type == "get_tools":
            # 请求当前工具列表
            try:
                tools = await self.tool_library.get_all_tools()
                tools_list = []
                for tool in tools:
                    if tool.enabled:
                        tools_list.append({
                            "tool_id": tool.tool_id,
                            "name": tool.name,
                            "capabilities": [cap.name for cap in tool.capabilities],
                            "type": tool.tool_type.value
                        })
                
                response = {
                    "type": "tools_list",
                    "tools": tools_list,
                    "total_count": len(tools_list),
                    "timestamp": time.time()
                }
                
                await ws.send_str(json.dumps(response))
                
            except Exception as e:
                logger.error(f"获取工具列表失败: {e}")
                await ws.send_str(json.dumps({
                    "type": "error",
                    "message": "Failed to get tools list",
                    "timestamp": time.time()
                }))
                
        else:
            logger.warning(f"未知的WebSocket消息类型: {message_type}")

async def start_monitoring_api(tool_library: UnifiedToolLibrary, port: int = 8080):
    """启动监控API的便捷函数"""
    api = ToolScoreMonitoringAPI(tool_library, port)
    return await api.start() 