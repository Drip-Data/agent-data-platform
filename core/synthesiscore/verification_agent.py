#!/usr/bin/env python3
"""
Verification Agent - 验证代理框架
基于TaskCraft的验证机制，实现任务质量的多维度验证
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union

from core.interfaces import TrajectoryResult
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient
from .enhanced_interfaces import (
    AtomicTask, ExtendedTask, CompositeTask, TaskUnion, 
    VerificationResult, TaskDifficulty, EnhancedSynthesisConfig
)

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器 - 用于验证任务的可执行性"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.config = EnhancedSynthesisConfig()
    
    async def execute_task_with_tools(self, question: str, expected_answer: Union[str, List[str]], 
                                     timeout: int = 60) -> Dict[str, Any]:
        """使用工具执行任务"""
        start_time = time.time()
        
        try:
            # 获取可用工具
            available_tools = await self._get_available_tools()
            
            # 使用LLM进行推理和工具调用
            reasoning_result = await self.llm_client.generate_enhanced_reasoning(
                task_description=question,
                available_tools=available_tools,
                tool_descriptions=await self._get_tool_descriptions(),
                execution_context={
                    "mode": "verification_execution",
                    "expected_answer": expected_answer,
                    "timeout": timeout
                }
            )
            
            # 执行推荐的工具调用
            if reasoning_result.get('action') == 'tool_call':
                tool_result = await self._execute_tool_call(
                    reasoning_result.get('tool'),
                    reasoning_result.get('parameters', {})
                )
                
                execution_result = {
                    "success": True,
                    "agent_result": tool_result.get('result', ''),
                    "tools_used": [reasoning_result.get('tool')],
                    "execution_time": time.time() - start_time,
                    "trajectory": [
                        {
                            "thinking": reasoning_result.get('thinking', ''),
                            "action": reasoning_result.get('action'),
                            "tool": reasoning_result.get('tool'),
                            "parameters": reasoning_result.get('parameters'),
                            "result": tool_result.get('result', '')
                        }
                    ]
                }
            else:
                execution_result = {
                    "success": False,
                    "agent_result": reasoning_result.get('thinking', ''),
                    "tools_used": [],
                    "execution_time": time.time() - start_time,
                    "error": "No tool call generated"
                }
            
            # 验证答案正确性
            answer_correct = await self._verify_answer_correctness(
                execution_result.get('agent_result', ''),
                expected_answer
            )
            
            execution_result['answer_correct'] = answer_correct
            execution_result['confidence'] = answer_correct * reasoning_result.get('confidence', 0.5)
            
            return execution_result
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Execution timeout",
                "execution_time": timeout,
                "tools_used": [],
                "confidence": 0.0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "tools_used": [],
                "confidence": 0.0
            }
    
    async def execute_task_without_tools(self, question: str, expected_answer: Union[str, List[str]]) -> Dict[str, Any]:
        """不使用工具执行任务（纯LLM推理）"""
        start_time = time.time()
        
        try:
            # 直接使用LLM回答问题
            reasoning_result = await self.llm_client.generate_reasoning(
                task_description=f"请直接回答以下问题，不要使用任何工具: {question}",
                available_tools=[],  # 不提供工具
                execution_context={"mode": "pure_llm_reasoning"}
            )
            
            llm_answer = reasoning_result.get('thinking', '')
            
            # 验证答案正确性
            answer_correct = await self._verify_answer_correctness(llm_answer, expected_answer)
            
            return {
                "success": answer_correct,
                "llm_result": llm_answer,
                "answer_correct": answer_correct,
                "execution_time": time.time() - start_time,
                "confidence": answer_correct * reasoning_result.get('confidence', 0.5)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "llm_result": "",
                "execution_time": time.time() - start_time,
                "confidence": 0.0
            }
    
    async def _get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        if not self.mcp_client:
            return []
        
        try:
            tools_info = await self.mcp_client.list_tools()
            return [tool.get('name', '') for tool in tools_info]
        except Exception as e:
            logger.warning(f"⚠️ 获取工具列表失败: {e}")
            return []
    
    async def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        if not self.mcp_client:
            return "无可用工具"
        
        try:
            tools_info = await self.mcp_client.list_tools()
            descriptions = []
            for tool in tools_info:
                name = tool.get('name', '')
                description = tool.get('description', '')
                descriptions.append(f"- {name}: {description}")
            return '\n'.join(descriptions)
        except Exception as e:
            logger.warning(f"⚠️ 获取工具描述失败: {e}")
            return "工具描述获取失败"
    
    async def _execute_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具调用"""
        if not self.mcp_client:
            return {"error": "MCP客户端不可用"}
        
        try:
            result = await self.mcp_client.call_tool(tool_name, parameters)
            return {"result": result, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}
    
    async def _verify_answer_correctness(self, actual_answer: str, expected_answer: Union[str, List[str]]) -> bool:
        """验证答案正确性"""
        if isinstance(expected_answer, list):
            # 对于复合任务，检查是否包含所有期望答案
            for exp_ans in expected_answer:
                if not self._is_answer_similar(actual_answer, exp_ans):
                    return False
            return True
        else:
            return self._is_answer_similar(actual_answer, expected_answer)
    
    def _is_answer_similar(self, actual: str, expected: str) -> bool:
        """检查答案相似性"""
        actual_lower = actual.lower().strip()
        expected_lower = expected.lower().strip()
        
        # 精确匹配
        if actual_lower == expected_lower:
            return True
        
        # 包含匹配
        if expected_lower in actual_lower or actual_lower in expected_lower:
            return True
        
        # 数值匹配
        import re
        actual_numbers = re.findall(r'\d+\.?\d*', actual)
        expected_numbers = re.findall(r'\d+\.?\d*', expected)
        
        if actual_numbers and expected_numbers:
            return any(abs(float(a) - float(e)) < 0.01 for a in actual_numbers for e in expected_numbers)
        
        return False


class AtomicityVerifier:
    """原子性验证器 - 验证任务的原子性"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def verify_atomicity(self, task: AtomicTask) -> Dict[str, Any]:
        """验证任务原子性"""
        
        # 1. 结构性原子性检查
        structural_check = self._check_structural_atomicity(task.question)
        
        # 2. LLM辅助原子性检查
        llm_check = await self._llm_atomicity_check(task)
        
        # 3. 综合评分
        atomicity_score = (structural_check['score'] + llm_check['score']) / 2
        
        return {
            "atomicity_score": atomicity_score,
            "is_atomic": atomicity_score > self.config.ATOMIC_GENERATION_CONFIG['atomicity_verification_threshold'],
            "structural_check": structural_check,
            "llm_check": llm_check,
            "details": {
                "question_complexity": len(task.question.split()),
                "contains_conjunctions": self._contains_conjunctions(task.question),
                "has_multiple_questions": self._has_multiple_questions(task.question)
            }
        }
    
    def _check_structural_atomicity(self, question: str) -> Dict[str, Any]:
        """结构性原子性检查"""
        score = 1.0
        issues = []
        
        # 检查是否包含并列连词
        conjunctions = ['and', 'or', '以及', '或者', '同时', '并且']
        if any(conj in question.lower() for conj in conjunctions):
            score -= 0.3
            issues.append("包含并列连词")
        
        # 检查是否包含多个问号
        question_marks = question.count('?') + question.count('？')
        if question_marks > 1:
            score -= 0.4
            issues.append("包含多个问号")
        
        # 检查句子长度
        if len(question.split()) > 30:
            score -= 0.2
            issues.append("问题过长")
        
        # 检查是否包含多个主题
        if self._has_multiple_topics(question):
            score -= 0.3
            issues.append("包含多个主题")
        
        return {
            "score": max(score, 0.0),
            "issues": issues
        }
    
    async def _llm_atomicity_check(self, task: AtomicTask) -> Dict[str, Any]:
        """LLM辅助原子性检查"""
        
        atomicity_prompt = f"""
        请评估以下问题是否是一个原子性任务（不可再分的基本任务）：
        
        问题: {task.question}
        预期答案: {task.golden_answer}
        
        评估标准:
        1. 任务是否可以拆分为多个独立的子任务？
        2. 问题是否只询问一个特定的信息点？
        3. 答案是否是单一、明确的？
        
        请返回JSON格式：
        {{
            "is_atomic": true/false,
            "confidence": 0.0-1.0,
            "reasoning": "评估理由",
            "suggested_splits": ["子任务1", "子任务2"] (如果可拆分)
        }}
        """
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=atomicity_prompt,
                available_tools=[],
                execution_context={"mode": "atomicity_verification"}
            )
            
            # 解析LLM响应
            thinking = response.get('thinking', '{}')
            try:
                result = json.loads(thinking)
                return {
                    "score": result.get('confidence', 0.5) if result.get('is_atomic', False) else 1 - result.get('confidence', 0.5),
                    "is_atomic": result.get('is_atomic', False),
                    "reasoning": result.get('reasoning', ''),
                    "suggested_splits": result.get('suggested_splits', [])
                }
            except json.JSONDecodeError:
                return {"score": 0.5, "is_atomic": True, "reasoning": "LLM响应解析失败"}
                
        except Exception as e:
            logger.error(f"❌ LLM原子性检查失败: {e}")
            return {"score": 0.5, "is_atomic": True, "reasoning": f"检查失败: {e}"}
    
    def _contains_conjunctions(self, question: str) -> bool:
        """检查是否包含连词"""
        conjunctions = ['and', 'or', '以及', '或者', '同时', '并且', '另外', '此外']
        return any(conj in question.lower() for conj in conjunctions)
    
    def _has_multiple_questions(self, question: str) -> bool:
        """检查是否包含多个问题"""
        return (question.count('?') + question.count('？')) > 1
    
    def _has_multiple_topics(self, question: str) -> bool:
        """检查是否包含多个主题"""
        # 简单的启发式检查
        keywords_count = 0
        common_keywords = ['什么', '如何', '为什么', '哪个', '多少', '何时', '何地']
        
        for keyword in common_keywords:
            if keyword in question:
                keywords_count += 1
        
        return keywords_count > 1


class QualityAssessor:
    """质量评估器 - 评估任务的各个质量维度"""
    
    def __init__(self, llm_client: LLMClient, task_executor: TaskExecutor):
        self.llm_client = llm_client
        self.task_executor = task_executor
        self.config = EnhancedSynthesisConfig()
    
    async def assess_task_quality(self, task: TaskUnion) -> Dict[str, float]:
        """评估任务质量的各个维度"""
        
        dimensions = {}
        
        # 1. 可执行性评估
        dimensions['executability'] = await self._assess_executability(task)
        
        # 2. 难度适中性评估
        dimensions['difficulty'] = await self._assess_difficulty(task)
        
        # 3. 答案唯一性评估
        dimensions['answer_uniqueness'] = await self._assess_answer_uniqueness(task)
        
        # 4. 工具需求准确性评估
        dimensions['tool_requirements'] = await self._assess_tool_requirements(task)
        
        # 5. 语言质量评估
        dimensions['language_quality'] = await self._assess_language_quality(task)
        
        # 6. 认知复杂度评估
        dimensions['cognitive_complexity'] = await self._assess_cognitive_complexity(task)
        
        # 7. 原子性评估（仅适用于原子任务）
        if isinstance(task, AtomicTask):
            atomicity_verifier = AtomicityVerifier(self.llm_client)
            atomicity_result = await atomicity_verifier.verify_atomicity(task)
            dimensions['atomicity'] = atomicity_result['atomicity_score']
        else:
            dimensions['atomicity'] = 1.0  # 非原子任务不需要原子性检查
        
        return dimensions
    
    async def _assess_executability(self, task: TaskUnion) -> float:
        """评估可执行性"""
        try:
            expected_answer = task.golden_answer if hasattr(task, 'golden_answer') else task.golden_answers
            
            execution_result = await self.task_executor.execute_task_with_tools(
                task.question, 
                expected_answer,
                timeout=self.config.VERIFICATION_CONFIG['execution_timeout_seconds']
            )
            
            if execution_result['success'] and execution_result.get('answer_correct', False):
                return 1.0
            elif execution_result['success']:
                return 0.7  # 能执行但答案不完全正确
            else:
                return 0.3  # 执行失败
                
        except Exception as e:
            logger.error(f"❌ 可执行性评估失败: {e}")
            return 0.0
    
    async def _assess_difficulty(self, task: TaskUnion) -> float:
        """评估难度适中性"""
        # 基于任务类型和复杂度的启发式评估
        if isinstance(task, AtomicTask):
            base_score = 0.8  # 原子任务通常难度适中
        elif isinstance(task, ExtendedTask):
            # 深度扩展任务的难度与跳跃数相关
            hop_score = min(task.hop_level / 3.0, 1.0)
            base_score = 0.5 + hop_score * 0.4
        elif isinstance(task, CompositeTask):
            # 复合任务的难度与原子任务数量相关
            composite_score = min(len(task.source_atomic_tasks) / 3.0, 1.0)
            base_score = 0.6 + composite_score * 0.3
        else:
            base_score = 0.5
        
        # 基于工具数量调整
        tool_count = len(getattr(task, 'expected_tools', getattr(task, 'required_tools', [])))
        tool_adjustment = min(tool_count / 3.0, 0.2)
        
        return min(base_score + tool_adjustment, 1.0)
    
    async def _assess_answer_uniqueness(self, task: TaskUnion) -> float:
        """评估答案唯一性"""
        
        uniqueness_prompt = f"""
        请评估以下问题的答案是否具有唯一性：
        
        问题: {task.question}
        
        评估标准:
        1. 问题是否有明确、唯一的正确答案？
        2. 是否存在多个同样正确的答案？
        3. 答案是否具体、可验证？
        
        请返回0.0-1.0的分数，1.0表示答案完全唯一。
        """
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=uniqueness_prompt,
                available_tools=[],
                execution_context={"mode": "answer_uniqueness_assessment"}
            )
            
            # 从响应中提取分数
            thinking = response.get('thinking', '')
            import re
            score_match = re.search(r'(\d+\.?\d*)', thinking)
            if score_match:
                score = float(score_match.group(1))
                return min(score, 1.0) if score <= 1.0 else score / 10.0
            else:
                return 0.7  # 默认分数
                
        except Exception as e:
            logger.error(f"❌ 答案唯一性评估失败: {e}")
            return 0.5
    
    async def _assess_tool_requirements(self, task: TaskUnion) -> float:
        """评估工具需求准确性"""
        expected_tools = getattr(task, 'expected_tools', getattr(task, 'required_tools', []))
        
        if not expected_tools:
            return 0.5  # 没有工具需求信息
        
        # 检查工具的可用性和相关性
        available_tools = await self.task_executor._get_available_tools()
        
        # 计算工具匹配度
        available_set = set(available_tools)
        expected_set = set(expected_tools)
        
        if not expected_set:
            return 1.0
        
        intersection = available_set & expected_set
        match_ratio = len(intersection) / len(expected_set)
        
        return match_ratio
    
    async def _assess_language_quality(self, task: TaskUnion) -> float:
        """评估语言质量"""
        question = task.question
        
        # 基础语言质量检查
        score = 1.0
        
        # 检查语法和拼写（简单启发式）
        if len(question) < 10:
            score -= 0.3  # 问题过短
        
        if question.count('?') == 0 and question.count('？') == 0:
            score -= 0.2  # 缺少问号
        
        # 检查是否包含无意义的重复
        words = question.split()
        if len(words) != len(set(words)) and len(set(words)) / len(words) < 0.7:
            score -= 0.3  # 重复词汇过多
        
        # 检查标点符号使用
        if question.count(',') + question.count('，') == 0 and len(words) > 15:
            score -= 0.1  # 长句缺少逗号
        
        return max(score, 0.0)
    
    async def _assess_cognitive_complexity(self, task: TaskUnion) -> float:
        """评估认知复杂度"""
        
        complexity_prompt = f"""
        请评估以下任务的认知复杂度：
        
        任务: {task.question}
        
        评估维度:
        1. 需要多少步骤的思考？
        2. 是否需要综合多个信息源？
        3. 是否需要逻辑推理或分析？
        4. 是否需要专业知识？
        
        请返回0.0-1.0的复杂度分数。
        """
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=complexity_prompt,
                available_tools=[],
                execution_context={"mode": "cognitive_complexity_assessment"}
            )
            
            # 从响应中提取分数
            thinking = response.get('thinking', '')
            import re
            score_match = re.search(r'(\d+\.?\d*)', thinking)
            if score_match:
                score = float(score_match.group(1))
                return min(score, 1.0) if score <= 1.0 else score / 10.0
            else:
                return 0.6  # 默认中等复杂度
                
        except Exception as e:
            logger.error(f"❌ 认知复杂度评估失败: {e}")
            return 0.5


class EnhancedVerificationEngine:
    """增强验证引擎 - 统一的任务验证接口"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.task_executor = TaskExecutor(llm_client, mcp_client)
        self.quality_assessor = QualityAssessor(llm_client, self.task_executor)
        self.config = EnhancedSynthesisConfig()
    
    async def comprehensive_task_verification(self, task: TaskUnion) -> VerificationResult:
        """综合任务验证"""
        logger.info(f"🔍 开始验证任务: {task.task_id}")
        
        try:
            # 1. 质量维度评估
            quality_dimensions = await self.quality_assessor.assess_task_quality(task)
            
            # 2. 计算综合分数
            overall_score = self._calculate_overall_score(quality_dimensions)
            
            # 3. 生成建议
            recommendation = self._generate_recommendation(overall_score, quality_dimensions)
            
            # 4. 生成改进建议
            improvements = self._suggest_improvements(quality_dimensions)
            
            # 5. 创建验证结果
            verification_result = VerificationResult(
                task_id=task.task_id,
                overall_score=overall_score,
                verification_dimensions=quality_dimensions,
                recommendation=recommendation,
                suggested_improvements=improvements,
                details={
                    "task_type": type(task).__name__,
                    "question_length": len(task.question),
                    "has_tools": bool(getattr(task, 'expected_tools', getattr(task, 'required_tools', []))),
                    "verification_timestamp": time.time()
                }
            )
            
            logger.info(f"✅ 任务验证完成: {task.task_id} (分数: {overall_score:.3f})")
            return verification_result
            
        except Exception as e:
            logger.error(f"❌ 任务验证失败 {task.task_id}: {e}")
            return VerificationResult(
                task_id=task.task_id,
                overall_score=0.0,
                recommendation="reject",
                suggested_improvements=[f"验证过程出错: {str(e)}"],
                details={"error": str(e)}
            )
    
    def _calculate_overall_score(self, dimensions: Dict[str, float]) -> float:
        """计算综合分数"""
        weights = self.config.VERIFICATION_CONFIG['dimension_weight']
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for dimension, score in dimensions.items():
            if dimension in weights:
                weight = weights[dimension]
                weighted_sum += score * weight
                total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _generate_recommendation(self, overall_score: float, dimensions: Dict[str, float]) -> str:
        """生成建议"""
        threshold = self.config.VERIFICATION_CONFIG['overall_quality_threshold']
        
        if overall_score >= threshold:
            return "accept"
        elif overall_score >= threshold * 0.7:
            return "modify"
        else:
            return "reject"
    
    def _suggest_improvements(self, dimensions: Dict[str, float]) -> List[str]:
        """生成改进建议"""
        improvements = []
        
        for dimension, score in dimensions.items():
            if score < 0.6:  # 低于60%的维度需要改进
                if dimension == "executability":
                    improvements.append("提高任务的可执行性，确保有明确的执行路径")
                elif dimension == "difficulty":
                    improvements.append("调整任务难度，使其更适合目标用户")
                elif dimension == "answer_uniqueness":
                    improvements.append("使问题的答案更加明确和唯一")
                elif dimension == "tool_requirements":
                    improvements.append("检查和优化工具需求的准确性")
                elif dimension == "language_quality":
                    improvements.append("改进问题的语言表达和语法")
                elif dimension == "cognitive_complexity":
                    improvements.append("调整认知复杂度，使其更合理")
                elif dimension == "atomicity":
                    improvements.append("确保任务的原子性，避免包含多个子任务")
        
        if not improvements:
            improvements.append("任务质量良好，无需特别改进")
        
        return improvements
    
    async def batch_verification(self, tasks: List[TaskUnion]) -> List[VerificationResult]:
        """批量验证任务"""
        logger.info(f"🔄 开始批量验证 {len(tasks)} 个任务")
        
        # 并行验证（限制并发数以避免资源耗尽）
        semaphore = asyncio.Semaphore(self.config.ATOMIC_GENERATION_CONFIG['parallel_workers'])
        
        async def verify_with_semaphore(task):
            async with semaphore:
                return await self.comprehensive_task_verification(task)
        
        results = await asyncio.gather(
            *[verify_with_semaphore(task) for task in tasks],
            return_exceptions=True
        )
        
        # 处理异常结果
        verification_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ 任务 {tasks[i].task_id} 验证异常: {result}")
                verification_results.append(VerificationResult(
                    task_id=tasks[i].task_id,
                    overall_score=0.0,
                    recommendation="reject",
                    suggested_improvements=[f"验证异常: {str(result)}"],
                    details={"exception": str(result)}
                ))
            else:
                verification_results.append(result)
        
        # 统计结果
        accepted = len([r for r in verification_results if r.recommendation == "accept"])
        modified = len([r for r in verification_results if r.recommendation == "modify"])
        rejected = len([r for r in verification_results if r.recommendation == "reject"])
        
        logger.info(f"✅ 批量验证完成: 接受 {accepted}, 修改 {modified}, 拒绝 {rejected}")
        return verification_results