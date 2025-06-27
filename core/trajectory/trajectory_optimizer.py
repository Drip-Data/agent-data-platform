"""
轨迹优化器 - 主要的优化处理器
Trajectory optimizer - main optimization processor
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path

from .text_cleaner import TrajectoryTextCleaner, TrajectoryMarkdownFormatter
from .metrics_collector import MetricsCollector, TrajectoryAggregator
from .optimized_structures import (
    OptimizedTrajectory, OptimizedTrajectoryStep, 
    DecisionContext, PerformanceMetrics, QualityAssessment
)

logger = logging.getLogger(__name__)

class TrajectoryOptimizer:
    """轨迹优化器"""
    
    def __init__(self):
        self.text_cleaner = TrajectoryTextCleaner()
        self.markdown_formatter = TrajectoryMarkdownFormatter()
        self.metrics_collector = MetricsCollector()
        self.aggregator = TrajectoryAggregator()
    
    def optimize_trajectory(self, trajectory_data: Dict[str, Any]) -> OptimizedTrajectory:
        """优化完整轨迹"""
        
        # 基础信息
        task_id = trajectory_data.get('task_id', '')
        task_name = trajectory_data.get('task_name', '')
        task_description = trajectory_data.get('task_description', '')
        runtime_id = trajectory_data.get('runtime_id', '')
        
        # 处理步骤
        raw_steps = trajectory_data.get('steps', [])
        optimized_steps = []
        
        for i, step_data in enumerate(raw_steps):
            optimized_step = self._optimize_step(step_data, i + 1)
            optimized_steps.append(optimized_step)
        
        # 聚合指标
        aggregated_metrics = self.aggregator.aggregate_trajectory_metrics(raw_steps)
        
        # 创建优化轨迹
        optimized_trajectory = OptimizedTrajectory(
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_id=runtime_id,
            steps=optimized_steps,
            success=trajectory_data.get('success', True),
            final_result=self._clean_final_result(trajectory_data.get('final_result', '')),
            total_duration_ms=aggregated_metrics['total_duration_ms'],
            total_tokens=aggregated_metrics['total_tokens'],
            total_cost=aggregated_metrics['total_cost'],
            overall_quality_score=aggregated_metrics['average_quality_score'],
            step_count=aggregated_metrics['total_steps'],
            retry_count=aggregated_metrics['total_retries'],
            backtrack_count=aggregated_metrics['total_backtracks'],
            metadata=trajectory_data.get('metadata', {})
        )
        
        return optimized_trajectory
    
    def _optimize_step(self, step_data: Dict[str, Any], step_number: int) -> OptimizedTrajectoryStep:
        """优化单个步骤"""
        
        # 基础信息
        step_id = step_data.get('step_id', step_number)
        step_type = step_data.get('action_type', 'unknown')
        
        # 清理文本内容
        raw_thinking = step_data.get('thinking', '')
        raw_output = step_data.get('tool_output', '')
        
        cleaned_output = self.text_cleaner.clean_llm_output(raw_output)
        structured_reasoning = self.text_cleaner.clean_thinking_process(raw_thinking)
        
        # 提取决策上下文
        decision_context = self._extract_decision_context(step_data, structured_reasoning)
        
        # 提取执行信息
        tool_input = step_data.get('tool_input', {})
        tool_id = tool_input.get('_tool_id', tool_input.get('tool_id', ''))
        action = tool_input.get('_action', tool_input.get('action', ''))
        parameters = {k: v for k, v in tool_input.items() 
                     if not k.startswith('_') and k not in ['tool_id', 'action']}
        
        # 收集性能指标
        monitor = self.metrics_collector.start_step_monitoring(step_id)
        # 模拟执行时间（从step_data中获取duration或使用默认值）
        import time
        time.sleep(0.001)  # 确保有一些执行时间
        performance_metrics = self.metrics_collector.collect_step_metrics(
            monitor, step_data, raw_thinking, cleaned_output
        )
        
        # 质量评估
        quality_assessment = self.metrics_collector.assess_step_quality(
            step_data, cleaned_output
        )
        
        # 创建优化步骤
        optimized_step = OptimizedTrajectoryStep(
            step_id=step_id,
            step_type=step_type,
            timestamp=datetime.now(),
            decision_context=decision_context,
            raw_thinking=raw_thinking,
            structured_reasoning=structured_reasoning,
            tool_id=tool_id,
            action=action,
            parameters=parameters,
            raw_output=raw_output,
            cleaned_output=cleaned_output,
            performance_metrics=performance_metrics,
            quality_assessment=quality_assessment,
            success=step_data.get('success', True),
            error_message=step_data.get('error_message', '')
        )
        
        return optimized_step
    
    def _extract_decision_context(self, step_data: Dict[str, Any], 
                                structured_reasoning: Dict[str, str]) -> DecisionContext:
        """提取决策上下文"""
        
        # 从thinking中提取信息
        situation_analysis = ""
        selection_reasoning = ""
        confidence_score = 0.8  # 默认值
        
        for key, value in structured_reasoning.items():
            if 'analysis' in key.lower() or 'situation' in key.lower():
                situation_analysis = value
            elif 'decision' in key.lower() or 'reasoning' in key.lower():
                selection_reasoning = value
            elif 'confidence' in key.lower():
                # 尝试提取数值
                import re
                confidence_match = re.search(r'(\d+\.?\d*)', value)
                if confidence_match:
                    confidence_score = min(1.0, float(confidence_match.group(1)))
        
        # 从工具输入获取选择信息
        tool_input = step_data.get('tool_input', {})
        selected_option = tool_input.get('_tool_id', '')
        
        return DecisionContext(
            situation_analysis=situation_analysis,
            selected_option=selected_option,
            selection_reasoning=selection_reasoning,
            confidence_score=confidence_score
        )
    
    def _clean_final_result(self, final_result: str) -> str:
        """清理最终结果"""
        return self.text_cleaner.clean_llm_output(final_result)
    
    def export_as_markdown(self, optimized_trajectory: OptimizedTrajectory) -> str:
        """导出为Markdown格式"""
        
        markdown_parts = []
        
        # 标题和概述
        markdown_parts.append(f"# 🎯 Task Execution Report: {optimized_trajectory.task_name}")
        markdown_parts.append(f"**Task ID**: `{optimized_trajectory.task_id}`")
        markdown_parts.append(f"**Description**: {optimized_trajectory.task_description}")
        markdown_parts.append(f"**Status**: {'✅ Success' if optimized_trajectory.success else '❌ Failed'}")
        markdown_parts.append(f"**Duration**: {optimized_trajectory.total_duration_ms/1000:.2f}s")
        
        # 执行摘要
        markdown_parts.append("## 📊 Execution Summary")
        markdown_parts.append(f"- **Total Steps**: {optimized_trajectory.step_count}")
        success_rate = ((optimized_trajectory.step_count - len([s for s in optimized_trajectory.steps if not s.success]))/optimized_trajectory.step_count*100) if optimized_trajectory.step_count > 0 else 0
        markdown_parts.append(f"- **Success Rate**: {success_rate:.1f}%")
        markdown_parts.append(f"- **Total Tokens**: {optimized_trajectory.total_tokens:,}")
        markdown_parts.append(f"- **Total Cost**: ${optimized_trajectory.total_cost:.4f}")
        markdown_parts.append(f"- **Quality Score**: {optimized_trajectory.overall_quality_score:.2f}/1.0")
        
        if optimized_trajectory.retry_count > 0:
            markdown_parts.append(f"- **Retries**: {optimized_trajectory.retry_count}")
        if optimized_trajectory.backtrack_count > 0:
            markdown_parts.append(f"- **Backtracks**: {optimized_trajectory.backtrack_count}")
        
        # 步骤详情
        markdown_parts.append("## 🔄 Execution Steps")
        
        for step in optimized_trajectory.steps:
            step_md = self._format_step_markdown(step)
            markdown_parts.append(step_md)
        
        # 最终结果
        if optimized_trajectory.final_result:
            markdown_parts.append("## 🎯 Final Result")
            markdown_parts.append(optimized_trajectory.final_result)
        
        return "\n\n".join(markdown_parts)
    
    def _format_step_markdown(self, step: OptimizedTrajectoryStep) -> str:
        """格式化步骤Markdown"""
        
        step_parts = []
        
        # 步骤标题
        status_icon = "✅" if step.success else "❌"
        step_parts.append(f"### {status_icon} Step {step.step_id}: {step.step_type.replace('_', ' ').title()}")
        
        if step.tool_id:
            step_parts.append(f"**Tool**: `{step.tool_id}` | **Action**: `{step.action}`")
        
        # 决策过程
        if step.decision_context.situation_analysis or step.decision_context.selection_reasoning:
            step_parts.append("#### 🧠 Decision Process")
            
            if step.decision_context.situation_analysis:
                step_parts.append(f"- **Analysis**: {step.decision_context.situation_analysis}")
            
            if step.decision_context.selection_reasoning:
                step_parts.append(f"- **Reasoning**: {step.decision_context.selection_reasoning}")
            
            step_parts.append(f"- **Confidence**: {step.decision_context.confidence_score:.2f}")
        
        # 执行参数
        if step.parameters:
            step_parts.append("#### ⚙️ Parameters")
            step_parts.append("```json")
            step_parts.append(json.dumps(step.parameters, indent=2, ensure_ascii=False))
            step_parts.append("```")
        
        # 性能指标
        metrics = step.performance_metrics
        step_parts.append("#### 📊 Performance")
        step_parts.append(f"- **Duration**: {metrics.execution_time_ms}ms")
        step_parts.append(f"- **Tokens**: {metrics.token_metrics.total_tokens}")
        step_parts.append(f"- **Cost**: ${metrics.token_metrics.cost_estimate:.4f}")
        step_parts.append(f"- **Quality**: {step.quality_assessment.overall_score:.2f}/1.0")
        
        if metrics.retry_count > 0:
            step_parts.append(f"- **Retries**: {metrics.retry_count}")
        
        # 结果
        if step.cleaned_output:
            step_parts.append("#### 📝 Result")
            # 限制长度以保持可读性
            if len(step.cleaned_output) > 1500:
                step_parts.append(f"{step.cleaned_output[:1500]}...\n\n*[Output truncated for readability]*")
            else:
                step_parts.append(step.cleaned_output)
        
        return "\n\n".join(step_parts)
    
    def export_as_json(self, optimized_trajectory: OptimizedTrajectory) -> Dict[str, Any]:
        """导出为JSON格式"""
        
        # 转换为字典
        result = {
            "task_metadata": {
                "task_id": optimized_trajectory.task_id,
                "task_name": optimized_trajectory.task_name,
                "task_description": optimized_trajectory.task_description,
                "runtime_id": optimized_trajectory.runtime_id,
                "created_at": optimized_trajectory.created_at.isoformat()
            },
            "execution_summary": {
                "success": optimized_trajectory.success,
                "total_duration_ms": optimized_trajectory.total_duration_ms,
                "step_count": optimized_trajectory.step_count,
                "retry_count": optimized_trajectory.retry_count,
                "backtrack_count": optimized_trajectory.backtrack_count,
                "overall_quality_score": optimized_trajectory.overall_quality_score
            },
            "resource_usage": {
                "total_tokens": optimized_trajectory.total_tokens,
                "total_cost": optimized_trajectory.total_cost,
                "average_cost_per_step": optimized_trajectory.total_cost / max(1, optimized_trajectory.step_count),
                "average_tokens_per_step": optimized_trajectory.total_tokens / max(1, optimized_trajectory.step_count)
            },
            "steps": [],
            "final_result": optimized_trajectory.final_result,
            "metadata": optimized_trajectory.metadata
        }
        
        # 转换步骤
        for step in optimized_trajectory.steps:
            step_dict = {
                "step_id": step.step_id,
                "step_type": step.step_type,
                "timestamp": step.timestamp.isoformat(),
                "tool_execution": {
                    "tool_id": step.tool_id,
                    "action": step.action,
                    "parameters": step.parameters,
                    "success": step.success,
                    "error_message": step.error_message
                },
                "decision_context": {
                    "situation_analysis": step.decision_context.situation_analysis,
                    "selection_reasoning": step.decision_context.selection_reasoning,
                    "confidence_score": step.decision_context.confidence_score
                },
                "performance_metrics": {
                    "execution_time_ms": step.performance_metrics.execution_time_ms,
                    "token_usage": {
                        "input_tokens": step.performance_metrics.token_metrics.input_tokens,
                        "output_tokens": step.performance_metrics.token_metrics.output_tokens,
                        "total_tokens": step.performance_metrics.token_metrics.total_tokens,
                        "cost_estimate": step.performance_metrics.token_metrics.cost_estimate,
                        "model_name": step.performance_metrics.token_metrics.model_name
                    },
                    "retry_count": step.performance_metrics.retry_count,
                    "efficiency_score": step.performance_metrics.efficiency_score
                },
                "quality_assessment": {
                    "reasoning_quality": step.quality_assessment.reasoning_quality.value,
                    "output_completeness": step.quality_assessment.output_completeness,
                    "accuracy_score": step.quality_assessment.accuracy_score,
                    "explanation_clarity": step.quality_assessment.explanation_clarity,
                    "overall_score": step.quality_assessment.overall_score
                },
                "content": {
                    "cleaned_output": step.cleaned_output,
                    "structured_reasoning": step.structured_reasoning
                }
            }
            
            result["steps"].append(step_dict)
        
        return result

def process_trajectory_file(input_file: Union[str, Path], 
                          output_dir: Union[str, Path]) -> Dict[str, str]:
    """处理轨迹文件"""
    
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 读取原始轨迹
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            trajectories_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read trajectory file: {e}")
        return {"error": str(e)}
    
    optimizer = TrajectoryOptimizer()
    processed_files = {}
    
    # 处理每个轨迹
    if isinstance(trajectories_data, list):
        for i, trajectory_data in enumerate(trajectories_data):
            try:
                optimized = optimizer.optimize_trajectory(trajectory_data)
                
                # 生成文件名
                task_name = trajectory_data.get('task_name', f'trajectory_{i}')
                safe_name = "".join(c for c in task_name if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_name = safe_name.replace(' ', '_')[:50]
                
                # 导出Markdown
                markdown_content = optimizer.export_as_markdown(optimized)
                markdown_file = output_path / f"{safe_name}.md"
                with open(markdown_file, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                
                # 导出JSON
                json_content = optimizer.export_as_json(optimized)
                json_file = output_path / f"{safe_name}_optimized.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(json_content, f, indent=2, ensure_ascii=False)
                
                processed_files[task_name] = {
                    "markdown": str(markdown_file),
                    "json": str(json_file)
                }
                
                logger.info(f"Processed trajectory: {task_name}")
                
            except Exception as e:
                logger.error(f"Failed to process trajectory {i}: {e}")
                processed_files[f"trajectory_{i}_error"] = {"error": str(e)}
    
    return processed_files