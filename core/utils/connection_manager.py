#!/usr/bin/env python3
"""
连接管理器 - 统一管理所有服务连接和端口配置
提供智能连接池、健康检查、自动重连等功能
"""

import asyncio
import logging
import time
import yaml
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ConnectionConfig:
    """连接配置数据类"""
    host: str = "localhost"
    port: int = 8000
    protocol: str = "http"
    endpoint: str = ""
    health_endpoint: str = "/health"
    auto_start: bool = False
    max_retries: int = 3
    retry_delay: float = 1.0
    connection_timeout: float = 10.0
    health_check_timeout: float = 5.0

@dataclass
class ConnectionStatus:
    """连接状态数据类"""
    service_name: str
    status: str = "disconnected"  # disconnected, connecting, connected, failed
    port: int = 0
    last_check: float = 0
    error_count: int = 0
    last_error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

class ConnectionManager:
    """智能连接管理器"""
    
    def __init__(self, config_file: str = "config/ports_config.yaml"):
        self.config_file = Path(config_file)
        self.connections: Dict[str, ConnectionStatus] = {}
        self.configs: Dict[str, ConnectionConfig] = {}
        
        # 全局配置
        self.global_config = {
            'connection_timeout': 10.0,
            'health_check_timeout': 5.0,
            'max_retries': 3,
            'retry_delay': 1.0,
            'cache_ttl': 300,
            'check_interval': 30
        }
        
        # 连接池和缓存
        self._connection_pool: Dict[str, Any] = {}
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("🔧 ConnectionManager 初始化完成")
    
    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            if not self.config_file.exists():
                logger.warning(f"配置文件不存在: {self.config_file}")
                return False
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 更新全局配置
            connection_settings = config_data.get('connection_settings', {})
            self.global_config.update(connection_settings)
            
            # 加载核心服务配置
            core_services = config_data.get('core_services', {})
            for service_name, service_config in core_services.items():
                self.configs[service_name] = ConnectionConfig(
                    port=service_config.get('port', 8000),
                    health_endpoint=service_config.get('health_endpoint', '/health'),
                    **self._extract_connection_config(service_config)
                )
            
            # 加载MCP服务器配置
            mcp_servers = config_data.get('mcp_servers', {})
            for service_name, service_config in mcp_servers.items():
                protocol = service_config.get('protocol', 'websocket')
                endpoint = service_config.get('endpoint', '/websocket' if protocol == 'websocket' else '')
                
                self.configs[service_name] = ConnectionConfig(
                    port=service_config.get('port', 8080),
                    protocol=protocol,
                    endpoint=endpoint,
                    health_endpoint=service_config.get('health_endpoint', '/health'),
                    auto_start=service_config.get('auto_start', False),
                    **self._extract_connection_config(service_config)
                )
            
            logger.info(f"✅ 成功加载 {len(self.configs)} 个服务配置")
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载配置失败: {e}")
            return False
    
    def _extract_connection_config(self, service_config: Dict[str, Any]) -> Dict[str, Any]:
        """从服务配置中提取连接参数"""
        return {
            'max_retries': service_config.get('max_retries', self.global_config['max_retries']),
            'retry_delay': service_config.get('retry_delay', self.global_config['retry_delay']),
            'connection_timeout': service_config.get('connection_timeout', self.global_config['connection_timeout']),
            'health_check_timeout': service_config.get('health_check_timeout', self.global_config['health_check_timeout'])
        }
    
    async def initialize(self) -> bool:
        """初始化连接管理器"""
        try:
            # 加载配置
            if not self.load_config():
                return False
            
            # 初始化连接状态
            for service_name in self.configs:
                self.connections[service_name] = ConnectionStatus(service_name=service_name)
            
            # 启动健康检查任务
            await self.start_health_monitoring()
            
            logger.info("✅ ConnectionManager 初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ ConnectionManager 初始化失败: {e}")
            return False
    
    async def get_service_connection(self, service_name: str) -> Optional[ConnectionStatus]:
        """获取服务连接状态"""
        if service_name not in self.connections:
            logger.warning(f"⚠️ 未知服务: {service_name}")
            return None
        
        connection = self.connections[service_name]
        
        # 如果连接状态过期，更新检查
        current_time = time.time()
        if current_time - connection.last_check > self.global_config['check_interval']:
            await self._update_connection_status(service_name)
        
        return connection
    
    async def _update_connection_status(self, service_name: str):
        """更新连接状态"""
        if service_name not in self.configs:
            return
        
        config = self.configs[service_name]
        connection = self.connections[service_name]
        
        try:
            # 进行健康检查
            from .port_discovery import PortDiscovery
            discovery = PortDiscovery()
            
            url = f"http://localhost:{config.port}"
            is_healthy = await discovery.check_service_health(url)
            
            if is_healthy:
                connection.status = "connected"
                connection.port = config.port
                connection.error_count = 0
                connection.last_error = ""
            else:
                connection.status = "disconnected"
                connection.error_count += 1
                connection.last_error = f"健康检查失败: {url}"
            
            connection.last_check = time.time()
            
        except Exception as e:
            connection.status = "failed"
            connection.error_count += 1
            connection.last_error = str(e)
            connection.last_check = time.time()
            logger.debug(f"🔄 更新连接状态失败 {service_name}: {e}")
    
    async def start_health_monitoring(self):
        """启动健康监控任务"""
        for service_name in self.configs:
            if service_name not in self._health_check_tasks:
                task = asyncio.create_task(self._health_check_loop(service_name))
                self._health_check_tasks[service_name] = task
                logger.debug(f"🔍 启动健康监控: {service_name}")
    
    async def _health_check_loop(self, service_name: str):
        """健康检查循环"""
        check_interval = self.global_config['check_interval']
        
        while True:
            try:
                await self._update_connection_status(service_name)
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查循环异常 {service_name}: {e}")
                await asyncio.sleep(check_interval)
    
    async def stop_health_monitoring(self):
        """停止健康监控"""
        for service_name, task in self._health_check_tasks.items():
            if not task.cancelled():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.debug(f"🛑 停止健康监控: {service_name}")
        
        self._health_check_tasks.clear()
    
    def get_healthy_services(self) -> List[str]:
        """获取健康的服务列表"""
        healthy_services = []
        for service_name, connection in self.connections.items():
            if connection.status == "connected":
                healthy_services.append(service_name)
        return healthy_services
    
    def get_service_statistics(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        stats = {
            'total_services': len(self.connections),
            'healthy_services': len(self.get_healthy_services()),
            'failed_services': 0,
            'disconnected_services': 0,
            'services': {}
        }
        
        for service_name, connection in self.connections.items():
            if connection.status == "failed":
                stats['failed_services'] += 1
            elif connection.status == "disconnected":
                stats['disconnected_services'] += 1
            
            stats['services'][service_name] = {
                'status': connection.status,
                'port': connection.port,
                'error_count': connection.error_count,
                'last_check': connection.last_check,
                'last_error': connection.last_error
            }
        
        return stats
    
    async def cleanup(self):
        """清理资源"""
        await self.stop_health_monitoring()
        self._connection_pool.clear()
        logger.info("🧹 ConnectionManager 清理完成")

# 全局连接管理器实例
_connection_manager: Optional[ConnectionManager] = None

def get_connection_manager() -> ConnectionManager:
    """获取全局连接管理器实例"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager

async def initialize_connection_manager() -> bool:
    """初始化全局连接管理器"""
    manager = get_connection_manager()
    return await manager.initialize()

async def cleanup_connection_manager():
    """清理全局连接管理器"""
    global _connection_manager
    if _connection_manager:
        await _connection_manager.cleanup()
        _connection_manager = None