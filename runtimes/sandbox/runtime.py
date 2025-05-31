import asyncio
import json
import logging
import os
import subprocess
import time
from typing import Dict, Any, Optional

import aioredis
import httpx

from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, ErrorType
from core.cache import TemplateCache
from core.metrics import EnhancedMetrics

logger = logging.getLogger(__name__)
metrics = EnhancedMetrics()

class NSJailExecutor:
    """NSJail执行器"""
    
    def __init__(self):
        self.base_cmd = [
            "nsjail",
            "--mode", "o",
            "--chroot", "/tmp/sandbox",
            "--user", "nobody",
            "--group", "nogroup",
            "--time_limit", "30",
            "--max_cpus", "1",
            "--rlimit_as", "128",
            "--rlimit_cpu", "10",
            "--rlimit_fsize", "1",
            "--disable_proc",
            "--"
        ]
    
    async def execute(self, code: str, timeout: int = 30) -> Dict:
        """执行代码"""
        # 创建临时文件
        script_path = f"/tmp/script_{int(time.time())}.py"
        
        try:
            with open(script_path, 'w') as f:
                f.write(code)
            
            # 构建命令
            cmd = self.base_cmd + ["python3", script_path]
            
            # 执行
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            
            return {
                "exit_code": process.returncode,
                "stdout": stdout.decode('utf-8', errors='ignore'),
                "stderr": stderr.decode('utf-8', errors='ignore')
            }
            
        except asyncio.TimeoutError:
            if process:
                process.kill()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Execution timeout"
            }
        finally:
            # 清理临时文件
            if os.path.exists(script_path):
                os.remove(script_path)

class LightweightSandboxRuntime(RuntimeInterface):
    """轻量级沙盒运行时"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.runtime_id = f"sandbox-{os.getpid()}"
        self.redis = None
        self.cache = None
        self.executor = NSJailExecutor()
        self.vllm_client = httpx.AsyncClient(base_url=config.get("vllm_url"))
        
    async def start(self):
        """启动运行时"""
        logger.info(f"Starting {self.runtime_id}")
        
        # 连接Redis
        self.redis = aioredis.from_url(self.config["redis_url"])
        
        # 初始化缓存
        self.cache = TemplateCache(self.redis)
        
        # 注册健康状态
        await self._register_health()
        
        # 启动指标服务器
        metrics.start_http_server(8080)
        
        # 开始消费任务
        await self._consume_tasks()
    
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行代码任务"""
        start_time = time.time()
        
        try:
            # 记录任务开始
            metrics.record_task_start(task.task_type.value)
            
            # 检查缓存
            cache_key = f"code:{task.task_type.value}:{hash(task.description)}"
            cached_code = await self.cache.get(cache_key)
            
            if cached_code:
                logger.info(f"Cache hit for task {task.task_id}")
                metrics.record_cache_hit()
                code = cached_code
            else:
                logger.info(f"Cache miss for task {task.task_id}")
                metrics.record_cache_miss()
                
                # 生成代码
                code = await self._generate_code(task.description)
                
                # 缓存代码
                await self.cache.set(cache_key, code, ttl=3600)
            
            # 执行代码
            execution_result = await self._execute_code_safely(code)
            
            # 构建轨迹结果
            result = TrajectoryResult(
                task_id=task.task_id,
                task_type=task.task_type,
                success=execution_result["success"],
                steps=[
                    {
                        "action": "generate_code",
                        "input": task.description,
                        "output": code,
                        "timestamp": start_time
                    },
                    {
                        "action": "execute_code",
                        "input": code,
                        "output": execution_result["output"],
                        "timestamp": time.time()
                    }
                ],
                final_output=execution_result["output"],
                error_message=execution_result.get("error"),
                error_type=execution_result.get("error_type"),
                duration=time.time() - start_time,
                metadata={
                    "runtime_id": self.runtime_id,
                    "cached": cached_code is not None,
                    "exit_code": execution_result.get("exit_code")
                }
            )
            
            # 记录指标
            if result.success:
                metrics.record_task_completion(task.task_type.value, result.duration)
            else:
                metrics.record_task_failure(task.task_type.value, result.error_type.value if result.error_type else "unknown")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing task {task.task_id}: {e}")
            metrics.record_task_failure(task.task_type.value, "system_error")
            
            return TrajectoryResult(
                task_id=task.task_id,
                task_type=task.task_type,
                success=False,
                steps=[],
                final_output="",
                error_message=str(e),
                error_type=ErrorType.SYSTEM_ERROR,
                duration=time.time() - start_time,
                metadata={"runtime_id": self.runtime_id}
            )
    
    async def _generate_code(self, description: str) -> str:
        """生成代码"""
        # 简单的模板匹配
        if "fibonacci" in description.lower():
            return """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# 计算斐波那契数列
for i in range(10):
    print(f"fibonacci({i}) = {fibonacci(i)}")
"""
        elif "factorial" in description.lower():
            return """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n-1)

# 计算阶乘
result = factorial(5)
print(f"factorial(5) = {result}")
"""
        elif "prime" in description.lower():
            return """
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

def find_primes(limit):
    return [i for i in range(2, limit) if is_prime(i)]

# 找出100以内的质数
primes = find_primes(100)
print(f"Primes up to 100: {primes}")
print(f"Count: {len(primes)}")
"""
        else:
            # 通用模板
            return f"""
# 生成的代码用于: {description}
def solution():
    # TODO: 根据描述实现具体逻辑
    return "This is a placeholder solution for: {description}"

result = solution()
print(result)
"""
    
    async def _execute_code_safely(self, code: str) -> Dict:
        """使用nsjail安全执行代码"""
        start_time = time.time()
        
        try:
            # 使用NSJail执行器
            result = await self.executor.execute(code, timeout=30)
            
            return {
                "success": result["exit_code"] == 0,
                "output": result["stdout"],
                "error": result["stderr"] if result["exit_code"] != 0 else None,
                "error_type": self._classify_error(result) if result["exit_code"] != 0 else None,
                "duration": time.time() - start_time,
                "exit_code": result["exit_code"]
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "output": "",
                "error": "Execution timeout",
                "error_type": ErrorType.TIMEOUT,
                "duration": time.time() - start_time,
                "exit_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "error_type": ErrorType.SYSTEM_ERROR,
                "duration": time.time() - start_time,
                "exit_code": -1
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
                    continue
                
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        try:
                            # 解析任务
                            task_data = json.loads(fields[b'task'].decode())
                            task = TaskSpec.from_dict(task_data)
                            
                            # 执行任务
                            result = await self.execute(task)
                            
                            # 保存轨迹
                            await self._save_trajectory(result)
                            
                            # 确认消息
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message {msg_id}: {e}")
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)
    
    async def _save_trajectory(self, result: TrajectoryResult):
        """保存轨迹到文件"""
        output_dir = "/app/output/trajectories"
        os.makedirs(output_dir, exist_ok=True)
        
        file_path = os.path.join(output_dir, f"{result.task_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(result.json())
        
        logger.info(f"Trajectory saved: {file_path}")
    
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
        await self.redis.close()

async def main():
    """运行时入口"""
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
        "vllm_url": os.getenv("VLLM_URL", "http://localhost:8000")
    }
    
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