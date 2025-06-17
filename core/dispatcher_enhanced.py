import asyncio
import logging
import os # 重新引入os，因为TaskLoader需要它
from typing import Dict, Any, Set # 引入Set
import redis.asyncio as async_redis
from core.interfaces import TaskSpec, TaskType
from core.config_manager import ConfigManager
from core.monitoring.queue_monitor import QueueMonitor
from core.toolscore.toolscore_client import ToolScoreClient
from core.task_processing.task_loader import TaskLoader
from core.task_processing.task_enhancer import TaskEnhancer
from core.task_processing.task_distributor import TaskDistributor
logger = logging.getLogger(__name__)

class TaskProcessingCoordinator:
    """
    任务处理协调器，负责协调任务的加载、增强和分发。
    取代原有的 EnhancedTaskDispatcher，职责更单一。
    """
    
    def __init__(self,
                 redis_url: str,
                 config_manager: ConfigManager, # 强制依赖注入
                 toolscore_client: ToolScoreClient, # 强制依赖注入
                 queue_monitor: QueueMonitor, # 强制依赖注入
                 task_loader: TaskLoader, # 依赖注入 TaskLoader
                 task_enhancer: TaskEnhancer, # 依赖注入 TaskEnhancer
                 task_distributor: TaskDistributor, # 依赖注入 TaskDistributor
                 queue_mapping: Dict[TaskType, str] # 直接注入队列映射
                ):
        self.config_manager = config_manager
        self.toolscore_client = toolscore_client
        self.queue_monitor = queue_monitor
        self.task_loader = task_loader
        self.task_enhancer = task_enhancer
        self.task_distributor = task_distributor
        self.queue_mapping = queue_mapping # 直接使用注入的队列映射
        
        logger.info(f"✅ TaskProcessingCoordinator 配置加载完成 - 队列映射: {self.queue_mapping}")
        
        # TemplateCache 已移除，待后续评估其职责并重新引入

    async def _process_single_task(self, task: TaskSpec):
        """处理单个任务的增强和分发流程"""
        # 🔧 智能工具增强
        task = await self.task_enhancer.enhance_task_with_tools(task) # 调用 TaskEnhancer
        
        # 分发到对应队列
        queue_name = self.queue_mapping.get(task.task_type)
        if queue_name:
            await self.task_distributor.distribute_task(task, queue_name) # 调用 TaskDistributor
            logger.info(f"分发增强任务 {task.task_id} 到 {queue_name}")
        else:
            logger.error(f"未找到任务类型 {task.task_type} 对应的队列")

    async def _coordinate_task_processing(self):
        """协调任务的加载、增强和分发"""
        async for task in self.task_loader.load_new_tasks(): # 通过 TaskLoader 获取任务
            await self._process_single_task(task)
            await asyncio.sleep(0.1) # 短暂等待，避免CPU空转

    async def start(self):
        """启动协调器"""
        logger.info("启动任务处理协调器...")
        
        await asyncio.gather(
            self._coordinate_task_processing(),
            self.queue_monitor.start()
        )

async def main():
    """主程序入口，负责依赖注入和启动"""
    # 这里将是依赖注入的核心区域，目前保持原样，待后续统一修改
    # 实例化ConfigManager并获取配置
    config_manager = ConfigManager()
    redis_url = config_manager.get_redis_url() # 从ConfigManager获取
    task_file = config_manager.get_task_file_path() # 从ConfigManager获取
    routing_config = config_manager.load_routing_config()
    queue_mapping = {
        TaskType(task_type_str.lower()): queue_name
        for task_type_str, queue_name in routing_config.task_type_mapping.items()
    }
    
    # 实例化所有依赖
    toolscore_client = ToolScoreClient(config_manager) # 注入config_manager
    queue_monitor = QueueMonitor(redis_url)
    task_loader = TaskLoader(task_file)
    task_enhancer = TaskEnhancer(toolscore_client) # TaskEnhancer 需要 ToolScoreClient
    from core.metrics import EnhancedMetrics
    metrics = EnhancedMetrics()
    task_distributor = TaskDistributor(redis_url, metrics)

    coordinator = TaskProcessingCoordinator(
        redis_url=redis_url,
        config_manager=config_manager,
        toolscore_client=toolscore_client,
        queue_monitor=queue_monitor,
        task_loader=task_loader,
        task_enhancer=task_enhancer,
        task_distributor=task_distributor,
        queue_mapping=queue_mapping # 注入队列映射
    )
    
    try:
        await coordinator.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        # Redis 连接现在由 RedisManager 管理，这里不再直接关闭
        pass