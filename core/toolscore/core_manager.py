"""
ToolScore 核心管理器 - 合并版本
整合所有分散的管理功能到单一文件中
"""

import asyncio
import json
import logging
import time
import docker
import redis.asyncio as redis
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import websockets

from .interfaces import ToolSpec, MCPServerSpec, ToolCapability, ToolType, RegistrationResult

logger = logging.getLogger(__name__)

class CoreManager:
    """
    ToolScore核心管理器 - 整合版本
    
    整合功能：
    - MCP容器和镜像管理 (原persistent_container_manager + mcp_image_manager)
    - 实时注册和缓存 (原real_time_registry + mcp_cache_manager)  
    - 自动注册预置服务器 (原auto_register)
    - 工具注册表管理 (原tool_registry)
    - 简化的持久化存储 (原persistent_storage)
    """
    
    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.docker_client = docker.from_env()
        
        # 内存缓存
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        
        # WebSocket连接管理
        self.websocket_connections: Set = set()
        
        # 预置MCP服务器配置
        self.predefined_servers = [
            {
                "tool_id": "python-executor-server",
                "name": "Python Executor",
                "description": "Execute Python code and scripts with full programming capabilities",
                "endpoint": "ws://python-executor-server:8081/mcp",
                "capabilities": [
                    {
                        "name": "python_execute",
                        "description": "Execute Python code and return results",
                        "parameters": {
                            "code": {"type": "string", "description": "Python code to execute", "required": True}
                        }
                    }
                ],
                "tags": ["python", "code", "execution", "programming"]
            },
            {
                "tool_id": "browser-navigator-server", 
                "name": "Browser Navigator",
                "description": "Navigate web pages, extract content, and perform browser automation",
                "endpoint": "ws://browser-navigator-server:8082/mcp",
                "capabilities": [
                    {
                        "name": "navigate_to_url",
                        "description": "Navigate to a specific URL",
                        "parameters": {
                            "url": {"type": "string", "description": "URL to navigate to", "required": True}
                        }
                    }
                ],
                "tags": ["browser", "web", "navigation", "automation"]
            }
        ]
        
        logger.info("✅ 核心管理器初始化完成")
    
    async def initialize(self):
        """初始化核心管理器"""
        try:
            # 连接Redis
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            
            # 恢复容器
            await self._recover_all_containers()
            
            # 自动注册预置服务器
            await self._auto_register_predefined_servers()
            
            logger.info("✅ 核心管理器启动成功")
            
        except Exception as e:
            logger.error(f"❌ 核心管理器初始化失败: {e}")
            raise
    
    # === 容器管理功能 (合并 persistent_container_manager + mcp_image_manager) ===
    
    async def _recover_all_containers(self):
        """恢复所有MCP容器"""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": "mcp.auto-recover=true"}
            )
            
            recovered_count = 0
            for container in containers:
                try:
                    if container.status != 'running':
                        container.start()
                        logger.info(f"恢复容器: {container.name}")
                        recovered_count += 1
                        
                except Exception as e:
                    logger.error(f"恢复容器失败 {container.name}: {e}")
            
            logger.info(f"恢复了 {recovered_count} 个MCP容器")
            return recovered_count
            
        except Exception as e:
            logger.error(f"容器恢复失败: {e}")
            return 0
    
    async def create_persistent_container(self, image_id: str, server_spec: MCPServerSpec, port: int) -> str:
        """创建持久化容器"""
        container_name = f"mcp-{server_spec.tool_id}"
        
        container_config = {
            "image": image_id,
            "name": container_name,
            "ports": {f"{port}/tcp": port},
            "environment": {
                "MCP_SERVER_PORT": str(port),
            },
            "restart_policy": {"Name": "unless-stopped"},
            "network_mode": "agent-data-platform_agent_network",
            "labels": {
                "mcp.server.id": server_spec.tool_id,
                "mcp.server.name": server_spec.name,
                "mcp.manager": "toolscore",
                "mcp.auto-recover": "true"
            }
        }
        
        try:
            container = self.docker_client.containers.run(detach=True, **container_config)
            logger.info(f"创建持久化容器: {container.name}")
            return container.id
            
        except Exception as e:
            logger.error(f"创建容器失败: {e}")
            raise
    
    # === 实时注册和缓存功能 (合并 real_time_registry + mcp_cache_manager) ===
    
    async def register_tool_immediately(self, server_spec: MCPServerSpec):
        """立即注册工具并通知所有客户端"""
        try:
            # 更新本地缓存
            async with self._cache_lock:
                self._tool_cache[server_spec.tool_id] = {
                    "tool_id": server_spec.tool_id,
                    "name": server_spec.name,
                    "description": server_spec.description,
                    "capabilities": [cap.name for cap in server_spec.capabilities],
                    "endpoint": server_spec.endpoint
                }
            
            # 发布Redis事件
            await self._publish_tool_event("tool_available", server_spec)
            
            # WebSocket通知
            await self._notify_websocket_clients({
                "type": "tool_installed",
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "status": "ready"
            })
            
            logger.info(f"工具立即可用: {server_spec.tool_id}")
            return True
            
        except Exception as e:
            logger.error(f"立即注册失败: {e}")
            return False
    
    async def _publish_tool_event(self, event_type: str, server_spec: MCPServerSpec):
        """发布工具事件到Redis"""
        if not self.redis_client:
            return
            
        event_data = {
            "event_type": event_type,
            "tool_id": server_spec.tool_id,
            "tool_spec": {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "endpoint": server_spec.endpoint
            },
            "timestamp": time.time()
        }
        
        await self.redis_client.publish('tool_events', json.dumps(event_data))
        await self.redis_client.publish('immediate_tool_updates', json.dumps(event_data))
    
    async def _notify_websocket_clients(self, notification: dict):
        """WebSocket通知所有客户端"""
        if not self.websocket_connections:
            return
            
        disconnected_clients = set()
        for websocket in self.websocket_connections:
            try:
                await websocket.send(json.dumps(notification))
            except Exception as e:
                logger.warning(f"WebSocket通知失败: {e}")
                disconnected_clients.add(websocket)
        
        # 清理断开的连接
        self.websocket_connections -= disconnected_clients
    
    async def add_websocket_connection(self, websocket):
        """添加WebSocket连接"""
        self.websocket_connections.add(websocket)
        logger.debug(f"WebSocket连接已添加，当前连接数: {len(self.websocket_connections)}")
    
    async def remove_websocket_connection(self, websocket):
        """移除WebSocket连接"""
        self.websocket_connections.discard(websocket)
        logger.debug(f"WebSocket连接已移除，当前连接数: {len(self.websocket_connections)}")
    
    # === 缓存管理功能 ===
    
    async def cache_search_result(self, cache_key: str, data: any, ttl: int = 3600):
        """缓存搜索结果"""
        if self.redis_client:
            await self.redis_client.setex(cache_key, ttl, json.dumps(data))
    
    async def get_cached_result(self, cache_key: str) -> Optional[any]:
        """获取缓存结果"""
        if not self.redis_client:
            return None
            
        try:
            cached_data = await self.redis_client.get(cache_key)
            return json.loads(cached_data) if cached_data else None
        except:
            return None
    
    # === 自动注册功能 (合并 auto_register) ===
    
    async def _auto_register_predefined_servers(self) -> Dict[str, Any]:
        """自动注册所有预置的MCP服务器"""
        logger.info("🔄 开始自动注册预置MCP服务器...")
        
        registration_results = {
            "success_count": 0,
            "failed_count": 0,
            "results": []
        }
        
        for server_config in self.predefined_servers:
            try:
                # 检查服务器是否可达
                is_available = await self._check_server_availability(server_config["endpoint"])
                
                if is_available:
                    # 创建服务器规范
                    server_spec = await self._create_server_spec_from_config(server_config)
                    
                    # 注册服务器
                    success = await self.register_tool_immediately(server_spec)
                    
                    if success:
                        registration_results["success_count"] += 1
                        logger.info(f"✅ 成功注册: {server_config['name']}")
                    else:
                        registration_results["failed_count"] += 1
                        
                else:
                    registration_results["failed_count"] += 1
                    logger.warning(f"⚠️ 服务器不可达: {server_config['name']}")
                    
            except Exception as e:
                registration_results["failed_count"] += 1
                logger.error(f"❌ 注册异常: {server_config['name']} - {e}")
        
        logger.info(f"🎯 自动注册完成: {registration_results['success_count']} 成功, {registration_results['failed_count']} 失败")
        return registration_results
    
    async def _check_server_availability(self, endpoint: str, timeout: float = 5.0) -> bool:
        """检查MCP服务器是否可达"""
        try:
            async with websockets.connect(endpoint, timeout=timeout) as websocket:
                ping_message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
                await websocket.send(json.dumps(ping_message))
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    return True
                except asyncio.TimeoutError:
                    return True  # 连接成功但无响应也算可达
                    
        except Exception as e:
            logger.debug(f"服务器 {endpoint} 不可达: {e}")
            return False
    
    async def _create_server_spec_from_config(self, server_config: Dict[str, Any]) -> MCPServerSpec:
        """从配置创建服务器规范"""
        capabilities = []
        for cap_config in server_config["capabilities"]:
            capability = ToolCapability(
                name=cap_config["name"],
                description=cap_config["description"],
                parameters=cap_config["parameters"]
            )
            capabilities.append(capability)
        
        return MCPServerSpec(
            tool_id=server_config["tool_id"],
            name=server_config["name"],
            description=server_config["description"],
            tool_type=ToolType.MCP_SERVER,
            capabilities=capabilities,
            tags=server_config["tags"],
            enabled=True,
            endpoint=server_config["endpoint"]
        )
    
    # === 持久化存储功能 (简化版) ===
    
    async def save_mcp_server(self, server_spec: MCPServerSpec, install_result: dict):
        """保存MCP服务器到持久化存储"""
        if not self.redis_client:
            return
            
        server_data = {
            "server_data": {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "endpoint": server_spec.endpoint,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "tags": server_spec.tags
            },
            "install_result": install_result,
            "saved_at": time.time()
        }
        
        await self.redis_client.hset("mcp_servers", server_spec.tool_id, json.dumps(server_data))
        logger.info(f"保存MCP服务器: {server_spec.tool_id}")
    
    async def load_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """加载所有持久化的MCP服务器"""
        if not self.redis_client:
            return []
            
        try:
            servers_data = await self.redis_client.hgetall("mcp_servers")
            return [json.loads(data) for data in servers_data.values()]
        except Exception as e:
            logger.error(f"加载MCP服务器失败: {e}")
            return []
    
    # === 清理功能 ===
    
    async def cleanup(self):
        """清理资源"""
        # 关闭所有WebSocket连接
        for websocket in list(self.websocket_connections):
            try:
                await websocket.close()
            except:
                pass
        self.websocket_connections.clear()
        
        # 关闭Redis连接
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("核心管理器资源已清理")
    
    async def check_cached_image(self, image_name: str) -> bool:
        """检查镜像是否已经缓存
        
        Args:
            image_name: 镜像名称
            
        Returns:
            bool: 如果镜像已缓存返回True，否则返回False
        """
        try:
            images = self.docker_client.images.list(name=image_name)
            return len(images) > 0
        except Exception as e:
            logger.error(f"检查镜像缓存失败: {e}")
            return False 