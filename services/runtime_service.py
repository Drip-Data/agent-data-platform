import logging
import os
from typing import Dict, Optional, List

# 导入运行时相关模块
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
from runtimes.reasoning.simple_runtime import SimpleReasoningRuntime

logger = logging.getLogger(__name__)

# 全局变量
runtime_instances = []

def initialize(config: Optional[Dict] = None, config_manager=None, llm_client=None, toolscore_client=None, toolscore_websocket_endpoint: Optional[str] = None, redis_manager=None, xml_streaming_mode: bool = False, use_simple_runtime: bool = False, trajectory_storage_mode: str = "daily_grouped"):
    """初始化推理运行时服务"""
    global runtime_instances
    
    if config is None:
        config = {}
    
    logger.info("正在初始化推理运行时服务...")
    
    # 如果没有传入依赖，尝试从全局或者延迟到运行时创建
    if not all([config_manager, llm_client, toolscore_client]):
        logger.warning("运行时服务未收到必要的依赖，将延迟到启动时创建运行时实例")
        return
    
    # 清空现有实例列表
    runtime_instances = []
    
    # 从环境变量中获取运行时实例数量
    instance_count = int(os.getenv('RUNTIME_INSTANCES', 1))
    
    # 创建指定数量的运行时实例
    for i in range(instance_count):
        if use_simple_runtime:
            instance_name = f"simple-runtime-{i+1}"
            logger.info(f"创建简化运行时实例: {instance_name} (存储模式: {trajectory_storage_mode})")
            # 创建简化运行时实例
            runtime = SimpleReasoningRuntime(config_manager, llm_client, toolscore_client, xml_streaming_mode, trajectory_storage_mode)
            runtime._runtime_id = f"simple-reasoning-{i+1}"
        else:
            instance_name = f"enhanced-runtime-{i+1}"
            logger.info(f"创建运行时实例: {instance_name}")
            # 创建运行时实例并传入依赖，包括新的websocket端点和redis_manager
            runtime = EnhancedReasoningRuntime(config_manager, llm_client, toolscore_client, redis_manager, toolscore_websocket_endpoint, xml_streaming_mode)
            runtime._runtime_id = f"enhanced-reasoning-{i+1}"
        
        runtime_instances.append(runtime)
    
    logger.info(f"推理运行时服务初始化完成，创建了 {len(runtime_instances)} 个实例")

def start():
    """启动推理运行时服务"""
    logger.info("正在启动推理运行时服务...")
    
    # 启动所有运行时实例（异步初始化和任务消费）
    import asyncio
    
    async def start_all_runtimes():
        # 初始化所有运行时实例
        for runtime in runtime_instances:
            runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
            logger.info(f"启动运行时实例: {runtime_name}")
            try:
                await runtime.initialize()
            except Exception as e:
                logger.error(f"运行时实例 {runtime_name} 初始化失败: {e}")
        
        # 启动所有运行时的任务消费服务
        from core.task_manager import start_runtime_service
        from core.redis_manager import RedisManager
        
        # 获取Redis管理器（需要从全局获取或创建）
        redis_manager = None
        try:
            # 尝试从环境变量获取Redis URL
            import os
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            redis_manager = RedisManager(redis_url)
        except Exception as e:
            logger.warning(f"无法创建Redis管理器: {e}")
        
        # 为每个运行时实例启动任务消费协程
        tasks = []
        for runtime in runtime_instances:
            runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
            logger.info(f"启动运行时任务消费: {runtime_name}")
            task = asyncio.create_task(
                start_runtime_service(runtime, redis_manager),
                name=f"runtime-{runtime_name}"
            )
            tasks.append(task)
        
        logger.info(f"推理运行时服务已启动 {len(runtime_instances)} 个实例和 {len(tasks)} 个任务消费协程")
        
        # 等待所有任务消费协程
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except (asyncio.CancelledError, GeneratorExit):
                logger.info("运行时服务正常停止，取消所有任务")
                # 取消所有剩余任务
                for task in tasks:
                    if not task.done():
                        task.cancel()
                # 等待任务真正取消
                await asyncio.gather(*tasks, return_exceptions=True)
    
    # 在新的事件循环中启动所有运行时
    asyncio.create_task(start_all_runtimes())

def stop():
    """停止推理运行时服务"""
    global runtime_instances
    
    logger.info("正在停止推理运行时服务...")
      # 停止所有运行时实例
    for runtime in runtime_instances:
        # 安全地获取运行时名称
        runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
        logger.info(f"停止运行时实例: {runtime_name}")
        
        # EnhancedReasoningRuntime使用cleanup方法而不是stop方法
        if hasattr(runtime, 'cleanup'):
            try:
                # cleanup是异步方法，使用asyncio.run同步执行
                import asyncio
                asyncio.run(runtime.cleanup())
            except Exception as e:
                logger.warning(f"运行时清理失败: {e}")
        elif hasattr(runtime, 'stop'):
            try:
                runtime.stop()
            except Exception as e:
                logger.warning(f"运行时停止失败: {e}")
    
    # 清理资源
    runtime_instances = []
    
    logger.info("推理运行时服务已停止")

def health_check():
    """检查推理运行时服务健康状态"""
    if not runtime_instances:
        return {'status': 'error', 'message': 'Runtime service not initialized'}
    # 检查所有运行时实例的状态
    instance_statuses = []
    for i, runtime in enumerate(runtime_instances):
        thread_alive = False  # 这里不再跟踪线程状态，始终设置为False
        
        instance_statuses.append({
            'name': getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown')),
            'running': thread_alive,
            'tasks_processed': runtime.get_tasks_processed() if hasattr(runtime, 'get_tasks_processed') else None
        })
    
    # 如果所有线程都不在运行，则服务不健康
    all_threads_dead = all(not status['running'] for status in instance_statuses)
    
    return {
        'status': 'error' if all_threads_dead else 'healthy',
        'message': 'All runtime threads stopped' if all_threads_dead else None,
        'instances': instance_statuses,
        'instance_count': len(runtime_instances)
    }

def get_runtime_instances() -> List[EnhancedReasoningRuntime]:
    """获取所有运行时实例"""
    if not runtime_instances:
        raise RuntimeError("推理运行时未初始化，请先调用initialize()")
    return runtime_instances
