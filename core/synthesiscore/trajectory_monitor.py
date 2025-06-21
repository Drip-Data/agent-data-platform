#!/usr/bin/env python3
"""
Trajectory Monitor - 轨迹监控器
自动监控轨迹文件变化，使用SynthesisCore v2.0生成seed_task
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.interfaces import TrajectoryResult, TaskSpec, TaskType, ExecutionStep, ActionType
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient
from .enhanced_synthesis_engine import SynthesisCoreV2
from .enhanced_interfaces import AtomicTask, ExtendedTask, CompositeTask

logger = logging.getLogger(__name__)


class TrajectoryFileHandler(FileSystemEventHandler):
    """轨迹文件事件处理器"""
    
    def __init__(self, trajectory_monitor):
        self.trajectory_monitor = trajectory_monitor
        self.last_processed = {}
        
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
            
        if event.src_path.endswith('trajectories_collection.json'):
            # 避免频繁触发，设置最小间隔
            current_time = time.time()
            last_time = self.last_processed.get(event.src_path, 0)
            
            if current_time - last_time > 2.0:  # 2秒间隔
                self.last_processed[event.src_path] = current_time
                logger.info(f"📁 检测到轨迹文件变化: {event.src_path}")
                
                # 异步处理
                asyncio.create_task(
                    self.trajectory_monitor.process_trajectory_changes(event.src_path)
                )


class TrajectoryMonitor:
    """轨迹监控器 - 集成SynthesisCore v2.0"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None,
                 trajectories_dir: str = None, seed_tasks_file: str = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        
        # 路径配置
        self.trajectories_dir = trajectories_dir or "/Users/zhaoxiang/Documents/Datapresso/agent-data-platform/output/trajectories"
        self.seed_tasks_file = seed_tasks_file or "/Users/zhaoxiang/Documents/Datapresso/agent-data-platform/output/seed_tasks.jsonl"
        self.trajectories_collection_file = os.path.join(self.trajectories_dir, "trajectories_collection.json")
        self.processed_trajectories_file = os.path.join(self.trajectories_dir, "processed_trajectories.json")
        
        # SynthesisCore v2.0
        self.synthesis_core = SynthesisCoreV2(llm_client, mcp_client)
        
        # 文件监控
        self.observer = Observer()
        self.file_handler = TrajectoryFileHandler(self)
        
        # 已处理轨迹记录
        self.processed_trajectories = self._load_processed_trajectories()
        
        logger.info(f"🔧 TrajectoryMonitor初始化完成")
        logger.info(f"📂 监控目录: {self.trajectories_dir}")
        logger.info(f"📝 种子文件: {self.seed_tasks_file}")
    
    async def initialize(self):
        """初始化监控器"""
        try:
            # 初始化SynthesisCore v2.0
            await self.synthesis_core.initialize()
            
            # 确保目录和文件存在
            os.makedirs(os.path.dirname(self.seed_tasks_file), exist_ok=True)
            os.makedirs(self.trajectories_dir, exist_ok=True)
            
            # 处理现有轨迹
            await self.process_existing_trajectories()
            
            logger.info("✅ TrajectoryMonitor初始化完成")
            
        except Exception as e:
            logger.error(f"❌ TrajectoryMonitor初始化失败: {e}")
            raise
    
    async def start_monitoring(self):
        """开始监控轨迹文件"""
        try:
            # 设置文件监控
            self.observer.schedule(
                self.file_handler,
                path=self.trajectories_dir,
                recursive=False
            )
            
            # 启动监控
            self.observer.start()
            logger.info(f"👁️ 开始监控轨迹文件变化: {self.trajectories_dir}")
            
        except Exception as e:
            logger.error(f"❌ 启动文件监控失败: {e}")
            raise
    
    async def stop_monitoring(self):
        """停止监控"""
        try:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join()
                logger.info("🛑 轨迹文件监控已停止")
            
            await self.synthesis_core.close()
            logger.info("🔒 SynthesisCore已关闭")
            
        except Exception as e:
            logger.error(f"❌ 停止监控失败: {e}")
    
    async def process_existing_trajectories(self):
        """处理现有轨迹"""
        logger.info("🔄 检查并处理现有轨迹...")
        
        if os.path.exists(self.trajectories_collection_file):
            await self.process_trajectory_changes(self.trajectories_collection_file)
        else:
            logger.info("📝 没有现有轨迹文件")
    
    async def process_trajectory_changes(self, file_path: str):
        """处理轨迹文件变化"""
        logger.info(f"🔄 处理轨迹文件: {file_path}")
        
        try:
            # 读取轨迹文件
            trajectories = self._load_trajectories_from_file(file_path)
            
            if not trajectories:
                logger.warning("⚠️ 轨迹文件为空或无效")
                return
            
            # 筛选未处理的轨迹
            new_trajectories = self._filter_new_trajectories(trajectories)
            
            if not new_trajectories:
                logger.info("✅ 没有新的轨迹需要处理")
                return
            
            logger.info(f"🆕 发现 {len(new_trajectories)} 个新轨迹，开始处理...")
            
            # 调试：显示所有新轨迹的信息
            logger.info("🔍 所有新轨迹详情:")
            for i, trajectory in enumerate(new_trajectories):
                logger.info(f"  {i+1}. task_id={trajectory.task_id}, runtime_id={trajectory.runtime_id}, success={trajectory.success}")
            
            # 过滤出值得处理的轨迹
            valid_trajectories = []
            for trajectory in new_trajectories:
                if self._should_process_trajectory(trajectory):
                    valid_trajectories.append(trajectory)
                    logger.info(f"✅ 轨迹通过过滤: {trajectory.task_id} (runtime={trajectory.runtime_id}, success={trajectory.success})")
                else:
                    logger.debug(f"⏭️ 跳过轨迹: {trajectory.task_id}")
            
            logger.info(f"📊 轨迹过滤结果: {len(valid_trajectories)}/{len(new_trajectories)} 个轨迹通过过滤")
            
            if not valid_trajectories:
                logger.warning("⚠️ 没有有效轨迹可处理")
                return {"success": False, "message": "No valid trajectories to process"}
            
            # 使用SynthesisCore v2.0处理有效轨迹
            result = await self.synthesis_core.synthesize_tasks(
                trajectories=valid_trajectories,
                mode="full",  # 生成所有类型的任务
                verify_quality=True
            )
            
            if result["success"]:
                # 转换为种子任务并保存
                await self._convert_and_save_seed_tasks(result)
                
                # 只标记成功处理的有效轨迹为已处理
                self._update_processed_trajectories([t.task_id for t in valid_trajectories])
                
                logger.info(f"✅ 轨迹处理完成，生成种子任务: 原子 {len(result['atomic_tasks'])}, 扩展 {len(result['extended_tasks'])}, 复合 {len(result['composite_tasks'])}")
                logger.info(f"✅ 标记 {len(valid_trajectories)} 个有效轨迹为已处理")
            else:
                logger.error(f"❌ SynthesisCore处理失败: {result.get('error', 'Unknown error')}")
                logger.warning(f"⚠️ 不标记轨迹为已处理，以便下次重试")
                
        except Exception as e:
            logger.error(f"❌ 处理轨迹变化失败: {e}")
    
    def _load_trajectories_from_file(self, file_path: str) -> List[TrajectoryResult]:
        """从文件加载轨迹"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            trajectories = []
            trajectory_list = data.get('trajectories', []) if isinstance(data, dict) else data
            
            for traj_data in trajectory_list:
                try:
                    trajectory = self._convert_to_trajectory_result(traj_data)
                    if trajectory:
                        trajectories.append(trajectory)
                except Exception as e:
                    logger.error(f"❌ 转换轨迹数据失败: {e}")
                    continue
            
            logger.info(f"📋 从文件加载 {len(trajectories)} 个轨迹")
            return trajectories
            
        except Exception as e:
            logger.error(f"❌ 加载轨迹文件失败 {file_path}: {e}")
            return []
    
    def _convert_to_trajectory_result(self, traj_data: Dict) -> Optional[TrajectoryResult]:
        """转换轨迹数据格式"""
        try:
            # 调试日志：检查数据结构
            logger.debug(f"🔍 TM Converting trajectory: {traj_data.get('task_id', 'unknown')}")
            
            # 基础信息
            task_id = traj_data.get('task_id', f"traj_{int(time.time())}")
            task_description = traj_data.get('task_description', traj_data.get('description', ''))
            runtime_id = traj_data.get('runtime_id', 'unknown')
            
            # 执行结果
            success = traj_data.get('success', False)
            final_result = traj_data.get('final_result', traj_data.get('result', ''))
            total_duration = traj_data.get('total_duration', 0.0)
            
            # 步骤信息
            steps = []
            steps_data = traj_data.get('steps', traj_data.get('execution_steps', []))
            
            for i, step_data in enumerate(steps_data):
                step = self._convert_step_data(step_data, i)
                if step:
                    steps.append(step)
            
            # 创建轨迹结果 
            # 注意: TrajectoryResult使用created_at字段，不是completed_at
            completed_at_str = traj_data.get('completed_at', datetime.now().isoformat())
            try:
                # 尝试解析ISO格式时间戳
                if isinstance(completed_at_str, str):
                    completed_at_time = datetime.fromisoformat(completed_at_str.replace('Z', '+00:00')).timestamp()
                else:
                    completed_at_time = float(completed_at_str)
            except:
                completed_at_time = time.time()
            
            trajectory = TrajectoryResult(
                task_name=task_id,  # task_name字段
                task_id=task_id,
                task_description=task_description,
                runtime_id=runtime_id,
                success=success,
                final_result=final_result,
                steps=steps,
                total_duration=total_duration,
                created_at=completed_at_time  # 使用created_at而不是completed_at
            )
            
            logger.debug(f"🔍 TM Created: {trajectory.task_id}")
            return trajectory
            
        except Exception as e:
            logger.error(f"❌ 轨迹数据转换失败: {e}")
            return None
    
    def _should_process_trajectory(self, trajectory: TrajectoryResult) -> bool:
        """判断轨迹是否值得处理"""
        # 1. 成功的轨迹总是处理
        if trajectory.success:
            return True
        
        # 2. reasoning runtime的轨迹，即使失败也可能有价值（不要求有执行步骤）
        runtime_id = trajectory.runtime_id.lower()
        if 'reasoning' in runtime_id:
            logger.info(f"🧠 Found reasoning trajectory: {trajectory.task_id}")
            return True
        
        # 3. 有执行步骤的轨迹
        if len(trajectory.steps) > 0:
            # 有多个步骤的复杂任务，即使失败也可能有价值
            if len(trajectory.steps) >= 2:
                return True
        
        # 4. 任务描述包含特定关键词
        task_desc = trajectory.task_description.lower()
        valuable_keywords = ['reasoning', '推理', '分析', 'analysis', 'compare', '对比', '研究']
        if any(keyword in task_desc for keyword in valuable_keywords):
            logger.info(f"🔎 Found valuable keywords in task description: {trajectory.task_id}")
            return True
        
        # 5. 有最终结果的轨迹，即使失败也可能有价值
        if trajectory.final_result and len(trajectory.final_result.strip()) > 50:
            logger.info(f"📝 Found trajectory with substantial final result: {trajectory.task_id}")
            return True
        
        return False
    
    def _convert_step_data(self, step_data: Dict, step_index: int) -> Optional[ExecutionStep]:
        """转换步骤数据"""
        try:
            
            step_id = step_data.get('step_id', f"step_{step_index}")
            thinking = step_data.get('thinking', '')
            action_type = ActionType.TOOL_CALL  # 默认为工具调用
            action_params = step_data.get('action_params', step_data.get('tool_call', {}))
            observation = step_data.get('observation', step_data.get('result', ''))
            success = step_data.get('success', True)
            duration = step_data.get('duration', 0.0)
            
            step = ExecutionStep(
                step_id=step_id,
                thinking=thinking,
                action_type=action_type,
                action_params=action_params,
                observation=observation,
                success=success,
                duration=duration
            )
            
            return step
            
        except Exception as e:
            logger.error(f"❌ 步骤数据转换失败: {e}")
            return None
    
    def _filter_new_trajectories(self, trajectories: List[TrajectoryResult]) -> List[TrajectoryResult]:
        """筛选未处理的轨迹"""
        new_trajectories = []
        
        for trajectory in trajectories:
            if trajectory.task_id not in self.processed_trajectories:
                new_trajectories.append(trajectory)
        
        return new_trajectories
    
    async def _convert_and_save_seed_tasks(self, synthesis_result: Dict):
        """转换任务结果为种子任务并保存"""
        try:
            seed_tasks = []
            
            # 处理原子任务
            for atomic_task in synthesis_result.get('atomic_tasks', []):
                seed_task = self._convert_atomic_task_to_seed(atomic_task)
                if seed_task:
                    seed_tasks.append(seed_task)
            
            # 处理深度扩展任务
            for extended_task in synthesis_result.get('extended_tasks', []):
                seed_task = self._convert_extended_task_to_seed(extended_task)
                if seed_task:
                    seed_tasks.append(seed_task)
            
            # 处理宽度扩展任务
            for composite_task in synthesis_result.get('composite_tasks', []):
                seed_task = self._convert_composite_task_to_seed(composite_task)
                if seed_task:
                    seed_tasks.append(seed_task)
            
            # 保存到seed_tasks.jsonl
            if seed_tasks:
                await self._append_seed_tasks_to_file(seed_tasks)
                logger.info(f"💾 保存 {len(seed_tasks)} 个种子任务到 {self.seed_tasks_file}")
            
        except Exception as e:
            logger.error(f"❌ 转换和保存种子任务失败: {e}")
    
    def _convert_atomic_task_to_seed(self, atomic_task: AtomicTask) -> Dict:
        """转换原子任务为种子任务"""
        return {
            "task_id": f"seed_atomic_{atomic_task.task_id}",
            "task_type": self._map_task_type(atomic_task.required_tools),
            "description": atomic_task.question,
            "expected_tools": atomic_task.required_tools,
            "max_steps": self._estimate_max_steps(atomic_task.difficulty_level.value),
            "success_criteria": {
                "contains": [atomic_task.golden_answer],
                "accuracy_threshold": 0.8
            },
            "metadata": {
                "source": "atomic_task",
                "original_task_id": atomic_task.task_id,
                "difficulty": atomic_task.difficulty_level.value,
                "verification_score": atomic_task.verification_score,
                "created_at": datetime.now().isoformat()
            }
        }
    
    def _convert_extended_task_to_seed(self, extended_task: ExtendedTask) -> Dict:
        """转换扩展任务为种子任务"""
        return {
            "task_id": f"seed_extended_{extended_task.task_id}",
            "task_type": self._map_task_type(extended_task.expected_tools),
            "description": extended_task.question,
            "expected_tools": extended_task.expected_tools,
            "max_steps": self._estimate_max_steps(extended_task.difficulty_level.value) + extended_task.hop_level,
            "success_criteria": {
                "contains": [extended_task.golden_answer],
                "accuracy_threshold": 0.7
            },
            "metadata": {
                "source": "extended_task",
                "original_task_id": extended_task.task_id,
                "hop_level": extended_task.hop_level,
                "source_atomic_task": extended_task.source_atomic_task,
                "difficulty": extended_task.difficulty_level.value,
                "complexity_score": extended_task.complexity_score,
                "created_at": datetime.now().isoformat()
            }
        }
    
    def _convert_composite_task_to_seed(self, composite_task: CompositeTask) -> Dict:
        """转换复合任务为种子任务"""
        return {
            "task_id": f"seed_composite_{composite_task.task_id}",
            "task_type": self._map_task_type(composite_task.expected_tools),
            "description": composite_task.question,
            "expected_tools": composite_task.expected_tools,
            "max_steps": self._estimate_max_steps(composite_task.difficulty_level.value) + len(composite_task.source_atomic_tasks),
            "success_criteria": {
                "contains": composite_task.golden_answers,
                "accuracy_threshold": 0.6
            },
            "metadata": {
                "source": "composite_task",
                "original_task_id": composite_task.task_id,
                "source_atomic_tasks": composite_task.source_atomic_tasks,
                "original_questions": composite_task.original_questions,
                "difficulty": composite_task.difficulty_level.value,
                "merge_strategy": composite_task.merge_strategy,
                "created_at": datetime.now().isoformat()
            }
        }
    
    def _map_task_type(self, tools: List[str]) -> str:
        """根据工具推断任务类型"""
        if not tools:
            return "reasoning"
        
        tool_lower = [tool.lower() for tool in tools]
        
        if any("browser" in tool or "web" in tool for tool in tool_lower):
            return "web"
        elif any("python" in tool or "code" in tool for tool in tool_lower):
            return "code"
        elif any("search" in tool for tool in tool_lower):
            return "research"
        else:
            return "reasoning"
    
    def _estimate_max_steps(self, difficulty: str) -> int:
        """估算最大步数"""
        mapping = {
            "simple": 3,
            "medium": 6,
            "complex": 10
        }
        return mapping.get(difficulty, 5)
    
    async def _append_seed_tasks_to_file(self, seed_tasks: List[Dict]):
        """追加种子任务到JSONL文件"""
        try:
            with open(self.seed_tasks_file, 'a', encoding='utf-8') as f:
                for task in seed_tasks:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
            
            logger.info(f"📝 追加 {len(seed_tasks)} 个种子任务到文件")
            
        except Exception as e:
            logger.error(f"❌ 写入种子任务文件失败: {e}")
    
    def _load_processed_trajectories(self) -> set:
        """加载已处理轨迹记录"""
        try:
            if os.path.exists(self.processed_trajectories_file):
                with open(self.processed_trajectories_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('processed', []))
            return set()
            
        except Exception as e:
            logger.error(f"❌ 加载已处理轨迹记录失败: {e}")
            return set()
    
    def _update_processed_trajectories(self, trajectory_ids: List[str]):
        """更新已处理轨迹记录"""
        try:
            # 更新内存记录
            self.processed_trajectories.update(trajectory_ids)
            
            # 保存到文件
            data = {
                "processed": list(self.processed_trajectories),
                "last_updated": datetime.now().isoformat(),
                "total_count": len(self.processed_trajectories)
            }
            
            with open(self.processed_trajectories_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📊 更新已处理轨迹记录: +{len(trajectory_ids)}, 总计: {len(self.processed_trajectories)}")
            
        except Exception as e:
            logger.error(f"❌ 更新已处理轨迹记录失败: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            # 读取种子任务文件统计
            seed_count = 0
            if os.path.exists(self.seed_tasks_file):
                with open(self.seed_tasks_file, 'r', encoding='utf-8') as f:
                    seed_count = sum(1 for line in f if line.strip())
            
            # 获取SynthesisCore指标
            synthesis_metrics = await self.synthesis_core.get_metrics("global")
            
            return {
                "processed_trajectories": len(self.processed_trajectories),
                "total_seed_tasks": seed_count,
                "synthesis_metrics": synthesis_metrics,
                "files": {
                    "trajectories_file": self.trajectories_collection_file,
                    "seed_tasks_file": self.seed_tasks_file,
                    "processed_record": self.processed_trajectories_file
                },
                "monitoring_status": self.observer.is_alive() if hasattr(self, 'observer') else False
            }
            
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}