#!/usr/bin/env python3
"""
任务复杂度评估器
评估任务的复杂度和质量，确保生成的综合任务真正有挑战性
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .interfaces import AtomicTask, DepthExtendedTask, WidthExtendedTask, TaskComplexity

logger = logging.getLogger(__name__)

class ComplexityDimension(Enum):
    """复杂度维度"""
    REASONING_STEPS = "reasoning_steps"      # 推理步骤数量
    TOOL_DIVERSITY = "tool_diversity"        # 工具多样性
    DOMAIN_BREADTH = "domain_breadth"        # 领域广度
    INTERDEPENDENCE = "interdependence"      # 步骤间依赖
    COGNITIVE_LOAD = "cognitive_load"        # 认知负荷
    OUTPUT_RICHNESS = "output_richness"      # 输出丰富度

@dataclass
class ComplexityScore:
    """复杂度评分"""
    total_score: float
    dimension_scores: Dict[ComplexityDimension, float]
    complexity_level: str
    quality_issues: List[str]
    enhancement_suggestions: List[str]

class TaskComplexityEvaluator:
    """任务复杂度评估器"""
    
    def __init__(self):
        # 复杂度阈值定义
        self.complexity_thresholds = {
            "trivial": 0.0,      # 无意义的扩展
            "simple": 2.0,       # 简单扩展
            "moderate": 4.0,     # 中等复杂度
            "complex": 7.0,      # 复杂任务
            "comprehensive": 10.0 # 综合性任务
        }
        
        # 维度权重
        self.dimension_weights = {
            ComplexityDimension.REASONING_STEPS: 0.25,
            ComplexityDimension.TOOL_DIVERSITY: 0.20,
            ComplexityDimension.DOMAIN_BREADTH: 0.15,
            ComplexityDimension.INTERDEPENDENCE: 0.20,
            ComplexityDimension.COGNITIVE_LOAD: 0.10,
            ComplexityDimension.OUTPUT_RICHNESS: 0.10
        }
    
    def evaluate_depth_extended_task(self, task: DepthExtendedTask) -> ComplexityScore:
        """评估深度扩展任务的复杂度"""
        logger.debug(f"🔍 评估深度扩展任务复杂度: {task.task_id}")
        
        dimension_scores = {}
        
        # 1. 推理步骤评估
        reasoning_score = self._evaluate_reasoning_complexity(
            task.combined_question, 
            task.base_task.question
        )
        dimension_scores[ComplexityDimension.REASONING_STEPS] = reasoning_score
        
        # 2. 工具多样性评估
        tool_score = self._evaluate_tool_diversity_depth(task)
        dimension_scores[ComplexityDimension.TOOL_DIVERSITY] = tool_score
        
        # 3. 领域深度评估
        domain_score = self._evaluate_domain_depth(task.combined_question, task.base_task.domain)
        dimension_scores[ComplexityDimension.DOMAIN_BREADTH] = domain_score
        
        # 4. 步骤依赖性评估
        interdependence_score = self._evaluate_step_interdependence(task.combined_question)
        dimension_scores[ComplexityDimension.INTERDEPENDENCE] = interdependence_score
        
        # 5. 认知负荷评估
        cognitive_score = self._evaluate_cognitive_load(task.combined_question)
        dimension_scores[ComplexityDimension.COGNITIVE_LOAD] = cognitive_score
        
        # 6. 输出丰富度评估
        output_score = self._evaluate_output_richness(task.combined_answer)
        dimension_scores[ComplexityDimension.OUTPUT_RICHNESS] = output_score
        
        # 计算总分
        total_score = self._calculate_weighted_score(dimension_scores)
        
        # 确定复杂度等级
        complexity_level = self._determine_complexity_level(total_score)
        
        # 识别质量问题
        quality_issues = self._identify_quality_issues_depth(task, dimension_scores)
        
        # 生成改进建议
        enhancement_suggestions = self._generate_enhancement_suggestions_depth(dimension_scores)
        
        return ComplexityScore(
            total_score=total_score,
            dimension_scores=dimension_scores,
            complexity_level=complexity_level,
            quality_issues=quality_issues,
            enhancement_suggestions=enhancement_suggestions
        )
    
    def evaluate_width_extended_task(self, task: WidthExtendedTask) -> ComplexityScore:
        """评估宽度扩展任务的复杂度"""
        logger.debug(f"🔍 评估宽度扩展任务复杂度: {task.task_id}")
        
        dimension_scores = {}
        
        # 1. 协同复杂度评估
        synergy_score = self._evaluate_synergy_complexity(task)
        dimension_scores[ComplexityDimension.REASONING_STEPS] = synergy_score
        
        # 2. 工具协同评估
        tool_score = self._evaluate_tool_synergy(task)
        dimension_scores[ComplexityDimension.TOOL_DIVERSITY] = tool_score
        
        # 3. 跨域整合评估
        domain_score = self._evaluate_cross_domain_integration(task)
        dimension_scores[ComplexityDimension.DOMAIN_BREADTH] = domain_score
        
        # 4. 信息流转评估
        flow_score = self._evaluate_information_flow(task.merged_question)
        dimension_scores[ComplexityDimension.INTERDEPENDENCE] = flow_score
        
        # 5. 整合难度评估
        integration_score = self._evaluate_integration_difficulty(task)
        dimension_scores[ComplexityDimension.COGNITIVE_LOAD] = integration_score
        
        # 6. 系统性输出评估
        system_score = self._evaluate_systematic_output(task.merged_answer)
        dimension_scores[ComplexityDimension.OUTPUT_RICHNESS] = system_score
        
        # 计算总分
        total_score = self._calculate_weighted_score(dimension_scores)
        
        # 确定复杂度等级
        complexity_level = self._determine_complexity_level(total_score)
        
        # 识别质量问题
        quality_issues = self._identify_quality_issues_width(task, dimension_scores)
        
        # 生成改进建议
        enhancement_suggestions = self._generate_enhancement_suggestions_width(dimension_scores)
        
        return ComplexityScore(
            total_score=total_score,
            dimension_scores=dimension_scores,
            complexity_level=complexity_level,
            quality_issues=quality_issues,
            enhancement_suggestions=enhancement_suggestions
        )
    
    def _evaluate_reasoning_complexity(self, extended_question: str, base_question: str) -> float:
        """评估推理复杂度"""
        # 分析步骤数量
        step_patterns = [
            r'\d+\)\s*',  # 1) 2) 3) 格式
            r'\d+\.\s*',  # 1. 2. 3. 格式
            r'第[一二三四五六七八九十\d]+步',  # 中文步骤
            r'首先|然后|接着|最后|其次',  # 连接词
        ]
        
        step_count = 0
        for pattern in step_patterns:
            matches = re.findall(pattern, extended_question, re.IGNORECASE)
            step_count = max(step_count, len(matches))
        
        # 分析逻辑连接词
        logic_words = ['因此', '所以', '基于', '结合', '综合', '对比', '分析', '评估', '预测']
        logic_count = sum(1 for word in logic_words if word in extended_question)
        
        # 计算复杂度增益
        base_complexity = len(base_question.split()) * 0.1
        extended_complexity = len(extended_question.split()) * 0.1
        complexity_gain = (extended_complexity - base_complexity) / base_complexity if base_complexity > 0 else 0
        
        # 综合评分
        score = min(10.0, step_count * 1.5 + logic_count * 0.5 + complexity_gain * 2)
        return score
    
    def _evaluate_tool_diversity_depth(self, task: DepthExtendedTask) -> float:
        """评估深度扩展的工具多样性"""
        # 提取问题中涉及的工具类型
        tool_indicators = {
            '搜索': ['搜索', '查找', '检索', 'search'],
            '代码': ['代码', '编程', '实现', '计算', 'code', 'python'],
            '分析': ['分析', '评估', '比较', '预测', 'analyze'],
            '可视化': ['图表', '可视化', '展示', 'chart', 'graph'],
            '下载': ['下载', '获取', '收集', 'download'],
            '报告': ['报告', '文档', '总结', 'report']
        }
        
        identified_tools = set()
        question = task.combined_question.lower()
        
        for tool_type, indicators in tool_indicators.items():
            if any(indicator in question for indicator in indicators):
                identified_tools.add(tool_type)
        
        # 基础工具数量评分
        base_score = len(identified_tools) * 1.5
        
        # 工具协同评分（如果有明确的工具链描述）
        if '结合' in question or '整合' in question or '协同' in question:
            base_score += 2.0
        
        return min(10.0, base_score)
    
    def _evaluate_domain_depth(self, question: str, base_domain: str) -> float:
        """评估领域深度"""
        # 专业术语指标
        professional_terms = {
            '金融': ['投资', '股票', '财报', '估值', '风险', 'ROI', '收益率'],
            '教育': ['学术', '研究', '论文', '院校', '专业', '就业'],
            '科技': ['算法', '数据', '模型', '系统', '架构', '优化'],
            '科学研究': ['实验', '假设', '变量', '统计', '相关性', '显著性']
        }
        
        domain_terms = professional_terms.get(base_domain, [])
        term_count = sum(1 for term in domain_terms if term in question)
        
        # 深度指标
        depth_indicators = ['深度', '系统', '全面', '专业', '详细', '综合']
        depth_count = sum(1 for indicator in depth_indicators if indicator in question)
        
        # 分析方法指标
        analysis_methods = ['比较分析', '趋势分析', '相关分析', '回归分析', '预测模型']
        method_count = sum(1 for method in analysis_methods if method in question)
        
        score = term_count * 1.0 + depth_count * 1.5 + method_count * 2.0
        return min(10.0, score)
    
    def _evaluate_step_interdependence(self, question: str) -> float:
        """评估步骤间依赖性"""
        # 依赖关系指标
        dependency_patterns = [
            r'基于.*[的].*结果',  # 基于...的结果
            r'根据.*[进行|实施]',  # 根据...进行
            r'结合.*[和].*',      # 结合...和...
            r'在.*[基础上]',      # 在...基础上
            r'利用.*[来].*',      # 利用...来...
        ]
        
        dependency_count = 0
        for pattern in dependency_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            dependency_count += len(matches)
        
        # 信息流转指标
        flow_words = ['传递', '输入', '输出', '流程', '管道', '链条']
        flow_count = sum(1 for word in flow_words if word in question)
        
        score = dependency_count * 2.0 + flow_count * 1.5
        return min(10.0, score)
    
    def _evaluate_cognitive_load(self, question: str) -> float:
        """评估认知负荷"""
        # 复杂概念数量
        complex_concepts = ['算法', '模型', '架构', '框架', '策略', '机制', '体系']
        concept_count = sum(1 for concept in complex_concepts if concept in question)
        
        # 抽象思维要求
        abstract_words = ['概念', '理论', '原理', '逻辑', '思维', '认知']
        abstract_count = sum(1 for word in abstract_words if word in question)
        
        # 综合判断要求
        judgment_words = ['判断', '决策', '选择', '权衡', '评判', '决定']
        judgment_count = sum(1 for word in judgment_words if word in question)
        
        score = concept_count * 1.0 + abstract_count * 1.5 + judgment_count * 2.0
        return min(10.0, score)
    
    def _evaluate_output_richness(self, answer: str) -> float:
        """评估输出丰富度"""
        # 输出类型多样性
        output_types = {
            '报告': ['报告', '分析', '总结'],
            '图表': ['图表', '可视化', '图形'],
            '数据': ['数据', '统计', '指标'],
            '建议': ['建议', '推荐', '方案'],
            '预测': ['预测', '预估', '展望']
        }
        
        identified_outputs = set()
        answer_lower = answer.lower()
        
        for output_type, indicators in output_types.items():
            if any(indicator in answer_lower for indicator in indicators):
                identified_outputs.add(output_type)
        
        # 结构化程度
        structure_indicators = ['包含', '分为', '组成', '结构', '层次']
        structure_count = sum(1 for indicator in structure_indicators if indicator in answer)
        
        score = len(identified_outputs) * 2.0 + structure_count * 1.0
        return min(10.0, score)
    
    def _evaluate_synergy_complexity(self, task: WidthExtendedTask) -> float:
        """评估协同复杂度"""
        # 任务数量
        task_count = len(task.component_tasks)
        
        # 协同指标
        synergy_words = ['协同', '整合', '结合', '融合', '综合', '系统']
        synergy_count = sum(1 for word in synergy_words if word in task.merged_question)
        
        # 复杂协同模式
        complex_patterns = ['交叉验证', '相互佐证', '互补分析', '双向验证']
        pattern_count = sum(1 for pattern in complex_patterns if pattern in task.merged_question)
        
        score = task_count * 1.5 + synergy_count * 1.0 + pattern_count * 3.0
        return min(10.0, score)
    
    def _evaluate_tool_synergy(self, task: WidthExtendedTask) -> float:
        """评估工具协同"""
        # 收集所有组件任务的工具
        all_tools = set()
        for component in task.component_tasks:
            if hasattr(component, 'expected_tools'):
                all_tools.update(component.expected_tools)
        
        tool_diversity = len(all_tools)
        
        # 工具链复杂度
        chain_indicators = ['流水线', '管道', '自动化', '批处理']
        chain_count = sum(1 for indicator in chain_indicators if indicator in task.merged_question)
        
        score = tool_diversity * 2.0 + chain_count * 1.5
        return min(10.0, score)
    
    def _evaluate_cross_domain_integration(self, task: WidthExtendedTask) -> float:
        """评估跨域整合"""
        # 领域多样性
        domains = set(component.domain for component in task.component_tasks)
        domain_diversity = len(domains)
        
        # 跨域指标
        cross_domain_words = ['跨领域', '多维度', '综合视角', '全面分析']
        cross_count = sum(1 for word in cross_domain_words if word in task.merged_question)
        
        score = domain_diversity * 2.5 + cross_count * 2.0
        return min(10.0, score)
    
    def _evaluate_information_flow(self, question: str) -> float:
        """评估信息流转"""
        # 流转指标
        flow_patterns = [
            r'将.*结果.*用于',    # 将...结果用于
            r'基于.*输出.*进行',  # 基于...输出进行
            r'利用.*数据.*分析'   # 利用...数据分析
        ]
        
        flow_count = 0
        for pattern in flow_patterns:
            matches = re.findall(pattern, question)
            flow_count += len(matches)
        
        # 数据传递复杂度
        transfer_words = ['传递', '流转', '汇总', '整合', '合并']
        transfer_count = sum(1 for word in transfer_words if word in question)
        
        score = flow_count * 2.0 + transfer_count * 1.5
        return min(10.0, score)
    
    def _evaluate_integration_difficulty(self, task: WidthExtendedTask) -> float:
        """评估整合难度"""
        # 任务复杂度差异
        complexities = []
        for component in task.component_tasks:
            complexity = len(component.question.split()) + (2 if component.requires_tool else 0)
            complexities.append(complexity)
        
        complexity_variance = max(complexities) - min(complexities) if complexities else 0
        
        # 整合方法复杂度
        integration_methods = ['加权合并', '层次整合', '模型融合', '决策树']
        method_count = sum(1 for method in integration_methods if method in task.merged_question)
        
        score = complexity_variance * 0.5 + method_count * 2.0
        return min(10.0, score)
    
    def _evaluate_systematic_output(self, answer: str) -> float:
        """评估系统性输出"""
        # 系统性指标
        system_words = ['系统', '平台', '框架', '体系', '架构']
        system_count = sum(1 for word in system_words if word in answer)
        
        # 完整性指标
        completeness_words = ['完整', '全面', '端到端', '一站式']
        completeness_count = sum(1 for word in completeness_words if word in answer)
        
        score = system_count * 1.5 + completeness_count * 2.0
        return min(10.0, score)
    
    def _calculate_weighted_score(self, dimension_scores: Dict[ComplexityDimension, float]) -> float:
        """计算加权总分"""
        total_score = 0.0
        for dimension, score in dimension_scores.items():
            weight = self.dimension_weights.get(dimension, 0.0)
            total_score += score * weight
        return total_score
    
    def _determine_complexity_level(self, total_score: float) -> str:
        """确定复杂度等级"""
        for level, threshold in sorted(self.complexity_thresholds.items(), key=lambda x: x[1], reverse=True):
            if total_score >= threshold:
                return level
        return "trivial"
    
    def _identify_quality_issues_depth(self, task: DepthExtendedTask, scores: Dict) -> List[str]:
        """识别深度扩展的质量问题"""
        issues = []
        
        if scores[ComplexityDimension.REASONING_STEPS] < 3.0:
            issues.append("推理步骤过少，缺乏真正的深度扩展")
        
        if scores[ComplexityDimension.TOOL_DIVERSITY] < 2.0:
            issues.append("工具使用单一，未充分利用多工具协同")
        
        if scores[ComplexityDimension.INTERDEPENDENCE] < 2.0:
            issues.append("步骤间缺乏逻辑依赖关系")
        
        # 检查是否只是简单的前缀添加
        if task.combined_question.startswith("先处理") and "然后" in task.combined_question:
            issues.append("疑似简单的前缀添加，而非真正的深度扩展")
        
        return issues
    
    def _identify_quality_issues_width(self, task: WidthExtendedTask, scores: Dict) -> List[str]:
        """识别宽度扩展的质量问题"""
        issues = []
        
        if scores[ComplexityDimension.REASONING_STEPS] < 3.0:
            issues.append("协同复杂度不足，任务间缺乏有效整合")
        
        if scores[ComplexityDimension.TOOL_DIVERSITY] < 3.0:
            issues.append("工具协同效果不佳")
        
        if scores[ComplexityDimension.INTERDEPENDENCE] < 2.0:
            issues.append("缺乏信息流转和步骤依赖")
        
        # 检查是否只是简单的任务列举
        if task.merged_question.count("1)") and task.merged_question.count("2)") and "同时" in task.merged_question:
            issues.append("疑似简单的任务列举，缺乏真正的协同设计")
        
        return issues
    
    def _generate_enhancement_suggestions_depth(self, scores: Dict) -> List[str]:
        """生成深度扩展的改进建议"""
        suggestions = []
        
        if scores[ComplexityDimension.REASONING_STEPS] < 5.0:
            suggestions.append("增加推理步骤，设计多层次的分析流程")
        
        if scores[ComplexityDimension.TOOL_DIVERSITY] < 4.0:
            suggestions.append("整合更多工具类型，设计工具协同使用方案")
        
        if scores[ComplexityDimension.OUTPUT_RICHNESS] < 4.0:
            suggestions.append("丰富输出类型，包含可视化、报告、建议等多种形式")
        
        return suggestions
    
    def _generate_enhancement_suggestions_width(self, scores: Dict) -> List[str]:
        """生成宽度扩展的改进建议"""
        suggestions = []
        
        if scores[ComplexityDimension.REASONING_STEPS] < 5.0:
            suggestions.append("设计更复杂的任务协同模式")
        
        if scores[ComplexityDimension.DOMAIN_BREADTH] < 4.0:
            suggestions.append("增加跨领域整合，提升任务的系统性")
        
        if scores[ComplexityDimension.INTERDEPENDENCE] < 4.0:
            suggestions.append("设计信息流转机制，确保任务间的有效连接")
        
        return suggestions