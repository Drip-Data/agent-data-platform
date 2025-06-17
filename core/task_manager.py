import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
import redis.asyncio as redis
from .interfaces import TaskSpec, TrajectoryResult
from .metrics import EnhancedMetrics
from .utils.path_utils import get_trajectories_dir

logger = logging.getLogger(__name__)

class TaskManager:
    """任务生命周期管理器"""
    
    def __init__(self, redis_url: str = None, redis_manager=None):
        self.redis_manager = redis_manager
        
        if redis_manager and not redis_manager.is_fallback_mode():
            # 使用真实Redis
            import redis.asyncio as redis
            self.redis = redis.from_url(redis_manager.get_redis_url())
            self.fallback_mode = False
        else:
            # 使用内存存储
            self.redis = None
            self.fallback_mode = True
            logger.warning("TaskManager 运行在内存模式")
            
        self.metrics = EnhancedMetrics()
        self._active_tasks: Dict[str, Dict] = {}

    async def submit_task(self, task: TaskSpec) -> str:
        """提交任务"""
        task_data = {
            "task": task.to_dict(),
            "status": "submitted",
            "submitted_at": time.time(),
            "updated_at": time.time()
        }
        
        if not self.fallback_mode and self.redis:
            # 存储任务状态到Redis
            await self.redis.hset(
                f"task:{task.task_id}",
                mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                        for k, v in task_data.items()}
            )
            
            # 设置过期时间（24小时）
            await self.redis.expire(f"task:{task.task_id}", 86400)
        else:
            # 内存模式：使用redis_manager的内存存储
            if self.redis_manager:
                await self.redis_manager.memory_set(
                    f"task:{task.task_id}", 
                    json.dumps(task_data)
                )
        
        self._active_tasks[task.task_id] = task_data
        
        logger.info(f"Task {task.task_id} submitted")
        return task.task_id
    
    async def update_task_status(self, task_id: str, status: str, metadata: Dict = None):
        """更新任务状态"""
        update_data = {
            "status": status,
            "updated_at": time.time()
        }
        
        if metadata:
            update_data["metadata"] = json.dumps(metadata)
        
        await self.redis.hset(
            f"task:{task_id}",
            mapping={k: str(v) for k, v in update_data.items()}
        )
        
        if task_id in self._active_tasks:
            self._active_tasks[task_id].update(update_data)
        
        logger.info(f"Task {task_id} status updated to {status}")
    
    async def complete_task(self, task_id: str, result: TrajectoryResult):
        """完成任务"""
        # 存储结果
        await self.redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "completed",
                "completed_at": time.time(),
                "result": result.json(),
                "success": str(result.success)
            }
        )
        
        # 保存轨迹到文件
        await self._save_trajectory(result)
        
        # 清理内存中的任务
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]
        
        logger.info(f"Task {task_id} completed with success={result.success}")
    
    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        task_data = await self.redis.hgetall(f"task:{task_id}")
        
        if not task_data:
            return None
        
        # 解析JSON字段
        result = {}
        for key, value in task_data.items():
            key = key.decode() if isinstance(key, bytes) else key
            value = value.decode() if isinstance(value, bytes) else value
            
            if key in ['task', 'metadata', 'result']:
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    async def list_active_tasks(self) -> List[Dict]:
        """列出活跃任务"""
        return list(self._active_tasks.values())
    async def _save_trajectory(self, result: TrajectoryResult):
        """保存轨迹到文件"""
        try:
            trajectories_dir = get_trajectories_dir()
            
            filename = f"{trajectories_dir}/{result.task_id}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(result.json())
            
            logger.info(f"Trajectory saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving trajectory for {result.task_id}: {e}")
    
    async def cleanup_expired_tasks(self):
        """清理过期任务"""
        current_time = time.time()
        expired_tasks = []
        
        for task_id, task_data in self._active_tasks.items():
            # 如果任务超过1小时未更新，标记为过期
            if current_time - task_data.get("updated_at", 0) > 3600:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            await self.update_task_status(task_id, "expired")
            del self._active_tasks[task_id]
            logger.warning(f"Task {task_id} marked as expired")
        
        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")
    
def get_runtime(task_type: str):
    """获取指定类型的运行时实例
    
    注意：历史运行时(sandbox, web_navigator)已被移除
    所有功能已迁移至MCP服务器，通过enhanced-reasoning-runtime + toolscore调用
    迁移日期: 2025-06-14
    """
    if task_type in ['reasoning', 'code', 'web']:
        # 所有任务类型现在都使用enhanced-reasoning-runtime
        # code和web功能通过toolscore调用相应的MCP服务器实现
        try:
            from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
            return EnhancedReasoningRuntime()
        except ImportError:
            raise ImportError("EnhancedReasoningRuntime not found")
    else:
        raise ValueError(f"Unsupported task type: {task_type}. Supported types: reasoning, code, web")

async def _update_task_api_status(redis_client, task_id: str, status: str, result: TrajectoryResult = None):
    """更新Task API使用的任务状态"""
    try:
        from datetime import datetime
        
        # 更新Task API使用的状态键
        status_data = {
            "task_id": task_id,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        if result:
            status_data["message"] = f"Task {status} with success={result.success}"
        else:
            status_data["message"] = f"Task {status}"
        
        # 设置状态，保存1小时
        await redis_client.setex(
            f"task_status:{task_id}", 
            3600, 
            json.dumps(status_data)
        )
        
        # 如果有结果，也保存结果数据
        if result and status in ["completed", "failed"]:
            result_data = {
                "success": result.success,
                "final_result": result.final_result,
                "error_message": result.error_message,
                "total_duration": result.total_duration,
                "steps_count": len(result.steps)
            }
            await redis_client.setex(
                f"task_result:{task_id}",
                3600,
                json.dumps(result_data)
            )
        
        logger.info(f"Task API status updated: {task_id} -> {status}")
        
    except Exception as e:
        logger.error(f"Failed to update Task API status for {task_id}: {e}")

async def start_runtime_service(runtime, redis_manager=None):
    """启动给定运行时的任务消费服务"""
    import os
    import asyncio
    import json
    from .interfaces import TaskSpec, ErrorType, TrajectoryResult

    async def _run_service():
        # 使用传入的redis_manager，否则fallback到内存模式
        if redis_manager and not redis_manager.is_fallback_mode():
            import redis.asyncio as redis_client
            redis_url = redis_manager.get_redis_url()
            r = redis_client.from_url(redis_url)
        else:
            # 内存模式 - 创建虚拟队列服务
            logger.warning(f"Runtime {runtime.runtime_id} 运行在内存模式，任务队列功能受限")
            
            # 在内存模式下，模拟任务处理
            while True:
                try:
                    # 每30秒检查一次是否有模拟任务
                    await asyncio.sleep(30)
                    logger.debug(f"Runtime {runtime.runtime_id} 在内存模式下等待任务...")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Runtime {runtime.runtime_id} 内存模式出错: {e}")
                    await asyncio.sleep(5)
            return
        
        # 根据runtime的能力确定队列名
        queue_name = None


        
        # if hasattr(runtime, 'capabilities'):
        #     try:
        #         # 如果capabilities是协程，需要await
        #         if asyncio.iscoroutine(runtime.capabilities):
        #             capabilities = await runtime.capabilities
        #         elif callable(runtime.capabilities):
        #             capabilities = await runtime.capabilities()
        #         else:
        #             capabilities = runtime.capabilities
                
        #         if capabilities:
        #             # 推理runtime处理reasoning队列
        #             if 'browser' in capabilities and 'python_executor' in capabilities:
        #                 queue_name = "tasks:reasoning"
        #             # 代码执行runtime处理code队列
        #             elif 'python_code_execution' in capabilities:
        #                 queue_name = "tasks:code"
        #             # Web导航runtime处理web队列
        #             elif 'browser_navigation' in capabilities:
        #                 queue_name = "tasks:web"
        #     except Exception as e:
        #         logger.warning(f"Error getting runtime capabilities: {e}")
        #         capabilities = None
        
        # 如果无法从capabilities确定，尝试从runtime类名推断
        if not queue_name:
            runtime_class = runtime.__class__.__name__.lower()
            if 'reasoning' in runtime_class:
                queue_name = "tasks:reasoning"
            elif 'sandbox' in runtime_class or 'code' in runtime_class:
                queue_name = "tasks:code"
            elif 'web' in runtime_class or 'navigator' in runtime_class:
                queue_name = "tasks:web"
            else:
                # 默认为reasoning队列
                queue_name = "tasks:reasoning"
        
        logger.info(f"Runtime {runtime.runtime_id} starting to consume from queue: {queue_name}")
        
        group = "workers"
        consumer_id = runtime.runtime_id
        # 创建消费者组
        try:
            await r.xgroup_create(queue_name, group, id="0", mkstream=True)
        except Exception:
            pass
        # 消费循环
        while True:
            msgs = await r.xreadgroup(group, consumer_id, {queue_name: ">"}, count=1, block=1000)
            if not msgs:
                continue
            for _, entries in msgs:
                for msg_id, fields in entries:
                    try:
                        data = json.loads(fields[b'task'].decode())
                        task = TaskSpec.from_dict(data)
                        logger.info(f"Processing task {task.task_id} from queue {queue_name}")
                        
                        # 更新任务状态为运行中
                        await _update_task_api_status(r, task.task_id, "running")
                        
                        result = await runtime.execute(task)
                        
                        # 更新任务状态为已完成
                        final_status = "completed" if result.success else "failed"
                        await _update_task_api_status(r, task.task_id, final_status, result)
                        
                        # 路径由 runtime 自行保存轨迹
                        logger.info(f"Task {task.task_id} executed successfully: {result.success}")
                    except Exception as e:
                        # 记录详细的错误信息
                        logger.error(f"Error executing task {data.get('task_id', 'unknown')}: {e}", exc_info=True)
                        
                        # 更新任务状态为失败
                        task_id = data.get('task_id', 'unknown')
                        await _update_task_api_status(r, task_id, "failed")
                        
                        # 创建错误轨迹结果
                        try:
                            error_result = TrajectoryResult(
                                task_name=data.get('task_id', 'unknown'),
                                task_id=data.get('task_id', 'unknown'),
                                task_description=data.get('description', ''),
                                runtime_id=getattr(runtime, 'runtime_id', 'unknown'),
                                success=False,
                                steps=[],
                                final_result="",
                                error_message=str(e),
                                error_type=ErrorType.SYSTEM_ERROR,
                                total_duration=0,
                                metadata={"execution_error": True, "error_details": str(e)}
                            )
                            
                            # 尝试保存错误轨迹
                            if hasattr(runtime, '_save_trajectory'):
                                await runtime._save_trajectory(error_result)
                        except Exception as save_error:
                            logger.error(f"Failed to save error trajectory: {save_error}")
                        
                        # 记录指标
                        if hasattr(runtime, 'metrics'):
                            runtime.metrics.record_task_failure(
                                data.get('task_id', 'unknown'), 
                                getattr(runtime, 'runtime_id', 'unknown'),
                                "system_error"
                            )
                    finally:
                        await r.xack(queue_name, group, msg_id)

    # === 改进：自动重启消费协程，防止异常退出导致任务堆积 ===
    while True:
        try:
            await _run_service()
        except asyncio.CancelledError:
            # 主程序取消时直接退出
            raise
        except Exception as fatal_err:
            logger.exception(f"❌ Runtime {getattr(runtime, 'runtime_id', 'unknown')} crashed: {fatal_err}")
            # 留出短暂冷却时间后自动重启
            await asyncio.sleep(3)