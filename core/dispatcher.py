import asyncio
import json
import logging
import os
import time
from typing import Dict, Set
import redis.asyncio as redis
from .interfaces import TaskSpec, TaskType
from .cache import TemplateCache
from .metrics import EnhancedMetrics

logger = logging.getLogger(__name__)

class TaskDispatcher:
    """优化后的任务分发器 - 支持分流和缓存"""
    
    def __init__(self, redis_url: str, task_file: str = "tasks.jsonl"):
        self.redis = redis.from_url(redis_url)
        self.task_file = task_file
        self.cache = TemplateCache(self.redis)
        self.metrics = EnhancedMetrics()
        
        # 队列映射表
        self.queue_mapping = {
            TaskType.CODE: "tasks:code",
            TaskType.WEB: "tasks:web",
            TaskType.REASONING: "tasks:reasoning"
        }
        
    async def start(self):
        """启动分发器"""
        logger.info("Starting optimized task dispatcher...")
        
        # 启动metrics服务器
        self.metrics.start_server()
        
        # 并行启动各个组件
        await asyncio.gather(
            self._load_and_dispatch_tasks(),
            self._monitor_queues(),
            self._monitor_pending_tasks()
        )
    
    async def _load_and_dispatch_tasks(self):
        """加载并按类型分发任务"""
        processed_tasks: Set[str] = set()
        last_position = 0
        
        while True:
            try:
                if not os.path.exists(self.task_file):
                    await asyncio.sleep(5)
                    continue
                
                # 读取新任务
                with open(self.task_file, 'r', encoding='utf-8') as f:
                    for line_number, line in enumerate(f):
                        if line_number <= last_position:
                            continue
                        
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            task_data = json.loads(line)
                            task = TaskSpec.from_dict(task_data)
                            
                            if task.task_id in processed_tasks:
                                continue
                            
                            # 直接分发到对应队列
                            queue_name = self.queue_mapping.get(task.task_type)
                            if queue_name:
                                await self.redis.xadd(
                                    queue_name,
                                    {
                                        "task": task.json(),
                                        "submitted_at": time.time(),
                                        "priority": task.priority
                                    }
                                )
                                
                                self.metrics.record_task_submitted(
                                    task.task_type.value,
                                    queue_name.split(":")[1]
                                )
                                processed_tasks.add(task.task_id)
                                
                                logger.info(f"Dispatched task {task.task_id} to {queue_name}")
                            else:
                                logger.error(f"No queue for task type {task.task_type}")
                                
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.error(f"Invalid task at line {line_number}: {e}")
                        
                        last_position = line_number
                
                await asyncio.sleep(5)  # 检查新任务间隔
                
            except Exception as e:
                logger.error(f"Error in task loading: {e}")
                await asyncio.sleep(10)
    
    async def _monitor_queues(self):
        """监控队列状态"""
        while True:
            try:
                for task_type, queue_name in self.queue_mapping.items():
                    # 获取队列长度
                    queue_length = await self.redis.xlen(queue_name)
                    self.metrics.update_queue_size(queue_name, queue_length)
                
                await asyncio.sleep(30)  # 每30秒更新
                
            except Exception as e:
                logger.error(f"Error monitoring queues: {e}")
                await asyncio.sleep(10)
    
    async def _monitor_pending_tasks(self):
        """监控挂起任务延迟"""
        while True:
            try:
                for task_type, queue_name in self.queue_mapping.items():
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
                logger.error(f"Error monitoring pending tasks: {e}")
                await asyncio.sleep(30)

async def main():
    """分发器主程序"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    task_file = os.getenv("TASK_FILE", "tasks.jsonl")
    
    dispatcher = TaskDispatcher(redis_url, task_file)
    
    try:
        await dispatcher.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await dispatcher.redis.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())