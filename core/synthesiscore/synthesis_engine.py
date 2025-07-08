#!/usr/bin/env python3
"""
Synthesis 统一合成引擎
严格按照 Synthesis 算法实现的单一、清晰的实现
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .interfaces import (
    AtomicTask, DepthExtendedTask, WidthExtendedTask, TaskUnion,
    TaskValidationResult, SynthesisResult, TaskType, TaskComplexity,
    SynthesisInput, SynthesisContent, SynthesisAnswer, SynthesisRelation
)
from .task_validator import TaskValidator
from .task_storage import TaskStorage
from .prompts import prompt_manager
from .trajectory_step_extractor import EnhancedTrajectoryBasedTaskGenerator
from .enhanced_task_extensions import EnhancedTaskExtensions
from .task_complexity_evaluator import TaskComplexityEvaluator, ComplexityScore

logger = logging.getLogger(__name__)


class SynthesisEngine:
    """
    Synthesis 统一合成引擎
    
    实现完整的 Synthesis 算法流程：
    1. 原子任务生成：iT → C → (a, R) → q
    2. 深度扩展：超集搜索 + 中间任务 + 任务合并
    3. 宽度扩展：多任务合并
    4. 智能验证：工具任务 vs 推理任务
    """
    
    def __init__(self, llm_client, mcp_client=None, storage_dir: str = "output", 
                 enable_strict_validation: bool = True):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.enable_strict_validation = enable_strict_validation
        
        # 初始化核心组件
        # self.corpus_ingestor = CorpusIngestor()
        # self.atomic_generator = AtomicTaskGenerator(llm_client, mcp_client)
        # self.depth_extender = DepthExtender(llm_client)
        # self.width_extender = WidthExtender(llm_client)
        self.validator = TaskValidator(llm_client, enable_strict_validation)
        self.storage = TaskStorage(storage_dir)
        
        # 初始化增强的基于轨迹的任务生成器
        self.trajectory_task_generator = EnhancedTrajectoryBasedTaskGenerator(llm_client, self.validator)
        
        # 初始化增强扩展器和复杂度评估器
        self.enhanced_extensions = EnhancedTaskExtensions(llm_client)
        self.complexity_evaluator = TaskComplexityEvaluator()
        
        # 运行统计
        self.session_stats = {
            "sessions_completed": 0,
            "total_tasks_generated": 0,
            "valid_tasks_count": 0,
            "tool_required_count": 0,
            "reasoning_only_count": 0  # Deprecated: now only generating tool_required tasks
        }
        
        # LLM重试配置
        self.max_retries = 3
        self.retry_delay = 2.0
        
        logger.info("✅ SynthesisEngine 初始化完成")
    
    async def _call_llm_with_retry(self, prompt: str, operation_name: str) -> str:
        """
        带重试机制的LLM调用方法
        
        Args:
            prompt: 发送给LLM的提示
            operation_name: 操作名称，用于日志
            
        Returns:
            LLM响应内容
            
        Raises:
            RuntimeError: 重试次数用尽后仍然失败
        """
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"🔄 {operation_name} - 尝试 {attempt}/{self.max_retries}")
                # 将字符串prompt转换为消息列表格式
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm_client._call_api(messages)
                logger.debug(f"✅ {operation_name} - 第{attempt}次尝试成功")
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ {operation_name} - 第{attempt}次尝试失败: {e}")
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries:
                    logger.info(f"⏰ 等待 {self.retry_delay}s 后重试...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    # 最后一次尝试失败，报错
                    logger.error(f"❌ {operation_name} - 所有 {self.max_retries} 次尝试均失败")
                    break
        
        # 抛出运行时错误，不再使用简单回退
        raise RuntimeError(f"{operation_name} 失败：经过 {self.max_retries} 次重试仍无法与LLM正常通信。最后错误: {last_error}")
    
    async def synthesize_from_trajectories(self, trajectories_data: List[Dict], 
                                         generate_depth_extensions: bool = True,
                                         generate_width_extensions: bool = True,
                                         max_atomic_tasks: int = 20,
                                         max_depth_extensions: int = 10,
                                         max_width_extensions: int = 5) -> SynthesisResult:
        """
        从轨迹数据合成任务的主入口
        
        Args:
            trajectories_data: 轨迹数据列表
            generate_depth_extensions: 是否生成深度扩展
            generate_width_extensions: 是否生成宽度扩展
            max_atomic_tasks: 最大原子任务数量
            max_depth_extensions: 最大深度扩展数量
            max_width_extensions: 最大宽度扩展数量
        """
        session_id = f"synthesis_{uuid.uuid4().hex[:8]}"
        logger.info(f"🚀 开始 Synthesis 合成会话: {session_id}")
        
        start_time = datetime.now()
        result = SynthesisResult(
            session_id=session_id,
            source_trajectories=[t.get("task_id", "unknown") for t in trajectories_data]
        )
        
        try:
            # 第一步：生成原子任务
            logger.info("📋 第一步：生成原子任务 (iT → C → (a, R) → q)")
            atomic_tasks = await self._generate_atomic_tasks(trajectories_data, max_atomic_tasks)
            result.atomic_tasks = atomic_tasks
            
            # 验证原子任务
            logger.info("🔍 验证原子任务")
            atomic_validations = await self.validator.batch_validate_tasks(atomic_tasks)
            result.validation_results.extend(atomic_validations)
            
            # 过滤有效的原子任务
            valid_atomic_tasks = [
                task for task, validation in zip(atomic_tasks, atomic_validations)
                if validation.is_valid
            ]
            logger.info(f"✅ 有效原子任务: {len(valid_atomic_tasks)}/{len(atomic_tasks)}")
            
            # 第二步：增强深度扩展（可选）
            if generate_depth_extensions and valid_atomic_tasks:
                logger.info("📈 第二步：增强深度扩展 (LLM驱动的多步骤推理)")
                depth_tasks = await self.enhanced_extensions.generate_enhanced_depth_extensions(
                    valid_atomic_tasks, max_depth_extensions
                )
                
                # 评估和过滤深度扩展任务
                filtered_depth_tasks = []
                for task in depth_tasks:
                    complexity_score = self.complexity_evaluator.evaluate_depth_extended_task(task)
                    logger.info(f"📊 深度任务 {task.task_id} 复杂度: {complexity_score.complexity_level} (分数: {complexity_score.total_score:.2f})")
                    
                    # 🔧 修复：降低复杂度门槛，包含简单任务以提升综合任务生成率
                    if complexity_score.complexity_level in ["simple", "moderate", "complex", "comprehensive"]:
                        filtered_depth_tasks.append(task)
                        logger.info(f"✅ 深度任务通过复杂度检查: {task.task_id} (级别: {complexity_score.complexity_level})")
                    else:
                        logger.warning(f"⚠️ 深度任务复杂度过低: {task.task_id} - {complexity_score.quality_issues}")
                
                result.depth_extended_tasks = filtered_depth_tasks
                
                # 验证通过评估的深度扩展任务
                if filtered_depth_tasks:
                    depth_validations = await self.validator.batch_validate_tasks(filtered_depth_tasks)
                    result.validation_results.extend(depth_validations)
            
            # 第三步：增强宽度扩展（可选）
            if generate_width_extensions and len(valid_atomic_tasks) >= 2:
                logger.info("📊 第三步：增强宽度扩展 (智能协同任务)")
                width_tasks = await self.enhanced_extensions.generate_enhanced_width_extensions(
                    valid_atomic_tasks, max_width_extensions
                )
                
                # 评估和过滤宽度扩展任务
                filtered_width_tasks = []
                for task in width_tasks:
                    complexity_score = self.complexity_evaluator.evaluate_width_extended_task(task)
                    logger.info(f"📊 宽度任务 {task.task_id} 复杂度: {complexity_score.complexity_level} (分数: {complexity_score.total_score:.2f})")
                    
                    # 🔧 修复：降低协同价值门槛，包含简单任务以提升综合任务生成率
                    if complexity_score.complexity_level in ["simple", "moderate", "complex", "comprehensive"]:
                        filtered_width_tasks.append(task)
                        logger.info(f"✅ 宽度任务通过复杂度检查: {task.task_id} (级别: {complexity_score.complexity_level})")
                    else:
                        logger.warning(f"⚠️ 宽度任务协同价值过低: {task.task_id} - {complexity_score.quality_issues}")
                
                result.width_extended_tasks = filtered_width_tasks
                
                # 验证通过评估的宽度扩展任务
                if filtered_width_tasks:
                    width_validations = await self.validator.batch_validate_tasks(filtered_width_tasks)
                    result.validation_results.extend(width_validations)
            
            # 第四步：存储结果
            logger.info("💾 第四步：存储合成结果")
            await self._store_synthesis_results(result)
            
            # 计算统计信息
            self._calculate_result_statistics(result)
            
            # 更新会话统计
            self._update_session_stats(result)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"🎉 Synthesis 合成完成: {session_id}, 耗时: {duration:.2f}s")
            logger.info(f"📊 生成统计: 原子{len(result.atomic_tasks)}, 深度{len(result.depth_extended_tasks)}, 宽度{len(result.width_extended_tasks)}")
            logger.info(f"✅ 有效任务: {result.valid_tasks_count}/{result.total_tasks_generated}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Synthesis 合成失败: {e}", exc_info=True)
            result.validation_results.append(TaskValidationResult(
                task_id="synthesis_error",
                is_valid=False,
                requires_tool=False,
                validation_score=0.0,
                tool_necessity_check=False,
                reasoning_sufficiency_check=False,
                atomicity_check=False,
                errors=[f"合成过程异常: {str(e)}"]
            ))
            return result
    
    async def _generate_atomic_tasks(self, trajectories_data: List[Dict], max_tasks: int) -> List[AtomicTask]:
        """生成原子任务 - 混合使用基于轨迹证据的生成和LLM生成"""
        logger.debug(f"🔬 从 {len(trajectories_data)} 个轨迹生成原子任务")
        
        atomic_tasks = []
        
        try:
            # 🆕 步骤1：基于轨迹证据生成任务（占60%）
            evidence_task_count = max(1, int(max_tasks * 0.6))
            logger.info(f"🧬 开始基于轨迹证据生成 {evidence_task_count} 个任务")
            
            evidence_tasks = await self.trajectory_task_generator.generate_evidence_based_tasks(
                trajectories_data, max_tasks=evidence_task_count
            )
            
            # 将证据任务转换为AtomicTask对象
            for i, task_data in enumerate(evidence_tasks):
                if len(atomic_tasks) >= max_tasks:
                    break
                    
                # 创建增强的Synthesis组件
                input_info = SynthesisInput(
                    input_id=f"evidence_input_{i}",
                    content=task_data.get("question", "未知问题"),
                    metadata={
                        "difficulty": task_data.get("difficulty", "中等"),
                        "creativity_level": task_data.get("creativity_level", "3"),
                        "source_conclusion": "基于轨迹证据生成",
                        "task_pattern": task_data.get("relation_pattern", "trajectory_evidence")
                    }
                )
                
                answer = SynthesisAnswer(
                    answer_id=f"evidence_answer_{i}",
                    answer=task_data.get("expected_answer", "基于轨迹证据的答案"),
                    confidence=float(task_data.get("creativity_level", "3")) / 5.0
                )
                
                relation = SynthesisRelation(
                    relation_id=f"evidence_relation_{i}",
                    relation_type=task_data.get("relation_pattern", "trajectory_evidence"),
                    description=task_data.get("creativity_explanation", "基于轨迹证据的任务"),
                    parameters={
                        "reasoning_steps": task_data.get("reasoning_steps", []),
                        "entity_generalization": task_data.get("entity_generalization", ""),
                        "reverse_reasoning": task_data.get("reverse_reasoning", "")
                    }
                )
                
                # 创建原子任务
                atomic_task = AtomicTask.create_atomic(
                    question=task_data.get("question", "未知问题"),
                    input_info=input_info,
                    answer=answer,
                    relation=relation,
                    domain=task_data.get("domain", "general"),
                    requires_tool=task_data.get("required_tools", []) != [],
                    expected_tools=task_data.get("required_tools", [])
                )
                
                atomic_tasks.append(atomic_task)
                
            logger.info(f"✨ 基于轨迹证据生成了 {len(atomic_tasks)} 个任务")
            
            # 步骤2：基于结论的传统LLM生成（占40%）
            remaining_tasks = max_tasks - len(atomic_tasks)
            if remaining_tasks > 0:
                logger.info(f"🧠 开始基于结论的LLM生成 {remaining_tasks} 个任务")
                
                # 从轨迹数据中提取结论
                conclusions = await self._extract_conclusions_from_trajectories(trajectories_data)
                logger.info(f"📊 提取到 {len(conclusions)} 个结论")
                
                # 基于结论生成原子任务
                for conclusion in conclusions[:remaining_tasks]:
                    try:
                        generated_tasks = await self._generate_tasks_from_conclusion(conclusion)
                        
                        for task_data in generated_tasks:
                            if len(atomic_tasks) >= max_tasks:
                                break
                                
                            # 创建增强的Synthesis组件
                            input_info = SynthesisInput(
                                input_id=f"llm_input_{len(atomic_tasks)}",
                                content=task_data.get("question", "未知问题"),
                                metadata={
                                    "difficulty": task_data.get("difficulty", "中等"),
                                    "creativity_level": task_data.get("creativity_level", "3"),
                                    "source_conclusion": conclusion.get("content", ""),
                                    "task_pattern": task_data.get("relation_pattern", "general")
                                }
                            )
                            
                            answer = SynthesisAnswer(
                                answer_id=f"llm_answer_{len(atomic_tasks)}",
                                answer=task_data.get("expected_answer", "示例答案"),
                                confidence=float(task_data.get("creativity_level", "3")) / 5.0
                            )
                            
                            # 使用更丰富的关系信息
                            relation_type = task_data.get("relation_pattern", "extract_info")
                            relation = SynthesisRelation(
                                relation_id=f"llm_relation_{len(atomic_tasks)}",
                                relation_type=relation_type,
                                description=task_data.get("creativity_explanation", "从输入中提取信息"),
                                parameters={
                                    "reasoning_steps": task_data.get("reasoning_steps", []),
                                    "entity_generalization": task_data.get("entity_generalization", ""),
                                    "reverse_reasoning": task_data.get("reverse_reasoning", "")
                                }
                            )
                            
                            # 创建原子任务
                            atomic_task = AtomicTask.create_atomic(
                                question=task_data.get("question", "未知问题"),
                                input_info=input_info,
                                answer=answer,
                                relation=relation,
                                domain=task_data.get("domain", "general"),
                                requires_tool=task_data.get("required_tools", []) != [],
                                expected_tools=task_data.get("required_tools", [])
                            )
                            
                            atomic_tasks.append(atomic_task)
                            
                    except Exception as e:
                        logger.error(f"❌ 从结论生成原子任务失败: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"❌ 原子任务生成过程失败: {e}")
            # 失败时直接报错，不再回退
            raise RuntimeError(f"原子任务生成失败: {e}")
        
        logger.info(f"📋 生成原子任务: {len(atomic_tasks)} 个 (证据任务: {len([t for t in atomic_tasks if 'evidence' in t.input_info.input_id])}, LLM任务: {len([t for t in atomic_tasks if 'llm' in t.input_info.input_id])})")
        return atomic_tasks
    
    async def _generate_depth_extensions(self, atomic_tasks: List[AtomicTask], max_extensions: int) -> List[DepthExtendedTask]:
        """生成深度扩展任务（简化实现）"""
        logger.debug(f"📈 从 {len(atomic_tasks)} 个原子任务生成深度扩展")
        
        depth_tasks = []
        
        # 选择合适的原子任务进行深度扩展
        suitable_tasks = [task for task in atomic_tasks if task.requires_tool]
        
        for task in suitable_tasks[:max_extensions]:
            try:
                # 简化的深度扩展：创建超集输入
                superset_input = SynthesisInput(
                    input_id=f"superset_{task.task_id}",
                    content=f"扩展的输入内容，包含：{task.input_info.content}"
                )
                
                superset_relation = SynthesisRelation(
                    relation_id=f"superset_relation_{task.task_id}",
                    relation_type="superset_extraction",
                    description="从更大范围提取信息"
                )
                
                extended_task = DepthExtendedTask.create_depth_extended(
                    base_task=task,
                    superset_input=superset_input,
                    superset_relation=superset_relation,
                    intermediate_question=f"首先处理：{superset_input.content}",
                    combined_question=f"先处理扩展输入，然后解决：{task.question}",
                    combined_answer=f"通过两步处理得到：{task.answer.answer}"
                )
                
                depth_tasks.append(extended_task)
                    
            except Exception as e:
                logger.error(f"❌ 深度扩展失败 {task.task_id}: {e}")
                continue
        
        logger.info(f"📈 生成深度扩展任务: {len(depth_tasks)} 个")
        return depth_tasks
    
    async def _generate_width_extensions(self, atomic_tasks: List[AtomicTask], max_extensions: int) -> List[WidthExtendedTask]:
        """生成宽度扩展任务（简化实现）"""
        logger.debug(f"📊 从 {len(atomic_tasks)} 个原子任务生成宽度扩展")
        
        width_tasks = []
        
        # 将原子任务按领域分组，便于合并
        domain_groups = {}
        for task in atomic_tasks:
            domain = task.domain
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(task)
        
        # 生成宽度扩展
        extensions_generated = 0
        for domain, tasks in domain_groups.items():
            if extensions_generated >= max_extensions:
                break
                
            if len(tasks) >= 2:
                try:
                    # 每个领域最多合并2-3个任务
                    for i in range(0, len(tasks), 2):
                        if extensions_generated >= max_extensions:
                            break
                            
                        component_tasks = tasks[i:i+2]
                        if len(component_tasks) >= 2:
                            # 简化的宽度扩展：合并任务
                            merged_question = f"请同时完成以下任务：1) {component_tasks[0].question} 2) {component_tasks[1].question}"
                            merged_answer = f"1) {component_tasks[0].answer.answer} 2) {component_tasks[1].answer.answer}"
                            
                            extended_task = WidthExtendedTask.create_width_extended(
                                component_tasks=component_tasks,
                                merged_question=merged_question,
                                merged_answer=merged_answer,
                                merge_strategy="parallel"
                            )
                            
                            width_tasks.append(extended_task)
                            extensions_generated += 1
                                
                except Exception as e:
                    logger.error(f"❌ 宽度扩展失败 {domain}: {e}")
                    continue
        
        logger.info(f"📊 生成宽度扩展任务: {len(width_tasks)} 个")
        return width_tasks
    
    async def _extract_conclusions_from_trajectories(self, trajectories_data: List[Dict]) -> List[Dict]:
        """从轨迹数据中提取深度结论和结构化关系 - 使用关系驱动的模板"""
        try:
            # 准备轨迹数据摘要（修复字段映射）
            trajectory_summary = []
            for trajectory in trajectories_data[:5]:  # 限制处理数量
                # 修复字段映射：使用实际存在的字段
                raw_response = trajectory.get("raw_response", "")
                
                # 解析步骤和工具信息
                parsed_steps = self._parse_steps_from_response(raw_response)
                tools_used = self._extract_tools_from_response(raw_response)
                reasoning_blocks = self._extract_reasoning_from_response(raw_response)
                
                summary = {
                    "task_id": trajectory.get("task_id", "unknown"),
                    "question": trajectory.get("task_description", "未知问题"),  # 修复：task_description
                    "steps": parsed_steps[:5],  # 从raw_response解析的真实步骤
                    "final_answer": trajectory.get("final_result", "无答案"),  # 修复：final_result
                    "success": trajectory.get("success", False),
                    "tools_used": tools_used,  # 从raw_response解析的工具
                    "reasoning_process": reasoning_blocks,  # 从raw_response解析的推理过程
                    "domain": self._infer_domain_from_content(trajectory.get("task_description", "")),
                    "duration": trajectory.get("duration", 0),
                    "raw_content": raw_response[:500]  # 保留部分原始内容用于分析
                }
                trajectory_summary.append(summary)
            
            # 使用增强的深度结论提取模板（关系驱动）
            prompt = prompt_manager.render_template(
                "extract_conclusions",
                trajectory_data=str(trajectory_summary),
                max_conclusions=3
            )
            
            # 调用LLM进行深度分析（使用重试机制）
            response = await self._call_llm_with_retry(prompt, "深度结论提取")
            
            # 解析响应（包括结构化关系）
            try:
                import json
                # 确保response是字符串
                if isinstance(response, dict):
                    result = response
                else:
                    result = json.loads(response)
                conclusions = result.get("conclusions", [])
                
                # 验证结论质量（确保包含关系信息）
                valid_conclusions = []
                for conclusion in conclusions:
                    if (
                        conclusion.get("content") and 
                        conclusion.get("entities") and 
                        conclusion.get("relation") and
                        conclusion.get("relation_type")
                    ):
                        valid_conclusions.append(conclusion)
                    else:
                        logger.warning(f"⚠️ 结论缺少关键关系信息，已过滤: {conclusion.get('content', 'Unknown')}")
                
                logger.info(f"✅ 成功提取 {len(valid_conclusions)} 个包含结构化关系的结论")
                return valid_conclusions if valid_conclusions else self._get_default_conclusions(trajectories_data)
                
            except json.JSONDecodeError:
                logger.warning("⚠️ LLM响应格式不正确，尝试修复后再解析")
                # 尝试修复和重新解析
                fixed_response = self._attempt_json_repair(response)
                if fixed_response:
                    try:
                        result = json.loads(fixed_response)
                        conclusions = result.get("conclusions", [])
                        logger.info(f"✅ JSON修复成功，提取到 {len(conclusions)} 个结论")
                        return conclusions if conclusions else self._get_default_conclusions(trajectories_data)
                    except json.JSONDecodeError:
                        logger.warning("⚠️ JSON修复失败，使用默认结论")
                
                return self._get_default_conclusions(trajectories_data)
                
        except Exception as e:
            logger.error(f"❌ 深度结论提取失败: {e}")
            return self._get_default_conclusions(trajectories_data)
    
    async def _generate_tasks_from_conclusion(self, conclusion: Dict) -> List[Dict]:
        """基于结论和结构化关系生成创造性原子任务 - 使用关系驱动的反向推理"""
        try:
            # 验证结论是否包含必要的关系信息
            if not all(k in conclusion for k in ["content", "entities", "relation", "relation_type"]):
                logger.warning(f"⚠️ 结论缺少关键关系信息，使用简化生成: {conclusion.get('content', 'Unknown')}")
                return await self._fallback_task_generation(conclusion)
            
            # 使用关系驱动的原子任务生成模板
            prompt = prompt_manager.render_template(
                "generate_atomic_tasks",
                conclusion=str(conclusion),
                max_tasks=2
            )
            
            # 调用LLM进行创造性任务生成（使用重试机制）
            response = await self._call_llm_with_retry(prompt, "关系驱动任务生成")
            
            # 解析响应并验证创造性
            try:
                import json
                # 确保response是字符串
                if isinstance(response, dict):
                    result = response
                else:
                    result = json.loads(response)
                tasks = result.get("atomic_tasks", [])
                
                # 验证任务的创造性和关系驱动特征
                creative_tasks = []
                for task in tasks:
                    creativity_level = task.get("creativity_level", "1")
                    relation_pattern = task.get("relation_pattern", "")
                    entity_generalization = task.get("entity_generalization", "")
                    
                    # 要求创造性等级≥3且包含关系信息
                    if (
                        int(creativity_level) >= 3 and 
                        relation_pattern and 
                        entity_generalization and
                        task.get("question") and 
                        task.get("reverse_reasoning")
                    ):
                        creative_tasks.append(task)
                        logger.debug(f"✨ 创造性任务: {task.get('question', 'Unknown')[:50]}... (创造性: {creativity_level}星)")
                    else:
                        logger.debug(f"❌ 过滤低创造性任务: {task.get('question', 'Unknown')[:30]}...")
                
                if creative_tasks:
                    logger.info(f"✅ 成功生成 {len(creative_tasks)} 个高创造性任务 (关系: {conclusion.get('relation_type', 'Unknown')})")
                    return creative_tasks
                else:
                    logger.warning("⚠️ 未生成符合要求的创造性任务，使用简化生成")
                    return await self._fallback_task_generation(conclusion)
                    
            except json.JSONDecodeError:
                logger.warning("⚠️ 创造性任务生成响应格式不正确，尝试修复后再解析")
                # 尝试修复和重新解析
                fixed_response = self._attempt_json_repair(response)
                if fixed_response:
                    try:
                        result = json.loads(fixed_response)
                        atomic_tasks = result.get("atomic_tasks", [])
                        logger.info(f"✅ JSON修复成功，提取到 {len(atomic_tasks)} 个任务")
                        if atomic_tasks:
                            return atomic_tasks
                    except json.JSONDecodeError:
                        logger.warning("⚠️ JSON修复失败，使用回退方法")
                
                return await self._fallback_task_generation(conclusion)
                
        except Exception as e:
            logger.error(f"❌ 关系驱动的任务生成失败: {e}")
            return await self._fallback_task_generation(conclusion)
    
    async def _fallback_atomic_generation(self, trajectories_data: List[Dict], max_tasks: int) -> List[AtomicTask]:
        """回退的原子任务生成方法"""
        logger.info("🔄 使用回退方法生成原子任务")
        
        atomic_tasks = []
        
        for trajectory_data in trajectories_data[:max_tasks]:
            try:
                # 简化的原子任务生成
                task_id = trajectory_data.get('task_id', f'trajectory_{len(atomic_tasks)}')
                description = trajectory_data.get('question', '未知任务')
                
                # 创建简单的Synthesis组件
                input_info = SynthesisInput(
                    input_id=f"input_{task_id}",
                    content=description
                )
                
                answer = SynthesisAnswer(
                    answer_id=f"answer_{task_id}",
                    answer="示例答案"
                )
                
                relation = SynthesisRelation(
                    relation_id=f"relation_{task_id}",
                    relation_type="extract_info",
                    description="从输入中提取信息"
                )
                
                atomic_task = AtomicTask.create_atomic(
                    question=f"请解决以下任务：{description}",
                    input_info=input_info,
                    answer=answer,
                    relation=relation,
                    domain="general",
                    requires_tool=True  # 默认需要工具
                )
                
                atomic_tasks.append(atomic_task)
                
                if len(atomic_tasks) >= max_tasks:
                    break
                    
            except Exception as e:
                logger.error(f"❌ 回退生成失败 {trajectory_data.get('task_id', 'unknown')}: {e}")
                continue
        
        return atomic_tasks
    
    def _attempt_json_repair(self, response: str) -> str:
        """
        尝试修复损坏的JSON响应，增强系统的容错能力
        """
        import re
        import json
        
        # 方法1: 提取JSON块
        try:
            # 查找JSON块标记
            json_markers = ['```json', '```', '{', '[']
            
            for marker in json_markers:
                if marker in response:
                    # 找到JSON内容
                    if marker == '```json':
                        # 从```json到```之间的内容
                        pattern = r'```json\s*(.*?)\s*```'
                        match = re.search(pattern, response, re.DOTALL)
                        if match:
                            json_content = match.group(1).strip()
                            # 验证JSON有效性
                            json.loads(json_content)
                            logger.info("🔧 通过```json标记修复JSON")
                            return json_content
                    elif marker == '```':
                        # 从```到```之间的内容
                        pattern = r'```\s*(.*?)\s*```'
                        match = re.search(pattern, response, re.DOTALL)
                        if match:
                            json_content = match.group(1).strip()
                            if json_content.startswith('{') or json_content.startswith('['):
                                json.loads(json_content)
                                logger.info("🔧 通过```标记修复JSON")
                                return json_content
                    elif marker in ['{', '[']:
                        # 提取第一个完整的JSON对象
                        start_pos = response.find(marker)
                        if start_pos != -1:
                            json_content = self._extract_complete_json(response, start_pos)
                            if json_content:
                                json.loads(json_content)
                                logger.info("🔧 通过JSON对象提取修复")
                                return json_content
                    break
                    
        except (json.JSONDecodeError, IndexError):
            pass
        
        # 方法2: 智能清理和修复
        try:
            # 移除非JSON内容
            cleaned_response = response.strip()
            
            # 移除常见的前缀和后缀
            prefixes_to_remove = [
                '以下是JSON格式的回复：',
                '回复格式如下：',
                '这是JSON格式的回复：',
                'Here is the JSON response:',
                'JSON response:',
                'Response:',
                '```json',
                '```'
            ]
            
            suffixes_to_remove = [
                '```',
                '以上是完整的JSON回复',
                '这是完整的JSON格式回复',
                'This is the complete JSON response'
            ]
            
            for prefix in prefixes_to_remove:
                if cleaned_response.startswith(prefix):
                    cleaned_response = cleaned_response[len(prefix):].strip()
                    break
                    
            for suffix in suffixes_to_remove:
                if cleaned_response.endswith(suffix):
                    cleaned_response = cleaned_response[:-len(suffix)].strip()
                    break
            
            # 尝试解析清理后的内容
            if cleaned_response.startswith('{') or cleaned_response.startswith('['):
                json.loads(cleaned_response)
                logger.info("🔧 通过清理前缀后缀修复JSON")
                return cleaned_response
                
        except json.JSONDecodeError:
            pass
        
        # 方法3: 基于模式的JSON重建
        try:
            # 查找关键JSON结构
            conclusions_pattern = r'"conclusions":\s*\[(.*?)\]'
            tasks_pattern = r'"atomic_tasks":\s*\[(.*?)\]'
            
            conclusions_match = re.search(conclusions_pattern, response, re.DOTALL)
            tasks_match = re.search(tasks_pattern, response, re.DOTALL)
            
            if conclusions_match:
                # 重建conclusions JSON
                conclusions_content = conclusions_match.group(1).strip()
                rebuilt_json = f'{{"conclusions": [{conclusions_content}]}}'
                json.loads(rebuilt_json)  # 验证
                logger.info("🔧 通过conclusions模式重建JSON")
                return rebuilt_json
                
            if tasks_match:
                # 重建atomic_tasks JSON
                tasks_content = tasks_match.group(1).strip()
                rebuilt_json = f'{{"atomic_tasks": [{tasks_content}]}}'
                json.loads(rebuilt_json)  # 验证
                logger.info("🔧 通过atomic_tasks模式重建JSON")
                return rebuilt_json
                
        except json.JSONDecodeError:
            pass
        
        # 方法4: 尝试修复常见的JSON错误
        try:
            # 修复常见的JSON格式错误
            fixed_response = response
            
            # 修复单引号为双引号
            fixed_response = re.sub(r"'([^']*)':", r'"\1":', fixed_response)
            fixed_response = re.sub(r":\s*'([^']*)'", r': "\1"', fixed_response)
            
            # 修复缺少引号的键
            fixed_response = re.sub(r'([a-zA-Z_]\w*)\s*:', r'"\1":', fixed_response)
            
            # 修复尾随逗号
            fixed_response = re.sub(r',\s*([}\]])', r'\1', fixed_response)
            
            # 尝试解析修复后的内容
            if fixed_response.strip().startswith('{') or fixed_response.strip().startswith('['):
                json.loads(fixed_response)
                logger.info("🔧 通过格式修复JSON")
                return fixed_response
                
        except json.JSONDecodeError:
            pass
        
        return ""
    
    def _extract_complete_json(self, text: str, start_pos: int) -> str:
        """
        从指定位置提取完整的JSON对象
        """
        import json
        
        try:
            bracket_count = 0
            brace_count = 0
            in_string = False
            escape_next = False
            
            start_char = text[start_pos]
            target_char = '}' if start_char == '{' else ']'
            
            for i, char in enumerate(text[start_pos:], start_pos):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                    
                if in_string:
                    continue
                    
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                elif char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                
                # 找到匹配的闭合标记
                if start_char == '{' and brace_count == 0 and i > start_pos:
                    return text[start_pos:i+1]
                elif start_char == '[' and bracket_count == 0 and i > start_pos:
                    return text[start_pos:i+1]
                    
        except Exception:
            pass
        
        return ""
    
    def _get_default_conclusions(self, trajectories_data: List[Dict]) -> List[Dict]:
        """获取增强的默认结论（深度挖掘轨迹信息）"""
        default_conclusions = []
        
        for i, trajectory in enumerate(trajectories_data[:5]):  # 处理更多轨迹
            task_id = trajectory.get('task_id', f'trajectory_{i}')
            question = trajectory.get('question', '未知任务')
            tools_used = trajectory.get("tools_used", [])
            success = trajectory.get("success", True)
            final_answer = trajectory.get("final_answer", "")
            execution_steps = trajectory.get("execution_steps", [])
            
            # 根据轨迹内容生成不同类型的结论
            if tools_used:
                # 工具使用类型
                primary_tool = tools_used[0] if tools_used else "unknown"
                conclusion = {
                    "content": f"使用{primary_tool}工具成功完成{question}任务，展现了工具集成能力",
                    "entities": [primary_tool, question, "工具集成", "任务完成"],
                    "relation": f"{primary_tool}-工具执行-{question}-成功完成",
                    "relation_type": "tool_integration",
                    "scenario": f"{primary_tool}工具应用场景",
                    "difficulty": "中等" if len(tools_used) == 1 else "困难",
                    "required_tools": tools_used,
                    "generalization_potential": f"可扩展到所有{primary_tool}相关任务",
                    "confidence": 0.8 if success else 0.5,
                    "domain_knowledge": self._extract_domain_from_question(question),
                    "task_pattern": "tool_execution_pattern"
                }
            else:
                # 纯推理类型
                conclusion = {
                    "content": f"通过逻辑推理解决{question}，展现了分析能力",
                    "entities": ["逻辑推理", question, "分析能力", "解决方案"],
                    "relation": "推理分析-问题求解-结论生成",
                    "relation_type": "logical_reasoning",
                    "scenario": "复杂推理场景",
                    "difficulty": "中等",
                    "required_tools": ["code_execution"],
                    "generalization_potential": "可应用于同类推理问题",
                    "confidence": 0.7,
                    "domain_knowledge": self._extract_domain_from_question(question),
                    "task_pattern": "reasoning_pattern"
                }
            
            # 添加执行步骤信息
            if execution_steps:
                conclusion["execution_complexity"] = len(execution_steps)
                conclusion["step_pattern"] = [step.get("action", "unknown") for step in execution_steps[:3]]
            
            default_conclusions.append(conclusion)
        
        logger.info(f"🔍 生成增强默认结论，包含 {len(default_conclusions)} 个多样化结论")
        return default_conclusions
    
    def _extract_domain_from_question(self, question: str) -> str:
        """从问题中提取领域信息"""
        question_lower = question.lower()
        
        if any(keyword in question_lower for keyword in ['计算', '数学', '公式', '面积']):
            return "数学计算"
        elif any(keyword in question_lower for keyword in ['json', '数据', '解析', '格式']):
            return "数据处理"
        elif any(keyword in question_lower for keyword in ['代码', '编程', '脚本']):
            return "编程开发"
        elif any(keyword in question_lower for keyword in ['分析', '研究', '报告']):
            return "分析研究"
        else:
            return "通用任务"
    
    async def _fallback_task_generation(self, conclusion: Dict) -> List[Dict]:
        """创造性回退任务生成方法"""
        try:
            content = conclusion.get("content", "未知结论")
            relation_type = conclusion.get("relation_type", "general")
            domain = conclusion.get("domain_knowledge", "通用任务")
            required_tools = conclusion.get("required_tools", [])
            task_pattern = conclusion.get("task_pattern", "general_pattern")
            
            creative_tasks = []
            
            # 根据关系类型生成不同的创造性任务
            if relation_type == "tool_integration":
                # 工具集成类任务
                primary_tool = required_tools[0] if required_tools else "code_execution"
                creative_tasks.extend([
                    {
                        "question": f"设计一个{primary_tool}工具的高级应用场景，要求比基础用法更复杂",
                        "expected_answer": f"基于{primary_tool}的创新应用方案",
                        "task_type": "tool_required",
                        "domain": domain,
                        "difficulty": "困难",
                        "required_tools": required_tools,
                        "reasoning_steps": ["分析工具能力", "设计应用场景", "优化实现方案"],
                        "relation_pattern": f"{primary_tool}_advanced_application",
                        "entity_generalization": "高级工具应用模式",
                        "creativity_level": "4",
                        "creativity_explanation": f"从基础{primary_tool}使用扩展到创新应用设计",
                        "reverse_reasoning": f"反向推理：从{primary_tool}能力边界探索创新用法"
                    },
                    {
                        "question": f"如果{primary_tool}工具失效，设计3种替代解决方案",
                        "expected_answer": "多元化的问题解决策略",
                        "task_type": "tool_required",
                        "domain": domain,
                        "difficulty": "困难",
                        "required_tools": ["code_execution"],
                        "reasoning_steps": ["分析工具依赖", "探索替代方案", "评估可行性"],
                        "relation_pattern": "tool_failure_contingency",
                        "entity_generalization": "容错性设计思维",
                        "creativity_level": "5",
                        "creativity_explanation": "从工具依赖转向多路径问题解决",
                        "reverse_reasoning": "逆向思维：从失败场景推导成功策略"
                    }
                ])
            
            elif relation_type == "logical_reasoning":
                # 逻辑推理类任务
                creative_tasks.extend([
                    {
                        "question": f"基于{domain}领域知识，构建一个需要多步推理的复杂问题",
                        "expected_answer": "结构化的推理问题和解决路径",
                        "task_type": "tool_required",
                        "domain": domain,
                        "difficulty": "困难",
                        "required_tools": ["code_execution"],
                        "reasoning_steps": ["问题构造", "推理链设计", "验证逻辑"],
                        "relation_pattern": "multi_step_reasoning_construction",
                        "entity_generalization": "复杂推理问题设计",
                        "creativity_level": "5",
                        "creativity_explanation": "从简单推理升级到复杂推理问题构造",
                        "reverse_reasoning": "从解答反推更具挑战性的问题设计"
                    },
                    {
                        "question": f"设计一个{domain}领域的思维陷阱题，并提供破解思路",
                        "expected_answer": "具有启发性的陷阱题目和解题方法",
                        "task_type": "tool_required",
                        "domain": domain,
                        "difficulty": "困难",
                        "required_tools": ["code_execution"],
                        "reasoning_steps": ["识别认知偏误", "设计陷阱机制", "构建解题路径"],
                        "relation_pattern": "cognitive_trap_design",
                        "entity_generalization": "认知挑战题设计",
                        "creativity_level": "5",
                        "creativity_explanation": "从直接推理转向认知偏误的识别和利用",
                        "reverse_reasoning": "反向工程：从常见错误构造挑战题"
                    }
                ])
            
            else:
                # 通用创造性任务
                creative_tasks.extend([
                    {
                        "question": f"将{domain}领域的概念跨界应用到另一个完全不同的领域",
                        "expected_answer": "创新的跨领域应用方案",
                        "task_type": "tool_required",
                        "domain": "跨领域创新",
                        "difficulty": "困难",
                        "required_tools": ["code_execution"],
                        "reasoning_steps": ["概念抽象", "领域映射", "创新整合"],
                        "relation_pattern": "cross_domain_innovation",
                        "entity_generalization": "跨界思维模式",
                        "creativity_level": "5",
                        "creativity_explanation": "从单领域知识扩展到跨领域创新思维",
                        "reverse_reasoning": "类比推理：从相似结构发现创新机会"
                    }
                ])
            
            # 限制任务数量并确保质量
            selected_tasks = creative_tasks[:2]  # 选择前2个高质量任务
            
            logger.info(f"🎨 生成创造性回退任务: {len(selected_tasks)} 个高创造性任务")
            return selected_tasks
            
        except Exception as e:
            logger.error(f"❌ 创造性回退任务生成失败: {e}")
            return []
    
    async def _store_synthesis_results(self, result: SynthesisResult) -> None:
        """存储合成结果"""
        logger.debug(f"💾 存储合成会话结果: {result.session_id}")
        
        try:
            # 存储原子任务
            for i, task in enumerate(result.atomic_tasks):
                validation = result.validation_results[i] if i < len(result.validation_results) else None
                await self.storage.store_atomic_task(task, validation)
            
            # 存储深度扩展任务
            depth_start_idx = len(result.atomic_tasks)
            for i, task in enumerate(result.depth_extended_tasks):
                validation_idx = depth_start_idx + i
                validation = result.validation_results[validation_idx] if validation_idx < len(result.validation_results) else None
                await self.storage.store_depth_extended_task(task, validation)
            
            # 存储宽度扩展任务
            width_start_idx = depth_start_idx + len(result.depth_extended_tasks)
            for i, task in enumerate(result.width_extended_tasks):
                validation_idx = width_start_idx + i
                validation = result.validation_results[validation_idx] if validation_idx < len(result.validation_results) else None
                await self.storage.store_width_extended_task(task, validation)
            
            # 存储验证结果
            for validation in result.validation_results:
                self.storage.store_validation_result(validation)
            
            # 存储会话信息
            await self.storage.store_synthesis_session(result)
            
            logger.debug("✅ 合成结果存储完成")
            
        except Exception as e:
            logger.error(f"❌ 存储合成结果失败: {e}")
    
    def _parse_steps_from_response(self, raw_response: str) -> List[str]:
        """从原始响应中解析执行步骤"""
        import re
        
        steps = []
        
        # 1. 提取工具调用步骤
        tool_patterns = [
            r'<(browser_use|microsandbox|deepsearch|memory_staging)>([^<]+)</\1>',
            r'<(browser_search_google|browser_extract_content|microsandbox_execute|microsandbox_install_package)>([^<]+)</\1>'
        ]
        
        for pattern in tool_patterns:
            matches = re.findall(pattern, raw_response, re.DOTALL)
            for tool_name, content in matches:
                # 提取工具调用的核心操作
                step_desc = self._extract_step_description(tool_name, content.strip()[:100])
                if step_desc:
                    steps.append(step_desc)
        
        # 2. 提取思考和推理步骤
        think_blocks = re.findall(r'<think>(.*?)</think>', raw_response, re.DOTALL)
        for think in think_blocks:
            reasoning_steps = self._extract_reasoning_steps(think.strip())
            steps.extend(reasoning_steps)
        
        # 3. 提取answer标签中的总结步骤
        answer_blocks = re.findall(r'<answer>(.*?)</answer>', raw_response, re.DOTALL)
        for answer in answer_blocks:
            summary_steps = self._extract_summary_steps(answer.strip())
            steps.extend(summary_steps)
        
        return list(dict.fromkeys(steps))  # 去重但保持顺序
    
    def _extract_tools_from_response(self, raw_response: str) -> List[str]:
        """从原始响应中提取使用的工具"""
        import re
        
        tools = []
        
        # 提取所有工具调用
        tool_patterns = [
            r'<(browser_use|microsandbox|deepsearch|memory_staging)',
            r'<(browser_search_google|browser_extract_content|microsandbox_execute|microsandbox_install_package)'
        ]
        
        for pattern in tool_patterns:
            matches = re.findall(pattern, raw_response)
            tools.extend(matches)
        
        return list(set(tools))  # 去重
    
    def _extract_reasoning_from_response(self, raw_response: str) -> str:
        """从原始响应中提取推理过程"""
        import re
        
        reasoning_blocks = []
        
        # 提取think块
        think_matches = re.findall(r'<think>(.*?)</think>', raw_response, re.DOTALL)
        for think in think_matches:
            clean_think = think.strip()[:200]  # 限制长度
            if clean_think:
                reasoning_blocks.append(clean_think)
        
        return " | ".join(reasoning_blocks)
    
    def _extract_step_description(self, tool_name: str, content: str) -> str:
        """根据工具名称和内容提取步骤描述"""
        tool_mappings = {
            "browser_search_google": f"搜索信息: {content[:50]}",
            "browser_extract_content": f"提取内容: {content[:50]}",
            "microsandbox_execute": f"执行代码: {content[:50]}",
            "microsandbox_install_package": f"安装包: {content}",
            "deepsearch": f"深度搜索: {content[:50]}",
            "memory_staging": f"内存操作: {content[:50]}"
        }
        
        return tool_mappings.get(tool_name, f"{tool_name}: {content[:50]}")
    
    def _extract_reasoning_steps(self, think_content: str) -> List[str]:
        """从思考内容中提取推理步骤"""
        steps = []
        
        # 查找明确的步骤指示词
        step_indicators = ["首先", "然后", "接下来", "最后", "步骤", "第一", "第二", "第三"]
        
        lines = think_content.split('\n')
        for line in lines:
            line = line.strip()
            if len(line) > 10:  # 过滤过短的行
                for indicator in step_indicators:
                    if indicator in line:
                        steps.append(f"推理步骤: {line[:80]}")
                        break
        
        return steps[:3]  # 限制推理步骤数量
    
    def _extract_summary_steps(self, answer_content: str) -> List[str]:
        """从答案内容中提取总结步骤"""
        steps = []
        
        # 提取boxed内容
        import re
        boxed_matches = re.findall(r'\\boxed\{([^}]+)\}', answer_content, re.DOTALL)
        for boxed in boxed_matches:
            if len(boxed.strip()) > 20:  # 只取有意义的内容
                steps.append(f"总结结果: {boxed.strip()[:80]}")
        
        return steps
    
    def _infer_domain_from_content(self, content: str) -> str:
        """从内容推断领域"""
        domain_keywords = {
            "股票|股价|金融|投资": "金融",
            "量子|物理|科学": "科学研究",
            "代码|编程|Python|算法": "编程",
            "搜索|研究|论文": "研究分析",
            "大学|学校|教育": "教育",
            "蛋白质|生物|医学": "生物医学"
        }
        
        import re
        for pattern, domain in domain_keywords.items():
            if re.search(pattern, content):
                return domain
        
        return "通用"
    
    def _calculate_result_statistics(self, result: SynthesisResult) -> None:
        """计算结果统计信息"""
        all_tasks = result.atomic_tasks + result.depth_extended_tasks + result.width_extended_tasks
        
        result.total_tasks_generated = len(all_tasks)
        result.valid_tasks_count = sum(1 for v in result.validation_results if v.is_valid)
        result.tool_required_count = sum(1 for v in result.validation_results if v.requires_tool)
        result.reasoning_only_count = result.valid_tasks_count - result.tool_required_count
    
    def _update_session_stats(self, result: SynthesisResult) -> None:
        """更新会话统计"""
        self.session_stats["sessions_completed"] += 1
        self.session_stats["total_tasks_generated"] += result.total_tasks_generated
        self.session_stats["valid_tasks_count"] += result.valid_tasks_count
        self.session_stats["tool_required_count"] += result.tool_required_count
        self.session_stats["reasoning_only_count"] += result.reasoning_only_count
    
    async def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        storage_stats = await self.storage.get_statistics()
        
        return {
            "session_statistics": self.session_stats,
            "storage_statistics": storage_stats,
            "storage_info": self.storage.get_storage_info()
        }
    
    async def validate_existing_tasks(self, task_type: Optional[TaskType] = None) -> List[TaskValidationResult]:
        """验证已存储的任务"""
        logger.info("🔍 开始验证已存储的任务")
        
        # 加载任务
        task_data_list = await self.storage.load_tasks_by_type(task_type or TaskType.TOOL_REQUIRED)
        
        # 转换为任务对象（简化版本，仅用于验证）
        tasks = []
        for task_data in task_data_list:
            # 这里需要根据数据结构重构任务对象
            # 简化实现，实际需要完整的反序列化逻辑
            pass
        
        # 执行验证
        if tasks:
            validations = await self.validator.batch_validate_tasks(tasks)
            
            # 存储验证结果
            for validation in validations:
                self.storage.store_validation_result(validation)
            
            return validations
        
        return []
    
    def get_component_info(self) -> Dict[str, Any]:
        """获取组件信息"""
        return {
            "engine": "SynthesisEngine",
            "version": "1.0.0",
            "components": {
                "validator": self.validator.__class__.__name__,
                "storage": self.storage.__class__.__name__
            },
            "configuration": {
                "enable_strict_validation": self.enable_strict_validation,
                "storage_directory": str(self.storage.storage_dir)
            },
            "capabilities": {
                "atomic_generation": True,
                "depth_extension": True,
                "width_extension": True,
                "intelligent_validation": True,
                "tool_vs_reasoning_classification": True,
                "simplified_storage": True,
                "taskcraft_algorithm": True,
                "backward_search": True,
                "theme_aware_fusion": True,
                "relation_driven_reasoning": True
            }
        }
    
    # ========== TaskCraft 算法新增方法 ==========
    
    async def _perform_backward_search(self, known_fact: str) -> Optional[Dict]:
        """执行反向搜索，找到已知事实的背景知识"""
        try:
            prompt = prompt_manager.render_template(
                "backward_search",
                known_fact=known_fact
            )
            
            response = await self._call_llm_with_retry(prompt, "反向搜索算法")
            
            import json
            # 确保response是字符串
            if isinstance(response, dict):
                result = response
            else:
                result = json.loads(response)
            return result.get("backward_search_result")
            
        except Exception as e:
            logger.error(f"❌ 反向搜索失败: {e}")
            return None
    
    async def _perform_task_fusion(self, background_task: str, core_task: str, logical_relation: str) -> Optional[Dict]:
        """执行任务融合，将背景任务和核心任务融合成连贯的复杂问题"""
        try:
            prompt = prompt_manager.render_template(
                "task_fusion",
                background_task=background_task,
                core_task=core_task,
                logical_relation=logical_relation
            )
            
            response = await self._call_llm_with_retry(prompt, "任务融合算法")
            
            import json
            # 确保response是字符串
            if isinstance(response, dict):
                result = response
            else:
                result = json.loads(response)
            return result.get("task_fusion_result")
            
        except Exception as e:
            logger.error(f"❌ 任务融合失败: {e}")
            return None
    
    async def _semantic_cluster_tasks(self, atomic_tasks: List[AtomicTask]) -> Dict[str, List[AtomicTask]]:
        """对原子任务进行语义聚类，返回主题组"""
        try:
            # 简化的主题聚类：按领域和问题关键词分组
            theme_groups = {}
            
            for task in atomic_tasks:
                # 基于领域和问题关键词生成主题
                domain = task.domain
                question_keywords = self._extract_keywords(task.question)
                theme = f"{domain}_{question_keywords}"
                
                if theme not in theme_groups:
                    theme_groups[theme] = []
                theme_groups[theme].append(task)
            
            # 过滤出只有一个任务的组
            filtered_groups = {k: v for k, v in theme_groups.items() if len(v) >= 2}
            
            logger.debug(f"📋 语义聚类结果: {len(filtered_groups)} 个主题组")
            return filtered_groups
            
        except Exception as e:
            logger.error(f"❌ 语义聚类失败: {e}")
            # 回退到简单领域分组
            domain_groups = {}
            for task in atomic_tasks:
                domain = task.domain
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(task)
            return {k: v for k, v in domain_groups.items() if len(v) >= 2}
    
    def _extract_keywords(self, question: str) -> str:
        """从问题中提取关键词（简化实现）"""
        try:
            # 简化的关键词提取：找名词和动词
            keywords = []
            question_lower = question.lower()
            
            # 常见的技术关键词
            tech_keywords = [
                'python', 'pandas', 'numpy', 'transformer', 'gpt', 'ai', 'model', 
                '股价', '公司', '分析', '数据', '代码', '算法'
            ]
            
            for keyword in tech_keywords:
                if keyword in question_lower:
                    keywords.append(keyword)
            
            return '_'.join(keywords[:2]) if keywords else 'general'
            
        except Exception:
            return 'general'
    
    async def _analyze_theme_relationships(self, tasks: List[AtomicTask]) -> str:
        """分析任务组的主题关系"""
        try:
            # 生成主题分析
            analysis = {
                "common_domain": tasks[0].domain,
                "task_count": len(tasks),
                "questions": [task.question for task in tasks],
                "complexity_levels": [task.complexity.value for task in tasks],
                "requires_tools": [task.requires_tool for task in tasks]
            }
            
            return str(analysis)
            
        except Exception as e:
            logger.error(f"❌ 主题关系分析失败: {e}")
            return "简化主题分析"
    
    async def _perform_theme_aware_fusion(self, tasks: List[AtomicTask], theme_analysis: str) -> Optional[Dict]:
        """执行主题感知合并"""
        try:
            # 准备输入数据
            related_tasks_data = []
            for task in tasks:
                task_data = {
                    "question": task.question,
                    "domain": task.domain,
                    "complexity": task.complexity.value,
                    "requires_tool": task.requires_tool
                }
                related_tasks_data.append(task_data)
            
            prompt = prompt_manager.render_template(
                "theme_aware_fusion",
                related_tasks=str(related_tasks_data),
                theme_analysis=theme_analysis
            )
            
            response = await self._call_llm_with_retry(prompt, "主题感知融合")
            
            import json
            # 确保response是字符串
            if isinstance(response, dict):
                result = response
            else:
                result = json.loads(response)
            return result.get("theme_fusion_result")
            
        except Exception as e:
            logger.error(f"❌ 主题感知合并失败: {e}")
            return None
    
    async def _fallback_width_extension(self, atomic_tasks: List[AtomicTask], max_tasks: int) -> List[WidthExtendedTask]:
        """简化的宽度扩展回退方法"""
        try:
            width_tasks = []
            
            # 简单的领域分组合并
            domain_groups = {}
            for task in atomic_tasks:
                domain = task.domain
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(task)
            
            tasks_generated = 0
            for domain, tasks in domain_groups.items():
                if tasks_generated >= max_tasks or len(tasks) < 2:
                    continue
                    
                # 简单合并前两个任务
                component_tasks = tasks[:2]
                merged_question = f"请同时完成以下任务：1) {component_tasks[0].question} 2) {component_tasks[1].question}"
                merged_answer = f"1) {component_tasks[0].answer.answer} 2) {component_tasks[1].answer.answer}"
                
                extended_task = WidthExtendedTask.create_width_extended(
                    component_tasks=component_tasks,
                    merged_question=merged_question,
                    merged_answer=merged_answer,
                    merge_strategy="simple_parallel"
                )
                
                width_tasks.append(extended_task)
                tasks_generated += 1
            
            logger.debug(f"🔄 简化回退生成 {len(width_tasks)} 个宽度扩展任务")
            return width_tasks
            
        except Exception as e:
            logger.error(f"❌ 简化宽度扩展回退失败: {e}")
            return []