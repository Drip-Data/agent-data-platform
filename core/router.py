"""
系统监控器 - 专注于系统健康监控
原 IntelligentRouter 已简化为监控组件，路由功能由 EnhancedTaskDispatcher 统一处理
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
import redis.asyncio as redis
from .interfaces import TaskSpec, TaskType
from .metrics import EnhancedMetrics
from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SystemMonitor:
    """系统健康监控器 - 简化版，专注监控功能"""
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.metrics = EnhancedMetrics()
        
        try:
            self.config_manager = ConfigManager()
            routing_config = self.config_manager.get_routing_config()
            
            # 从配置获取运行时能力
            self.runtime_capabilities = {}
            for runtime_name, runtime_config in routing_config['runtimes'].items():
                self.runtime_capabilities[runtime_name] = runtime_config['capabilities']
            
            # 从配置获取队列映射
            self.queue_mapping = routing_config['queue_mapping']['task_type_mapping']
            
            logger.info("✅ SystemMonitor 配置加载完成")
            
        except Exception as e:
            logger.warning(f"SystemMonitor 配置加载失败，使用默认配置: {e}")
            self.runtime_capabilities = {
                "enhanced-reasoning": ["text_analysis", "logical_reasoning", "planning", 
                                     "python_executor", "browser_automation"]
            }
            self.queue_mapping = {
                "CODE": "tasks:reasoning",
                "WEB": "tasks:reasoning",
                "REASONING": "tasks:reasoning"
            }
      async def get_system_health(self) -> Dict[str, Any]:
        """获取系统整体健康状态 - 主要监控功能"""
        health_status = {}
        
        try:
            # 检查Redis连接
            health_status["redis"] = {
                "healthy": await self._check_redis_health(),
                "timestamp": time.time()
            }
            
            # 检查所有运行时健康状态
            health_status["runtimes"] = {}
            for runtime_name in self.runtime_capabilities.keys():
                health_status["runtimes"][runtime_name] = {
                    "healthy": await self._check_runtime_health(runtime_name),
                    "capabilities": self.runtime_capabilities[runtime_name]
                }
            
            # 检查队列状态
            health_status["queues"] = {}
            for queue_name in set(self.queue_mapping.values()):
                health_status["queues"][queue_name] = {
                    "length": await self._get_queue_load(queue_name),
                    "healthy": await self._get_queue_load(queue_name) < 1000  # 健康阈值
                }
            
            # 整体健康评估
            all_healthy = all([
                health_status["redis"]["healthy"],
                all(rt["healthy"] for rt in health_status["runtimes"].values()),
                all(q["healthy"] for q in health_status["queues"].values())
            ])
            
            health_status["overall"] = {
                "healthy": all_healthy,
                "status": "healthy" if all_healthy else "degraded",
                "timestamp": time.time()
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {
                "overall": {
                    "healthy": False, 
                    "status": "error",
                    "error": str(e),
                    "timestamp": time.time()
                }
            }
    
    async def _check_redis_health(self) -> bool:
        """检查Redis健康状态"""
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis健康检查失败: {e}")
            return False
    
    async def _check_runtime_health(self, runtime_name: str) -> bool:
        """检查运行时健康状态"""
        try:
            health_key = f"health:{runtime_name}"
            health_data = await self.redis.get(health_key)
            
            if not health_data:
                return False
            
            health_info = json.loads(health_data.decode())
            last_heartbeat = health_info.get("timestamp", 0)
            
            # 如果超过60秒没有心跳，认为不健康
            return (time.time() - last_heartbeat) < 60
            
        except Exception as e:
            logger.error(f"Error checking health for {runtime_name}: {e}")
            return False
    
    async def _get_queue_load(self, queue_name: str) -> int:
        """获取队列当前负载"""
        try:
            return await self.redis.xlen(queue_name)
        except Exception as e:
            logger.error(f"Error getting queue load for {queue_name}: {e}")
            return 0
      async def get_runtime_stats(self) -> Dict[str, Dict]:
        """获取所有运行时统计信息 - 增强版"""
        stats = {}
        
        for runtime_name in self.runtime_capabilities.keys():
            try:
                # 构建队列名（如果有对应队列）
                queue_name = None
                for task_type, queue in self.queue_mapping.items():
                    if runtime_name in queue or "reasoning" in queue:
                        queue_name = queue
                        break
                
                stats[runtime_name] = {
                    "healthy": await self._check_runtime_health(runtime_name),
                    "queue_name": queue_name,
                    "queue_size": await self._get_queue_load(queue_name) if queue_name else 0,
                    "capabilities": self.runtime_capabilities[runtime_name],
                    "last_check": time.time()
                }
                
            except Exception as e:
                logger.error(f"获取运行时 {runtime_name} 统计失败: {e}")
                stats[runtime_name] = {
                    "healthy": False,
                    "error": str(e),
                    "last_check": time.time()
                }
        
        return stats

# 保持向后兼容性的别名
IntelligentRouter = SystemMonitor