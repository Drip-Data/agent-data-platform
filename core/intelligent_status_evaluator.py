"""
智能状态评估器 - 基于结果驱动的语义判定逻辑

核心设计原则：
1. 从"格式驱动"转向"结果驱动"
2. 引入LLM语义理解能力
3. 识别Agent自我纠正过程
4. 关注任务实际产出而非标签格式
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from core.interfaces import TaskExecutionConstants

logger = logging.getLogger(__name__)


class TaskOutcomeType(Enum):
    """任务结果类型"""
    CLEAR_SUCCESS = "clear_success"         # 明确成功
    CORRECTED_SUCCESS = "corrected_success" # 经过纠正的成功
    PARTIAL_SUCCESS = "partial_success"     # 部分成功
    PROCESS_FAILURE = "process_failure"     # 过程失败但可恢复
    COMPLETE_FAILURE = "complete_failure"   # 完全失败


@dataclass
class OutcomeEvidence:
    """结果证据"""
    evidence_type: str
    content: str
    confidence: float
    source_step: int
    timestamp: str


@dataclass
class TaskEvaluation:
    """任务评估结果"""
    outcome_type: TaskOutcomeType
    confidence_score: float
    primary_evidence: List[OutcomeEvidence]
    final_output: str
    correction_detected: bool
    semantic_reasoning: str
    

class IntelligentStatusEvaluator:
    """
    智能状态评估器
    
    核心特性：
    1. 语义理解：使用LLM分析任务完成情况
    2. 自我纠正识别：检测Agent的错误修复过程
    3. 结果驱动：基于实际产出而非格式标签
    4. 上下文感知：考虑完整的任务执行上下文
    """
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.evaluation_prompt_template = self._create_evaluation_prompt()
        
    def _create_evaluation_prompt(self) -> str:
        """创建评估提示模板"""
        return """你是一个专业的任务执行评估专家。请分析以下Agent任务执行过程，判断任务是否真正完成。

**评估原则**：
1. 关注最终实际产出，而非中间过程错误
2. 识别Agent的自我纠正行为（错误→发现→修正→成功）
3. 重视工具执行的实际结果
4. 考虑任务的实际完成度，而非格式完整性

**分析内容**：
任务要求：{task_input}
执行轨迹：{trajectory_summary}
最终输出：{final_output}
工具执行情况：{tool_execution_summary}

**请回答以下问题（用JSON格式）**：
1. 任务是否实际完成？（考虑最终结果）
2. 是否检测到自我纠正过程？
3. 主要成功证据是什么？
4. 置信度评分（0-1）
5. 一句话评估理由

输出格式：
{{
    "task_completed": true/false,
    "self_correction_detected": true/false,
    "success_evidence": "具体证据描述",
    "confidence_score": 0.95,
    "reasoning": "评估理由"
}}"""

    async def evaluate_task_completion(
        self,
        task_input: str,
        trajectory: List[Dict[str, Any]],
        final_output: str,
        tool_results: List[Dict[str, Any]]
    ) -> TaskEvaluation:
        """
        智能评估任务完成状态
        
        Args:
            task_input: 原始任务输入
            trajectory: 完整执行轨迹
            final_output: 最终输出内容
            tool_results: 工具执行结果列表
            
        Returns:
            TaskEvaluation: 评估结果
        """
        try:
            # 1. 预处理和特征提取
            trajectory_summary = self._summarize_trajectory(trajectory)
            tool_summary = self._summarize_tool_execution(tool_results)
            
            # 2. 检测自我纠正模式
            correction_evidence = self._detect_self_correction(trajectory)
            
            # 3. LLM语义评估
            semantic_evaluation = await self._llm_semantic_evaluation(
                task_input, trajectory_summary, final_output, tool_summary
            )
            
            # 4. 基于规则的辅助判定
            rule_based_signals = self._rule_based_evaluation(
                trajectory, final_output, tool_results
            )
            
            # 5. 综合判定
            final_evaluation = self._synthesize_evaluation(
                semantic_evaluation, 
                rule_based_signals, 
                correction_evidence
            )
            
            logger.info(f"🧠 智能状态评估完成: {final_evaluation.outcome_type.value}, "
                       f"置信度: {final_evaluation.confidence_score:.2f}")
            
            return final_evaluation
            
        except Exception as e:
            logger.error(f"❌ 智能状态评估失败: {e}")
            # 降级到简单规则判定
            return self._fallback_evaluation(final_output, tool_results)

    def _summarize_trajectory(self, trajectory: List[Dict[str, Any]]) -> str:
        """总结执行轨迹的关键信息"""
        if not trajectory:
            return "无执行轨迹"
            
        summary_parts = []
        step_count = len(trajectory)
        
        # 统计工具使用情况
        tools_used = set()
        success_steps = 0
        error_steps = 0
        
        for step in trajectory:
            step_content = str(step)
            
            # 检测工具使用
            if 'tool_name' in step or any(tool in step_content.lower() 
                                        for tool in ['microsandbox', 'deepsearch', 'browser_use']):
                if 'tool_name' in step:
                    tools_used.add(step.get('tool_name', 'unknown'))
                    
            # 统计成功/失败步骤
            if any(indicator in step_content.lower() 
                   for indicator in ['success', '成功', 'completed', '完成']):
                success_steps += 1
            elif any(indicator in step_content.lower() 
                    for indicator in ['error', 'failed', '错误', '失败']):
                error_steps += 1
        
        summary_parts.append(f"总步数: {step_count}")
        summary_parts.append(f"使用工具: {', '.join(tools_used) if tools_used else '无'}")
        summary_parts.append(f"成功步骤: {success_steps}, 错误步骤: {error_steps}")
        
        # 添加最后几步的内容摘要
        if len(trajectory) > 0:
            last_steps = trajectory[-min(3, len(trajectory)):]
            last_content = " | ".join([str(step)[:100] + "..." 
                                     for step in last_steps])
            summary_parts.append(f"最后步骤: {last_content}")
        
        return " ; ".join(summary_parts)

    def _summarize_tool_execution(self, tool_results: List[Dict[str, Any]]) -> str:
        """总结工具执行情况"""
        if not tool_results:
            return "无工具执行"
            
        tool_summary = {}
        total_success = 0
        total_failure = 0
        
        for result in tool_results:
            tool_name = result.get('tool_name', 'unknown')
            is_success = result.get('success', False)
            
            if tool_name not in tool_summary:
                tool_summary[tool_name] = {'success': 0, 'failure': 0}
                
            if is_success:
                tool_summary[tool_name]['success'] += 1
                total_success += 1
            else:
                tool_summary[tool_name]['failure'] += 1
                total_failure += 1
        
        summary_parts = []
        for tool, stats in tool_summary.items():
            summary_parts.append(f"{tool}: {stats['success']}成功/{stats['failure']}失败")
            
        summary_parts.append(f"总计: {total_success}成功/{total_failure}失败")
        
        return " ; ".join(summary_parts)

    def _detect_self_correction(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """检测自我纠正模式"""
        correction_patterns = {
            'error_to_correction': [],  # 错误→纠正模式
            'retry_patterns': [],       # 重试模式
            'strategy_adjustment': []   # 策略调整模式
        }
        
        for i, step in enumerate(trajectory):
            step_content = str(step).lower()
            
            # 模式1: 错误识别和纠正
            if any(error_word in step_content for error_word in 
                   ['error', 'mistake', '错误', '失败', 'incorrect']):
                # 检查后续步骤是否有纠正行为
                if i + 1 < len(trajectory):
                    next_step = str(trajectory[i + 1]).lower()
                    if any(fix_word in next_step for fix_word in 
                           ['fix', 'correct', '修正', '纠正', 'retry', '重试']):
                        correction_patterns['error_to_correction'].append({
                            'error_step': i,
                            'correction_step': i + 1,
                            'error_content': step_content[:200],
                            'correction_content': next_step[:200]
                        })
            
            # 模式2: 重试模式
            if any(retry_word in step_content for retry_word in 
                   ['retry', 'try again', '重试', '再次尝试']):
                correction_patterns['retry_patterns'].append({
                    'step': i,
                    'content': step_content[:200]
                })
            
            # 模式3: 策略调整
            if any(adjust_word in step_content for adjust_word in 
                   ['different approach', 'alternative', '换个方法', '调整策略']):
                correction_patterns['strategy_adjustment'].append({
                    'step': i,
                    'content': step_content[:200]
                })
        
        return correction_patterns

    async def _llm_semantic_evaluation(
        self, 
        task_input: str, 
        trajectory_summary: str, 
        final_output: str, 
        tool_summary: str
    ) -> Dict[str, Any]:
        """使用LLM进行语义评估"""
        
        prompt = self.evaluation_prompt_template.format(
            task_input=task_input[:500],  # 限制长度避免超出token限制
            trajectory_summary=trajectory_summary,
            final_output=final_output[:1000],
            tool_execution_summary=tool_summary
        )
        
        try:
            # 使用LLMClient的_call_api方法
            response_data = await self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                timeout=30  # 快速响应
            )
            
            # 🔧 兼容新的返回格式：提取content字段
            if isinstance(response_data, dict):
                response = response_data.get('content', '')
            else:
                response = str(response_data)
            
            # 尝试解析JSON响应
            try:
                # 提取JSON部分
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_content = json_match.group(0)
                    evaluation = json.loads(json_content)
                    logger.debug(f"🧠 LLM语义评估结果: {evaluation}")
                    return evaluation
                else:
                    logger.warning("❌ LLM响应中未找到JSON格式")
                    return self._default_semantic_evaluation()
            except json.JSONDecodeError as e:
                logger.warning(f"❌ JSON解析失败: {e}, 响应: {response[:200]}")
                return self._default_semantic_evaluation()
                
        except Exception as e:
            logger.error(f"❌ LLM语义评估调用失败: {e}")
            return self._default_semantic_evaluation()

    def _default_semantic_evaluation(self) -> Dict[str, Any]:
        """默认语义评估结果"""
        return {
            "task_completed": False,
            "self_correction_detected": False,
            "success_evidence": "语义评估不可用",
            "confidence_score": 0.5,
            "reasoning": "LLM语义评估失败，使用规则基准"
        }

    def _rule_based_evaluation(
        self, 
        trajectory: List[Dict[str, Any]], 
        final_output: str, 
        tool_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """基于规则的辅助评估"""
        
        evaluation = {
            'has_meaningful_output': False,
            'tool_success_rate': 0.0,
            'contains_answer_tags': False,
            'error_indicators_count': 0,
            'success_indicators_count': 0
        }
        
        # 1. 检查是否有有意义的输出
        evaluation['has_meaningful_output'] = (
            len(final_output.strip()) > 20 and
            final_output.strip() != TaskExecutionConstants.NO_ACTION_PERFORMED
        )
        
        # 2. 计算工具成功率
        if tool_results:
            successful_tools = sum(1 for result in tool_results 
                                 if result.get('success', False))
            evaluation['tool_success_rate'] = successful_tools / len(tool_results)
        
        # 3. 检查答案标签
        answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
        evaluation['contains_answer_tags'] = (
            f"<{answer_tag}>" in final_output or 
            f"</{answer_tag}>" in final_output or
            "\\boxed{" in final_output
        )
        
        # 4. 统计错误和成功指示词
        final_output_lower = final_output.lower()
        
        evaluation['error_indicators_count'] = sum(
            1 for indicator in TaskExecutionConstants.FAILURE_INDICATORS
            if indicator.lower() in final_output_lower
        )
        
        evaluation['success_indicators_count'] = sum(
            1 for indicator in TaskExecutionConstants.SUCCESS_INDICATORS
            if indicator.lower() in final_output_lower
        )
        
        return evaluation

    def _synthesize_evaluation(
        self,
        semantic_eval: Dict[str, Any],
        rule_eval: Dict[str, Any],
        correction_evidence: Dict[str, Any]
    ) -> TaskEvaluation:
        """综合所有评估信息得出最终判定"""
        
        # 基础信息
        llm_says_completed = semantic_eval.get('task_completed', False)
        llm_confidence = semantic_eval.get('confidence_score', 0.5)
        self_correction_detected = (
            semantic_eval.get('self_correction_detected', False) or
            any(len(patterns) > 0 for patterns in correction_evidence.values())
        )
        
        # 规则指标
        has_meaningful_output = rule_eval['has_meaningful_output']
        tool_success_rate = rule_eval['tool_success_rate']
        has_answer_tags = rule_eval['contains_answer_tags']
        error_count = rule_eval['error_indicators_count']
        success_count = rule_eval['success_indicators_count']
        
        # 综合决策逻辑
        if llm_says_completed and llm_confidence > 0.8:
            # LLM高置信度认为完成
            if self_correction_detected:
                outcome_type = TaskOutcomeType.CORRECTED_SUCCESS
                confidence = min(0.95, llm_confidence + 0.1)
            else:
                outcome_type = TaskOutcomeType.CLEAR_SUCCESS
                confidence = llm_confidence
                
        elif llm_says_completed and llm_confidence > 0.6:
            # LLM中等置信度认为完成，需要规则验证
            if (has_meaningful_output and 
                (tool_success_rate > 0.5 or has_answer_tags) and
                success_count > error_count):
                
                if self_correction_detected:
                    outcome_type = TaskOutcomeType.CORRECTED_SUCCESS
                else:
                    outcome_type = TaskOutcomeType.CLEAR_SUCCESS
                confidence = (llm_confidence + tool_success_rate) / 2
            else:
                outcome_type = TaskOutcomeType.PARTIAL_SUCCESS
                confidence = 0.6
                
        elif tool_success_rate > 0.7 and has_meaningful_output and success_count > 0:
            # LLM不确定，但规则指标良好
            outcome_type = TaskOutcomeType.PARTIAL_SUCCESS
            confidence = 0.7
            
        elif has_meaningful_output and error_count == 0:
            # 有输出且无明显错误
            outcome_type = TaskOutcomeType.PARTIAL_SUCCESS  
            confidence = 0.5
            
        else:
            # 其他情况视为失败
            if error_count > 2 or tool_success_rate < 0.3:
                outcome_type = TaskOutcomeType.COMPLETE_FAILURE
            else:
                outcome_type = TaskOutcomeType.PROCESS_FAILURE
            confidence = 0.3
        
        # 构建证据
        evidence = []
        if llm_says_completed:
            evidence.append(OutcomeEvidence(
                evidence_type="llm_semantic",
                content=semantic_eval.get('success_evidence', ''),
                confidence=llm_confidence,
                source_step=-1,
                timestamp=""
            ))
        
        if tool_success_rate > 0.5:
            evidence.append(OutcomeEvidence(
                evidence_type="tool_execution",
                content=f"工具成功率: {tool_success_rate:.2f}",
                confidence=tool_success_rate,
                source_step=-1,
                timestamp=""
            ))
        
        # 构建最终评估
        evaluation = TaskEvaluation(
            outcome_type=outcome_type,
            confidence_score=confidence,
            primary_evidence=evidence,
            final_output=semantic_eval.get('success_evidence', ''),
            correction_detected=self_correction_detected,
            semantic_reasoning=semantic_eval.get('reasoning', '')
        )
        
        return evaluation

    def _fallback_evaluation(
        self, 
        final_output: str, 
        tool_results: List[Dict[str, Any]]
    ) -> TaskEvaluation:
        """降级评估 - 当智能评估失败时使用"""
        
        has_output = len(final_output.strip()) > 20
        tool_success_rate = 0.0
        
        if tool_results:
            successful = sum(1 for r in tool_results if r.get('success', False))
            tool_success_rate = successful / len(tool_results)
        
        if has_output and tool_success_rate > 0.5:
            outcome_type = TaskOutcomeType.PARTIAL_SUCCESS
            confidence = 0.6
        else:
            outcome_type = TaskOutcomeType.PROCESS_FAILURE
            confidence = 0.4
        
        return TaskEvaluation(
            outcome_type=outcome_type,
            confidence_score=confidence,
            primary_evidence=[],
            final_output=final_output,
            correction_detected=False,
            semantic_reasoning="使用降级评估逻辑"
        )


# 便捷接口函数
async def intelligent_task_evaluation(
    llm_client,
    task_input: str,
    trajectory: List[Dict[str, Any]],
    final_output: str,
    tool_results: List[Dict[str, Any]]
) -> Tuple[bool, float, str]:
    """
    便捷的智能任务评估接口
    
    Returns:
        Tuple[is_success, confidence, reasoning]
    """
    try:
        evaluator = IntelligentStatusEvaluator(llm_client)
        
        evaluation = await evaluator.evaluate_task_completion(
            task_input, trajectory, final_output, tool_results
        )
        
        is_success = evaluation.outcome_type in [
            TaskOutcomeType.CLEAR_SUCCESS,
            TaskOutcomeType.CORRECTED_SUCCESS,
            TaskOutcomeType.PARTIAL_SUCCESS
        ]
        
        return is_success, evaluation.confidence_score, evaluation.semantic_reasoning
        
    except Exception as e:
        logger.error(f"❌ 智能任务评估失败: {e}")
        return False, 0.3, f"评估异常: {str(e)}"