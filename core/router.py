import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
import redis.asyncio as redis
from .interfaces import TaskSpec, TaskType
from .metrics import EnhancedMetrics

logger = logging.getLogger(__name__)

class IntelligentRouter:
    """智能任务路由器"""
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.metrics = EnhancedMetrics()
          # 运行时能力映射 - 已简化为unified reasoning runtime
        # 注意：sandbox和web_navigator功能已迁移到MCP服务器
        self.runtime_capabilities = {
            "reasoning": ["text_analysis", "logical_reasoning", "planning", "python_executor", "browser_automation", "web_scraping", "form_filling", "file_operations"]
        }
        
        # 队列映射 - 所有任务类型现在都路由到reasoning队列
        # enhanced-reasoning-runtime会通过toolscore调用相应的MCP服务器
        self.queue_mapping = {
            TaskType.CODE: "tasks:reasoning",  # 通过python-executor-server处理
            TaskType.WEB: "tasks:reasoning",   # 通过browser-navigator-server处理
            TaskType.REASONING: "tasks:reasoning"
        }
    
    async def route_task(self, task: TaskSpec) -> str:
        """智能路由任务到最佳运行时"""
        # 基于任务类型的基础路由
        base_queue = self.queue_mapping.get(task.task_type)
        if not base_queue:
            raise ValueError(f"Unknown task type: {task.task_type}")
        
        # 检查运行时健康状态
        runtime_name = base_queue.split(":")[1]
        is_healthy = await self._check_runtime_health(runtime_name)
        
        if not is_healthy:
            logger.warning(f"Runtime {runtime_name} is unhealthy, using fallback")
            # 可以实现降级逻辑
        
        # 检查队列负载
        queue_load = await self._get_queue_load(base_queue)
        if queue_load > 100:  # 队列过载阈值
            logger.warning(f"Queue {base_queue} is overloaded ({queue_load} tasks)")
        
        return base_queue
    
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
        """获取所有运行时统计信息"""
        stats = {}
        
        for runtime_name in self.runtime_capabilities.keys():
            queue_name = f"tasks:{runtime_name}"
            
            stats[runtime_name] = {
                "healthy": await self._check_runtime_health(runtime_name),
                "queue_size": await self._get_queue_load(queue_name),
                "capabilities": self.runtime_capabilities[runtime_name]
            }
        
        return stats