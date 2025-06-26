"""
🔧 P2: 生产级健康检查模块
提供端口监控、服务恢复和系统指标监控功能
"""

import asyncio
import logging
import time
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class PortStatus:
    """端口状态信息"""
    port: int
    available: bool
    occupying_process: Optional[Dict[str, Any]] = None
    recovery_action: Optional[str] = None
    error: Optional[str] = None

@dataclass
class ServiceHealth:
    """服务健康状态"""
    service: str
    status: str  # healthy, degraded, unhealthy, error
    port_status: Optional[PortStatus] = None
    connectivity: Optional[Dict[str, Any]] = None
    response_time: Optional[float] = None
    last_check: Optional[str] = None
    error: Optional[str] = None

@dataclass
class SystemMetrics:
    """系统指标"""
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    load_average: Optional[List[float]] = None
    error: Optional[str] = None

class HealthMonitor:
    """生产级健康检查和恢复管理器"""
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.port_whitelist = {8003, 8086, 8090, 8080, 8088, 8089, 8091, 8092}  # 豁免端口
        self._health_history: Dict[str, List[ServiceHealth]] = {}
        self._max_history_size = 50
        
        # 验证依赖可用性
        if not PSUTIL_AVAILABLE:
            logger.warning("⚠️ psutil不可用，系统指标功能受限")
        if not AIOHTTP_AVAILABLE:
            logger.warning("⚠️ aiohttp不可用，连通性检查功能受限")
    
    async def check_port_health(self, port: int, auto_recovery: bool = True) -> PortStatus:
        """安全的端口健康检查"""
        result = PortStatus(port=port, available=False)
        
        if not PSUTIL_AVAILABLE:
            result.error = "psutil不可用，无法检查端口状态"
            return result
        
        try:
            # 检查端口占用
            connections = psutil.net_connections()
            for conn in connections:
                if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                    if conn.status == 'LISTEN':
                        try:
                            process = psutil.Process(conn.pid)
                            result.occupying_process = {
                                "pid": conn.pid,
                                "name": process.name(),
                                "cmdline": " ".join(process.cmdline()[:3])  # 只显示前3个参数
                            }
                            
                            # 🛡️ 自动恢复（仅开发环境）
                            if auto_recovery and self.environment == "development":
                                recovery_result = await self._safe_port_recovery(port, conn.pid, process)
                                result.recovery_action = recovery_result
                            elif self.environment == "production":
                                result.recovery_action = "生产环境禁止自动kill进程，请手动处理"
                                
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            result.occupying_process = {
                                "pid": conn.pid, 
                                "name": "unknown", 
                                "accessible": False,
                                "error": str(e)
                            }
                        
                        return result
            
            # 端口空闲
            result.available = True
            return result
            
        except Exception as e:
            result.error = f"端口检查异常: {e}"
            logger.error(f"❌ 端口 {port} 检查失败: {e}")
            return result
    
    async def _safe_port_recovery(self, port: int, pid: int, process: psutil.Process) -> str:
        """安全的端口恢复"""
        try:
            process_name = process.name()
            cmdline = " ".join(process.cmdline())
            
            # 🔍 智能判断是否为同类进程
            safe_keywords = ['python', 'node', 'mcp', 'browser', 'uvicorn', 'fastapi']
            unsafe_keywords = ['system', 'kernel', 'launchd', 'sshd', 'ssh', 'systemd']
            
            # 检查是否为系统关键进程
            if any(keyword in process_name.lower() for keyword in unsafe_keywords):
                return f"🚫 跳过系统进程: {process_name} (PID: {pid})"
            
            # 检查是否为开发相关进程
            if any(keyword in process_name.lower() or keyword in cmdline.lower() 
                   for keyword in safe_keywords):
                
                # 豁免端口检查
                if port in self.port_whitelist:
                    logger.info(f"🛡️ 端口 {port} 在豁免列表中，跳过进程终止")
                    return f"🛡️ 豁免端口 {port}，保留进程 {process_name} (PID: {pid})"
                
                # 先尝试优雅关闭
                try:
                    logger.info(f"🔄 尝试优雅关闭进程: {process_name} (PID: {pid})")
                    process.terminate()  # SIGTERM
                    await asyncio.sleep(3)
                    
                    if process.is_running():
                        logger.warning(f"⚠️ 优雅关闭失败，强制终止: {process_name} (PID: {pid})")
                        process.kill()  # SIGKILL
                        await asyncio.sleep(1)
                    
                    return f"✅ 成功终止进程 {process_name} (PID: {pid})"
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    return f"⚠️ 进程终止失败: {e}"
            else:
                return f"🚫 跳过未知进程: {process_name} (PID: {pid})"
                
        except Exception as e:
            return f"❌ 端口恢复异常: {e}"
    
    async def check_service_health(self, service_name: str, config: Dict[str, Any]) -> ServiceHealth:
        """单个服务健康检查"""
        health = ServiceHealth(
            service=service_name,
            status="unknown",
            last_check=datetime.now().isoformat()
        )
        
        try:
            # 端口检查
            if "port" in config:
                port_result = await self.check_port_health(config["port"], auto_recovery=False)
                health.port_status = port_result
            
            # 连通性检查
            if "health_endpoint" in config and AIOHTTP_AVAILABLE:
                connectivity = await self._check_connectivity(config["health_endpoint"])
                health.connectivity = connectivity
                health.response_time = connectivity.get("response_time")
            
            # 综合状态判断
            port_available = health.port_status.available if health.port_status else True
            connectivity_ok = health.connectivity.get("accessible", True) if health.connectivity else True
            
            if port_available and connectivity_ok:
                health.status = "healthy"
            elif connectivity_ok:
                health.status = "degraded"  # 端口被占用但服务可访问
            else:
                health.status = "unhealthy"
                
        except Exception as e:
            health.status = "error"
            health.error = str(e)
            logger.error(f"❌ 服务 {service_name} 健康检查失败: {e}")
        
        # 记录健康历史
        self._record_health_history(service_name, health)
        
        return health
    
    async def _check_connectivity(self, endpoint: str, timeout: int = 5) -> Dict[str, Any]:
        """检查服务连通性"""
        result = {"accessible": False, "response_time": None, "status_code": None}
        
        if not AIOHTTP_AVAILABLE:
            result["error"] = "aiohttp不可用，无法检查连通性"
            return result
        
        start_time = asyncio.get_event_loop().time()
        try:
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.get(endpoint) as response:
                    result.update({
                        "accessible": True,
                        "response_time": round((asyncio.get_event_loop().time() - start_time) * 1000, 2),
                        "status_code": response.status
                    })
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def comprehensive_health_check(self, services: Dict[str, Dict]) -> Dict[str, Any]:
        """综合健康检查"""
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.environment,
            "overall_status": "healthy",
            "services": {},
            "system_metrics": await self._get_system_metrics(),
            "summary": {
                "total_services": len(services),
                "healthy_services": 0,
                "degraded_services": 0,
                "unhealthy_services": 0,
                "error_services": 0
            }
        }
        
        # 并发检查所有服务
        service_tasks = []
        for service_name, service_config in services.items():
            task = self.check_service_health(service_name, service_config)
            service_tasks.append((service_name, task))
        
        # 等待所有检查完成
        for service_name, task in service_tasks:
            try:
                service_health = await task
                health_report["services"][service_name] = asdict(service_health)
                
                # 更新统计
                if service_health.status == "healthy":
                    health_report["summary"]["healthy_services"] += 1
                elif service_health.status == "degraded":
                    health_report["summary"]["degraded_services"] += 1
                    health_report["overall_status"] = "degraded"
                elif service_health.status == "unhealthy":
                    health_report["summary"]["unhealthy_services"] += 1
                    health_report["overall_status"] = "degraded"
                else:  # error
                    health_report["summary"]["error_services"] += 1
                    health_report["overall_status"] = "degraded"
                    
            except Exception as e:
                logger.error(f"❌ 服务 {service_name} 健康检查异常: {e}")
                health_report["services"][service_name] = {
                    "service": service_name,
                    "status": "error",
                    "error": str(e)
                }
        
        return health_report
    
    async def _get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        metrics = SystemMetrics()
        
        if not PSUTIL_AVAILABLE:
            metrics.error = "psutil不可用，无法获取系统指标"
            return metrics
        
        try:
            metrics.cpu_percent = psutil.cpu_percent(interval=1)
            metrics.memory_percent = psutil.virtual_memory().percent
            metrics.disk_percent = psutil.disk_usage('/').percent
            
            if hasattr(psutil, 'getloadavg'):
                metrics.load_average = list(psutil.getloadavg())
                
        except Exception as e:
            metrics.error = str(e)
            logger.error(f"❌ 系统指标获取失败: {e}")
        
        return metrics
    
    def _record_health_history(self, service_name: str, health: ServiceHealth):
        """记录服务健康历史"""
        if service_name not in self._health_history:
            self._health_history[service_name] = []
        
        self._health_history[service_name].append(health)
        
        # 限制历史记录大小
        if len(self._health_history[service_name]) > self._max_history_size:
            self._health_history[service_name] = self._health_history[service_name][-self._max_history_size:]
    
    def get_health_trend(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """获取服务健康趋势"""
        if service_name not in self._health_history:
            return {"error": f"服务 {service_name} 无健康历史记录"}
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_history = []
            
            for health in self._health_history[service_name]:
                if health.last_check:
                    check_time = datetime.fromisoformat(health.last_check)
                    if check_time >= cutoff_time:
                        recent_history.append(health)
            
            if not recent_history:
                return {"error": f"服务 {service_name} 在过去{hours}小时内无健康记录"}
            
            # 统计状态分布
            status_counts = {}
            response_times = []
            
            for health in recent_history:
                status = health.status
                status_counts[status] = status_counts.get(status, 0) + 1
                
                if health.response_time:
                    response_times.append(health.response_time)
            
            # 计算可用性
            total_checks = len(recent_history)
            healthy_checks = status_counts.get("healthy", 0) + status_counts.get("degraded", 0)
            availability = (healthy_checks / total_checks * 100) if total_checks > 0 else 0
            
            # 计算平均响应时间
            avg_response_time = sum(response_times) / len(response_times) if response_times else None
            
            return {
                "service": service_name,
                "period_hours": hours,
                "total_checks": total_checks,
                "availability_percent": round(availability, 2),
                "avg_response_time_ms": round(avg_response_time, 2) if avg_response_time else None,
                "status_distribution": status_counts,
                "latest_status": recent_history[-1].status if recent_history else None
            }
            
        except Exception as e:
            return {"error": f"健康趋势分析失败: {e}"}
    
    async def auto_recovery_services(self, services: Dict[str, Dict]) -> Dict[str, Any]:
        """自动恢复不健康的服务"""
        recovery_results = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.environment,
            "attempted_recoveries": [],
            "successful_recoveries": [],
            "failed_recoveries": []
        }
        
        # 只在开发环境执行自动恢复
        if self.environment != "development":
            recovery_results["error"] = "生产环境禁用自动恢复功能"
            return recovery_results
        
        # 先进行健康检查
        health_report = await self.comprehensive_health_check(services)
        
        for service_name, service_health in health_report["services"].items():
            if service_health.get("status") in ["unhealthy", "error"]:
                recovery_results["attempted_recoveries"].append(service_name)
                
                try:
                    # 尝试端口恢复
                    if service_name in services and "port" in services[service_name]:
                        port = services[service_name]["port"]
                        port_recovery = await self.check_port_health(port, auto_recovery=True)
                        
                        if port_recovery.recovery_action and "成功" in port_recovery.recovery_action:
                            recovery_results["successful_recoveries"].append({
                                "service": service_name,
                                "action": port_recovery.recovery_action
                            })
                        else:
                            recovery_results["failed_recoveries"].append({
                                "service": service_name,
                                "error": port_recovery.recovery_action or "端口恢复失败"
                            })
                    
                except Exception as e:
                    recovery_results["failed_recoveries"].append({
                        "service": service_name,
                        "error": f"恢复异常: {e}"
                    })
        
        return recovery_results
    
    def export_health_report(self, report: Dict[str, Any], 
                           export_path: Optional[Path] = None) -> Path:
        """导出健康报告到文件"""
        if export_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = Path(f"logs/health_report_{timestamp}.json")
        
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📋 健康报告已导出: {export_path}")
            return export_path
            
        except Exception as e:
            logger.error(f"❌ 健康报告导出失败: {e}")
            raise

# 全局实例
_health_monitor = None

def get_health_monitor(environment: str = "development") -> HealthMonitor:
    """获取全局健康监控实例"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor(environment=environment)
    return _health_monitor