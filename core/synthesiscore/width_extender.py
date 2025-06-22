#!/usr/bin/env python3
"""
Width Extender - 宽度扩展器
基于TaskCraft算法，实现原子任务的宽度优先扩展（复合任务生成）
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import asdict
from collections import defaultdict

from core.interfaces import TrajectoryResult
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient
from .enhanced_interfaces import (
    AtomicTask, CompositeTask, TaskDifficulty, TaskType, 
    EnhancedSynthesisConfig, generate_task_id, calculate_complexity_score
)

logger = logging.getLogger(__name__)


class SemanticGrouper:
    """语义分组器 - 将相似的原子任务分组"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def group_atomic_tasks(self, atomic_tasks: List[AtomicTask]) -> List[List[AtomicTask]]:
        """将原子任务按语义相似性分组"""
        logger.info(f"🔄 开始对 {len(atomic_tasks)} 个原子任务进行语义分组")
        
        if len(atomic_tasks) < self.config.WIDTH_EXTENSION_CONFIG['min_tasks_for_grouping']:
            logger.warning(f"⚠️ 任务数量不足，无法进行分组 ({len(atomic_tasks)} < {self.config.WIDTH_EXTENSION_CONFIG['min_tasks_for_grouping']})")
            return []
        
        try:
            # 1. 计算任务间相似度矩阵
            similarity_matrix = await self._calculate_similarity_matrix(atomic_tasks)
            
            # 2. 基于相似度进行聚类
            task_groups = await self._cluster_tasks_by_similarity(atomic_tasks, similarity_matrix)
            
            # 3. 过滤和验证分组
            valid_groups = self._filter_valid_groups(task_groups)
            
            logger.info(f"✅ 语义分组完成，得到 {len(valid_groups)} 个有效组")
            return valid_groups
            
        except Exception as e:
            logger.error(f"❌ 语义分组失败: {e}")
            return []
    
    async def _calculate_similarity_matrix(self, atomic_tasks: List[AtomicTask]) -> List[List[float]]:
        """计算任务间相似度矩阵"""
        n = len(atomic_tasks)
        similarity_matrix = [[0.0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                try:
                    similarity = await self._calculate_task_similarity(atomic_tasks[i], atomic_tasks[j])
                    similarity_matrix[i][j] = similarity
                    similarity_matrix[j][i] = similarity
                except Exception as e:
                    logger.error(f"❌ 计算相似度失败 ({i}, {j}): {e}")
                    similarity_matrix[i][j] = 0.0
                    similarity_matrix[j][i] = 0.0
        
        return similarity_matrix
    
    async def _calculate_task_similarity(self, task1: AtomicTask, task2: AtomicTask) -> float:
        """计算两个任务的相似度"""
        
        similarity_prompt = f"""
评估以下两个任务的语义相似性：

任务1:
问题: {task1.question}
答案: {task1.golden_answer}
工具: {task1.required_tools}

任务2:
问题: {task2.question}
答案: {task2.golden_answer}
工具: {task2.required_tools}

评估维度:
1. 问题领域相似性（如都关于股价、都关于地理信息等）
2. 答案类型相似性（如都是数值、都是日期等）
3. 工具使用相似性
4. 知识背景相似性

请返回0.0-1.0的相似度分数，1.0表示非常相似。
只返回数值，不要其他文字。
"""
        
        try:
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=similarity_prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": "task_similarity_assessment"}
            )
            
            thinking = response.get('thinking', '0.0')
            
            # 提取数值
            score_match = re.search(r'(\d+\.?\d*)', thinking)
            if score_match:
                score = float(score_match.group(1))
                return min(score, 1.0) if score <= 1.0 else score / 10.0
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"❌ 相似度计算失败: {e}")
            return 0.0
    
    async def _cluster_tasks_by_similarity(self, atomic_tasks: List[AtomicTask], 
                                         similarity_matrix: List[List[float]]) -> List[List[AtomicTask]]:
        """基于相似度矩阵进行聚类"""
        n = len(atomic_tasks)
        threshold = self.config.WIDTH_EXTENSION_CONFIG['semantic_similarity_threshold']
        max_group_size = self.config.WIDTH_EXTENSION_CONFIG['max_tasks_per_group']
        
        # 使用简单的基于阈值的聚类算法
        groups = []
        used_indices = set()
        
        for i in range(n):
            if i in used_indices:
                continue
            
            # 开始新的聚类
            current_group = [i]
            used_indices.add(i)
            
            # 寻找相似的任务
            for j in range(i + 1, n):
                if j in used_indices:
                    continue
                
                if len(current_group) >= max_group_size:
                    break
                
                # 检查与组内所有任务的相似度
                avg_similarity = sum(similarity_matrix[k][j] for k in current_group) / len(current_group)
                
                if avg_similarity >= threshold:
                    current_group.append(j)
                    used_indices.add(j)
            
            # 只保留包含多个任务的组
            if len(current_group) >= self.config.WIDTH_EXTENSION_CONFIG['min_tasks_for_grouping']:
                group_tasks = [atomic_tasks[idx] for idx in current_group]
                groups.append(group_tasks)
        
        return groups
    
    def _filter_valid_groups(self, task_groups: List[List[AtomicTask]]) -> List[List[AtomicTask]]:
        """过滤和验证分组"""
        valid_groups = []
        
        for group in task_groups:
            if (self.config.WIDTH_EXTENSION_CONFIG['min_tasks_for_grouping'] <= 
                len(group) <= 
                self.config.WIDTH_EXTENSION_CONFIG['max_tasks_per_group']):
                
                # 验证组内任务不完全重复
                if self._check_group_diversity(group):
                    valid_groups.append(group)
        
        return valid_groups
    
    def _check_group_diversity(self, group: List[AtomicTask]) -> bool:
        """检查组内任务的多样性"""
        if len(group) < 2:
            return False
        
        # 检查问题不完全相同
        questions = set(task.question.lower().strip() for task in group)
        if len(questions) < len(group):
            return False
        
        # 检查答案不完全相同
        answers = set(task.golden_answer.lower().strip() for task in group)
        if len(answers) < 2:  # 允许部分答案相同，但不能全部相同
            return False
        
        return True


class TaskFuser:
    """任务融合器 - 将分组的任务融合为复合任务"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def fuse_task_group(self, task_group: List[AtomicTask]) -> Optional[CompositeTask]:
        """融合任务组为复合任务"""
        logger.debug(f"🔗 开始融合任务组，包含 {len(task_group)} 个任务")
        
        try:
            # 1. 分析任务组的共同主题
            common_theme = await self._analyze_common_theme(task_group)
            
            # 2. 生成复合问题
            composite_question = await self._generate_composite_question(task_group, common_theme)
            
            # 3. 整合答案
            composite_answers = self._integrate_answers(task_group)
            
            # 4. 确定工具需求和复杂度
            expected_tools = self._merge_tool_requirements(task_group)
            difficulty_level = self._determine_composite_difficulty(task_group)
            
            # 5. 创建复合任务
            composite_task = CompositeTask(
                task_id=generate_task_id(TaskType.WIDTH_EXTENDED, f"group_{len(task_group)}"),
                question=composite_question,
                golden_answers=composite_answers,
                source_atomic_tasks=[task.task_id for task in task_group],
                original_questions=[task.question for task in task_group],
                content_identifier=self._generate_group_identifier(task_group),
                expected_tools=expected_tools,
                difficulty_level=difficulty_level,
                merge_strategy="width"
            )
            
            logger.info(f"✅ 任务组融合完成: {composite_task.task_id}")
            return composite_task
            
        except Exception as e:
            logger.error(f"❌ 任务组融合失败: {e}")
            return None
    
    async def _analyze_common_theme(self, task_group: List[AtomicTask]) -> str:
        """分析任务组的共同主题"""
        
        theme_prompt = f"""
分析以下原子任务组的共同主题和领域：

任务列表:
{chr(10).join(f"- {task.question} (答案: {task.golden_answer})" for task in task_group)}

请识别：
1. 这些任务的共同领域或主题
2. 它们之间的内在联系
3. 可以如何整合为一个更大的问题

返回一个简洁的主题描述。
"""
        
        try:
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=theme_prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": "theme_analysis"}
            )
            
            return response.get('thinking', '').strip() or "相关信息查询"
            
        except Exception as e:
            logger.error(f"❌ 主题分析失败: {e}")
            return "相关信息查询"
    
    async def _generate_composite_question(self, task_group: List[AtomicTask], common_theme: str) -> str:
        """生成复合问题"""
        
        question_prompt = f"""
基于以下原子任务组和共同主题，生成一个综合性问题。

共同主题: {common_theme}

原子任务:
{chr(10).join(f"{i+1}. {task.question}" for i, task in enumerate(task_group))}

要求：
1. 包含所有原子任务的信息需求
2. 比单个原子任务更复杂但仍可执行
3. 需要多步骤推理和工具调用
4. 有明确的执行路径

请直接返回JSON格式：
{{
    "composite_question": "生成的复合问题内容",
    "explanation": "简要说明如何整合原子任务"
}}
"""
        
        try:
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=question_prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": "composite_question_generation"}
            )
            
            # 尝试从JSON响应中提取复合问题
            thinking = response.get('thinking', '').strip()
            if thinking:
                try:
                    # 尝试解析JSON
                    import json
                    parsed = json.loads(thinking)
                    if 'composite_question' in parsed:
                        generated_question = parsed['composite_question'].strip()
                        if len(generated_question) > 20:
                            return generated_question
                except json.JSONDecodeError:
                    pass
            
            # 如果JSON解析失败，尝试从thinking中提取
            generated_question = self._extract_question_from_thinking(thinking)
            
            # 如果仍然失败，使用回退策略
            if not generated_question or len(generated_question) < 20:
                return self._fallback_composite_question(task_group, common_theme)
            
            return generated_question
            
        except Exception as e:
            logger.error(f"❌ 复合问题生成失败: {e}")
            return self._fallback_composite_question(task_group, common_theme)
    
    def _extract_question_from_thinking(self, thinking: str) -> str:
        """从thinking中提取复合问题"""
        if not thinking:
            return ""
        
        # 尝试找到以问号结尾的句子
        sentences = thinking.split('。')
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence.endswith('？') or sentence.endswith('?'):
                # 确保句子足够长且看起来像一个完整的问题
                if len(sentence) > 20 and not sentence.startswith('STEP'):
                    return sentence
        
        # 如果没找到问号结尾的句子，尝试找到以请求动词开头的长句子
        lines = thinking.split('\n')
        for line in lines:
            line = line.strip()
            if (line.startswith('请') or line.startswith('基于') or line.startswith('结合')) and len(line) > 30:
                # 移除可能的编号前缀
                if '.' in line[:10]:
                    line = line.split('.', 1)[-1].strip()
                return line
        
        return ""
    
    def _fallback_composite_question(self, task_group: List[AtomicTask], common_theme: str) -> str:
        """复合问题生成失败时的回退策略"""
        if len(task_group) == 2:
            return f"请同时回答以下问题：1) {task_group[0].question} 2) {task_group[1].question}"
        else:
            return f"请收集关于{common_theme}的以下信息：" + "；".join(f"({i+1}) {task.question}" for i, task in enumerate(task_group))
    
    def _integrate_answers(self, task_group: List[AtomicTask]) -> List[str]:
        """整合答案"""
        return [task.golden_answer for task in task_group]
    
    def _merge_tool_requirements(self, task_group: List[AtomicTask]) -> List[str]:
        """合并工具需求"""
        all_tools = set()
        for task in task_group:
            all_tools.update(task.required_tools)
        return list(all_tools)
    
    def _determine_composite_difficulty(self, task_group: List[AtomicTask]) -> TaskDifficulty:
        """确定复合任务难度"""
        # 复合任务的难度基于组内任务数量和复杂度
        group_size = len(task_group)
        total_tools = len(self._merge_tool_requirements(task_group))
        
        if group_size <= 2 and total_tools <= 3:
            return TaskDifficulty.MEDIUM
        elif group_size <= 3 and total_tools <= 5:
            return TaskDifficulty.COMPLEX
        else:
            return TaskDifficulty.COMPLEX
    
    def _generate_group_identifier(self, task_group: List[AtomicTask]) -> str:
        """生成组标识符"""
        # 使用第一个任务的内容标识符作为基础
        base_identifier = task_group[0].content_identifier if task_group else "unknown"
        return f"composite_{base_identifier}_{len(task_group)}"


class DecompositionValidator:
    """分解验证器 - 验证复合任务的合理性"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def validate_composite_task(self, composite_task: CompositeTask) -> Dict[str, Any]:
        """验证复合任务的合理性"""
        logger.debug(f"🔍 验证复合任务: {composite_task.task_id}")
        
        try:
            # 1. 分解验证
            decomposition_result = await self._validate_decomposition(composite_task)
            
            # 2. 复杂性验证
            complexity_result = await self._validate_complexity(composite_task)
            
            # 3. 可执行性评估
            executability_result = await self._assess_executability(composite_task)
            
            # 4. 综合评分
            overall_score = self._calculate_overall_validation_score(
                decomposition_result, complexity_result, executability_result
            )
            
            validation_result = {
                "is_valid": overall_score >= 0.7,
                "overall_score": overall_score,
                "decomposition": decomposition_result,
                "complexity": complexity_result,
                "executability": executability_result,
                "recommendation": "accept" if overall_score >= 0.8 else "modify" if overall_score >= 0.6 else "reject"
            }
            
            logger.info(f"✅ 复合任务验证完成: {composite_task.task_id} (分数: {overall_score:.3f})")
            return validation_result
            
        except Exception as e:
            logger.error(f"❌ 复合任务验证失败 {composite_task.task_id}: {e}")
            return {
                "is_valid": False,
                "overall_score": 0.0,
                "error": str(e),
                "recommendation": "reject"
            }
    
    async def _validate_decomposition(self, composite_task: CompositeTask) -> Dict[str, Any]:
        """验证分解合理性"""
        
        decomposition_prompt = f"""
验证以下复合任务是否可以合理分解为其组成的原子任务：

复合任务问题: {composite_task.question}

原子任务列表:
{chr(10).join(f"- {q}" for q in composite_task.original_questions)}

验证标准:
1. 复合任务是否涵盖了所有原子任务的信息需求？
2. 各原子任务之间是否存在逻辑关联？
3. 复合任务是否比单个原子任务更有价值？
4. 分解是否自然合理？

请返回JSON格式的验证结果：
{{
    "covers_all_atomics": true/false,
    "logical_connection": true/false,
    "added_value": true/false,
    "natural_decomposition": true/false,
    "score": 0.0-1.0,
    "reasoning": "验证理由"
}}
"""
        
        try:
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=decomposition_prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": "decomposition_validation"}
            )
            
            return self._parse_validation_response(response)
            
        except Exception as e:
            logger.error(f"❌ 分解验证失败: {e}")
            return {"score": 0.0, "reasoning": f"验证失败: {e}"}
    
    async def _validate_complexity(self, composite_task: CompositeTask) -> Dict[str, Any]:
        """验证复杂性合理性"""
        
        complexity_prompt = f"""
评估以下复合任务的复杂性是否合理：

复合任务: {composite_task.question}
预期工具: {composite_task.expected_tools}
原子任务数量: {len(composite_task.source_atomic_tasks)}

评估标准:
1. 任务复杂度是否适中（不过于简单也不过于复杂）？
2. 工具需求是否合理？
3. 是否需要多步骤推理？
4. 认知负荷是否在可接受范围内？

请返回0.0-1.0的复杂性评分。
"""
        
        try:
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=complexity_prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": "complexity_validation"}
            )
            
            thinking = response.get('thinking', '0.5')
            score_match = re.search(r'(\d+\.?\d*)', thinking)
            if score_match:
                score = float(score_match.group(1))
                score = min(score, 1.0) if score <= 1.0 else score / 10.0
            else:
                score = 0.5
            
            return {"score": score, "reasoning": thinking}
            
        except Exception as e:
            logger.error(f"❌ 复杂性验证失败: {e}")
            return {"score": 0.5, "reasoning": f"验证失败: {e}"}
    
    async def _assess_executability(self, composite_task: CompositeTask) -> Dict[str, Any]:
        """评估可执行性"""
        
        # 基于启发式规则评估可执行性
        score = 1.0
        issues = []
        
        # 检查问题长度
        if len(composite_task.question) > 500:
            score -= 0.2
            issues.append("问题过长，可能影响理解")
        
        # 检查工具需求
        if len(composite_task.expected_tools) > 5:
            score -= 0.2
            issues.append("工具需求过多")
        elif len(composite_task.expected_tools) == 0:
            score -= 0.3
            issues.append("缺少工具需求")
        
        # 检查子任务数量
        if len(composite_task.source_atomic_tasks) > 4:
            score -= 0.2
            issues.append("子任务过多")
        
        # 检查答案数量匹配
        if len(composite_task.golden_answers) != len(composite_task.source_atomic_tasks):
            score -= 0.3
            issues.append("答案数量与子任务不匹配")
        
        return {
            "score": max(score, 0.0),
            "issues": issues,
            "reasoning": "; ".join(issues) if issues else "可执行性良好"
        }
    
    def _parse_validation_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """解析验证响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                result = json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"score": 0.5, "reasoning": "解析失败"}
            
            return result
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析验证响应失败: {e}")
            return {"score": 0.5, "reasoning": f"解析失败: {e}"}
    
    def _calculate_overall_validation_score(self, decomposition_result: Dict[str, Any], 
                                          complexity_result: Dict[str, Any], 
                                          executability_result: Dict[str, Any]) -> float:
        """计算总体验证分数"""
        weights = {
            "decomposition": 0.4,
            "complexity": 0.3,
            "executability": 0.3
        }
        
        decomposition_score = decomposition_result.get('score', 0.0)
        complexity_score = complexity_result.get('score', 0.0)
        executability_score = executability_result.get('score', 0.0)
        
        overall_score = (
            decomposition_score * weights["decomposition"] +
            complexity_score * weights["complexity"] +
            executability_score * weights["executability"]
        )
        
        return overall_score


class WidthExtender:
    """宽度扩展器 - 统一的宽度扩展接口"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.semantic_grouper = SemanticGrouper(llm_client)
        self.task_fuser = TaskFuser(llm_client)
        self.decomposition_validator = DecompositionValidator(llm_client)
        self.config = EnhancedSynthesisConfig()
    
    async def extend_atomic_tasks_width(self, atomic_tasks: List[AtomicTask], 
                                       adaptive_config: Optional[Any] = None) -> List[CompositeTask]:
        """优化的宽度扩展原子任务为复合任务"""
        logger.info(f"🚀 开始宽度扩展 {len(atomic_tasks)} 个原子任务")
        
        if not atomic_tasks:
            return []
        
        try:
            # 使用自适应配置更新相似度阈值
            if adaptive_config:
                original_threshold = self.config.WIDTH_EXTENSION_CONFIG['semantic_similarity_threshold']
                adaptive_threshold = adaptive_config.width_config["semantic_similarity_threshold"]
                self.config.WIDTH_EXTENSION_CONFIG['semantic_similarity_threshold'] = adaptive_threshold
                logger.debug(f"🔧 使用自适应相似度阈值: {adaptive_threshold} (原值: {original_threshold})")
            
            # 1. 语义分组
            task_groups = await self.semantic_grouper.group_atomic_tasks(atomic_tasks)
            
            if not task_groups:
                logger.warning("⚠️ 未找到可分组的任务")
                return []
            
            logger.info(f"📊 语义分组完成，得到 {len(task_groups)} 个任务组")
            
            # 2. 批量并行融合各组任务
            composite_tasks = await self._batch_fuse_task_groups(task_groups, adaptive_config)
            
            # 3. 批量验证复合任务
            validated_tasks = await self._batch_validate_composite_tasks(composite_tasks, adaptive_config)
            
            logger.info(f"✅ 宽度扩展完成，生成 {len(validated_tasks)} 个有效复合任务")
            return validated_tasks
            
        except Exception as e:
            logger.error(f"❌ 宽度扩展失败: {e}")
            return []
    
    async def _batch_fuse_task_groups(self, task_groups: List[List[AtomicTask]], 
                                     adaptive_config: Optional[Any] = None) -> List[CompositeTask]:
        """批量融合任务组"""
        max_concurrent = adaptive_config.batch_config["max_concurrent_batches"] if adaptive_config else 3
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fuse_with_semaphore(group: List[AtomicTask]):
            async with semaphore:
                try:
                    return await self.task_fuser.fuse_task_group(group)
                except Exception as e:
                    logger.error(f"❌ 任务组融合失败: {e}")
                    return None
        
        # 并行处理所有组
        fusion_results = await asyncio.gather(
            *[fuse_with_semaphore(group) for group in task_groups],
            return_exceptions=True
        )
        
        # 收集有效结果
        composite_tasks = []
        for i, result in enumerate(fusion_results):
            if isinstance(result, CompositeTask):
                composite_tasks.append(result)
            elif isinstance(result, Exception):
                logger.error(f"❌ 任务组 {i} 融合异常: {result}")
            elif result is None:
                logger.warning(f"⚠️ 任务组 {i} 融合返回空结果")
        
        logger.info(f"✅ 任务组融合完成，成功融合 {len(composite_tasks)}/{len(task_groups)} 个组")
        return composite_tasks
    
    async def _batch_validate_composite_tasks(self, composite_tasks: List[CompositeTask], 
                                            adaptive_config: Optional[Any] = None) -> List[CompositeTask]:
        """批量验证复合任务"""
        if not composite_tasks:
            return []
        
        max_concurrent = adaptive_config.batch_config["max_concurrent_batches"] if adaptive_config else 3
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def validate_with_semaphore(task: CompositeTask):
            async with semaphore:
                try:
                    validation_result = await self.decomposition_validator.validate_composite_task(task)
                    return task, validation_result
                except Exception as e:
                    logger.error(f"❌ 复合任务验证失败 {task.task_id}: {e}")
                    return task, {"is_valid": False, "error": str(e)}
        
        # 并行验证所有任务
        validation_results = await asyncio.gather(
            *[validate_with_semaphore(task) for task in composite_tasks],
            return_exceptions=True
        )
        
        # 筛选有效任务
        validated_tasks = []
        for result in validation_results:
            if isinstance(result, tuple):
                task, validation = result
                if validation.get('is_valid', False):
                    validated_tasks.append(task)
                else:
                    logger.warning(f"⚠️ 复合任务验证不通过: {task.task_id}")
            elif isinstance(result, Exception):
                logger.error(f"❌ 复合任务验证异常: {result}")
        
        logger.info(f"✅ 复合任务验证完成，{len(validated_tasks)}/{len(composite_tasks)} 个任务通过验证")
        return validated_tasks
    
    async def get_width_extension_statistics(self, atomic_tasks: List[AtomicTask], 
                                           composite_tasks: List[CompositeTask]) -> Dict[str, Any]:
        """获取宽度扩展统计信息"""
        if not atomic_tasks:
            return {"total_atomic_tasks": 0, "total_composite_tasks": 0}
        
        # 计算分组效率
        grouped_atomic_tasks = set()
        for composite_task in composite_tasks:
            grouped_atomic_tasks.update(composite_task.source_atomic_tasks)
        
        grouping_efficiency = len(grouped_atomic_tasks) / len(atomic_tasks)
        
        # 计算平均组大小
        if composite_tasks:
            avg_group_size = sum(len(task.source_atomic_tasks) for task in composite_tasks) / len(composite_tasks)
        else:
            avg_group_size = 0.0
        
        # 统计工具使用
        tool_usage_before = defaultdict(int)
        tool_usage_after = defaultdict(int)
        
        for task in atomic_tasks:
            for tool in task.required_tools:
                tool_usage_before[tool] += 1
        
        for task in composite_tasks:
            for tool in task.expected_tools:
                tool_usage_after[tool] += 1
        
        return {
            "total_atomic_tasks": len(atomic_tasks),
            "total_composite_tasks": len(composite_tasks),
            "grouping_efficiency": grouping_efficiency,
            "average_group_size": avg_group_size,
            "tool_usage_before": dict(tool_usage_before),
            "tool_usage_after": dict(tool_usage_after),
            "complexity_increase": self._calculate_average_complexity_increase(atomic_tasks, composite_tasks)
        }
    
    def _calculate_average_complexity_increase(self, atomic_tasks: List[AtomicTask], 
                                             composite_tasks: List[CompositeTask]) -> float:
        """计算平均复杂度增长"""
        if not atomic_tasks or not composite_tasks:
            return 0.0
        
        # 计算原子任务的平均复杂度
        atomic_complexity = sum(calculate_complexity_score(task) for task in atomic_tasks) / len(atomic_tasks)
        
        # 计算复合任务的平均复杂度
        composite_complexity = sum(calculate_complexity_score(task) for task in composite_tasks) / len(composite_tasks)
        
        return composite_complexity - atomic_complexity