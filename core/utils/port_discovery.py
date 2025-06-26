"""
端口发现工具
自动检测服务实际运行的端口，避免硬编码问题
"""

import socket
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, List
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

class PortDiscovery:
    """端口发现和服务健康检查工具 - 增强版本"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "config/ports_config.yaml"
        self.discovered_ports: Dict[str, int] = {}
        # 端口发现缓存，避免重复扫描
        self.port_cache: Dict[str, Dict] = {}
        self.cache_ttl = 300  # 缓存5分钟
        # 连接超时配置
        self.connection_timeout = 3.0
        self.health_check_timeout = 5.0
        
    def load_base_config(self) -> Dict:
        """加载基础端口配置"""
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"配置文件不存在: {config_path}")
                return {}
        except Exception as e:
            logger.error(f"加载端口配置失败: {e}")
            return {}
    
    def check_port_available(self, port: int, host: str = "localhost") -> bool:
        """检查端口是否被占用，增强版本：支持超时配置"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.connection_timeout)
                result = sock.connect_ex((host, port))
                return result == 0  # 0表示连接成功，端口被占用
        except Exception:
            return False
    
    def _is_cache_valid(self, service_name: str) -> bool:
        """检查缓存是否有效"""
        import time
        if service_name not in self.port_cache:
            return False
        
        cache_time = self.port_cache[service_name].get('timestamp', 0)
        return (time.time() - cache_time) < self.cache_ttl
    
    def _update_cache(self, service_name: str, port: int, status: str):
        """更新端口发现缓存"""
        import time
        self.port_cache[service_name] = {
            'port': port,
            'status': status,
            'timestamp': time.time()
        }
    
    async def check_service_health(self, url: str) -> bool:
        """检查服务健康状态，增强版本：支持多端点和智能重试"""
        try:
            timeout = aiohttp.ClientTimeout(total=self.health_check_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 尝试多个健康检查端点
                health_endpoints = ['', '/health', '/ping', '/status']
                
                for endpoint in health_endpoints:
                    check_url = f"{url.rstrip('/')}{endpoint}"
                    try:
                        async with session.get(check_url) as response:
                            if response.status < 400:
                                logger.debug(f"✅ 服务健康检查成功: {check_url}")
                                return True
                    except Exception as e:
                        logger.debug(f"🔄 健康检查端点失败 {check_url}: {e}")
                        continue
                
                return False
        except Exception as e:
            logger.debug(f"❌ 服务健康检查失败 {url}: {e}")
            return False
    
    async def discover_service_port(self, service_name: str, base_port: int, auto_detect_enabled: bool = True) -> Optional[int]:
        """智能服务端口发现，带缓存和多端口扫描"""
        # 检查缓存
        if self._is_cache_valid(service_name):
            cached_info = self.port_cache[service_name]
            if cached_info['status'] == 'healthy':
                logger.debug(f"🎯 使用缓存的端口: {service_name} -> {cached_info['port']}")
                return cached_info['port']
        
        # 首先测试基础端口
        candidate_ports = [base_port]
        
        # 如果启用自动检测，扩展端口范围
        if auto_detect_enabled:
            # 扩展到附近端口范围
            nearby_range = range(max(base_port - 10, 8000), min(base_port + 50, 9000))
            candidate_ports.extend([p for p in nearby_range if p != base_port])
        
        for port in candidate_ports:
            if self.check_port_available(port):
                # 进行健康检查
                health_url = f"http://localhost:{port}"
                if await self.check_service_health(health_url):
                    logger.info(f"✅ 发现健康的服务: {service_name} -> 端口 {port}")
                    self._update_cache(service_name, port, 'healthy')
                    return port
                else:
                    logger.debug(f"🔄 端口 {port} 有服务但健康检查失败")
        
        # 未找到健康的服务
        logger.warning(f"⚠️ 未找到健康的 {service_name} 服务")
        self._update_cache(service_name, base_port, 'not_found')
        return None
    
    async def discover_task_api_port(self) -> Optional[int]:
        """发现Task API的实际端口"""
        config = self.load_base_config()
        
        # 候选端口列表
        candidate_ports = []
        
        # 1. 从配置文件获取基础端口
        task_api_config = config.get('core_services', {}).get('task_api', {})
        base_port = task_api_config.get('port', 8000)
        candidate_ports.append(base_port)
        
        # 2. 如果启用了自动检测，添加动态范围端口
        port_mgmt = config.get('port_management', {})
        if port_mgmt.get('auto_detect', False):
            start_range = port_mgmt.get('port_range_start', 8100)
            end_range = port_mgmt.get('port_range_end', 8200)
            candidate_ports.extend(range(start_range, min(end_range + 1, start_range + 50)))
        
        # 3. 常见的默认端口
        candidate_ports.extend([8100, 8101, 8102, 8103])
        
        # 去重并保持顺序
        candidate_ports = list(dict.fromkeys(candidate_ports))
        
        logger.info(f"检测Task API端口，候选端口: {candidate_ports[:10]}...")
        
        for port in candidate_ports:
            if self.check_port_available(port):
                health_url = f"http://localhost:{port}/health"
                if await self.check_service_health(health_url):
                    logger.info(f"✅ 发现Task API运行在端口: {port}")
                    self.discovered_ports['task_api'] = port
                    return port
        
        logger.warning("❌ 未发现Task API运行端口")
        return None
    
    async def discover_toolscore_ports(self) -> Dict[str, Optional[int]]:
        """发现ToolScore服务的端口"""
        config = self.load_base_config()
        result = {'http': None, 'mcp': None}
        
        # ToolScore HTTP端口
        toolscore_http_config = config.get('mcp_servers', {}).get('toolscore_http', {})
        http_port = toolscore_http_config.get('port', 8088)
        
        if self.check_port_available(http_port):
            health_url = f"http://localhost:{http_port}/health"
            if await self.check_service_health(health_url):
                logger.info(f"✅ 发现ToolScore HTTP API运行在端口: {http_port}")
                result['http'] = http_port
                self.discovered_ports['toolscore_http'] = http_port
        
        # ToolScore MCP端口
        toolscore_mcp_config = config.get('mcp_servers', {}).get('toolscore_mcp', {})
        mcp_port = toolscore_mcp_config.get('port', 8089)
        
        if self.check_port_available(mcp_port):
            logger.info(f"✅ 发现ToolScore MCP运行在端口: {mcp_port}")
            result['mcp'] = mcp_port
            self.discovered_ports['toolscore_mcp'] = mcp_port
        
        return result
    
    async def discover_all_services(self) -> Dict[str, Optional[int]]:
        """发现所有服务的端口"""
        result = {}
        
        # 发现Task API
        task_api_port = await self.discover_task_api_port()
        result['task_api'] = task_api_port
        
        # 发现ToolScore服务
        toolscore_ports = await self.discover_toolscore_ports()
        result.update(toolscore_ports)
        
        return result
    
    def get_discovered_port(self, service_name: str) -> Optional[int]:
        """获取已发现的服务端口"""
        return self.discovered_ports.get(service_name)
    
    def build_service_url(self, service_name: str, path: str = "/") -> Optional[str]:
        """构建服务URL"""
        port = self.get_discovered_port(service_name)
        if port:
            return f"http://localhost:{port}{path}"
        return None


# 全局实例
_port_discovery = None

def get_port_discovery() -> PortDiscovery:
    """获取全局端口发现实例"""
    global _port_discovery
    if _port_discovery is None:
        _port_discovery = PortDiscovery()
    return _port_discovery

async def discover_task_api_url() -> Optional[str]:
    """快速发现Task API URL"""
    discovery = get_port_discovery()
    port = await discovery.discover_task_api_port()
    if port:
        return f"http://localhost:{port}"
    return None