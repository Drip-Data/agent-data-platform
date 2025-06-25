"""
MCP连接池
提供连接复用和管理功能
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import weakref

from .session_handler import MCPSessionHandler
from ..exceptions import MCPConnectionError


@dataclass
class PooledConnection:
    """池化连接信息"""
    connection_id: str
    handler: MCPSessionHandler
    server_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    use_count: int = 0
    is_busy: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPConnectionPool:
    """MCP连接池"""
    
    def __init__(self, 
                 max_connections_per_server: int = 5,
                 max_idle_time: float = 600.0,  # 10分钟
                 connection_timeout: float = 30.0):
        self.max_connections_per_server = max_connections_per_server
        self.max_idle_time = max_idle_time
        self.connection_timeout = connection_timeout
        
        # 按服务器ID组织的连接池
        self.pools: Dict[str, List[PooledConnection]] = {}
        # 所有连接的索引
        self.connections: Dict[str, PooledConnection] = {}
        # 正在创建的连接
        self.creating_connections: Set[str] = set()
        
        self.logger = logging.getLogger(__name__)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
    async def start(self):
        """启动连接池"""
        self.logger.info("启动MCP连接池")
        self._cleanup_task = asyncio.create_task(self._cleanup_connections())
        
    async def stop(self):
        """停止连接池"""
        self.logger.info("停止MCP连接池")
        
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        # 关闭所有连接
        await self.close_all_connections()
        
    async def get_connection(self, server_id: str, connection_config: Dict[str, Any]) -> PooledConnection:
        """获取连接（优先复用现有连接）"""
        async with self._lock:
            # 查找可用的空闲连接
            if server_id in self.pools:
                for conn in self.pools[server_id]:
                    if not conn.is_busy:
                        conn.is_busy = True
                        conn.last_used = datetime.now()
                        conn.use_count += 1
                        self.logger.debug(f"复用连接: {conn.connection_id}")
                        return conn
                        
            # 检查是否超过最大连接数
            current_count = len(self.pools.get(server_id, []))
            if current_count >= self.max_connections_per_server:
                # 等待有连接可用或超时
                return await self._wait_for_available_connection(server_id)
                
            # 创建新连接
            return await self._create_new_connection(server_id, connection_config)
            
    async def release_connection(self, connection_id: str):
        """释放连接"""
        async with self._lock:
            conn = self.connections.get(connection_id)
            if conn:
                conn.is_busy = False
                conn.last_used = datetime.now()
                self.logger.debug(f"释放连接: {connection_id}")
                
    async def close_connection(self, connection_id: str):
        """关闭指定连接"""
        async with self._lock:
            conn = self.connections.get(connection_id)
            if conn:
                try:
                    await conn.handler.disconnect()
                    self.logger.info(f"关闭连接: {connection_id}")
                except Exception as e:
                    self.logger.error(f"关闭连接失败: {e}")
                finally:
                    # 从池中移除
                    self._remove_connection_from_pool(conn)
                    self.connections.pop(connection_id, None)
                    
    async def close_server_connections(self, server_id: str):
        """关闭指定服务器的所有连接"""
        if server_id in self.pools:
            connections = self.pools[server_id].copy()
            for conn in connections:
                await self.close_connection(conn.connection_id)
                
    async def close_all_connections(self):
        """关闭所有连接"""
        connection_ids = list(self.connections.keys())
        for connection_id in connection_ids:
            await self.close_connection(connection_id)
            
    async def _create_new_connection(self, server_id: str, connection_config: Dict[str, Any]) -> PooledConnection:
        """创建新连接"""
        connection_id = f"pool_{server_id}_{datetime.now().timestamp()}"
        
        # 防止重复创建
        if connection_id in self.creating_connections:
            raise MCPConnectionError(f"连接正在创建中: {connection_id}")
            
        self.creating_connections.add(connection_id)
        
        try:
            handler = MCPSessionHandler()
            
            # 设置超时
            await asyncio.wait_for(
                handler.connect(
                    connection_config.get("uri", f"ws://localhost:8080"),
                    connection_config.get("transport", "websocket")
                ),
                timeout=self.connection_timeout
            )
            
            await handler.initialize()
            
            conn = PooledConnection(
                connection_id=connection_id,
                handler=handler,
                server_id=server_id,
                is_busy=True,  # 创建后立即标记为忙碌
                metadata=connection_config
            )
            
            # 添加到池中
            if server_id not in self.pools:
                self.pools[server_id] = []
            self.pools[server_id].append(conn)
            self.connections[connection_id] = conn
            
            self.logger.info(f"创建新连接: {connection_id} for server: {server_id}")
            return conn
            
        except Exception as e:
            self.logger.error(f"创建连接失败: {e}")
            raise MCPConnectionError(f"连接创建失败: {e}", server_id=server_id)
        finally:
            self.creating_connections.discard(connection_id)
            
    async def _wait_for_available_connection(self, server_id: str) -> PooledConnection:
        """等待有连接可用"""
        max_wait_time = 30.0  # 最大等待30秒
        check_interval = 0.1  # 每100ms检查一次
        waited = 0.0
        
        while waited < max_wait_time:
            # 检查是否有可用连接
            if server_id in self.pools:
                for conn in self.pools[server_id]:
                    if not conn.is_busy:
                        conn.is_busy = True
                        conn.last_used = datetime.now()
                        conn.use_count += 1
                        return conn
                        
            await asyncio.sleep(check_interval)
            waited += check_interval
            
        raise MCPConnectionError(f"等待可用连接超时: {server_id}")
        
    def _remove_connection_from_pool(self, conn: PooledConnection):
        """从池中移除连接"""
        if conn.server_id in self.pools:
            try:
                self.pools[conn.server_id].remove(conn)
                if not self.pools[conn.server_id]:
                    # 如果池为空，删除池
                    del self.pools[conn.server_id]
            except ValueError:
                pass  # 连接不在池中
                
    async def _cleanup_connections(self):
        """定期清理空闲连接"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"连接清理错误: {e}")
                
    async def _cleanup_idle_connections(self):
        """清理空闲超时的连接"""
        async with self._lock:
            now = datetime.now()
            idle_threshold = now - timedelta(seconds=self.max_idle_time)
            
            connections_to_close = []
            
            for conn in self.connections.values():
                if not conn.is_busy and conn.last_used < idle_threshold:
                    connections_to_close.append(conn.connection_id)
                    
            for connection_id in connections_to_close:
                self.logger.info(f"清理空闲连接: {connection_id}")
                await self.close_connection(connection_id)
                
    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        stats = {
            "total_connections": len(self.connections),
            "servers": {},
            "busy_connections": 0,
            "idle_connections": 0
        }
        
        for server_id, connections in self.pools.items():
            server_stats = {
                "total": len(connections),
                "busy": sum(1 for conn in connections if conn.is_busy),
                "idle": sum(1 for conn in connections if not conn.is_busy),
                "average_use_count": sum(conn.use_count for conn in connections) / len(connections) if connections else 0
            }
            stats["servers"][server_id] = server_stats
            stats["busy_connections"] += server_stats["busy"]
            stats["idle_connections"] += server_stats["idle"]
            
        return stats