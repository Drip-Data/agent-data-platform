#!/usr/bin/env python3
"""
TaskCraft 任务存储管理器
统一管理不同类型任务的存储和检索
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import aiofiles
from dataclasses import asdict

from .interfaces import (
    AtomicTask, DepthExtendedTask, WidthExtendedTask, TaskUnion,
    TaskValidationResult, SynthesisResult, TaskType, TaskComplexity
)

logger = logging.getLogger(__name__)


class TaskStorage:
    """
    Synthesis 任务存储管理器
    
    功能：
    1. 简化存储：仅保留两个文件 - 原子任务和综合任务
    2. 原子任务：基础单元任务
    3. 综合任务：基于原子任务库扩展的复合任务（深度+宽度）
    4. 验证存储：保存验证结果
    5. 统一接口：提供统一的存储和检索接口
    """
    
    def __init__(self, storage_dir: str = "output/SynthesisTask"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 简化存储文件路径 - 只保留两个核心文件
        self.files = {
            # 原子任务存储
            "atomic_tasks": self.storage_dir / "atomic_tasks.jsonl",
            
            # 综合任务存储（深度扩展+宽度扩展）
            "composite_tasks": self.storage_dir / "composite_tasks.jsonl"
        }
        
        # 初始化文件
        self._initialize_storage_files()
        
        logger.info(f"✅ TaskStorage 初始化完成，存储目录: {self.storage_dir}")
    
    def _initialize_storage_files(self):
        """初始化存储文件"""
        for file_path in self.files.values():
            if not file_path.exists():
                file_path.touch()  # 只创建JSONL文件
    
    async def store_atomic_task(self, task: AtomicTask, validation_result: Optional[TaskValidationResult] = None) -> bool:
        """存储原子任务"""
        try:
            # 所有原子任务存储到同一个文件
            file_path = self.files["atomic_tasks"]
            
            # 准备存储数据
            task_data = asdict(task)
            task_data["created_at"] = task.created_at.isoformat()
            task_data["task_category"] = "atomic"  # 标记任务类别
            
            # 修复枚举序列化问题
            task_data["task_type"] = task.task_type.value
            task_data["complexity"] = task.complexity.value
            
            # 异步写入
            async with aiofiles.open(file_path, 'a', encoding='utf-8') as f:
                await f.write(json.dumps(task_data, ensure_ascii=False) + '\n')
            
            logger.debug(f"✅ 存储原子任务: {task.task_id} -> {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 存储原子任务失败 {task.task_id}: {e}")
            return False
    
    async def store_depth_extended_task(self, task: DepthExtendedTask, validation_result: Optional[TaskValidationResult] = None) -> bool:
        """存储深度扩展任务"""
        try:
            # 所有综合任务存储到同一个文件
            file_path = self.files["composite_tasks"]
            
            # 准备存储数据
            task_data = {
                "task_id": task.task_id,
                "complexity": task.complexity.value,
                "task_category": "composite_depth",  # 标记任务类别
                "base_task": asdict(task.base_task),
                "intermediate_task": asdict(task.intermediate_task),
                "superset_input": asdict(task.superset_input),
                "superset_relation": asdict(task.superset_relation),
                "combined_question": task.combined_question,
                "combined_answer": task.combined_answer,
                "created_at": task.created_at.isoformat()
            }
            
            # 修复datetime字段和枚举字段
            task_data["base_task"]["created_at"] = task.base_task.created_at.isoformat()
            task_data["base_task"]["task_type"] = task.base_task.task_type.value
            task_data["base_task"]["complexity"] = task.base_task.complexity.value
            
            task_data["intermediate_task"]["created_at"] = task.intermediate_task.created_at.isoformat()
            task_data["intermediate_task"]["task_type"] = task.intermediate_task.task_type.value
            task_data["intermediate_task"]["complexity"] = task.intermediate_task.complexity.value
            
            # 异步写入
            async with aiofiles.open(file_path, 'a', encoding='utf-8') as f:
                await f.write(json.dumps(task_data, ensure_ascii=False) + '\n')
            
            logger.debug(f"✅ 存储深度扩展任务: {task.task_id} -> {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 存储深度扩展任务失败 {task.task_id}: {e}")
            return False
    
    async def store_width_extended_task(self, task: WidthExtendedTask, validation_result: Optional[TaskValidationResult] = None) -> bool:
        """存储宽度扩展任务"""
        try:
            # 所有综合任务存储到同一个文件
            file_path = self.files["composite_tasks"]
            
            # 准备存储数据
            task_data = {
                "task_id": task.task_id,
                "complexity": task.complexity.value,
                "task_category": "composite_width",  # 标记任务类别
                "component_tasks": [asdict(t) for t in task.component_tasks],
                "merged_question": task.merged_question,
                "merged_answer": task.merged_answer,
                "merge_strategy": task.merge_strategy,
                "created_at": task.created_at.isoformat()
            }
            
            # 修复datetime字段和枚举字段
            for i, comp_task_data in enumerate(task_data["component_tasks"]):
                comp_task_data["created_at"] = task.component_tasks[i].created_at.isoformat()
                comp_task_data["task_type"] = task.component_tasks[i].task_type.value
                comp_task_data["complexity"] = task.component_tasks[i].complexity.value
            
            # 异步写入
            async with aiofiles.open(file_path, 'a', encoding='utf-8') as f:
                await f.write(json.dumps(task_data, ensure_ascii=False) + '\n')
            
            logger.debug(f"✅ 存储宽度扩展任务: {task.task_id} -> {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 存储宽度扩展任务失败 {task.task_id}: {e}")
            return False
    
    
    async def load_tasks_by_type(self, task_type: TaskType, complexity: Optional[TaskComplexity] = None) -> List[Dict]:
        """按类型加载任务"""
        tasks = []
        
        try:
            # 确定要读取的文件
            if complexity is None or complexity == TaskComplexity.ATOMIC:
                files_to_read = [self.files["atomic_tasks"]]
            else:
                files_to_read = []
                
            if complexity is None or complexity in [TaskComplexity.DEPTH, TaskComplexity.WIDTH]:
                files_to_read.append(self.files["composite_tasks"])
            
            # 读取文件
            for file_path in files_to_read:
                if file_path.exists():
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        async for line in f:
                            if line.strip():
                                try:
                                    task_data = json.loads(line)
                                    
                                    # 根据任务类型过滤
                                    if task_type == TaskType.TOOL_REQUIRED:
                                        if 'task_type' in task_data and task_data['task_type'] == 'tool_required':
                                            tasks.append(task_data)
                                        elif 'base_task' in task_data and task_data['base_task'].get('task_type') == 'tool_required':
                                            tasks.append(task_data)
                                    else:
                                        if 'task_type' in task_data and task_data['task_type'] == 'reasoning_only':
                                            tasks.append(task_data)
                                        elif 'base_task' in task_data and task_data['base_task'].get('task_type') == 'reasoning_only':
                                            tasks.append(task_data)
                                    
                                    # 根据复杂度过滤
                                    if complexity == TaskComplexity.DEPTH:
                                        if task_data.get('task_category') != 'composite_depth':
                                            continue
                                    elif complexity == TaskComplexity.WIDTH:
                                        if task_data.get('task_category') != 'composite_width':
                                            continue
                                    elif complexity == TaskComplexity.ATOMIC:
                                        if task_data.get('task_category') != 'atomic':
                                            continue
                                    
                                except json.JSONDecodeError as e:
                                    logger.warning(f"⚠️ 跳过无效JSON行: {e}")
            
            logger.debug(f"📖 加载任务: {task_type.value}, 数量: {len(tasks)}")
            return tasks
            
        except Exception as e:
            logger.error(f"❌ 加载任务失败: {e}")
            return []
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {
                "total_tasks": 0,
                "atomic_tasks": 0,
                "composite_tasks": {
                    "depth_extended": 0,
                    "width_extended": 0,
                    "total": 0
                },
                "storage_files": {}
            }
            
            # 统计原子任务数量
            if self.files["atomic_tasks"].exists():
                atomic_count = await self._count_lines(self.files["atomic_tasks"])
                stats["atomic_tasks"] = atomic_count
                stats["total_tasks"] += atomic_count
                stats["storage_files"]["atomic_tasks"] = {
                    "path": str(self.files["atomic_tasks"]),
                    "count": atomic_count,
                    "size_bytes": self.files["atomic_tasks"].stat().st_size
                }
            
            # 统计综合任务数量
            if self.files["composite_tasks"].exists():
                composite_count = await self._count_lines(self.files["composite_tasks"])
                # 需要读取文件内容来区分深度和宽度任务
                depth_count = 0
                width_count = 0
                
                async with aiofiles.open(self.files["composite_tasks"], 'r', encoding='utf-8') as f:
                    async for line in f:
                        if line.strip():
                            try:
                                task_data = json.loads(line)
                                if task_data.get('task_category') == 'composite_depth':
                                    depth_count += 1
                                elif task_data.get('task_category') == 'composite_width':
                                    width_count += 1
                            except json.JSONDecodeError:
                                pass
                
                stats["composite_tasks"]["depth_extended"] = depth_count
                stats["composite_tasks"]["width_extended"] = width_count
                stats["composite_tasks"]["total"] = depth_count + width_count
                stats["total_tasks"] += composite_count
                
                stats["storage_files"]["composite_tasks"] = {
                    "path": str(self.files["composite_tasks"]),
                    "count": composite_count,
                    "size_bytes": self.files["composite_tasks"].stat().st_size
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}
    
    async def store_synthesis_session(self, result) -> bool:
        """存储合成会话结果（简化版本）"""
        try:
            # 简化的会话记录，只记录统计信息
            logger.info(f"📊 合成会话完成: {getattr(result, 'session_id', 'unknown')}")
            logger.info(f"  生成任务: {getattr(result, 'total_tasks_generated', 0)} 个")
            logger.info(f"  有效任务: {getattr(result, 'valid_tasks_count', 0)} 个")
            return True
        except Exception as e:
            logger.error(f"❌ 存储合成会话失败: {e}")
            return False
    
    async def _count_lines(self, file_path: Path) -> int:
        """计算文件行数"""
        try:
            count = 0
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                async for line in f:
                    if line.strip():
                        count += 1
            return count
        except Exception:
            return 0
    
    def store_validation_result(self, validation_result: 'TaskValidationResult'):
        """存储验证结果（已禁用文件输出）"""
        try:
            # 不再生成独立的validation.json文件，只记录日志
            logger.debug(f"🔍 验证完成 - 任务 {validation_result.task_id}: "
                        f"有效={validation_result.is_valid}, "
                        f"分数={validation_result.validation_score:.2f}")
            
            # 如果需要详细信息，只在调试级别记录
            if not validation_result.is_valid and validation_result.errors:
                logger.debug(f"  验证错误: {validation_result.errors}")
            
        except Exception as e:
            logger.error(f"❌ 记录验证结果失败: {e}")

    async def clear_storage(self, confirm: bool = False) -> bool:
        """清空存储（危险操作）"""
        if not confirm:
            logger.warning("⚠️ 清空存储需要确认参数 confirm=True")
            return False
        
        try:
            for file_path in self.files.values():
                if file_path.exists():
                    file_path.write_text('', encoding='utf-8')
            
            logger.warning("🗑️ 所有存储文件已清空")
            return True
        except Exception as e:
            logger.error(f"❌ 清空存储失败: {e}")
            return False
    
    def get_storage_info(self) -> Dict[str, str]:
        """获取存储信息"""
        return {
            "storage_directory": str(self.storage_dir),
            "files": {key: str(path) for key, path in self.files.items()},
            "description": {
                "atomic_tasks": "原子任务（基础单元任务）",
                "composite_tasks": "综合任务（深度扩展+宽度扩展，基于原子任务库扩展）"
            }
        }