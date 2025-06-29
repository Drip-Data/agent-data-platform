"""
简化的推理运行时 - 核心版本
专注于核心功能：LLM推理、工具执行、任务处理
移除所有冗余和可选增强功能
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

logger = logging.getLogger(__name__)


class TrajectoryStorageMode(Enum):
    """轨迹存储模式"""
    INDIVIDUAL_FILES = "individual"  # 每个任务单独文件
    DAILY_GROUPED = "daily_grouped"  # 按日期分组
    WEEKLY_GROUPED = "weekly_grouped"  # 按周分组
    MONTHLY_GROUPED = "monthly_grouped"  # 按月分组


class SimpleReasoningRuntime(RuntimeInterface):
    """简化的推理运行时 - 专注核心功能"""
    
    def __init__(self, config_manager, llm_client, toolscore_client, xml_streaming_mode: bool = False, 
                 trajectory_storage_mode: str = "daily_grouped"):
        self._runtime_id = f"simple-reasoning-{uuid.uuid4()}"
        self.config_manager = config_manager
        self.client = llm_client
        self.toolscore_client = toolscore_client
        self.xml_streaming_mode = xml_streaming_mode
        
        # 轨迹存储配置
        self.trajectory_storage_mode = TrajectoryStorageMode(trajectory_storage_mode)
        
        # 初始化提示构建器
        self.prompt_builder = ReasoningPromptBuilder(streaming_mode=xml_streaming_mode)
        
        # 最小化状态管理
        self.is_initialized = False
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    async def capabilities(self) -> List[str]:
        """获取运行时能力"""
        return ['llm_reasoning', 'tool_execution', 'xml_streaming']
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 简单的客户端可用性检查
            if hasattr(self.toolscore_client, 'health_check'):
                return await self.toolscore_client.health_check()
            return True
        except Exception:
            return False
    
    async def initialize(self):
        """初始化运行时"""
        logger.info("🚀 初始化Simple Reasoning Runtime")
        
        # 简单的初始化：只检查必要组件
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
        
        # XML Streaming模式
        if self.xml_streaming_mode:
            return await self._execute_xml_streaming(task)
        
        # 标准执行模式
        return await self._execute_standard(task)
    
    async def _execute_xml_streaming(self, task: TaskSpec) -> TrajectoryResult:
        """XML Streaming执行模式"""
        logger.info(f"🎯 XML Streaming模式 - 任务: {task.description}")
        
        start_time = time.time()
        success = False
        raw_llm_response = ""
        
        try:
            # 构建XML streaming提示
            available_tools = await self._get_available_tools()
            tool_descriptions = await self._get_tool_descriptions()
            
            # 使用提示构建器生成XML流式提示
            messages = self.prompt_builder.build_prompt(
                task_description=task.description,
                available_tools=available_tools,
                tool_descriptions=tool_descriptions,
                streaming_mode=True
            )
            
            # 调用LLM获取原始响应
            logger.info("🤖 调用LLM获取XML响应...")
            raw_llm_response = await self.client._call_api(messages)
            logger.info(f"📥 获得原始响应 (长度: {len(raw_llm_response)})")
            
            # 输出原始轨迹
            print("\n" + "="*50)
            print("原始轨迹输出:")
            print("="*50)
            print(raw_llm_response)
            print("="*50 + "\n")
            
            # 简单的成功检测
            success = self._detect_success(raw_llm_response)
            final_result = "任务执行完成，已输出原始XML轨迹格式" if success else "任务执行存在问题，请检查输出"
            
        except Exception as e:
            logger.error(f"XML streaming执行失败: {e}")
            raw_llm_response = f"<error>执行失败: {str(e)}</error>"
            success = False
            final_result = f"执行失败: {str(e)}"
        
        total_duration = time.time() - start_time
        
        # 创建轨迹结果
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id,
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],  # XML模式不使用传统步骤
            success=success,
            final_result=final_result,
            total_duration=total_duration,
            metadata={
                'output_format': 'raw_xml_streaming',
                'runtime_id': self._runtime_id,
                'raw_llm_response': raw_llm_response,
                'response_length': len(raw_llm_response)
            }
        )
        
        # 保存轨迹
        await self._save_trajectory(trajectory)
        return trajectory
    
    async def _execute_standard(self, task: TaskSpec) -> TrajectoryResult:
        """标准执行模式"""
        logger.info("🔄 标准执行模式")
        
        start_time = time.time()
        steps = []
        success = False
        
        try:
            # 获取工具信息
            available_tools = await self._get_available_tools()
            tool_descriptions = await self._get_tool_descriptions()
            
            # 执行主循环
            max_steps = task.max_steps or 5
            for step_id in range(1, max_steps + 1):
                logger.info(f"🔄 执行步骤 {step_id}/{max_steps}")
                
                # 获取LLM推理结果
                action_result = await self._get_llm_action(
                    task, steps, available_tools, tool_descriptions
                )
                
                # 执行工具调用
                step_result = await self._execute_tool_step(action_result, step_id)
                steps.append(step_result)
                
                # 检查完成条件
                if step_result.success and self._should_complete(action_result, step_result):
                    success = True
                    break
                
                # 检查失败条件
                if not step_result.success and step_id >= 3:
                    break
            
            final_result = self._generate_final_result(steps, success)
            
        except Exception as e:
            logger.error(f"标准执行失败: {e}")
            final_result = f"任务执行失败: {str(e)}"
        
        total_duration = time.time() - start_time
        
        # 创建轨迹结果
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id,
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=steps,
            success=success,
            final_result=final_result,
            total_duration=total_duration,
            metadata={'runtime_id': self._runtime_id}
        )
        
        await self._save_trajectory(trajectory)
        return trajectory
    
    async def _get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        try:
            tools = await self.toolscore_client.get_available_tools()
            if isinstance(tools, list):
                return [str(tool) for tool in tools]
            return []
        except Exception as e:
            logger.warning(f"获取工具列表失败: {e}")
            return []
    
    async def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        try:
            tools = await self._get_available_tools()
            if not tools:
                return "暂无可用工具"
            
            # 简单的工具描述
            descriptions = []
            for tool in tools:
                descriptions.append(f"- **{tool}**: 可用工具")
            
            return "\n".join(descriptions)
        except Exception as e:
            logger.warning(f"获取工具描述失败: {e}")
            return "工具描述获取失败"
    
    
    async def _get_llm_action(self, task: TaskSpec, steps: List[ExecutionStep], available_tools: List[str], tool_descriptions: str) -> Dict[str, Any]:
        """获取LLM推理动作"""
        try:
            # 构建标准推理提示
            serializable_steps = [self._step_to_dict(step) for step in steps]
            
            # 使用提示构建器生成标准提示
            prompt = self.prompt_builder.build_prompt(
                task_description=task.description,
                available_tools=available_tools,
                tool_descriptions=tool_descriptions,
                previous_steps=serializable_steps,
                streaming_mode=False
            )
            response = await self.client._call_api(prompt)
            
            # 解析响应
            return self._parse_llm_response(response)
            
        except Exception as e:
            logger.error(f"LLM推理失败: {e}")
            return {
                "thinking": f"LLM调用失败: {str(e)}",
                "action": "error",
                "tool_id": None,
                "parameters": {},
                "confidence": 0.0
            }
    
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应"""
        try:
            import re
            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "thinking": response,
                    "action": "complete_task",
                    "tool_id": None,
                    "parameters": {},
                    "confidence": 0.5
                }
        except Exception as e:
            logger.warning(f"响应解析失败: {e}")
            return {
                "thinking": f"解析失败: {response[:200]}",
                "action": "error",
                "tool_id": None,
                "parameters": {},
                "confidence": 0.0
            }
    
    async def _execute_tool_step(self, action_result: Dict[str, Any], step_id: int) -> ExecutionStep:
        """执行工具步骤"""
        start_time = time.time()
        
        action = action_result.get('action')
        tool_id = action_result.get('tool_id')
        params = action_result.get('parameters', {})
        thinking = action_result.get('thinking', '')
        
        # 特殊处理：完成任务
        if action == 'complete_task':
            observation = "任务已完成"
            success = True
        elif tool_id and action:
            # 执行工具调用
            try:
                result = await self.toolscore_client.execute_tool(
                    tool_id=tool_id,
                    action=action,
                    parameters=params
                )
                success = result.get('success', False)
                observation = str(result.get('result', ''))
                if not success:
                    observation = f"工具执行失败: {result.get('error', '未知错误')}"
            except Exception as e:
                success = False
                observation = f"工具调用异常: {str(e)}"
        else:
            success = False
            observation = f"无效的工具调用: tool_id={tool_id}, action={action}"
        
        duration = time.time() - start_time
        
        return ExecutionStep(
            step_id=step_id,
            action_type=ActionType.TOOL_CALL,
            action_params=params,
            observation=observation,
            success=success,
            thinking=thinking,
            execution_code=json.dumps({"action": action, "tool_id": tool_id, "parameters": params}),
            timestamp=time.time(),
            duration=duration
        )
    
    def _should_complete(self, action_result: Dict[str, Any], step_result: ExecutionStep) -> bool:
        """判断是否应该完成任务"""
        # 简单的完成检测
        action = action_result.get('action')
        return action == 'complete_task' and step_result.success
    
    def _generate_final_result(self, steps: List[ExecutionStep], success: bool) -> str:
        """生成最终结果"""
        if success:
            if steps and steps[-1].observation:
                return f"任务完成。{steps[-1].observation}"
            return "任务已完成。"
        else:
            failed_steps = [step for step in steps if not step.success]
            if failed_steps:
                return f"任务失败。最后错误: {failed_steps[-1].observation}"
            return "任务执行失败。"
    
    def _step_to_dict(self, step: ExecutionStep) -> Dict[str, Any]:
        """将步骤转换为字典"""
        return {
            'step_id': step.step_id,
            'success': step.success,
            'observation': step.observation,
            'thinking': getattr(step, 'thinking', ''),
            'action_type': step.action_type.value if step.action_type else 'unknown'
        }
    
    def _detect_success(self, response: str) -> bool:
        """检测XML响应是否成功"""
        response_lower = response.lower()
        return (
            '<answer>' in response_lower or
            ('<think>' in response_lower and 'error>' not in response_lower)
        )
    
    def _get_trajectory_file_path(self, task_id: str, is_raw: bool = False) -> str:
        """根据存储模式获取轨迹文件路径"""
        out_dir = get_trajectories_dir()
        now = datetime.now()
        
        if self.trajectory_storage_mode == TrajectoryStorageMode.INDIVIDUAL_FILES:
            # 原有的单独文件模式
            return os.path.join(out_dir, f"{task_id}_raw.txt" if is_raw else "trajectories_collection.json")
        
        elif self.trajectory_storage_mode == TrajectoryStorageMode.DAILY_GROUPED:
            date_str = now.strftime("%Y-%m-%d")
            group_dir = os.path.join(out_dir, "grouped", date_str)
            if is_raw:
                return os.path.join(group_dir, f"raw_trajectories_{date_str}.jsonl")
            else:
                return os.path.join(group_dir, f"trajectories_{date_str}.jsonl")
        
        elif self.trajectory_storage_mode == TrajectoryStorageMode.WEEKLY_GROUPED:
            year, week, _ = now.isocalendar()
            week_str = f"{year}-W{week:02d}"
            group_dir = os.path.join(out_dir, "grouped", week_str)
            if is_raw:
                return os.path.join(group_dir, f"raw_trajectories_{week_str}.jsonl")
            else:
                return os.path.join(group_dir, f"trajectories_{week_str}.jsonl")
        
        elif self.trajectory_storage_mode == TrajectoryStorageMode.MONTHLY_GROUPED:
            month_str = now.strftime("%Y-%m")
            group_dir = os.path.join(out_dir, "grouped", month_str)
            if is_raw:
                return os.path.join(group_dir, f"raw_trajectories_{month_str}.jsonl")
            else:
                return os.path.join(group_dir, f"trajectories_{month_str}.jsonl")
        
        # 默认按日期分组
        date_str = now.strftime("%Y-%m-%d")
        group_dir = os.path.join(out_dir, "grouped", date_str)
        if is_raw:
            return os.path.join(group_dir, f"raw_trajectories_{date_str}.jsonl")
        else:
            return os.path.join(group_dir, f"trajectories_{date_str}.jsonl")

    async def _save_trajectory_grouped(self, trajectory: TrajectoryResult):
        """按组保存轨迹到JSONL文件"""
        try:
            # XML streaming模式：保存原始文本
            if (trajectory.metadata and 
                trajectory.metadata.get('output_format') == 'raw_xml_streaming' and 
                trajectory.metadata.get('raw_llm_response')):
                
                await self._save_raw_trajectory_grouped(trajectory)
            
            # 保存结构化轨迹
            await self._save_structured_trajectory_grouped(trajectory)
            
        except Exception as e:
            logger.error(f"保存轨迹失败: {e}")

    async def _save_raw_trajectory_grouped(self, trajectory: TrajectoryResult):
        """保存原始XML轨迹到分组文件"""
        raw_file = self._get_trajectory_file_path(trajectory.task_id, is_raw=True)
        os.makedirs(os.path.dirname(raw_file), exist_ok=True)
        
        raw_data = {
            "timestamp": datetime.now().isoformat(),
            "task_id": trajectory.task_id,
            "task_description": trajectory.task_description,
            "duration": trajectory.total_duration,
            "success": trajectory.success,
            "final_result": trajectory.final_result,
            "raw_response": trajectory.metadata.get('raw_llm_response', ''),
            "response_length": len(trajectory.metadata.get('raw_llm_response', ''))
        }
        
        # 追加到JSONL文件
        with open(raw_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(raw_data, ensure_ascii=False) + '\n')
        
        # 为了兼容性，仍然保存单独的原始文件
        if self.trajectory_storage_mode == TrajectoryStorageMode.INDIVIDUAL_FILES:
            out_dir = get_trajectories_dir()
            individual_file = os.path.join(out_dir, f"{trajectory.task_id}_raw.txt")
            
            raw_response = trajectory.metadata['raw_llm_response']
            with open(individual_file, 'w', encoding='utf-8') as f:
                f.write(f"任务: {trajectory.task_description}\n")
                f.write(f"任务ID: {trajectory.task_id}\n")
                f.write(f"执行时间: {trajectory.total_duration:.2f}秒\n")
                f.write(f"成功状态: {'✅' if trajectory.success else '❌'}\n")
                f.write("-" * 50 + "\n")
                f.write("原始轨迹输出:\n")
                f.write("-" * 50 + "\n")
                f.write(raw_response)
                f.write("\n" + "-" * 50 + "\n")
                f.write(f"最终结果: {trajectory.final_result}\n")
        
        logger.info(f"保存原始轨迹到: {raw_file}")

    async def _save_structured_trajectory_grouped(self, trajectory: TrajectoryResult):
        """保存结构化轨迹到分组文件"""
        file_path = self._get_trajectory_file_path(trajectory.task_id, is_raw=False)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        trajectory_data = {
            "timestamp": datetime.now().isoformat(),
            "task_id": trajectory.task_id,
            "trajectory": trajectory.to_dict()
        }
        
        if self.trajectory_storage_mode == TrajectoryStorageMode.INDIVIDUAL_FILES:
            # 原有的集合文件模式
            trajectories = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        trajectories = json.load(f)
                        if not isinstance(trajectories, list):
                            trajectories = []
                except json.JSONDecodeError:
                    trajectories = []
            
            trajectories.append(trajectory.to_dict())
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(trajectories, f, ensure_ascii=False, indent=2)
        else:
            # 追加到JSONL文件
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(trajectory_data, ensure_ascii=False) + '\n')
        
        logger.info(f"保存结构化轨迹到: {file_path}")

    async def _save_trajectory(self, trajectory: TrajectoryResult):
        """保存轨迹 - 统一入口"""
        await self._save_trajectory_grouped(trajectory)
    
    async def cleanup(self):
        """清理资源"""
        logger.info("🧹 清理Simple Reasoning Runtime资源")
        
        if self.toolscore_client and hasattr(self.toolscore_client, 'close'):
            await self.toolscore_client.close()
        
        self.is_initialized = False
        logger.info("✅ 资源清理完成")