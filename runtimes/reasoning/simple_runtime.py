"""
简化的推理运行时 - 核心版本
专注于核心功能：LLM推理、工具执行、任务处理
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, ExecutionStep, ActionType
from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder
from core.utils.path_utils import get_trajectories_dir
from core.streaming.sequential_executor import SequentialStreamingExecutor
from core.memory_manager import MemoryManager
from core.trajectory_enhancer import TrajectoryEnhancer


logger = logging.getLogger(__name__)


class TrajectoryStorageMode(Enum):
    """轨迹存储模式"""
    INDIVIDUAL_FILES = "individual"
    DAILY_GROUPED = "daily_grouped"
    WEEKLY_GROUPED = "weekly_grouped"
    MONTHLY_GROUPED = "monthly_grouped"


class SimpleReasoningRuntime(RuntimeInterface):
    """
    简化的推理运行时 - 专注核心功能, 并集成高级模块
    """
    
    def __init__(self, config_manager, llm_client, toolscore_client, redis_manager=None, xml_streaming_mode: bool = False, 
                 trajectory_storage_mode: str = "daily_grouped"):
        self._runtime_id = f"simple-reasoning-{uuid.uuid4()}"
        self.config_manager = config_manager
        self.client = llm_client
        self.toolscore_client = toolscore_client
        self.xml_streaming_mode = xml_streaming_mode
        self.trajectory_storage_mode = TrajectoryStorageMode(trajectory_storage_mode)
        self.prompt_builder = ReasoningPromptBuilder(streaming_mode=xml_streaming_mode)
        self.is_initialized = False

        # 初始化高级模块
        self.memory_manager = MemoryManager(redis_manager=redis_manager)
        self.trajectory_enhancer = TrajectoryEnhancer()
        self.sequential_executor = SequentialStreamingExecutor(
            llm_client=self.client, 
            tool_executor=self.toolscore_client,
            memory_manager=self.memory_manager
        )
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    async def capabilities(self) -> List[str]:
        """获取运行时能力"""
        return ['llm_reasoning', 'tool_execution', 'xml_streaming', 'memory', 'trajectory_enhancement', 'error_recovery']
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if hasattr(self.toolscore_client, 'health_check'):
                return await self.toolscore_client.health_check()
            return True
        except Exception:
            return False
    
    async def initialize(self):
        """初始化运行时"""
        logger.info("🚀 初始化Simple Reasoning Runtime")
        if not self.client:
            raise RuntimeError("LLM客户端未配置")
        if not self.toolscore_client:
            raise RuntimeError("工具客户端未配置")
        self.is_initialized = True
        logger.info("✅ Simple Reasoning Runtime 初始化完成")
    
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行任务"""
        logger.info(f"🧠 开始执行任务: {task.description}")
        if not self.is_initialized:
            await self.initialize()
        
        if self.xml_streaming_mode:
            return await self._execute_xml_streaming(task)
        else:
            # 保留标准模式作为备选，但主要流程是XML流
            return await self._execute_standard(task)
    
    async def _execute_xml_streaming(self, task: TaskSpec) -> TrajectoryResult:
        """XML Streaming执行模式 - 已集成高级模块"""
        logger.info(f"🎯 XML Streaming模式 - 任务: {task.description}")
        start_time = time.time()
        session_id = f"session_{task.task_id}_{int(start_time)}"
        raw_llm_response = ""
        final_response = ""

        try:
            # 1. 从MemoryManager获取上下文
            logger.info(f"🧠 正在为任务 {task.task_id} 检索记忆上下文...")
            memory_context = await self.memory_manager.generate_context_summary(session_id)
            
            # 2. 构建prompt并从LLM获取初始的XML计划
            available_tools = await self._get_available_tools()
            tool_descriptions = await self._get_tool_descriptions()
            messages = self.prompt_builder.build_prompt(
                task_description=task.description,
                available_tools=available_tools,
                tool_descriptions=tool_descriptions,
                streaming_mode=True,
                execution_context={"memory_context": memory_context}
            )
            raw_llm_response = await self.client._call_api(messages)
            logger.info(f"📥 获得初始XML计划 (长度: {len(raw_llm_response)})")

            # 3. 调用Sequential执行器来执行这个XML计划
            execution_result = await self.sequential_executor.execute_streaming_task(
                initial_response=raw_llm_response,
                task_description=task.description,
                max_steps=task.max_steps or 10,
                session_id=session_id
            )
            success = execution_result.get('success', False)
            final_result = execution_result.get('final_answer', '未能提取最终答案。')
            final_response = execution_result.get('final_response', raw_llm_response)
            
            # 构建包含原始响应的metadata
            metadata = execution_result.copy()
            metadata.update({
                'raw_response': final_response,
                'response_length': len(final_response),
                'initial_llm_response': raw_llm_response
            })

        except Exception as e:
            logger.error(f"任务执行过程中发生顶层异常: {e}", exc_info=True)
            success = False
            final_result = f"执行失败: {str(e)}"
            # 如果在sequential执行之前发生异常，使用原始LLM响应
            if not final_response:
                final_response = raw_llm_response
            metadata = {'error': str(e), 'raw_llm_response': raw_llm_response, 'raw_response': final_response, 'response_length': len(final_response)}

        # 4. 直接输出XML格式数据
        total_duration = time.time() - start_time
        
        # 构建XML输出数据格式
        xml_output = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task.task_id,
            "task_description": task.description,
            "duration": total_duration,
            "success": success,
            "final_result": "任务执行完成，已输出原始XML轨迹格式",
            "raw_response": final_response,
            "response_length": len(final_response)
        }
        
        # 输出到控制台
        print(json.dumps(xml_output, ensure_ascii=False, indent=2))
        
        # 保存到文件
        await self._save_xml_output(xml_output)
        
        # 构建简单的返回对象
        from core.interfaces import TrajectoryResult
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id, 
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],  
            success=success,
            final_result="任务执行完成，已输出原始XML轨迹格式",
            total_duration=total_duration,
            metadata=metadata
        )
        
        return trajectory
    
    async def _execute_standard(self, task: TaskSpec) -> TrajectoryResult:
        """标准执行模式 (作为备用)"""
        logger.warning("执行标准（ReAct）模式，此模式功能有限。")
        # ... 此处省略未更改的标准模式代码 ...
        return await super()._execute_standard(task) # 假设有一个基类实现

    async def _get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        try:
            tools = await self.toolscore_client.get_available_tools()
            return [str(tool) for tool in tools] if isinstance(tools, list) else []
        except Exception as e:
            logger.warning(f"获取工具列表失败: {e}")
            return []
    
    async def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        # ... 此处省略未更改的代码 ...
        return "工具描述获取失败"

    def _detect_success(self, response: str) -> bool:
        """检测XML响应是否成功"""
        response_lower = response.lower()
        return ('<answer>' in response_lower) and ('error>' not in response_lower)
    
    def _get_trajectory_file_path(self, task_id: str, is_raw: bool = False) -> str:
        """根据存储模式获取轨迹文件路径"""
        # ... 此处省略未更改的代码 ...
        out_dir = get_trajectories_dir()
        date_str = datetime.now().strftime("%Y-%m-%d")
        group_dir = os.path.join(out_dir, "grouped", date_str)
        if is_raw:
            return os.path.join(group_dir, f"raw_trajectories_{date_str}.jsonl")
        else:
            return os.path.join(group_dir, f"trajectories_{date_str}.jsonl")
    

    async def _save_xml_output(self, xml_output):
        """保存XML输出数据到JSONL文件"""
        file_path = self._get_trajectory_file_path(xml_output['task_id'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(xml_output, ensure_ascii=False) + '\n')
        
        logger.info(f"保存XML数据到: {file_path}")

    async def cleanup(self):
        """清理资源"""
        logger.info("🧹 清理Simple Reasoning Runtime资源")
        if self.toolscore_client and hasattr(self.toolscore_client, 'close'):
            await self.toolscore_client.close()
        self.is_initialized = False
        logger.info("✅ 资源清理完成")