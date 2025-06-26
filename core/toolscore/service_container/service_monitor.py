"""
服务监控器
提供实时的服务健康监控和自动故障恢复
"""

import asyncio
import logging
import aiohttp
import websockets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .models import ServiceStatus, ServiceHealth

if TYPE_CHECKING:
    from .mcp_service_container import MCPServiceContainer

logger = logging.getLogger(__name__)


class ServiceMonitor:
    """服务监控器"""
    
    def __init__(self, container: 'MCPServiceContainer'):
        self.container = container
        self.is_monitoring = False
        self.monitor_task = None
        self.check_interval = 30  # 30秒检查一次
        
    async def start_monitoring(self) -> None:
        """开始监控"""
        if self.is_monitoring:
            logger.debug("⏭️ 服务监控已启动")
            return
        
        logger.info("🔍 启动服务监控...")
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self) -> None:
        """停止监控"""
        if not self.is_monitoring:
            return
        
        logger.info("🛑 停止服务监控...")
        self.is_monitoring = False
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitoring_loop(self) -> None:
        """监控循环"""
        logger.info(f"🔄 开始服务监控循环，检查间隔: {self.check_interval}秒")
        
        while self.is_monitoring:
            try:
                await self._check_all_services()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 监控循环异常: {e}")
                await asyncio.sleep(5)  # 短暂等待后继续
    
    async def _check_all_services(self) -> None:
        """检查所有服务"""
        running_services = [
            (service_id, config) 
            for service_id, config in self.container.service_catalog.items()
            if config.status == ServiceStatus.RUNNING
        ]
        
        if not running_services:
            return
        
        logger.debug(f"🔍 检查 {len(running_services)} 个运行中的服务...")
        
        # 并发检查所有服务
        check_tasks = [
            self._check_single_service(service_id, config)
            for service_id, config in running_services
        ]
        
        await asyncio.gather(*check_tasks, return_exceptions=True)
    
    async def _check_single_service(self, service_id: str, config) -> None:
        """检查单个服务"""
        try:
            start_time = datetime.now()
            
            # 根据协议选择检查方式
            if config.protocol == "websocket":
                is_healthy = await self._check_websocket_service(config)
            elif config.protocol == "http":
                is_healthy = await self._check_http_service(config)
            else:
                is_healthy = await self._check_generic_service(config)
            
            # 计算响应时间
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # 更新健康状态
            self._update_health_status(config, is_healthy, response_time)
            
            # 如果服务不健康，尝试恢复
            if not is_healthy:
                await self._handle_unhealthy_service(service_id, config)
            
        except Exception as e:
            logger.error(f"❌ 检查服务失败 {service_id}: {e}")
            self._update_health_status(config, False, None, str(e))
    
    async def _check_websocket_service(self, config) -> bool:
        """检查WebSocket服务"""
        try:
            endpoint = config.actual_endpoint or config.endpoint
            if not endpoint:
                return False
            
            # 对于内置服务，先检查进程是否存在
            if config.service_type.value == "builtin" and config.process_id:
                try:
                    import psutil
                    if not psutil.pid_exists(config.process_id):
                        logger.warning(f"内置服务进程不存在: {config.name} (PID: {config.process_id})")
                        return False  # 进程不存在则不健康
                except ImportError:
                    pass
            
            # WebSocket连接检查（简化版）
            async with websockets.connect(endpoint, timeout=3) as websocket:
                return True  # 能连接就认为健康，不发送ping消息
                    
        except Exception:
            # 对于内置服务，检查进程是否存在
            if config.service_type.value == "builtin" and config.process_id:
                try:
                    import psutil
                    return psutil.pid_exists(config.process_id)
                except ImportError:
                    return False
            return False
    
    async def _check_http_service(self, config) -> bool:
        """检查HTTP服务"""
        try:
            endpoint = config.actual_endpoint or config.endpoint
            if not endpoint:
                return False
            
            # 构建健康检查URL
            if "/health" not in endpoint:
                health_url = f"{endpoint.rstrip('/')}/health"
            else:
                health_url = endpoint
            
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
                    
        except Exception:
            return False
    
    async def _check_generic_service(self, config) -> bool:
        """通用服务检查"""
        try:
            # 检查进程是否存在
            if config.process_id:
                import psutil
                return psutil.pid_exists(config.process_id)
            
            # 检查容器是否运行
            if config.container_id:
                import subprocess
                result = subprocess.run(
                    ["docker", "ps", "-q", "-f", f"id={config.container_id}"],
                    capture_output=True, text=True, timeout=5
                )
                return bool(result.stdout.strip())
            
            return False
            
        except Exception:
            return False
    
    def _update_health_status(self, config, is_healthy: bool, response_time_ms: float = None, error_message: str = None) -> None:
        """更新健康状态"""
        health = config.health
        health.last_check = datetime.now()
        health.check_count += 1
        health.response_time_ms = int(response_time_ms) if response_time_ms else None
        
        if is_healthy:
            health.is_healthy = True
            health.consecutive_failures = 0
            health.error_message = None
        else:
            health.is_healthy = False
            health.consecutive_failures += 1
            health.error_message = error_message
        
        # 记录状态变化
        if is_healthy:
            logger.debug(f"✅ 服务健康: {config.name} ({response_time_ms:.0f}ms)")
        else:
            logger.warning(f"⚠️ 服务不健康: {config.name} (失败次数: {health.consecutive_failures})")
    
    async def _handle_unhealthy_service(self, service_id: str, config) -> None:
        """处理不健康的服务"""
        # 如果连续失败次数超过阈值，尝试重启
        if config.health.consecutive_failures >= 3 and config.auto_restart:
            logger.warning(f"🔄 尝试重启不健康的服务: {config.name}")
            
            try:
                success = await self.container.restart_service(service_id)
                if success:
                    logger.info(f"✅ 服务重启成功: {config.name}")
                else:
                    logger.error(f"❌ 服务重启失败: {config.name}")
                    config.status = ServiceStatus.ERROR
            except Exception as e:
                logger.error(f"❌ 重启服务异常: {e}")
                config.status = ServiceStatus.ERROR
    
    def get_monitoring_statistics(self) -> dict:
        """获取监控统计信息"""
        total_services = len(self.container.service_catalog)
        healthy_services = len([
            c for c in self.container.service_catalog.values()
            if c.health.is_healthy
        ])
        
        avg_response_time = 0
        response_times = [
            c.health.response_time_ms 
            for c in self.container.service_catalog.values()
            if c.health.response_time_ms is not None
        ]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
        
        return {
            "monitoring_active": self.is_monitoring,
            "check_interval": self.check_interval,
            "total_services": total_services,
            "healthy_services": healthy_services,
            "unhealthy_services": total_services - healthy_services,
            "health_percentage": (healthy_services / total_services * 100) if total_services > 0 else 0,
            "average_response_time_ms": round(avg_response_time, 2),
            "last_check": datetime.now().isoformat()
        }