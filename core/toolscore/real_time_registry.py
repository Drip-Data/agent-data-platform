"""
实时工具注册器
确保MCP服务器注册后立即可用，并通过WebSocket通知所有客户端
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Set, Optional, List
import redis.asyncio as redis
import websockets
from websockets.exceptions import ConnectionClosed

from .interfaces import MCPServerSpec, InstallationResult, RegistrationResult
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

class RealTimeToolRegistry:
    """实时工具注册器 - 确保注册后立即可用"""
    
    def __init__(self, redis_url: str = "redis://redis:6379", tool_library: 'UnifiedToolLibrary' = None):
        self.redis_url = redis_url
        self.redis_client = None
        self.tool_library = tool_library
        
        # WebSocket连接管理
        self.websocket_connections: Set[websockets.WebSocketServerProtocol] = set()
        self.websocket_server = None
        
        # 本地工具缓存
        self.local_tool_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("实时工具注册器初始化完成")
    
    async def initialize(self):
        """初始化实时注册器"""
        try:
            # 初始化Redis连接
            self.redis_client = redis.Redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Redis连接成功")
            
            # 启动WebSocket服务器
            await self._start_websocket_server()
            
            # 加载现有工具到缓存
            await self._load_existing_tools()
            
        except Exception as e:
            logger.error(f"初始化实时注册器失败: {e}")
            raise
    
    async def _start_websocket_server(self):
        """启动WebSocket服务器用于实时通知"""
        try:
            async def handle_websocket(websocket, path):
                await self._handle_websocket_connection(websocket, path)
            
            # 在后台启动WebSocket服务器
            self.websocket_server = await websockets.serve(
                handle_websocket,
                "0.0.0.0",
                8091,
                ping_interval=30,
                ping_timeout=10
            )
            
            logger.info("WebSocket服务器启动成功，端口: 8091")
            
        except Exception as e:
            logger.error(f"启动WebSocket服务器失败: {e}")
            # 继续运行，但禁用WebSocket功能
    
    async def _handle_websocket_connection(self, websocket, path):
        """处理WebSocket连接"""
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        logger.info(f"新的WebSocket连接: {client_ip}")
        
        # 添加到连接集合
        self.websocket_connections.add(websocket)
        
        try:
            # 发送当前工具列表给新连接的客户端
            await self._send_current_tools_to_client(websocket)
            
            # 保持连接活跃
            async for message in websocket:
                try:
                    # 处理客户端消息
                    data = json.loads(message)
                    await self._handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"收到无效JSON消息: {message}")
                except Exception as e:
                    logger.error(f"处理客户端消息失败: {e}")
                    
        except ConnectionClosed:
            logger.info(f"WebSocket连接断开: {client_ip}")
        except Exception as e:
            logger.error(f"WebSocket连接处理失败: {e}")
        finally:
            # 移除连接
            self.websocket_connections.discard(websocket)
    
    async def _send_current_tools_to_client(self, websocket):
        """向新连接的客户端发送当前工具列表"""
        try:
            current_tools = await self._get_formatted_tools_list()
            
            welcome_message = {
                "type": "welcome",
                "tools": current_tools,
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(welcome_message))
            logger.debug("已向新客户端发送当前工具列表")
            
        except Exception as e:
            logger.error(f"发送工具列表给客户端失败: {e}")
    
    async def _handle_client_message(self, websocket, data):
        """处理客户端发送的消息"""
        message_type = data.get("type")
        
        if message_type == "ping":
            # 响应ping消息
            await websocket.send(json.dumps({"type": "pong", "timestamp": time.time()}))
            
        elif message_type == "subscribe":
            # 订阅特定事件
            logger.debug(f"客户端订阅事件: {data.get('events', [])}")
            
        elif message_type == "get_tools":
            # 请求当前工具列表
            await self._send_current_tools_to_client(websocket)
            
        else:
            logger.warning(f"未知的客户端消息类型: {message_type}")
    
    async def _load_existing_tools(self):
        """加载现有工具到本地缓存"""
        if not self.tool_library:
            logger.warning("工具库未初始化，跳过加载现有工具")
            return
        
        try:
            tools = await self.tool_library.get_all_tools()
            for tool in tools:
                self.local_tool_cache[tool.tool_id] = {
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "description": tool.description,
                    "capabilities": [cap.name for cap in tool.capabilities],
                    "type": tool.tool_type.value,
                    "enabled": tool.enabled,
                    "cached_at": time.time()
                }
            
            logger.info(f"加载了 {len(self.local_tool_cache)} 个现有工具到缓存")
            
        except Exception as e:
            logger.error(f"加载现有工具失败: {e}")
    
    async def register_tool_immediately(self, server_spec: MCPServerSpec, install_result: InstallationResult) -> bool:
        """立即注册工具并通知所有客户端"""
        logger.info(f"开始立即注册工具: {server_spec.name}")
        
        try:
            # 1. 立即注册到工具库
            if self.tool_library:
                registration_result = await self.tool_library.register_mcp_server(server_spec)
                
                if not registration_result.success:
                    logger.error(f"工具注册失败: {registration_result.error}")
                    return False
            else:
                logger.warning("工具库未初始化，跳过注册到工具库")
            
            # 2. 立即发布Redis事件
            await self._publish_tool_available_event(server_spec, install_result)
            
            # 3. 立即通过WebSocket通知所有连接的客户端
            await self._notify_clients_immediately(server_spec, install_result)
            
            # 4. 更新本地缓存
            await self._update_local_cache(server_spec)
            
            logger.info(f"工具 {server_spec.tool_id} 立即可用！")
            return True
            
        except Exception as e:
            logger.error(f"立即注册失败: {e}")
            return False
    
    async def _publish_tool_available_event(self, server_spec: MCPServerSpec, install_result: InstallationResult):
        """发布工具可用事件到Redis"""
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，跳过事件发布")
            return
        
        try:
            event_data = {
                "event_type": "tool_available",
                "tool_id": server_spec.tool_id,
                "tool_spec": {
                    "tool_id": server_spec.tool_id,
                    "name": server_spec.name,
                    "description": server_spec.description,
                    "capabilities": [cap.name for cap in server_spec.capabilities],
                    "endpoint": install_result.endpoint,
                    "type": server_spec.tool_type.value,
                    "enabled": server_spec.enabled
                },
                "install_result": {
                    "container_id": install_result.container_id,
                    "port": install_result.port,
                    "endpoint": install_result.endpoint
                },
                "timestamp": time.time(),
                "source": "dynamic_installer"
            }
            
            # 发布到多个频道
            await self.redis_client.publish('tool_events', json.dumps(event_data))
            await self.redis_client.publish('immediate_tool_updates', json.dumps(event_data))
            
            logger.info(f"已发布工具可用事件: {server_spec.tool_id}")
            
        except Exception as e:
            logger.error(f"发布Redis事件失败: {e}")
    
    async def _notify_clients_immediately(self, server_spec: MCPServerSpec, install_result: InstallationResult):
        """立即通过WebSocket通知所有连接的客户端"""
        if not self.websocket_connections:
            logger.debug("没有活跃的WebSocket连接")
            return
        
        notification = {
            "type": "tool_installed",
            "tool_id": server_spec.tool_id,
            "name": server_spec.name,
            "description": server_spec.description,
            "capabilities": [cap.name for cap in server_spec.capabilities],
            "endpoint": install_result.endpoint,
            "container_id": install_result.container_id,
            "port": install_result.port,
            "status": "ready",
            "timestamp": time.time()
        }
        
        # 发送给所有连接的客户端
        disconnected_clients = set()
        successful_notifications = 0
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send(json.dumps(notification))
                successful_notifications += 1
            except ConnectionClosed:
                logger.debug("WebSocket连接已断开")
                disconnected_clients.add(websocket)
            except Exception as e:
                logger.warning(f"通知客户端失败: {e}")
                disconnected_clients.add(websocket)
        
        # 清理断开的连接
        self.websocket_connections -= disconnected_clients
        
        logger.info(f"成功通知 {successful_notifications} 个客户端，清理了 {len(disconnected_clients)} 个断开的连接")
    
    async def _update_local_cache(self, server_spec: MCPServerSpec):
        """更新本地工具缓存"""
        try:
            self.local_tool_cache[server_spec.tool_id] = {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "type": server_spec.tool_type.value,
                "enabled": server_spec.enabled,
                "cached_at": time.time(),
                "source": "dynamic_install"
            }
            
            logger.debug(f"已更新本地缓存: {server_spec.tool_id}")
            
        except Exception as e:
            logger.error(f"更新本地缓存失败: {e}")
    
    async def unregister_tool_immediately(self, tool_id: str) -> bool:
        """立即注销工具并通知客户端"""
        logger.info(f"开始立即注销工具: {tool_id}")
        
        try:
            # 1. 从工具库注销
            if self.tool_library:
                success = await self.tool_library.unregister_tool(tool_id)
                if not success:
                    logger.warning(f"从工具库注销失败: {tool_id}")
            
            # 2. 发布注销事件
            await self._publish_tool_removed_event(tool_id)
            
            # 3. 通知客户端
            await self._notify_clients_tool_removed(tool_id)
            
            # 4. 从本地缓存移除
            if tool_id in self.local_tool_cache:
                del self.local_tool_cache[tool_id]
            
            logger.info(f"工具 {tool_id} 已立即注销")
            return True
            
        except Exception as e:
            logger.error(f"立即注销失败: {e}")
            return False
    
    async def _publish_tool_removed_event(self, tool_id: str):
        """发布工具移除事件"""
        if not self.redis_client:
            return
        
        try:
            event_data = {
                "event_type": "tool_removed",
                "tool_id": tool_id,
                "timestamp": time.time(),
                "source": "dynamic_installer"
            }
            
            await self.redis_client.publish('tool_events', json.dumps(event_data))
            await self.redis_client.publish('immediate_tool_updates', json.dumps(event_data))
            
        except Exception as e:
            logger.error(f"发布工具移除事件失败: {e}")
    
    async def _notify_clients_tool_removed(self, tool_id: str):
        """通知客户端工具已移除"""
        if not self.websocket_connections:
            return
        
        notification = {
            "type": "tool_uninstalled",
            "tool_id": tool_id,
            "timestamp": time.time()
        }
        
        disconnected_clients = set()
        for websocket in self.websocket_connections:
            try:
                await websocket.send(json.dumps(notification))
            except (ConnectionClosed, Exception) as e:
                disconnected_clients.add(websocket)
        
        self.websocket_connections -= disconnected_clients
    
    async def _get_formatted_tools_list(self) -> List[Dict[str, Any]]:
        """获取格式化的工具列表"""
        return list(self.local_tool_cache.values())
    
    async def get_active_connections_count(self) -> int:
        """获取活跃连接数"""
        return len(self.websocket_connections)
    
    async def broadcast_message(self, message: Dict[str, Any]) -> int:
        """广播消息给所有连接的客户端"""
        if not self.websocket_connections:
            return 0
        
        disconnected_clients = set()
        successful_broadcasts = 0
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send(json.dumps(message))
                successful_broadcasts += 1
            except (ConnectionClosed, Exception):
                disconnected_clients.add(websocket)
        
        # 清理断开的连接
        self.websocket_connections -= disconnected_clients
        
        return successful_broadcasts
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册器统计信息"""
        return {
            "active_connections": len(self.websocket_connections),
            "cached_tools": len(self.local_tool_cache),
            "redis_connected": self.redis_client is not None,
            "websocket_server_running": self.websocket_server is not None,
            "tools": list(self.local_tool_cache.keys())
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
            # 关闭所有WebSocket连接
            if self.websocket_connections:
                disconnect_tasks = []
                for websocket in self.websocket_connections:
                    disconnect_tasks.append(websocket.close())
                
                if disconnect_tasks:
                    await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            
            # 关闭WebSocket服务器
            if self.websocket_server:
                self.websocket_server.close()
                await self.websocket_server.wait_closed()
            
            # 关闭Redis连接
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("实时工具注册器清理完成")
            
        except Exception as e:
            logger.error(f"清理实时注册器失败: {e}") 