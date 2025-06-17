import asyncio
import logging
import time
import redis.asyncio as redis
from typing import Dict, Any, Set

from core.metrics import EnhancedMetrics
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class QueueMonitor:
    """队列和挂起任务监控器"""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.metrics = EnhancedMetrics()
        self.config_manager = ConfigManager()
        
        try:
            routing_config = self.config_manager.load_routing_config()
            self.queue_mapping = routing_config.task_type_mapping
            logger.info("✅ QueueMonitor 配置加载完成")
        except Exception as e:
            logger.warning(f"QueueMonitor 配置加载失败，使用默认配置: {e}")
            self.queue_mapping = {
                "CODE": "tasks:reasoning",
                "WEB": "tasks:reasoning",
                "REASONING": "tasks:reasoning"
            }

    async def _monitor_queues(self):
        """监控队列状态"""
        while True:
            try:
                for task_type_str, queue_name in self.queue_mapping.items():
                    # 获取队列长度
                    queue_length = await self.redis.xlen(queue_name)
                    self.metrics.update_queue_size(queue_name, queue_length)
                
                await asyncio.sleep(30)  # 每30秒更新
                
            except Exception as e:
                logger.error(f"监控队列时出错: {e}")
                await asyncio.sleep(10)

    async def _monitor_pending_tasks(self):
        """监控挂起任务延迟"""
        while True:
            try:
                for task_type_str, queue_name in self.queue_mapping.items():
                    runtime = queue_name.split(":")[1]
                    
                    # 检查挂起任务
                    try:
                        pending_info = await self.redis.xpending_range(
                            queue_name, "workers", count=100
                        )
                        
                        if pending_info:
                            # 计算最大延迟
                            current_time = time.time() * 1000  # Redis使用毫秒时间戳
                            max_lag = 0
                            
                            for entry in pending_info:
                                idle_time = current_time - entry['time_since_delivered']
                                max_lag = max(max_lag, idle_time / 1000)  # 转换为秒
                            
                            self.metrics.pending_lag_seconds.labels(runtime=runtime).set(max_lag)
                    except Exception:
                        # 如果consumer group不存在，忽略错误
                        pass
                
                await asyncio.sleep(60)  # 每分钟检查
                
            except Exception as e:
                logger.error(f"监控挂起任务时出错: {e}")
                await asyncio.sleep(30)

    async def start(self):
        """启动队列监控器"""
        logger.info("启动队列监控器...")
        await asyncio.gather(
            self._monitor_queues(),
            self._monitor_pending_tasks()
        )