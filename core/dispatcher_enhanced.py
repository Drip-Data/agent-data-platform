import asyncio
import logging
import os
from typing import Dict, Any, Optional
import xml.etree.ElementTree as ET
from core.orchestrator import Orchestrator
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
    新增了处理LLM直接输出并调度到Orchestrator的能力。
    """
    
    def __init__(self,
                 redis_url: str,
                 config_manager: ConfigManager,
                 toolscore_client: ToolScoreClient,
                 queue_monitor: QueueMonitor,
                 task_loader: TaskLoader,
                 task_enhancer: TaskEnhancer,
                 task_distributor: TaskDistributor,
                 orchestrator: Orchestrator,  # 注入Orchestrator
                 queue_mapping: Dict[TaskType, str]
                ):
        self.config_manager = config_manager
        self.toolscore_client = toolscore_client
        self.queue_monitor = queue_monitor
        self.task_loader = task_loader
        self.task_enhancer = task_enhancer
        self.task_distributor = task_distributor
        self.orchestrator = orchestrator  # 持有Orchestrator实例
        self.queue_mapping = queue_mapping
        
        logger.info(f"✅ TaskProcessingCoordinator 配置加载完成 - 队列映射: {self.queue_mapping}")

    def _find_last_instruction_block(self, xml_string: str) -> Optional[str]:
        """
        从XML字符串末尾向前查找并返回紧邻 <execute_tools /> 之前的指令块。
        支持V4设计的三种格式：
        1. 单工具调用: <server_name><tool_name>...</tool_name></server_name>
        2. 并行执行: <parallel>...</parallel>
        3. 串行执行: <sequential>...</sequential>
        """
        execute_pos = xml_string.rfind('<execute_tools />')
        if execute_pos == -1:
            return None

        content_before_trigger = xml_string[:execute_pos].strip()

        # 正则表达式匹配三种可能的指令块
        # 1. <parallel>...</parallel>
        # 2. <sequential>...</sequential>
        # 3. <some_server><some_tool>...</some_tool></some_server>
        # 我们需要找到最后一个完整的块
        
        # 使用正则表达式查找所有可能的块的结束标签位置
        # 模式解释:
        # (</(parallel|sequential)>) - 匹配 </parallel> 或 </sequential>
        # | - 或
        # (</([a-zA-Z0-9_]+)></([a-zA-Z0-9_]+)>) - 匹配 </tool></server>
        patterns = [
            r'<(parallel)>.+?</\1>',
            r'<(sequential)>.+?</\1>',
            r'<([a-zA-Z0-9_]+_server)><([a-zA-Z0-9_]+)>.+?</\2></\1>'
        ]
        
        last_match = None
        
        for pattern in patterns:
            # We search from right to left
            for match in re.finditer(pattern, content_before_trigger, re.DOTALL):
                if last_match is None or match.end() > last_match.end():
                    last_match = match
        
        if last_match:
            instruction_block = last_match.group(0)
            logger.debug(f"提取到的指令块: {instruction_block}")
            return instruction_block
        else:
            logger.warning("在 execute_tools 之前未找到符合V4格式的指令块")
            return None


    async def dispatch_and_execute_llm_output(self, llm_output: str) -> Optional[str]:
        """
        V4设计的核心流式交互处理器：
        1. 监听 <execute_tools /> 触发信号
        2. 提取紧邻的指令块 (单工具/parallel/sequential)  
        3. 通过Orchestrator执行指令
        4. 返回符合V4规范的结果XML
        """
        if '<execute_tools />' not in llm_output:
            logger.debug("未检测到执行触发器，跳过处理")
            return None

        logger.info("🚀 V4流式交互触发 - 开始指令解析...")
        
        instruction_block = self._find_last_instruction_block(llm_output)
        if not instruction_block:
            error_result = '<result index="0">Error: No valid instruction block found before execute_tools trigger.</result>'
            logger.warning("指令块提取失败")
            return error_result
            
        logger.info(f"📋 V4指令块解析成功:\n{instruction_block}")
        
        try:
            # 执行指令并获取V4格式的结果
            results = await self.orchestrator.execute_instruction(instruction_block)
            logger.info(f"✅ 指令执行完成，结果长度: {len(results) if results else 0}")
            return results
            
        except Exception as e:
            logger.error(f"❌ 指令执行异常: {e}", exc_info=True)
            return f'<result index="0">Error: Instruction execution failed. {str(e)}</result>'

    async def _process_single_task(self, task: TaskSpec):
        """处理单个任务的增强和分发流程"""
        task = await self.task_enhancer.enhance_task_with_tools(task)
        
        queue_name = self.queue_mapping.get(task.task_type)
        if queue_name:
            await self.task_distributor.distribute_task(task, queue_name)
            logger.info(f"分发增强任务 {task.task_id} 到 {queue_name}")
        else:
            logger.error(f"未找到任务类型 {task.task_type} 对应的队列")

    async def _coordinate_task_processing(self):
        """协调任务的加载、增强和分发"""
        async for task in self.task_loader.load_new_tasks():
            await self._process_single_task(task)
            await asyncio.sleep(0.1)

    async def start(self):
        """启动协调器"""
        logger.info("启动任务处理协调器...")
        
        await asyncio.gather(
            self._coordinate_task_processing(),
            self.queue_monitor.start()
        )

async def main():
    """主程序入口，负责依赖注入和启动"""
    config_manager = ConfigManager()
    redis_url = config_manager.get_redis_url()
    task_file = config_manager.get_task_file_path()
    routing_config = config_manager.load_routing_config()
    queue_mapping = {
        TaskType(task_type_str.lower()): queue_name
        for task_type_str, queue_name in routing_config.task_type_mapping.items()
    }
    
    toolscore_client = ToolScoreClient(config_manager)
    queue_monitor = QueueMonitor(redis_url)
    task_loader = TaskLoader(task_file)
    task_enhancer = TaskEnhancer(toolscore_client)
    from core.metrics import EnhancedMetrics
    metrics = EnhancedMetrics()
    task_distributor = TaskDistributor(redis_url, metrics)
    
    # 实例化Orchestrator (注意：Orchestrator自身也需要依赖)
    # 这是一个临时的实例化，后续需要完善Orchestrator的依赖注入
    from core.tool_schema_manager import ToolSchemaManager
    from core.unified_tool_manager import UnifiedToolManager
    from core.llm_client import LLMClient
    tool_schema_manager = ToolSchemaManager(config_manager)
    unified_tool_manager = UnifiedToolManager(config_manager, tool_schema_manager)
    # 临时的LLMClient，可能很多功能无法使用
    llm_client = LLMClient(config_manager=config_manager, tool_manager=unified_tool_manager)

    orchestrator = Orchestrator(
        tool_manager=unified_tool_manager,
        llm_client=llm_client, # Orchestrator可能需要LLMClient来进行某些操作
        redis_manager=None, # 临时传入None
        metrics_manager=metrics
    )

    coordinator = TaskProcessingCoordinator(
        redis_url=redis_url,
        config_manager=config_manager,
        toolscore_client=toolscore_client,
        queue_monitor=queue_monitor,
        task_loader=task_loader,
        task_enhancer=task_enhancer,
        task_distributor=task_distributor,
        orchestrator=orchestrator, # 注入Orchestrator实例
        queue_mapping=queue_mapping
    )
    
    try:
        await coordinator.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        pass
