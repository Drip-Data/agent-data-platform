import asyncio
import json
import logging
import os
import time
import httpx
from typing import Dict, Set
import redis.asyncio as redis
from core.interfaces.task_interfaces import TaskSpec, TaskType
from core.cache.cache import TemplateCache
from core.metrics.metrics import EnhancedMetrics

logger = logging.getLogger(__name__)

class EnhancedTaskDispatcher:
    """增强版任务分发器 - 集成智能工具选择"""
    
    def __init__(self, redis_url: str, task_file: str = "tasks.jsonl"):
        self.redis = redis.from_url(redis_url)
        self.task_file = task_file
        self.cache = TemplateCache(self.redis)
        self.metrics = EnhancedMetrics()
        
        # 工具管理服务配置
        self.tool_service_url = os.getenv("TOOL_SERVICE_URL", "http://toolscore:8083")
        
        # 队列映射表 - 支持环境变量配置
        default_mapping = {
            TaskType.CODE: "tasks:code",
            TaskType.WEB: "tasks:web", 
            TaskType.REASONING: "tasks:reasoning"
        }
        
        # 从环境变量读取队列映射配置
        queue_mapping_env = os.getenv("QUEUE_MAPPING")
        if queue_mapping_env:
            try:
                custom_mapping = json.loads(queue_mapping_env)
                # 转换字符串键为TaskType枚举
                self.queue_mapping = {}
                for task_type_str, queue_name in custom_mapping.items():
                    task_type = TaskType(task_type_str)
                    self.queue_mapping[task_type] = queue_name
                logger.info(f"使用自定义队列映射: {self.queue_mapping}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"解析QUEUE_MAPPING环境变量失败，使用默认配置: {e}")
                self.queue_mapping = default_mapping
        else:
            self.queue_mapping = default_mapping
        
    async def _call_tool_selector_service(self, task: TaskSpec) -> Dict:
        """调用工具管理服务进行智能推荐"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.tool_service_url}/api/tools/intelligent-recommend",
                    json={
                        "task_description": task.description,
                        "task_type": task.task_type.value,
                        "constraints": task.constraints,
                        "max_steps": task.max_steps
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"工具推荐服务返回错误: {response.status_code}")
                    return self._get_fallback_tools(task.task_type)
                    
        except Exception as e:
            logger.error(f"调用工具推荐服务失败: {e}")
            return self._get_fallback_tools(task.task_type)
    
    def _get_fallback_tools(self, task_type: TaskType) -> Dict:
        """获取备选工具推荐 - 支持环境变量配置"""
        # 默认备选工具映射
        default_fallback = {
            TaskType.CODE: ["python_executor"],
            TaskType.WEB: ["browser", "web_search"],
            TaskType.REASONING: ["browser", "python_executor"]
        }
        
        # 从环境变量读取备选工具配置
        fallback_env = os.getenv("FALLBACK_TOOLS_MAPPING")
        if fallback_env:
            try:
                custom_fallback = json.loads(fallback_env)
                # 转换字符串键为TaskType枚举
                fallback_mapping = {}
                for task_type_str, tools in custom_fallback.items():
                    task_type_enum = TaskType(task_type_str)
                    fallback_mapping[task_type_enum] = tools
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"解析FALLBACK_TOOLS_MAPPING环境变量失败，使用默认配置: {e}")
                fallback_mapping = default_fallback
        else:
            fallback_mapping = default_fallback
        
        return {
            "recommended_tools": fallback_mapping.get(task_type, ["python_executor"]),
            "confidence": float(os.getenv("FALLBACK_CONFIDENCE", "0.5")),
            "reason": "使用备选工具配置",
            "strategy": "fallback"
        }
    
    async def _enhance_task_with_tools(self, task: TaskSpec) -> TaskSpec:
        """为任务增强工具选择"""
        # 如果已经有明确的工具指定，且不是auto，就保持不变
        if task.expected_tools and task.expected_tools != ["auto"]:
            logger.debug(f"任务 {task.task_id} 已有明确工具: {task.expected_tools}")
            return task
        
        # 调用智能工具推荐
        tool_recommendation = await self._call_tool_selector_service(task)
        
        # 更新任务的工具配置
        task.expected_tools = tool_recommendation["recommended_tools"]
        
        # 添加推荐元数据
        if "tool_metadata" not in task.constraints:
            task.constraints["tool_metadata"] = {}
            
        task.constraints["tool_metadata"].update({
            "recommendation_confidence": tool_recommendation.get("confidence", 0.0),
            "recommended_at": time.time(),
            "recommendation_reason": tool_recommendation.get("reason", ""),
            "recommendation_strategy": tool_recommendation.get("strategy", "intelligent"),
            "original_tools": task.expected_tools if task.expected_tools != ["auto"] else []
        })
        
        logger.info(f"为任务 {task.task_id} 推荐工具: {task.expected_tools} (置信度: {tool_recommendation.get('confidence', 0.0)})")
        
        return task
    
    async def _load_and_dispatch_tasks(self):
        """加载并按类型分发任务 - 集成智能工具选择"""
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
                            
                            # 🔧 智能工具增强
                            task = await self._enhance_task_with_tools(task)
                            
                            # 分发到对应队列
                            queue_name = self.queue_mapping.get(task.task_type)
                            if queue_name:
                                await self.redis.xadd(
                                    queue_name,
                                    {
                                        "task": task.json(),
                                        "submitted_at": time.time(),
                                        "priority": task.priority,
                                        "enhanced_with_tools": True  # 标记已进行工具增强
                                    }
                                )
                                
                                self.metrics.record_task_submitted(
                                    task.task_type.value,
                                    queue_name.split(":")[1]
                                )
                                processed_tasks.add(task.task_id)
                                
                                logger.info(f"分发增强任务 {task.task_id} 到 {queue_name}")
                                
                                # 记录工具推荐统计
                                tool_metadata = task.constraints.get("tool_metadata", {})
                                logger.debug(f"工具推荐日志: {json.dumps({
                                    'task_id': task.task_id,
                                    'recommended_tools': task.expected_tools,
                                    'confidence': tool_metadata.get('recommendation_confidence', 0.0),
                                    'strategy': tool_metadata.get('recommendation_strategy', 'unknown')
                                })}")
                                
                            else:
                                logger.error(f"未找到任务类型 {task.task_type} 对应的队列")
                                
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.error(f"第 {line_number} 行任务解析失败: {e}")
                        
                        last_position = line_number
                
                await asyncio.sleep(5)  # 检查新任务间隔
                
            except Exception as e:
                logger.error(f"任务加载过程中出错: {e}")
                await asyncio.sleep(10)
    
    # ... 其他方法保持与原Dispatcher相同 ...
    async def start(self):
        """启动分发器"""
        logger.info("启动增强版任务分发器（集成智能工具选择）...")
        
        # 启动metrics服务器
        self.metrics.start_server()
        
        # 并行启动各个组件
        await asyncio.gather(
            self._load_and_dispatch_tasks(),
            self._monitor_queues(),
            self._monitor_pending_tasks()
        )
    
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
                logger.error(f"监控队列时出错: {e}")
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
                logger.error(f"监控挂起任务时出错: {e}")
                await asyncio.sleep(30)

async def main():
    """增强分发器主程序"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    task_file = os.getenv("TASK_FILE", "tasks.jsonl")
    
    dispatcher = EnhancedTaskDispatcher(redis_url, task_file)
    
    try:
        await dispatcher.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        await dispatcher.redis.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main()) 