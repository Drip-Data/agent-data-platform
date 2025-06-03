import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
import re
import threading
from typing import Dict, Any, Optional, List

import redis.asyncio as redis
import httpx

from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, ErrorType
from core.cache import TemplateCache
from core.metrics import EnhancedMetrics
from core.llm_client import LLMClient

# 跨平台文件锁导入
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

logger = logging.getLogger(__name__)
metrics = EnhancedMetrics(port=8001)

class NSJailExecutor:
    """NSJail执行器"""
    
    def __init__(self):
        # 暂时使用直接执行，不使用NSJail
        # TODO: 后续添加NSJail支持
        self.use_nsjail = False
    
    def _is_safe_code(self, code: str) -> tuple[bool, str]:
        """基本的代码安全检查"""
        dangerous_patterns = [
            r'import\s+os\s*;.*os\.system',
            r'subprocess\.',
            r'eval\s*\(',
            r'exec\s*\(',
            r'__import__',
            r'open\s*\([^)]*["\'][wa]',  # 写入文件操作
            r'file\s*\(',
            r'input\s*\(',
            r'raw_input\s*\(',
            r'compile\s*\(',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Potentially dangerous code detected: {pattern}"
        
        return True, ""

    async def execute(self, code: str, timeout: int = 30) -> Dict:
        """执行代码"""
        # 基本安全检查
        is_safe, reason = self._is_safe_code(code)
        if not is_safe:
            return {
                "exit_code": -2,
                "stdout": "",
                "stderr": f"Code execution blocked: {reason}"
            }
        
        # 使用UUID生成唯一文件名避免竞态条件
        script_path = f"/tmp/script_{uuid.uuid4().hex}.py"
        
        try:
            with open(script_path, 'w') as f:
                f.write(code)
            
            # 直接使用python3执行，不使用NSJail
            cmd = ["python3", script_path]
            
            # 执行命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=timeout
                )
                
                return {
                    "exit_code": process.returncode,
                    "stdout": stdout.decode('utf-8', errors='ignore'),
                    "stderr": stderr.decode('utf-8', errors='ignore')
                }
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Execution timeout"
                }
                
        finally:
            # 清理临时文件
            try:
                os.unlink(script_path)
            except:
                pass

class LightweightSandboxRuntime(RuntimeInterface):
    """轻量级沙盒运行时"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._runtime_id = f"sandbox-{os.getpid()}"
        self.redis = None
        self.cache = None
        self.executor = NSJailExecutor()
        self.llm_client = LLMClient(config)
          # 是否禁用缓存，从环境变量中读取，默认启用缓存
        self.disable_cache = config.get("disable_cache", False) or os.getenv("DISABLE_CACHE", "").lower() in ("1", "true", "yes")
        
        # 是否同时保存单独的轨迹文件，从环境变量中读取，默认不保存
        self.config["save_individual_trajectories"] = config.get("save_individual_trajectories", False) or os.getenv("SAVE_INDIVIDUAL_TRAJECTORIES", "").lower() in ("1", "true", "yes")
        
        # 添加文件锁用于跨平台兼容
        self._file_locks = {}
        self._lock_mutex = threading.Lock()
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    @property
    def capabilities(self) -> List[str]:
        return ["code_execution", "python", "sandbox"]
        
    async def start(self):
        """启动运行时"""
        logger.info(f"Starting {self.runtime_id}")
        
        # 连接Redis
        self.redis = redis.from_url(self.config["redis_url"])
        
        # 初始化缓存
        self.cache = TemplateCache(self.redis)
        
        # 注册健康状态
        await self._register_health()
        
        # 创建消费者组
        queue_name = "tasks:code"
        try:
            await self.redis.xgroup_create(queue_name, "workers", id="0", mkstream=True)
        except Exception:
            pass
        
        # 启动指标服务器
        metrics.start_server()
        logger.info(f"Metrics server started on port 8001")
        
        # 开始消费任务（在后台运行）
        asyncio.create_task(self._consume_tasks())
        
        # 保持服务运行
        while True:
            await asyncio.sleep(1)
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行代码任务"""
        start_time = time.time()
        
        # 生成新的UUID作为轨迹ID
        trajectory_id = str(uuid.uuid4())
        
        try:
            # 记录任务开始
            metrics.record_task_start(task.task_id, 'sandbox')
            
            # 是否使用缓存
            cached_code = None
            if not self.disable_cache:
                # 检查缓存
                cached_code = await self.cache.get(task.task_type.value, task.description)
            
            if cached_code and not self.disable_cache:
                logger.info(f"Cache hit for task {task.task_id}")
                metrics.record_cache_hit()
                code = cached_code.get("code", "")
                thinking = "使用缓存的代码解决方案。如需禁用缓存，请设置环境变量 DISABLE_CACHE=true"
            else:
                if self.disable_cache:
                    logger.info(f"Cache disabled for task {task.task_id}")
                else:
                    logger.info(f"Cache miss for task {task.task_id}")
                    metrics.record_cache_miss()
                
                # 生成代码并捕获思考过程
                code_response = await self._generate_code_with_thinking(task.description)
                code = code_response["code"]
                thinking = code_response["thinking"]
                
                # 如果未禁用缓存，则缓存代码
                if not self.disable_cache:
                    await self.cache.set(task.task_type.value, task.description, {"code": code})
            
            # 执行代码
            execution_result = await self._execute_code_safely(code)
              # 构建执行步骤
            from core.interfaces import ExecutionStep, ActionType
            # 增强思考过程的代码生成步骤
            cache_status = "使用了缓存的代码" if cached_code and not self.disable_cache else "无可用缓存或缓存已禁用"
            generation_thinking = f"""
缓存状态: {cache_status}
禁用缓存: {"是" if self.disable_cache else "否"}
LLM提供商: {self.llm_client.provider.value}
任务描述: {task.description}

思考过程:
{thinking}
"""
            # 增强思考过程的代码执行步骤
            execution_thinking = f"""
执行代码中...
超时设置: 30秒
执行环境: Python安全沙箱
执行结果: {"成功" if execution_result["success"] else "失败"}
退出代码: {execution_result.get("exit_code", "未知")}
执行时长: {execution_result.get("duration", 0):.2f} 秒
{"发生错误: " + execution_result.get("error", "未知错误") if not execution_result["success"] else "执行成功完成，无错误"}
"""

            steps = [
                ExecutionStep(
                    step_id=1,
                    action_type=ActionType.CODE_GENERATION,
                    action_params={"description": task.description},
                    observation=code,
                    thinking=generation_thinking,
                    execution_code=code,
                    success=True,  # 代码生成成功
                    timestamp=start_time
                ),
                ExecutionStep(
                    step_id=2,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": code},
                    observation=execution_result["output"],
                    thinking=execution_thinking,
                    execution_code=code,
                    success=execution_result["success"],  # 基于实际执行结果
                    error_type=execution_result.get("error_type"),
                    error_message=execution_result.get("error"),
                    timestamp=time.time()
                )
            ]
              # 构建增强的元数据
            enhanced_metadata = {
                "cached": cached_code is not None and not self.disable_cache,
                "cache_disabled": self.disable_cache,
                "exit_code": execution_result.get("exit_code"),
                "original_task_id": task.task_id,
                "llm_provider": self.llm_client.provider.value,
                "execution_time": execution_result.get("duration", 0),
                "code_stats": execution_result.get("code_stats", {}),
                "execution_details": execution_result.get("execution_details", {})
            }
            
            # 构建轨迹结果
            result = TrajectoryResult(
                task_name=task.task_id,  # 保持原始task_id作为task_name
                task_id=trajectory_id,   # 使用新的UUID作为轨迹ID
                runtime_id=self.runtime_id,
                success=execution_result["success"],
                steps=steps,
                final_result=execution_result["output"],
                task_description=task.description,
                error_message=execution_result.get("error"),
                error_type=execution_result.get("error_type"),
                total_duration=time.time() - start_time,
                metadata=enhanced_metadata            )
            # 记录指标
            if result.success:
                metrics.record_task_completed(task.task_id, 'sandbox', result.success)
            else:
                metrics.record_task_failure(task.task_id, 'sandbox', result.error_type.value if result.error_type else "unknown")
            return result
            
        except Exception as e:
            logger.error(f"Error executing task {task.task_id}: {e}")
            metrics.record_task_failure(task.task_id, 'sandbox', "system_error")
            
            return TrajectoryResult(
                task_name=task.task_id,
                task_id=trajectory_id,  # 使用新的UUID
                task_description=task.description,
                runtime_id=self.runtime_id,
                success=False,
                steps=[],
                final_result="",
                error_message=str(e),
                error_type=ErrorType.SYSTEM_ERROR,
                total_duration=time.time() - start_time,
                metadata={"original_task_id": task.task_id}
            )
    
    async def _generate_code_with_thinking(self, description: str) -> Dict[str, str]:
        """使用LLM生成代码并捕获思考过程"""
        try:
            # 记录开始时间，用于计算生成时间
            generation_start_time = time.time()
            
            # 使用统一的LLM客户端生成代码和思考过程
            result = await self.llm_client.generate_code(description, "python")
            generation_time = time.time() - generation_start_time
            
            # 现在 result 应该是一个包含 code 和 thinking 的字典
            code = result["code"]
            thinking = result["thinking"]
            success = result.get("success", True)  # 如果字段不存在，假设成功
            
            # 创建增强版的思考过程，包含更多元数据
            provider_info = f"使用 {self.llm_client.provider.value} 生成代码"
            
            # 增强的思考过程，添加了时间戳、运行时环境、生成时间等更多信息
            enhanced_thinking = f"""
代码生成详情:
==================
时间戳: {time.strftime('%Y-%m-%d %H:%M:%S')}
LLM提供商: {self.llm_client.provider.value}
运行时环境: {self.runtime_id}
代码生成状态: {"成功" if success else "失败"}
生成时间: {generation_time:.2f} 秒
代码长度: {len(code)} 字符
缓存状态: 强制生成新代码 (禁用缓存: {self.disable_cache})
任务描述: {description}

LLM思考过程:
==================
{thinking}
"""
            
            logger.info(f"Generated code using {self.llm_client.provider.value} for: {description[:50]}... in {generation_time:.2f}s")
            return {
                "code": code,
                "thinking": enhanced_thinking,
                "success": success,
                "generation_time": generation_time
            }
        except Exception as e:
            logger.error(f"Failed to generate code with LLM: {e}")
            # 发生错误，记录详细信息并重新抛出异常
            error_message = f"""
代码生成失败:
==================
时间戳: {time.strftime('%Y-%m-%d %H:%M:%S')}
错误: {str(e)}
操作: 停止执行并报告错误
任务描述: {description}
"""
            # 重新抛出带有更多上下文的异常
            raise RuntimeError(f"生成代码失败: {e}") from e
    async def _generate_code(self, description: str) -> str:
        """使用LLM生成代码"""
        try:
            # 使用统一的LLM客户端生成代码
            result = await self.llm_client.generate_code(description, "python")
            code = result["code"]  # 现在返回的是字典
            logger.info(f"Generated code using {self.llm_client.provider.value} for: {description[:50]}...")
            return code
        except Exception as e:
            logger.error(f"Failed to generate code with LLM: {e}")
            # 不再使用备用模板，而是直接抛出异常
            raise RuntimeError(f"代码生成失败: {str(e)}") from e
      # 备注: 我们不再需要备用代码生成方法，所有的代码生成都将由LLM完成
    # 如果LLM调用失败，应当抛出异常，而不是使用备用代码模板
    
    async def _execute_code_safely(self, code: str) -> Dict:
        """使用nsjail安全执行代码，并捕获详细的执行信息"""
        start_time = time.time()
        timeout = 30  # 设置超时时间为30秒
        
        try:
            # 使用NSJail执行器
            result = await self.executor.execute(code, timeout=timeout)
            exec_duration = time.time() - start_time
            
            # 计算代码的统计信息
            code_lines = code.count('\n') + 1
            code_chars = len(code)
            
            # 添加详细的执行信息
            exec_result = {
                "success": result["exit_code"] == 0,
                "output": result["stdout"],
                "error": result["stderr"] if result["exit_code"] != 0 else None,
                "error_type": self._classify_error(result) if result["exit_code"] != 0 else None,
                "duration": exec_duration,
                "exit_code": result["exit_code"],
                # 添加额外信息以丰富轨迹数据
                "code_stats": {
                    "lines": code_lines,
                    "chars": code_chars
                },
                "execution_details": {
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "timeout_setting": timeout,
                    "runtime": self.runtime_id,
                    "execution_environment": "Python Sandbox"
                }
            }
            
            # 记录执行的时间信息
            if exec_duration > 5.0:
                logger.warning(f"Code execution took {exec_duration:.2f}s which is unusually long")
            else:
                logger.debug(f"Code executed in {exec_duration:.2f}s with result: {result['exit_code']}")
                
            return exec_result
            
        except asyncio.TimeoutError:
            exec_duration = time.time() - start_time
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "error_type": ErrorType.TIMEOUT,
                "duration": exec_duration,
                "exit_code": -1,
                "code_stats": {
                    "lines": code.count('\n') + 1,
                    "chars": len(code)
                },
                "execution_details": {
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "timeout_setting": timeout,
                    "runtime": self.runtime_id,
                    "execution_environment": "Python Sandbox (Timeout)"
                }
            }
        except Exception as e:
            exec_duration = time.time() - start_time
            return {
                "success": False,
                "output": "",
                "error": f"System error: {str(e)}",
                "error_type": ErrorType.SYSTEM_ERROR,
                "duration": exec_duration,
                "exit_code": -1,
                "code_stats": {
                    "lines": code.count('\n') + 1,
                    "chars": len(code)
                },
                "execution_details": {
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "timeout_setting": timeout,
                    "runtime": self.runtime_id,
                    "execution_environment": "Python Sandbox (Error)"
                }
            }
    
    def _classify_error(self, result: Dict) -> ErrorType:
        """分类错误类型"""
        stderr = result.get("stderr", "").lower()
        
        if "syntaxerror" in stderr:
            return ErrorType.COMPILE_ERROR
        elif "timeout" in stderr:
            return ErrorType.TIMEOUT
        elif "permission" in stderr or "access" in stderr:
            return ErrorType.SYSTEM_ERROR
        else:
            return ErrorType.RUNTIME_ERROR
    
    async def _consume_tasks(self):
        """消费任务队列"""
        consumer_id = f"sandbox-{os.getpid()}"
        queue_name = "tasks:code"
        
        logger.info(f"Starting task consumer {consumer_id}")
        
        while True:
            try:
                # 读取任务
                messages = await self.redis.xreadgroup(
                    "workers", consumer_id,
                    {queue_name: ">"},
                    count=1, block=1000
                )
                
                if not messages:
                    logger.debug(f"No messages received by {consumer_id}")
                    continue
                
                logger.info(f"Received {len(messages)} message streams")
                
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        try:
                            logger.info(f"Processing message {msg_id}")
                            # 解析任务
                            task_data = json.loads(fields[b'task'].decode())
                            logger.info(f"Parsed task data: {task_data.get('task_id', 'unknown')}")
                            task = TaskSpec.from_dict(task_data)
                            
                            # 执行任务
                            logger.info(f"Executing task {task.task_id}")
                            result = await self.execute(task)
                            
                            # 保存轨迹
                            await self._save_trajectory(result)
                            
                            # 确认消息
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message {msg_id}: {e}")
                            
                            # 创建错误轨迹
                            try:
                                task_data = json.loads(fields[b'task'].decode())
                                task = TaskSpec.from_dict(task_data)
                                
                                error_result = TrajectoryResult(
                                    task_name=task.task_id,
                                    task_id=task.task_id,
                                    task_description=task.description,
                                    runtime_id=self.runtime_id,
                                    success=False,
                                    steps=[],
                                    final_result="",
                                    error_message=str(e),
                                    error_type=ErrorType.SYSTEM_ERROR,
                                    total_duration=0,
                                    metadata={}
                                )
                                
                                await self._save_trajectory(error_result)
                            except Exception as save_error:
                                logger.error(f"Failed to save error trajectory: {save_error}")
                            
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)
    
    def _acquire_file_lock(self, file_path: str) -> bool:
        """跨平台文件锁获取"""
        with self._lock_mutex:
            if file_path in self._file_locks:
                return False  # 已被锁定
            
            if HAS_FCNTL:
                # Unix系统使用fcntl
                try:
                    lock_file = file_path + ".lock"
                    fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._file_locks[file_path] = fd
                    return True
                except (OSError, IOError):
                    return False
            else:
                # Windows系统使用线程锁
                lock = threading.Lock()
                if lock.acquire(blocking=False):
                    self._file_locks[file_path] = lock
                    return True
                return False
    
    def _release_file_lock(self, file_path: str):
        """释放文件锁"""
        with self._lock_mutex:
            if file_path in self._file_locks:
                lock_obj = self._file_locks.pop(file_path)
                
                if HAS_FCNTL and isinstance(lock_obj, int):
                    # Unix系统释放fcntl锁
                    try:
                        fcntl.flock(lock_obj, fcntl.LOCK_UN)
                        os.close(lock_obj)
                        # 清理锁文件
                        lock_file = file_path + ".lock"
                        if os.path.exists(lock_file):
                            os.unlink(lock_file)
                    except (OSError, IOError):
                        pass
                elif not HAS_FCNTL and hasattr(lock_obj, 'release'):
                    # Windows系统释放线程锁
                    lock_obj.release()
    
    async def _save_trajectory(self, result: TrajectoryResult):
        """保存轨迹到集合文件（跨平台文件锁保护）"""
        output_dir = "/app/output/trajectories"
        os.makedirs(output_dir, exist_ok=True)
        
        # 集合文件路径
        collection_file = os.path.join(output_dir, "trajectories_collection.json")
        
        # 尝试获取文件锁，最多等待5秒
        max_retries = 50
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            if self._acquire_file_lock(collection_file):
                break
            await asyncio.sleep(retry_delay)
        else:
            logger.warning(f"Could not acquire file lock for {collection_file}, proceeding without lock")
        
        try:
            # 读取现有集合或创建新集合
            trajectories = []
            if os.path.exists(collection_file):
                try:
                    with open(collection_file, 'r', encoding='utf-8') as f:
                        trajectories = json.load(f)
                        # 确保trajectories是一个列表
                        if not isinstance(trajectories, list):
                            trajectories = []
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"Error reading trajectories collection: {e}")
                    # 如果文件损坏，创建新的集合
                    trajectories = []
            
            # 将新轨迹添加到集合中
            trajectories.append(result.to_dict())
            
            # 原子性写入：先写入临时文件，再重命名
            temp_file = collection_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(trajectories, f, indent=2, ensure_ascii=False)
            
            # 原子性重命名
            os.rename(temp_file, collection_file)
            
            logger.info(f"Trajectory safely added to collection: {collection_file}")
            
        except Exception as e:
            logger.error(f"Error saving trajectory: {e}")
            # 清理可能的临时文件
            temp_file = collection_file + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            raise
        finally:
            # 释放文件锁
            self._release_file_lock(collection_file)
        
        # 同时也保存单独的文件（可选）
        if self.config.get("save_individual_trajectories", False):
            individual_file = os.path.join(output_dir, f"{result.task_id}.json")
            with open(individual_file, 'w', encoding='utf-8') as f:
                f.write(result.json())
            logger.info(f"Individual trajectory saved: {individual_file}")
    
    async def _register_health(self):
        """注册健康状态"""
        await self.redis.hset("runtime_health", self.runtime_id, "healthy")
        
        # 定期更新健康状态
        asyncio.create_task(self._health_updater())
    
    async def _health_updater(self):
        """定期更新健康状态"""
        while True:
            try:
                healthy = await self.health_check()
                status = "healthy" if healthy else "unhealthy"
                await self.redis.hset("runtime_health", self.runtime_id, status)
                metrics.update_runtime_health(self.runtime_id, healthy)
                
                await asyncio.sleep(30)  # 每30秒更新
            except Exception as e:
                logger.error(f"Health update error: {e}")
                await asyncio.sleep(10)
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查Redis连接
            await self.redis.ping()
            
            # 检查nsjail可用性
            result = subprocess.run(
                ["nsjail", "--help"], 
                capture_output=True, 
                timeout=5
            )
            if result.returncode != 0:
                return False
            
            return True
        except Exception:
            return False
    
    async def cleanup(self):
        """清理资源"""
        # 清理所有文件锁
        with self._lock_mutex:
            for file_path in list(self._file_locks.keys()):
                self._release_file_lock(file_path)
        
        await self.redis.close()

async def main():
    """运行时入口"""
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
        "vllm_url": os.getenv("VLLM_URL", "http://localhost:8000"),
        # 从环境变量读取是否禁用缓存
        "disable_cache": os.getenv("DISABLE_CACHE", "").lower() in ("1", "true", "yes")
    }
    
    if config["disable_cache"]:
        logger.info("Cache disabled by environment variable DISABLE_CACHE")
    
    runtime = LightweightSandboxRuntime(config)
    
    try:
        await runtime.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await runtime.cleanup()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())