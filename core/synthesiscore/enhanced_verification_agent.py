#!/usr/bin/env python3
"""
Enhanced Verification Agent - 增强的多维度任务验证器
基于TaskCraft的质量控制体系，实现多维度任务质量评估
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import asdict

from core.llm_client import LLMClient
from .enhanced_interfaces import (
    AtomicTask, ExtendedTask, CompositeTask, TaskVerificationMetrics,
    TaskUnion, TaskType, TaskDifficulty
)

logger = logging.getLogger(__name__)


class EnhancedVerificationAgent:
    """增强验证代理 - 多维度任务质量评估"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        
        # 验证提示词模板
        self.verification_prompts = {
            "executability": self._get_executability_prompt(),
            "difficulty": self._get_difficulty_prompt(),
            "answer_uniqueness": self._get_uniqueness_prompt(),
            "tool_requirements": self._get_tool_requirements_prompt(),
            "language_quality": self._get_language_quality_prompt(),
            "cognitive_complexity": self._get_cognitive_complexity_prompt(),
            "atomicity": self._get_atomicity_prompt()
        }
    
    async def verify_task(self, task: TaskUnion) -> TaskVerificationMetrics:
        """执行多维度任务验证"""
        logger.info(f"🔍 开始多维度验证任务: {task.task_id}")
        
        try:
            # 创建验证指标对象
            metrics = TaskVerificationMetrics(task_id=task.task_id)
            
            # 并行执行所有维度的验证
            verification_tasks = []
            
            # 基础维度验证（所有任务类型）
            basic_dimensions = [
                "executability", "difficulty", "answer_uniqueness", 
                "tool_requirements", "language_quality", "cognitive_complexity"
            ]
            
            for dimension in basic_dimensions:
                verification_tasks.append(
                    self._verify_dimension(task, dimension)
                )
            
            # 原子性验证（仅适用于原子任务）
            if isinstance(task, AtomicTask):
                verification_tasks.append(
                    self._verify_dimension(task, "atomicity")
                )
            
            # 执行并发验证
            results = await asyncio.gather(*verification_tasks, return_exceptions=True)
            
            # 处理验证结果
            for i, result in enumerate(results):
                if isinstance(result, tuple):
                    dimension, score, feedback = result
                    metrics.verification_dimensions[dimension] = score
                    if feedback:
                        metrics.detailed_feedback.append(f"{dimension}: {feedback}")
                elif isinstance(result, Exception):
                    logger.error(f"❌ 维度验证失败: {result}")
                    # 对失败的维度使用默认分数
                    dimension = basic_dimensions[i] if i < len(basic_dimensions) else "atomicity"
                    metrics.verification_dimensions[dimension] = 0.5
            
            # 计算总体分数
            overall_score = metrics.calculate_overall_score()
            
            logger.info(f"✅ 任务验证完成: {task.task_id} (总分: {overall_score:.3f})")
            return metrics
            
        except Exception as e:
            logger.error(f"❌ 任务验证失败 {task.task_id}: {e}")
            # 返回失败的验证结果
            metrics = TaskVerificationMetrics(task_id=task.task_id)
            metrics.detailed_feedback.append(f"验证过程异常: {str(e)}")
            return metrics
    
    async def _verify_dimension(self, task: TaskUnion, dimension: str) -> tuple[str, float, str]:
        """验证单个维度"""
        try:
            prompt_template = self.verification_prompts[dimension]
            prompt = self._format_verification_prompt(task, prompt_template, dimension)
            
            response = await self.llm_client.generate_enhanced_reasoning(
                task_description=prompt,
                available_tools=[],
                tool_descriptions="",
                execution_context={"mode": f"verification_{dimension}"}
            )
            
            # 解析验证结果
            score, feedback = self._parse_verification_response(response, dimension)
            return dimension, score, feedback
            
        except Exception as e:
            logger.error(f"❌ 维度 {dimension} 验证失败: {e}")
            return dimension, 0.5, f"验证失败: {str(e)}"
    
    def _format_verification_prompt(self, task: TaskUnion, template: str, dimension: str) -> str:
        """格式化验证提示词"""
        
        # 提取任务信息
        task_info = {
            "question": getattr(task, 'question', ''),
            "answer": getattr(task, 'golden_answer', '') or getattr(task, 'golden_answers', []),
            "tools": getattr(task, 'required_tools', []) or getattr(task, 'expected_tools', []),
            "task_type": task.task_type.value if hasattr(task, 'task_type') else 'unknown',
            "difficulty": task.difficulty_level.value if hasattr(task, 'difficulty_level') else 'unknown'
        }
        
        # 针对不同任务类型的特殊处理
        if isinstance(task, ExtendedTask):
            task_info.update({
                "hop_level": task.hop_level,
                "source_task": task.source_atomic_task,
                "complexity_score": getattr(task, 'complexity_score', 0.0)
            })
        elif isinstance(task, CompositeTask):
            task_info.update({
                "source_tasks": task.source_atomic_tasks,
                "original_questions": task.original_questions,
                "merge_strategy": task.merge_strategy
            })
        
        return template.format(**task_info)
    
    def _parse_verification_response(self, response: Dict[str, Any], dimension: str) -> tuple[float, str]:
        """解析验证响应"""
        try:
            thinking = response.get('thinking', '')
            
            # 尝试解析JSON格式的响应
            if thinking.strip().startswith('{'):
                result = json.loads(thinking)
                score = result.get('score', 0.5)
                feedback = result.get('feedback', result.get('reasoning', ''))
            else:
                # 尝试从文本中提取分数
                score_match = re.search(r'(?:score|分数)[:：]\s*(\d+\.?\d*)', thinking, re.IGNORECASE)
                if score_match:
                    score = float(score_match.group(1))
                    # 如果分数 > 1，假设是百分制，转换为小数
                    if score > 1:
                        score = score / 100.0
                else:
                    # 根据关键词判断分数
                    score = self._extract_score_from_keywords(thinking)
                
                feedback = thinking.strip()
            
            # 确保分数在合理范围内
            score = max(0.0, min(1.0, score))
            
            return score, feedback
            
        except (json.JSONDecodeError, ValueError, Exception) as e:
            logger.error(f"❌ 解析 {dimension} 验证响应失败: {e}")
            return 0.5, f"解析失败: {str(e)}"
    
    def _extract_score_from_keywords(self, text: str) -> float:
        """从关键词中提取分数"""
        text_lower = text.lower()
        
        # 优秀关键词
        excellent_keywords = ['excellent', 'outstanding', '优秀', '出色', '非常好', '完美']
        good_keywords = ['good', 'satisfactory', '良好', '不错', '合适', '可以']
        average_keywords = ['average', 'acceptable', '一般', '普通', '中等', '还行']
        poor_keywords = ['poor', 'unsatisfactory', '差', '不好', '不合适', '问题']
        
        if any(keyword in text_lower for keyword in excellent_keywords):
            return 0.9
        elif any(keyword in text_lower for keyword in good_keywords):
            return 0.75
        elif any(keyword in text_lower for keyword in average_keywords):
            return 0.6
        elif any(keyword in text_lower for keyword in poor_keywords):
            return 0.3
        else:
            return 0.5  # 默认分数
    
    # 各维度的验证提示词模板
    def _get_executability_prompt(self) -> str:
        return """
评估以下任务的可执行性：

任务类型: {task_type}
问题: {question}
预期答案: {answer}
所需工具: {tools}
难度级别: {difficulty}

评估标准:
1. 任务描述是否清晰明确？
2. 所需工具是否足够和合适？
3. 任务是否有明确的执行路径？
4. 答案是否可验证？
5. 是否存在技术或逻辑障碍？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "详细评估理由",
    "executable": true/false,
    "potential_issues": ["问题1", "问题2"]
}}
"""
    
    def _get_difficulty_prompt(self) -> str:
        return """
评估以下任务的难度是否适中：

任务类型: {task_type}
问题: {question}
预期答案: {answer}
所需工具: {tools}
当前难度级别: {difficulty}

评估标准:
1. 任务复杂度是否与目标用户匹配？
2. 步骤数量是否合理？
3. 认知负荷是否适中？
4. 工具使用难度是否合适？
5. 是否过于简单或过于复杂？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "难度评估说明",
    "suggested_difficulty": "simple/medium/complex",
    "complexity_factors": ["因素1", "因素2"]
}}
"""
    
    def _get_uniqueness_prompt(self) -> str:
        return """
评估以下任务答案的唯一性：

问题: {question}
预期答案: {answer}
任务类型: {task_type}

评估标准:
1. 答案是否唯一且明确？
2. 是否存在多种可能的正确答案？
3. 答案的表述是否清晰？
4. 是否容易产生歧义？
5. 验证标准是否明确？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "唯一性评估",
    "is_unique": true/false,
    "ambiguity_risk": "low/medium/high"
}}
"""
    
    def _get_tool_requirements_prompt(self) -> str:
        return """
评估以下任务的工具需求是否准确：

问题: {question}
预期答案: {answer}
当前工具列表: {tools}
任务类型: {task_type}

评估标准:
1. 列出的工具是否都是必需的？
2. 是否遗漏了必要的工具？
3. 工具组合是否合理？
4. 工具的使用顺序是否清晰？
5. 是否存在更好的工具替代方案？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "工具需求评估",
    "missing_tools": ["工具1", "工具2"],
    "unnecessary_tools": ["工具3"],
    "optimal_tools": ["推荐工具列表"]
}}
"""
    
    def _get_language_quality_prompt(self) -> str:
        return """
评估以下任务的语言质量：

问题: {question}
预期答案: {answer}
任务类型: {task_type}

评估标准:
1. 语言表达是否清晰准确？
2. 语法是否正确？
3. 专业术语使用是否恰当？
4. 描述是否简洁明了？
5. 是否易于理解？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "语言质量评估",
    "clarity": "high/medium/low",
    "grammar_issues": ["问题1", "问题2"],
    "suggestions": ["改进建议1", "改进建议2"]
}}
"""
    
    def _get_cognitive_complexity_prompt(self) -> str:
        return """
评估以下任务的认知复杂度：

问题: {question}
预期答案: {answer}
所需工具: {tools}
任务类型: {task_type}

评估标准:
1. 需要多少步推理？
2. 是否需要复杂的逻辑思维？
3. 信息整合的难度如何？
4. 是否需要领域专知识？
5. 认知负荷是否合理？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "认知复杂度评估",
    "reasoning_steps": 数字,
    "cognitive_load": "low/medium/high",
    "knowledge_domains": ["领域1", "领域2"]
}}
"""
    
    def _get_atomicity_prompt(self) -> str:
        return """
评估以下原子任务的原子性：

问题: {question}
预期答案: {answer}
所需工具: {tools}

评估标准:
1. 任务是否可以进一步分解？
2. 是否只关注一个核心问题？
3. 执行步骤是否足够简单？
4. 是否避免了多个独立的子目标？
5. 是否符合原子任务的定义？

请返回JSON格式：
{{
    "score": 0.0-1.0,
    "feedback": "原子性评估",
    "is_atomic": true/false,
    "decomposition_suggestions": ["可能的分解方案"],
    "atomic_level": "high/medium/low"
}}
"""


class BatchVerificationProcessor:
    """批量验证处理器"""
    
    def __init__(self, verification_agent: EnhancedVerificationAgent):
        self.verification_agent = verification_agent
    
    async def batch_verify_tasks(self, tasks: List[TaskUnion], 
                                max_concurrent: int = 5) -> List[TaskVerificationMetrics]:
        """批量验证任务"""
        logger.info(f"🔄 开始批量验证 {len(tasks)} 个任务")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def verify_with_semaphore(task):
            async with semaphore:
                return await self.verification_agent.verify_task(task)
        
        try:
            results = await asyncio.gather(
                *[verify_with_semaphore(task) for task in tasks],
                return_exceptions=True
            )
            
            valid_results = []
            for i, result in enumerate(results):
                if isinstance(result, TaskVerificationMetrics):
                    valid_results.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"❌ 任务 {tasks[i].task_id} 验证异常: {result}")
                    # 创建失败的验证结果
                    failed_metrics = TaskVerificationMetrics(task_id=tasks[i].task_id)
                    failed_metrics.detailed_feedback.append(f"验证异常: {str(result)}")
                    valid_results.append(failed_metrics)
            
            # 统计验证结果
            passed_count = sum(1 for r in valid_results if r.verification_passed)
            logger.info(f"✅ 批量验证完成: {passed_count}/{len(valid_results)} 通过验证")
            
            return valid_results
            
        except Exception as e:
            logger.error(f"❌ 批量验证失败: {e}")
            return []
    
    def analyze_verification_results(self, results: List[TaskVerificationMetrics]) -> Dict[str, Any]:
        """分析验证结果"""
        if not results:
            return {"total_tasks": 0}
        
        # 基础统计
        total_tasks = len(results)
        passed_tasks = sum(1 for r in results if r.verification_passed)
        pass_rate = passed_tasks / total_tasks
        
        # 各维度平均分数
        dimension_scores = {}
        for result in results:
            for dimension, score in result.verification_dimensions.items():
                if dimension not in dimension_scores:
                    dimension_scores[dimension] = []
                dimension_scores[dimension].append(score)
        
        avg_dimension_scores = {
            dimension: sum(scores) / len(scores)
            for dimension, scores in dimension_scores.items()
        }
        
        # 整体质量分布
        score_distribution = {
            "excellent": sum(1 for r in results if r.overall_score >= 0.9),
            "good": sum(1 for r in results if 0.8 <= r.overall_score < 0.9),
            "fair": sum(1 for r in results if 0.6 <= r.overall_score < 0.8),
            "poor": sum(1 for r in results if r.overall_score < 0.6)
        }
        
        # 常见问题分析
        common_issues = []
        for result in results:
            if not result.verification_passed:
                common_issues.extend(result.detailed_feedback)
        
        return {
            "total_tasks": total_tasks,
            "passed_tasks": passed_tasks,
            "pass_rate": pass_rate,
            "average_overall_score": sum(r.overall_score for r in results) / total_tasks,
            "dimension_scores": avg_dimension_scores,
            "score_distribution": score_distribution,
            "common_issues": common_issues[:10],  # 取前10个常见问题
            "recommendations": self._generate_recommendations(avg_dimension_scores, pass_rate)
        }
    
    def _generate_recommendations(self, dimension_scores: Dict[str, float], pass_rate: float) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if pass_rate < 0.7:
            recommendations.append("整体通过率较低，建议检查任务生成策略")
        
        for dimension, score in dimension_scores.items():
            if score < 0.6:
                recommendations.append(f"{dimension} 维度得分较低 ({score:.2f})，需要重点改进")
        
        if dimension_scores.get("executability", 0) < 0.7:
            recommendations.append("可执行性不足，建议优化工具选择和任务描述")
        
        if dimension_scores.get("difficulty", 0) < 0.6:
            recommendations.append("任务难度不合适，建议调整复杂度控制算法")
        
        return recommendations