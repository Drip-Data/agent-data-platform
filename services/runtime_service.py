import logging
import os
from typing import Dict, Optional, List

# 导入运行时相关模块
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime

logger = logging.getLogger(__name__)

# 全局变量
runtime_instances = []

def initialize(config: Optional[Dict] = None):
    """初始化推理运行时服务"""
    global runtime_instances
    
    if config is None:
        config = {}
    
    logger.info("正在初始化推理运行时服务...")
    
    # 清空现有实例列表
    runtime_instances = []
    
    # 从环境变量中获取运行时实例数量
    instance_count = int(os.getenv('RUNTIME_INSTANCES', 1))
    
    # 创建指定数量的运行时实例
    for i in range(instance_count):
        instance_name = f"enhanced-runtime-{i+1}"
        logger.info(f"创建运行时实例: {instance_name}")
          # 创建运行时实例
        runtime = EnhancedReasoningRuntime()
        
        # 设置实例名称（如果运行时支持的话）
        if hasattr(runtime, 'name'):
            runtime.name = instance_name
        else:
            # 使用_runtime_id作为标识
            runtime._runtime_id = f"enhanced-reasoning-{i+1}"
        
        runtime_instances.append(runtime)
    
    logger.info(f"推理运行时服务初始化完成，创建了 {len(runtime_instances)} 个实例")

def start():
    """启动推理运行时服务"""
    logger.info("正在启动推理运行时服务...")
    
    # 启动所有运行时实例（只需异步初始化）
    import asyncio
    for runtime in runtime_instances:
        runtime_name = getattr(runtime, 'name', getattr(runtime, '_runtime_id', 'unknown'))
        logger.info(f"启动运行时实例: {runtime_name}")
        try:
            asyncio.run(runtime.initialize())
        except Exception as e:
            logger.error(f"运行时实例 {runtime_name} 初始化失败: {e}")
    logger.info(f"推理运行时服务已启动 {len(runtime_instances)} 个实例")

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
