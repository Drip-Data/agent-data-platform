"""
持久化存储管理器
使用Redis作为后端存储，支持MCP服务器配置的持久化
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import asdict
import redis.asyncio as redis

from .interfaces import MCPServerSpec, ToolType

logger = logging.getLogger(__name__)


class PersistentStorage:
    """持久化存储管理器"""
    
    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        
        # Redis键前缀
        self.MCP_SERVERS_KEY = "dynamic_mcp:servers"
        self.INSTALL_RESULTS_KEY = "dynamic_mcp:install_results" 
        self.SERVER_CONFIGS_KEY = "dynamic_mcp:configs"
        self.LAST_UPDATE_KEY = "dynamic_mcp:last_update"
    
    async def initialize(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Persistent storage initialized with Redis")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            raise
    
    async def save_mcp_server(self, server_spec: MCPServerSpec, install_result: Dict[str, Any]):
        """保存MCP服务器配置"""
        try:
            # 将MCPServerSpec转换为可序列化的字典
            server_data = {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "tool_type": server_spec.tool_type.value,
                "capabilities": [
                    {
                        "name": cap.name,
                        "description": cap.description,
                        "parameters": cap.parameters,
                        "examples": cap.examples
                    }
                    for cap in server_spec.capabilities
                ],
                "tags": server_spec.tags,
                "endpoint": server_spec.endpoint,
                "server_config": server_spec.server_config,
                "connection_params": server_spec.connection_params,
                "enabled": server_spec.enabled
            }
            
            # 保存服务器规范
            await self.redis_client.hset(
                self.MCP_SERVERS_KEY,
                server_spec.tool_id,
                json.dumps(server_data)
            )
            
            # 保存安装结果
            await self.redis_client.hset(
                self.INSTALL_RESULTS_KEY,
                server_spec.tool_id,
                json.dumps(install_result)
            )
            
            # 更新最后更新时间
            import time
            await self.redis_client.set(self.LAST_UPDATE_KEY, str(int(time.time())))
            
            logger.info(f"Saved MCP server {server_spec.name} to persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to save MCP server {server_spec.name}: {e}")
            raise
    
    async def load_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """加载所有持久化的MCP服务器"""
        try:
            # 获取所有服务器数据
            servers_data = await self.redis_client.hgetall(self.MCP_SERVERS_KEY)
            install_results_data = await self.redis_client.hgetall(self.INSTALL_RESULTS_KEY)
            
            loaded_servers = []
            
            for tool_id, server_json in servers_data.items():
                tool_id = tool_id.decode() if isinstance(tool_id, bytes) else tool_id
                server_json = server_json.decode() if isinstance(server_json, bytes) else server_json
                
                try:
                    server_data = json.loads(server_json)
                    
                    # 获取对应的安装结果
                    install_result = None
                    if tool_id in install_results_data:
                        install_json = install_results_data[tool_id]
                        install_json = install_json.decode() if isinstance(install_json, bytes) else install_json
                        install_result = json.loads(install_json)
                    
                    loaded_servers.append({
                        "server_data": server_data,
                        "install_result": install_result
                    })
                    
                    logger.debug(f"Loaded MCP server: {server_data['name']}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse server data for {tool_id}: {e}")
                    continue
            
            logger.info(f"Loaded {len(loaded_servers)} MCP servers from persistent storage")
            return loaded_servers
            
        except Exception as e:
            logger.error(f"Failed to load MCP servers from storage: {e}")
            return []
    
    async def remove_mcp_server(self, tool_id: str):
        """从持久化存储中删除MCP服务器"""
        try:
            await self.redis_client.hdel(self.MCP_SERVERS_KEY, tool_id)
            await self.redis_client.hdel(self.INSTALL_RESULTS_KEY, tool_id)
            
            # 更新最后更新时间
            import time
            await self.redis_client.set(self.LAST_UPDATE_KEY, str(int(time.time())))
            
            logger.info(f"Removed MCP server {tool_id} from persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to remove MCP server {tool_id}: {e}")
            raise
    
    async def get_mcp_server(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """获取单个MCP服务器配置"""
        try:
            server_json = await self.redis_client.hget(self.MCP_SERVERS_KEY, tool_id)
            if not server_json:
                return None
            
            server_json = server_json.decode() if isinstance(server_json, bytes) else server_json
            server_data = json.loads(server_json)
            
            # 获取安装结果
            install_result = None
            install_json = await self.redis_client.hget(self.INSTALL_RESULTS_KEY, tool_id)
            if install_json:
                install_json = install_json.decode() if isinstance(install_json, bytes) else install_json
                install_result = json.loads(install_json)
            
            return {
                "server_data": server_data,
                "install_result": install_result
            }
            
        except Exception as e:
            logger.error(f"Failed to get MCP server {tool_id}: {e}")
            return None
    
    async def list_server_ids(self) -> List[str]:
        """获取所有已保存的服务器ID"""
        try:
            keys = await self.redis_client.hkeys(self.MCP_SERVERS_KEY)
            return [key.decode() if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            logger.error(f"Failed to list server IDs: {e}")
            return []
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            server_count = await self.redis_client.hlen(self.MCP_SERVERS_KEY)
            install_count = await self.redis_client.hlen(self.INSTALL_RESULTS_KEY)
            
            last_update = await self.redis_client.get(self.LAST_UPDATE_KEY)
            if last_update:
                last_update = last_update.decode() if isinstance(last_update, bytes) else last_update
            
            return {
                "server_count": server_count,
                "install_count": install_count,
                "last_update": last_update,
                "redis_connected": True
            }
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {
                "server_count": 0,
                "install_count": 0,
                "last_update": None,
                "redis_connected": False,
                "error": str(e)
            }
    
    async def cleanup(self):
        """清理资源"""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("Redis client closed")
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}") 