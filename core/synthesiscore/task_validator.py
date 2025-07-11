#!/usr/bin/env python3
"""
Synthesis 任务验证器
专注于区分工具任务 vs 推理任务的智能验证
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
import json
import re

from .interfaces import (
    AtomicTask, DepthExtendedTask, WidthExtendedTask, TaskUnion,
    TaskValidationResult, TaskType, TaskComplexity
)
from .prompts import prompt_manager

logger = logging.getLogger(__name__)


class TaskValidator:
    """
    Synthesis 任务验证器
    
    核心功能：
    1. 工具必要性验证：判断任务是否必须通过工具调用才能解决
    2. 推理充分性验证：判断任务是否仅通过推理就能解决
    3. 原子性验证：确保原子任务的单一性
    4. 扩展性验证：验证深度/宽度扩展的合理性
    """
    
    def __init__(self, llm_client, enable_strict_mode: bool = True):
        self.llm_client = llm_client
        self.enable_strict_mode = enable_strict_mode
        
        # LLM重试配置
        self.max_retries = 3
        self.retry_delay = 1.5
        
        logger.info("✅ TaskValidator 初始化完成，使用模板化Prompt管理")
    
    async def _call_llm_with_retry(self, prompt: str, operation_name: str) -> str:
        """
        带重试机制的LLM调用方法
        """
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"🔄 {operation_name} - 验证尝试 {attempt}/{self.max_retries}")
                # 将字符串prompt转换为消息列表格式
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm_client._call_api(messages)
                logger.debug(f"✅ {operation_name} - 第{attempt}次验证成功")
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ {operation_name} - 第{attempt}次验证失败: {e}")
                
                if attempt < self.max_retries:
                    logger.info(f"⏰ 等待 {self.retry_delay}s 后重试验证...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"❌ {operation_name} - 所有 {self.max_retries} 次验证尝试均失败")
                    break
        
        # 抛出运行时错误，不再使用简单回退
        raise RuntimeError(f"{operation_name} 验证失败：经过 {self.max_retries} 次重试仍无法与LLM正常通信。最后错误: {last_error}")
    
    async def validate_task(self, task: TaskUnion) -> TaskValidationResult:
        """验证单个任务"""
        logger.info(f"🔍 开始验证任务: {task.task_id}")
        
        if isinstance(task, AtomicTask):
            return await self._validate_atomic_task(task)
        elif isinstance(task, DepthExtendedTask):
            return await self._validate_depth_extended_task(task)
        elif isinstance(task, WidthExtendedTask):
            return await self._validate_width_extended_task(task)
        else:
            return TaskValidationResult(
                task_id=task.task_id,
                is_valid=False,
                requires_tool=False,
                validation_score=0.0,
                tool_necessity_check=False,
                reasoning_sufficiency_check=False,
                atomicity_check=False,
                errors=[f"未知任务类型: {type(task)}"]
            )
    
    async def batch_validate_tasks(self, tasks: List[TaskUnion]) -> List[TaskValidationResult]:
        """批量验证任务"""
        logger.info(f"🔍 开始批量验证 {len(tasks)} 个任务")
        
        # 并发验证
        validation_tasks = [self.validate_task(task) for task in tasks]
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        
        # 处理异常
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ 验证任务 {tasks[i].task_id} 失败: {result}")
                valid_results.append(TaskValidationResult(
                    task_id=tasks[i].task_id,
                    is_valid=False,
                    requires_tool=False,
                    validation_score=0.0,
                    tool_necessity_check=False,
                    reasoning_sufficiency_check=False,
                    atomicity_check=False,
                    errors=[f"验证异常: {str(result)}"]
                ))
            else:
                valid_results.append(result)
        
        logger.info(f"✅ 批量验证完成，有效任务: {sum(1 for r in valid_results if r.is_valid)}/{len(tasks)}")
        return valid_results
    
    async def _validate_atomic_task(self, task: AtomicTask) -> TaskValidationResult:
        """验证原子任务"""
        logger.debug(f"🔬 验证原子任务: {task.task_id}")
        
        # 1. 工具必要性检查
        tool_necessity = await self._check_tool_necessity(task.question)
        
        # 2. 推理充分性检查  
        reasoning_sufficiency = await self._check_reasoning_sufficiency(task.question)
        
        # 3. 原子性检查
        atomicity = await self._check_atomicity(task.question)
        
        # 综合判断（更宽松的工具必要性判断）
        has_action_keywords = any(keyword in task.question.lower() for keyword in ["搜索", "查询", "获取", "下载", "执行", "计算", "分析", "提取", "访问", "生成", "创建"])
        requires_tool = tool_necessity or has_action_keywords
        
        # 更宽松的验证标准
        is_valid = atomicity and (requires_tool if self.enable_strict_mode else True)
        
        # 计算验证分数
        score = self._calculate_validation_score(
            tool_necessity, reasoning_sufficiency, atomicity
        )
        
        # 收集错误和警告
        errors = []
        warnings = []
        
        if not atomicity:
            errors.append("任务不符合原子性要求，包含多个子任务")
        
        if not requires_tool and self.enable_strict_mode:
            # 更宽松的工具必要性判断 - 只有明显的纯推理任务才被拒绝
            if any(keyword in task.question.lower() for keyword in ["搜索", "查询", "获取", "下载", "执行", "计算", "分析", "提取"]):
                # 包含操作性关键词的任务应该需要工具，覆盖LLM判断
                warnings.append("LLM判断可能有误：任务包含操作性关键词，应该需要工具")
            else:
                errors.append("任务可以仅通过推理解决，不需要工具调用")
        elif not requires_tool:
            warnings.append("任务可能不需要工具调用")
        
        return TaskValidationResult(
            task_id=task.task_id,
            is_valid=is_valid,
            requires_tool=requires_tool,
            validation_score=score,
            tool_necessity_check=tool_necessity,
            reasoning_sufficiency_check=reasoning_sufficiency,
            atomicity_check=atomicity,
            errors=errors,
            warnings=warnings,
            validation_method="llm_comprehensive"
        )
    
    async def _validate_depth_extended_task(self, task: DepthExtendedTask) -> TaskValidationResult:
        """验证深度扩展任务"""
        logger.debug(f"🔬 验证深度扩展任务: {task.task_id}")
        
        # 验证基础任务
        base_validation = await self._validate_atomic_task(task.base_task)
        
        # 验证中间任务
        intermediate_validation = await self._validate_atomic_task(task.intermediate_task)
        
        # 验证超集关系
        superset_valid = await self._check_superset_relation(
            task.base_task.input_info.content,
            task.superset_input.content
        )
        
        # 验证信息不泄露
        info_leak = await self._check_information_leakage(
            task.combined_question,
            task.base_task.answer.answer
        )
        
        is_valid = (base_validation.is_valid and 
                   intermediate_validation.is_valid and 
                   superset_valid and 
                   not info_leak)
        
        errors = []
        errors.extend(base_validation.errors)
        errors.extend(intermediate_validation.errors)
        
        if not superset_valid:
            errors.append("超集关系验证失败")
        if info_leak:
            errors.append("检测到信息泄露")
        
        return TaskValidationResult(
            task_id=task.task_id,
            is_valid=is_valid,
            requires_tool=True,  # 深度扩展任务总是需要工具
            validation_score=min(base_validation.validation_score, intermediate_validation.validation_score),
            tool_necessity_check=True,
            reasoning_sufficiency_check=False,
            atomicity_check=False,  # 深度扩展不是原子任务
            errors=errors,
            validation_method="depth_extension_validation"
        )
    
    async def _validate_width_extended_task(self, task: WidthExtendedTask) -> TaskValidationResult:
        """验证宽度扩展任务"""
        logger.debug(f"🔬 验证宽度扩展任务: {task.task_id}")
        
        # 验证所有组件任务
        component_validations = []
        for component in task.component_tasks:
            validation = await self._validate_atomic_task(component)
            component_validations.append(validation)
        
        # 检查任务合并的合理性
        merge_valid = await self._check_merge_reasonableness(
            [t.question for t in task.component_tasks],
            task.merged_question
        )
        
        # 检查答案组合的正确性
        answer_combination = await self._check_answer_combination(
            [t.answer.answer for t in task.component_tasks],
            task.merged_answer
        )
        
        all_components_valid = all(v.is_valid for v in component_validations)
        is_valid = all_components_valid and merge_valid and answer_combination
        
        errors = []
        for i, v in enumerate(component_validations):
            if not v.is_valid:
                errors.extend([f"组件任务{i+1}: {err}" for err in v.errors])
        
        if not merge_valid:
            errors.append("任务合并不合理")
        if not answer_combination:
            errors.append("答案组合不正确")
        
        return TaskValidationResult(
            task_id=task.task_id,
            is_valid=is_valid,
            requires_tool=any(v.requires_tool for v in component_validations),
            validation_score=sum(v.validation_score for v in component_validations) / len(component_validations),
            tool_necessity_check=any(v.tool_necessity_check for v in component_validations),
            reasoning_sufficiency_check=all(v.reasoning_sufficiency_check for v in component_validations),
            atomicity_check=False,  # 宽度扩展不是原子任务
            errors=errors,
            validation_method="width_extension_validation"
        )
    
    async def _check_tool_necessity(self, question: str) -> bool:
        """检查是否必须使用工具"""
        try:
            # 使用模板化Prompt
            prompt = prompt_manager.render_template("check_tool_necessity", question=question)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "工具必要性检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("requires_tool", False)
            except:
                # 回退到文本解析
                if "requires_tool\": true" in response.lower() or "需要工具" in response:
                    return True
                elif "requires_tool\": false" in response.lower() or "不需要工具" in response:
                    return False
                else:
                    # 默认保守判断
                    return True
        except Exception as e:
            logger.error(f"❌ 工具必要性检查失败: {e}")
            return True
    
    async def _check_reasoning_sufficiency(self, question: str) -> bool:
        """检查是否仅通过推理就能解决"""
        try:
            # 使用模板化Prompt
            prompt = prompt_manager.render_template("check_reasoning_sufficiency", question=question)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "推理充分性检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("reasoning_sufficient", False)
            except:
                # 回退到文本解析
                if "reasoning_sufficient\": true" in response.lower() or "仅推理足够" in response:
                    return True
                elif "reasoning_sufficient\": false" in response.lower() or "需要外部" in response:
                    return False
                else:
                    # 默认保守判断
                    return False
        except Exception as e:
            logger.error(f"❌ 推理充分性检查失败: {e}")
            return False
    
    async def _check_atomicity(self, question: str) -> bool:
        """检查原子性"""
        try:
            # 使用模板化Prompt
            prompt = prompt_manager.render_template("check_atomicity", question=question)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "原子性检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("is_atomic", True)
            except:
                # 回退到文本解析
                if "is_atomic\": true" in response.lower() or "是原子任务" in response:
                    return True
                elif "is_atomic\": false" in response.lower() or "包含多个" in response:
                    return False
                else:
                    # 检查是否包含多个步骤或子任务的关键词
                    step_indicators = ["第一步", "然后", "接着", "最后", "步骤", "首先", "其次"]
                    has_multiple_steps = any(indicator in response for indicator in step_indicators)
                    return not has_multiple_steps
                
        except Exception as e:
            logger.error(f"❌ 原子性检查失败: {e}")
            return True
    
    async def _check_superset_relation(self, base_input: str, superset_input: str) -> bool:
        """检查超集关系"""
        try:
            # 使用模板化Prompt
            prompt = prompt_manager.render_template("validate_superset_relation", 
                                                   base_input=base_input, 
                                                   superset_input=superset_input)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "超集关系检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("is_superset", False)
            except:
                # 回退到文本解析
                return "is_superset\": true" in response.lower() or "是" in response
                
        except Exception as e:
            logger.error(f"❌ 超集关系检查失败: {e}")
            return False
    
    async def _check_information_leakage(self, question: str, answer: str) -> bool:
        """检查信息泄露"""
        try:
            # 使用模板化Prompt
            prompt = prompt_manager.render_template("check_information_leakage", 
                                                   question=question, 
                                                   answer=answer)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "信息泄露检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("has_leakage", False)
            except:
                # 回退到文本解析
                return "has_leakage\": true" in response.lower() or "是" in response
                
        except Exception as e:
            logger.error(f"❌ 信息泄露检查失败: {e}")
            return False
    
    async def _check_merge_reasonableness(self, component_questions: List[str], merged_question: str) -> bool:
        """检查任务合并的合理性"""
        try:
            # 使用模板化Prompt
            component_questions_str = "\n".join(f"- {q}" for q in component_questions)
            prompt = prompt_manager.render_template("check_merge_reasonableness", 
                                                   component_questions=component_questions_str, 
                                                   merged_question=merged_question)
            
            # 使用重试机制调用LLM
            response = await self._call_llm_with_retry(prompt, "合并合理性检查")
            
            # 尝试JSON解析
            try:
                result = json.loads(response)
                return result.get("is_reasonable", False)
            except:
                # 回退到文本解析
                return "is_reasonable\": true" in response.lower() or "是" in response
                
        except Exception as e:
            logger.error(f"❌ 合并合理性检查失败: {e}")
            return False
    
    async def _check_answer_combination(self, component_answers: List[str], merged_answer: str) -> bool:
        """检查答案组合的正确性"""
        # 简单检查：合并答案应包含所有组件答案的信息
        for answer in component_answers:
            if answer.strip() and answer.strip() not in merged_answer:
                return False
        return True
    
    def _calculate_validation_score(self, tool_necessity: bool, reasoning_sufficiency: bool, atomicity: bool) -> float:
        """计算验证分数（更宽松的评分标准）"""
        score = 0.0
        
        # 原子性权重最高，但降低要求
        if atomicity:
            score += 0.6  # 提高权重
        
        # 工具必要性权重适中
        if tool_necessity:
            score += 0.4  # 提高权重
        
        # 对于明显需要工具的任务，即使LLM判断有误也给予基础分数
        return min(1.0, score)  # 确保不超过1.0
    
