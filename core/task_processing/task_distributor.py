import logging
import time
import json
import redis.asyncio as async_redis
from typing import Dict
from core.interfaces import TaskSpec, TaskType
from core.metrics import EnhancedMetrics # 导入 EnhancedMetrics

logger = logging.getLogger(__name__)

class TaskDistributor:
    """
    任务分发器，负责将增强后的任务分发到 Redis 队列。
    """
    def __init__(self, redis_url: str, metrics: EnhancedMetrics): # 注入 metrics
        self.redis = async_redis.from_url(redis_url)
        self.metrics = metrics # 保存 metrics 实例

    async def distribute_task(self, task: TaskSpec, queue_name: str):
        """将任务分发到对应的 Redis 队列"""
        if queue_name:
            await self.redis.xadd(
                queue_name,
                {
                    "task": task.json(),
                    "submitted_at": str(time.time()),
                    "priority": str(task.priority),
                    "enhanced_with_tools": "true"  # 标记已进行工具增强，转换为字符串
                }
            )
            logger.info(f"分发增强任务 {task.task_id} 到 {queue_name}")
            
            # 记录任务提交 Metrics
            # 将 queue_name 作为 runtime 标签，因为它是任务实际分发到的“运行时环境”
            self.metrics.record_task_submitted(task_type=task.task_type.value, runtime=queue_name)
            
            # 记录工具推荐统计
            tool_metadata = task.constraints.get("tool_metadata", {})
            logger.debug(f"工具推荐日志: {json.dumps({
                'task_id': task.task_id,
                'recommended_tools': task.expected_tools,
                'confidence': tool_metadata.get('recommendation_confidence', 0.0),
                'strategy': tool_metadata.get('recommendation_strategy', 'unknown')
            })}")
        else:
            logger.error(f"未找到队列名称，任务 {task.task_id} 未分发。")