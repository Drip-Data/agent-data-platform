import logging
import os
from typing import Dict, Optional, List

# 导入运行时相关模块
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime

logger = logging.getLogger(__name__)

# 全局变量
runtime_instances = []
# 🔧 新增：运行时任务追踪
runtime_tasks = []

from core.unified_tool_manager import UnifiedToolManager

def initialize(config: Optional[Dict] = None, config_manager=None, llm_client=None, toolscore_client=None, tool_manager: UnifiedToolManager = None, toolscore_websocket_endpoint: Optional[str] = None, redis_manager=None, trajectory_storage_mode: str = "daily_grouped", num_workers: int = 1):
    """初始化推理运行时服务"""
    global runtime_instances, runtime_tasks
    
    if config is None:
        config = {}
    
    logger.info(f"正在初始化推理运行时服务，计划启动 {num_workers} 个工作进程...")
    
    # 如果没有传入依赖，尝试从全局或者延迟到运行时创建
    if not all([config_manager, llm_client, toolscore_client, tool_manager]):
        logger.error("运行时服务初始化失败：缺少必要的依赖（config_manager, llm_client, toolscore_client, tool_manager）")
        return
    
    # 清空现有实例列表
    runtime_instances = []
    runtime_tasks = []
    
    # 创建指定数量的运行时实例
    for i in range(num_workers):
        instance_name = f"enhanced-runtime-{i+1}"
        logger.info(f"创建增强运行时实例: {instance_name} (存储模式: {trajectory_storage_mode})")
        # 创建运行时实例并传入依赖，默认启用XML streaming模式
        runtime = EnhancedReasoningRuntime(
            config_manager=config_manager, 
            llm_client=llm_client, 
            toolscore_client=toolscore_client,
            tool_manager=tool_manager,
            redis_manager=redis_manager, 
            toolscore_websocket_endpoint=toolscore_websocket_endpoint, 
            xml_streaming_mode=True,  # 默认启用XML streaming
            trajectory_storage_mode=trajectory_storage_mode
        )
        runtime._runtime_id = f"enhanced-reasoning-{i+1}"
        runtime_instances.append(runtime)
    
    logger.info(f"推理运行时服务初始化完成，创建了 {len(runtime_instances)} 个实例")

async def start():
    """启动推理运行时服务"""
    logger.info("正在启动推理运行时服务...")
    
    # 🔧 修复：确保启动函数正确处理异步任务
    global runtime_tasks
    
    # 启动所有运行时实例（异步初始化和任务消费）
    import asyncio
    
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
    runtime_tasks = []
    for runtime in runtime_instances:
        runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
        logger.info(f"启动运行时任务消费: {runtime_name}")
        task = asyncio.create_task(
            start_runtime_service(runtime, redis_manager),
            name=f"runtime-{runtime_name}"
        )
        runtime_tasks.append(task)
    
    logger.info(f"推理运行时服务已启动 {len(runtime_instances)} 个实例和 {len(runtime_tasks)} 个任务消费协程")
    
    # 🔧 修复：不等待任务完成，让它们在后台运行
    # 运行时任务将在后台持续运行
    logger.info("运行时任务已启动并在后台运行")
    
    # 启动完成后返回
    return True

async def stop():
    """停止推理运行时服务"""
    global runtime_instances, runtime_tasks
    
    logger.info("正在停止推理运行时服务...")
    
    import asyncio
    
    # 🔧 新增：取消运行时任务
    if runtime_tasks:
        for task in runtime_tasks:
            if not task.done():
                task.cancel()
                logger.info(f"取消运行时任务: {task.get_name()}")
        
        # 等待所有任务完成取消
        await asyncio.gather(*runtime_tasks, return_exceptions=True)
    
    # 停止所有运行时实例
    for runtime in runtime_instances:
        # 安全地获取运行时名称
        runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
        logger.info(f"停止运行时实例: {runtime_name}")
        
        # EnhancedReasoningRuntime使用cleanup方法而不是stop方法
        if hasattr(runtime, 'cleanup'):
            try:
                # cleanup是异步方法，可以直接await
                await runtime.cleanup()
            except Exception as e:
                logger.warning(f"运行时清理失败: {e}")
        elif hasattr(runtime, 'stop'):
            try:
                runtime.stop()
            except Exception as e:
                logger.warning(f"运行时停止失败: {e}")
    
    # 清理资源
    runtime_instances = []
    runtime_tasks = []
    
    logger.info("推理运行时服务已停止")

def health_check():
    """检查推理运行时服务健康状态"""
    if not runtime_instances:
        return {'status': 'error', 'message': 'Runtime service not initialized'}
    
    # 检查所有运行时实例的状态
    instance_statuses = []
    for i, runtime in enumerate(runtime_instances):
        # 🔧 修复：检查对应的运行时任务状态
        task_running = False
        if i < len(runtime_tasks):
            task = runtime_tasks[i]
            task_running = not task.done()
        
        instance_statuses.append({
            'name': getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown')),
            'running': task_running,
            'tasks_processed': runtime.get_tasks_processed() if hasattr(runtime, 'get_tasks_processed') else None
        })
    
    # 如果所有任务都不在运行，则服务不健康
    all_tasks_dead = all(not status['running'] for status in instance_statuses)
    
    return {
        'status': 'error' if all_tasks_dead else 'healthy',
        'message': 'All runtime tasks stopped' if all_tasks_dead else None,
        'instances': instance_statuses,
        'instance_count': len(runtime_instances),
        'runtime_tasks_count': len(runtime_tasks)
    }

def get_runtime_instances():
    """获取所有运行时实例"""
    if not runtime_instances:
        raise RuntimeError("推理运行时未初始化，请先调用initialize()")
    return runtime_instances

# 🔧 新增：获取运行时任务状态
def get_runtime_tasks_status():
    """获取运行时任务状态"""
    if not runtime_tasks:
        return {'status': 'no_tasks', 'tasks': []}
    
    tasks_status = []
    for task in runtime_tasks:
        tasks_status.append({
            'name': task.get_name(),
            'done': task.done(),
            'cancelled': task.cancelled(),
            'exception': str(task.exception()) if task.done() and task.exception() else None
        })
    
    return {
        'status': 'ok',
        'tasks': tasks_status,
        'total_tasks': len(runtime_tasks)
    }
