import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
import redis.asyncio as redis
from .interfaces import TaskSpec, TrajectoryResult
from .metrics import EnhancedMetrics
from .path_utils import get_trajectories_dir

logger = logging.getLogger(__name__)

class TaskManager:
    """任务生命周期管理器"""
    
    def __init__(self, config=None, redis_url: str = None, redis_manager=None):
        # 处理配置参数
        if config is None:
            config = {}
        if isinstance(config, str):
            # 如果第一个参数是字符串，则认为是 redis_url
            redis_url = config
            config = {}
        
        # 设置默认配置
        self.config = {
            "task_timeout": 300,
            "cleanup_interval": 3600,
            **config
        }
        
        self.redis_manager = redis_manager
        
        # 从配置中获取 redis_url（如果没有通过参数传递）
        if redis_url is None and "redis_url" in self.config:
            redis_url = self.config["redis_url"]
        
        if redis_manager and not redis_manager.is_fallback_mode():
            # 使用真实Redis
            import redis.asyncio as redis
            self.redis = redis.from_url(redis_manager.get_redis_url())
            self.redis_client = self.redis  # 为了向后兼容
            self.fallback_mode = False
        elif redis_url:
            # 直接使用 redis_url
            import redis.asyncio as redis
            try:
                self.redis = redis.from_url(redis_url)
                self.redis_client = self.redis
                self.fallback_mode = False
            except Exception as e:
                logger.warning(f"Redis连接失败: {e}，切换到内存模式")
                self.redis = None
                self.redis_client = None
                self.fallback_mode = True
        else:
            # 使用内存存储
            self.redis = None
            self.redis_client = None  # 为了向后兼容
            self.fallback_mode = True
            logger.warning("TaskManager 运行在内存模式")
            
        # 如果redis_client为None但测试环境需要，创建一个mock对象
        if self.redis_client is None and hasattr(self, '_test_mode'):
            from unittest.mock import AsyncMock
            self.redis_client = AsyncMock()
            self.fallback_mode = False
    
        self.metrics = EnhancedMetrics()
        self._active_tasks: Dict[str, Dict] = {}
        # 为了向后兼容
        self.tasks = self._active_tasks
        self.task_history: List[Dict] = []
    
    def set_redis_client(self, redis_client):
        """设置Redis客户端（主要用于测试）"""
        self.redis = redis_client
        self.redis_client = redis_client
        self.fallback_mode = False if redis_client else True
    
    @property
    def active_tasks(self) -> Dict[str, Dict]:
        """获取活跃任务字典（用于测试和调试）"""
        return self._active_tasks

    async def submit_task(self, task: TaskSpec) -> str:
        """提交任务"""
        task_data = {
            "task_id": task.task_id,
            "task": task.to_dict(),
            "status": "submitted",
            "submitted_at": time.time(),
            "updated_at": time.time()
        }
        
        if not self.fallback_mode and self.redis:
            try:
                # 存储任务状态到Redis
                await self.redis.hset(
                    f"task:{task.task_id}",
                    mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                            for k, v in task_data.items()}
                )
                
                # 设置过期时间（24小时）
                await self.redis.expire(f"task:{task.task_id}", 86400)
            except Exception as e:
                logger.warning(f"Redis operation failed, falling back to memory mode: {e}")
                self.fallback_mode = True
                # 内存模式：使用redis_manager的内存存储
                if self.redis_manager:
                    await self.redis_manager.memory_set(
                        f"task:{task.task_id}", 
                        json.dumps(task_data)
                    )
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
    
    async def update_task_status(self, task_id: str, status: str, status_message: str = None) -> bool:
        """更新任务状态"""
        try:
            # 首先检查任务是否存在
            if not self.fallback_mode and self.redis:
                # Redis模式：检查任务是否存在
                existing_status = await self.redis.hget(f"task:{task_id}", "status")
                if not existing_status:
                    logger.warning(f"Task {task_id} not found in Redis")
                    return False
            else:
                # 内存模式：检查任务是否存在
                if task_id not in self._active_tasks:
                    logger.warning(f"Task {task_id} not found in memory")
                    return False
            
            update_data = {
                "status": status,
                "updated_at": time.time()
            }
            
            if status_message:
                update_data["status_message"] = status_message
            
            if not self.fallback_mode and self.redis:
                # Redis模式：存储到Redis
                result = await self.redis.hset(
                    f"task:{task_id}",
                    mapping={k: str(v) for k, v in update_data.items()}
                )
                success = result is not None
            else:
                # 内存模式：使用redis_manager的内存存储
                if self.redis_manager:
                    await self.redis_manager.memory_set(
                        f"task:{task_id}", 
                        json.dumps(update_data)
                    )
                success = True
            
            if task_id in self._active_tasks:
                self._active_tasks[task_id].update(update_data)
            
            logger.info(f"Task {task_id} status updated to {status}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to update task {task_id} status: {e}")
            return False
    
    async def complete_task(self, task_id: str, result: TrajectoryResult):
        """完成任务"""
        if not self.fallback_mode and self.redis:
            # 存储结果到Redis
            await self.redis.hset(
                f"task:{task_id}",
                mapping={
                    "status": "completed",
                    "completed_at": time.time(),
                    "result": result.json(),
                    "success": str(result.success)
                }
            )
        else:
            # 内存模式：存储到task_history
            # 检查result是否是TrajectoryResult对象
            if hasattr(result, 'to_dict'):
                result_data = result.to_dict()
            else:
                # 如果是字典，直接使用
                result_data = result if isinstance(result, dict) else str(result)
            
            task_data = {
                "task_id": task_id,
                "status": "completed",
                "completed_at": time.time(),
                "result": result_data,
                "success": getattr(result, 'success', True),
                "steps": getattr(result, 'steps', []),
                "final_status": "completed"
            }
            self.task_history.append(task_data)
        
        # 保存轨迹到文件
        await self._save_trajectory(result)
        
        # 清理内存中的任务
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]
        
        logger.info(f"Task {task_id} completed with success={result.success}")
    
    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        if not self.fallback_mode and self.redis:
            try:
                # 从Redis获取
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
            except Exception as e:
                logger.error(f"Redis获取任务状态失败: {e}")
                # 回退到内存模式
                self.fallback_mode = True
                # 继续使用内存模式获取
        
        # 内存模式：从_active_tasks或task_history获取
        if task_id in self._active_tasks:
            return self._active_tasks[task_id]
        
        # 从历史记录中查找
        for task_data in self.task_history:
            if task_data.get("task_id") == task_id:
                return task_data
        
        return None
    
    async def list_active_tasks(self) -> List[Dict]:
        """列出活跃任务"""
        if not self.fallback_mode and self.redis:
            # Redis模式：从Redis获取所有任务
            try:
                task_keys = await self.redis.keys("task:*")
                active_tasks = []
                
                for key in task_keys:
                    task_data = await self.redis.hgetall(key)
                    if task_data:
                        # 解析任务数据
                        result = {}
                        for k, v in task_data.items():
                            k = k.decode() if isinstance(k, bytes) else k
                            v = v.decode() if isinstance(v, bytes) else v
                            
                            if k in ['task', 'metadata', 'result']:
                                try:
                                    result[k] = json.loads(v)
                                except json.JSONDecodeError:
                                    result[k] = v
                            else:
                                result[k] = v
                        
                        # 只返回活跃状态的任务
                        if result.get('status') in ['pending', 'running']:
                            active_tasks.append(result)
                
                return active_tasks
            except Exception as e:
                logger.error(f"Redis获取活跃任务失败: {e}")
                # 回退到内存模式
                self.fallback_mode = True
                return list(self._active_tasks.values())
        else:
            # 内存模式：从_active_tasks获取
            return list(self._active_tasks.values())
    
    async def save_trajectory(self, task_id: str, trajectory) -> bool:
        """保存任务轨迹"""
        try:
            # 首先检查任务是否存在
            if self.fallback_mode:
                # 内存模式：检查任务是否在活跃任务中或历史记录中
                task_exists = (task_id in self._active_tasks or 
                             any(task.get("task_id") == task_id for task in self.task_history))
                if not task_exists:
                    logger.warning(f"Task {task_id} not found, cannot save trajectory")
                    return False
                    
                # 内存模式：保存到内存
                if hasattr(trajectory, 'to_dict'):
                    trajectory_data = trajectory.to_dict()
                elif isinstance(trajectory, dict):
                    trajectory_data = trajectory.copy()
                else:
                    trajectory_data = trajectory
                
                trajectory_data["task_id"] = task_id
                from datetime import datetime
                trajectory_data["saved_at"] = datetime.now().isoformat()
                self.task_history.append(trajectory_data)
                return True
            else:
                # Redis模式：首先检查任务是否存在
                task_exists = await self.redis.exists(f"task:{task_id}")
                if not task_exists:
                    logger.warning(f"Task {task_id} not found in Redis, cannot save trajectory")
                    return False
                    
                # Redis模式：保存到Redis
                trajectory_key = f"trajectory:{task_id}"
                if hasattr(trajectory, 'json'):
                    trajectory_data = trajectory.json()
                else:
                    import json
                    trajectory_data = json.dumps(trajectory)
                
                await self.redis.set(trajectory_key, trajectory_data)
                await self.redis.expire(trajectory_key, 86400)  # 24小时过期
                return True
        except Exception as e:
            logger.error(f"保存轨迹失败: {e}")
            return False
    
    async def get_task_trajectory(self, task_id: str) -> Optional[Dict]:
        """获取任务轨迹"""
        try:
            # 从历史记录中查找
            for trajectory in self.task_history:
                if trajectory.get("task_id") == task_id:
                    return trajectory
            
            return None
        except Exception as e:
            logger.error(f"Error getting trajectory for {task_id}: {e}")
            return None
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
    
    async def cleanup_expired_tasks(self, timeout_seconds: int = 3600) -> int:
        """清理过期任务"""
        current_time = time.time()
        expired_tasks = []
        
        for task_id, task_data in self._active_tasks.items():
            # 如果任务超过指定时间未更新，标记为过期
            if current_time - task_data.get("updated_at", 0) > timeout_seconds:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            await self.update_task_status(task_id, "expired")
            del self._active_tasks[task_id]
            logger.warning(f"Task {task_id} marked as expired")
        
        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")
        
        return len(expired_tasks)
    
def get_runtime(task_type: str) -> int:
    """获取指定类型任务的超时时间（秒）
    
    注意：历史运行时(sandbox, web_navigator)已被移除
    所有功能已迁移至MCP服务器，通过enhanced-reasoning-runtime + toolscore调用
    迁移日期: 2025-06-14
    """
    # 任务类型到超时时间的映射
    timeout_mapping = {
        "code_execution": 300,    # 5分钟
        "web_automation": 600,    # 10分钟
        "data_analysis": 900,     # 15分钟
        "file_processing": 180,   # 3分钟
        "reasoning": 300,         # 5分钟
        "code": 300,              # 5分钟
        "web": 600,               # 10分钟
    }
    
    # 处理边缘情况：None、空字符串或未知类型返回默认超时时间
    if not task_type:
        return 300  # 默认5分钟超时
        
    return timeout_mapping.get(task_type, 300)  # 未知类型返回默认值

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