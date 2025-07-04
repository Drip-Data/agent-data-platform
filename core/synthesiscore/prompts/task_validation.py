#!/usr/bin/env python3
"""
任务验证相关的 Prompt 模板
包含原子性检查、工具必要性验证、推理充分性验证等
"""

from typing import Dict, Any
from .base import PromptTemplate, PromptModule, PromptType


class TaskValidationPrompts(PromptModule):
    """任务验证 Prompt 模板集合"""
    
    def __init__(self):
        self._templates = self._initialize_templates()
    
    def _initialize_templates(self) -> Dict[str, PromptTemplate]:
        """初始化所有任务验证模板"""
        templates = {}
        
        # 工具必要性检查模板
        templates["check_tool_necessity"] = PromptTemplate(
            name="check_tool_necessity",
            template="""你是一个任务分析专家。请判断以下任务是否必须使用工具才能完成。

任务问题：
{question}

分析维度：
1. 是否需要查询实时信息或外部数据？
2. 是否需要执行计算、代码或特定操作？
3. 是否需要访问文件系统或网络资源？
4. 是否需要调用特定的API或服务？
5. 是否仅凭语言模型的推理能力就能回答？

判断标准：
- 如果任务需要获取模型训练数据之外的信息，则需要工具
- 如果任务需要执行具体操作（而非描述），则需要工具
- 如果任务可以通过纯推理和已知知识完成，则不需要工具

请以JSON格式返回分析结果：
{{
    "requires_tool": true|false,
    "reasoning": "详细的判断理由",
    "tool_categories": ["search", "computation", "file_access", "api_call"],
    "confidence": 0.95,
    "alternative_approach": "如果不用工具，是否有其他方法"
}}""",
            description="判断任务是否必须使用工具",
            prompt_type=PromptType.TOOL_NECESSITY,
            required_params=["question"]
        )
        
        # 推理充分性检查模板
        templates["check_reasoning_sufficiency"] = PromptTemplate(
            name="check_reasoning_sufficiency",
            template="""你是一个认知能力评估专家。请判断以下任务是否仅通过推理就能解决。

任务问题：
{question}

评估维度：
1. 任务是否涉及常识推理或逻辑推理？
2. 所需知识是否在语言模型的训练范围内？
3. 是否需要实时数据或动态信息？
4. 推理的复杂度是否在可接受范围内？

推理类型分析：
- 演绎推理：从一般原理推出特定结论
- 归纳推理：从特例归纳出一般规律
- 类比推理：基于相似性进行推理
- 因果推理：分析因果关系

请以JSON格式返回评估结果：
{{
    "reasoning_sufficient": true|false,
    "reasoning_type": "演绎|归纳|类比|因果|混合",
    "knowledge_requirement": "所需知识类型",
    "complexity_level": "简单|中等|复杂",
    "limitations": ["推理局限性1", "推理局限性2"],
    "confidence": 0.90
}}""",
            description="评估任务是否可通过纯推理解决",
            prompt_type=PromptType.REASONING_SUFFICIENCY,
            required_params=["question"]
        )
        
        # 原子性检查模板
        templates["check_atomicity"] = PromptTemplate(
            name="check_atomicity",
            template="""你是一个任务分解专家。请判断以下任务是否为原子任务（不可进一步分解）。

任务问题：
{question}

原子性评估标准：
1. 任务是否只有一个明确的目标？
2. 任务是否不能分解为多个独立的子任务？
3. 任务描述中是否不包含"然后"、"接着"、"同时"等连接词？
4. 任务是否可以一次性完成，不需要多个步骤？

分解测试：
- 尝试将任务分解为更小的步骤
- 检查每个步骤是否独立有意义
- 验证是否存在明显的顺序依赖

非原子任务的典型特征：
- 包含多个动作词
- 有明显的步骤顺序
- 可以用"首先...然后...最后"描述
- 涉及多个不同的操作或判断

请以JSON格式返回分析结果：
{{
    "is_atomic": true|false,
    "decomposition_test": [
        {{
            "step": 1,
            "description": "可能的子任务描述"
        }}
    ],
    "complexity_indicators": ["指标1", "指标2"],
    "atomic_level": "原子|接近原子|明显复合",
    "improvement_suggestion": "如何改进为原子任务"
}}""",
            description="检查任务的原子性",
            prompt_type=PromptType.ATOMICITY_CHECK,
            required_params=["question"]
        )
        
        # 超集关系验证模板
        templates["validate_superset_relation"] = PromptTemplate(
            name="validate_superset_relation",
            template="""你是一个逻辑关系专家。请判断两个输入之间是否存在超集关系。

基础输入：
{base_input}

候选超集输入：
{superset_input}

超集关系标准：
1. 超集输入是否包含基础输入的所有信息？
2. 超集输入是否提供了额外的信息或约束？
3. 基础输入的解决方案是否是超集输入解决方案的子集？
4. 超集关系是否在逻辑上成立？

验证方法：
- 信息包含性检查
- 复杂度比较
- 逻辑一致性验证
- 实际应用场景分析

请以JSON格式返回验证结果：
{{
    "is_superset": true|false,
    "inclusion_analysis": "包含关系分析",
    "additional_elements": ["超集中的额外元素"],
    "logical_consistency": true|false,
    "relationship_strength": "强|中|弱",
    "validation_confidence": 0.88
}}""",
            description="验证输入间的超集关系",
            prompt_type=PromptType.TASK_VALIDATION,
            required_params=["base_input", "superset_input"]
        )
        
        # 信息泄露检查模板
        templates["check_information_leakage"] = PromptTemplate(
            name="check_information_leakage",
            template="""你是一个信息安全专家。请检查任务问题是否泄露了答案信息。

任务问题：
{question}

预期答案：
{answer}

泄露检查维度：
1. 问题中是否直接包含答案？
2. 问题中是否包含强烈暗示答案的线索？
3. 问题描述是否过于具体，导致答案显而易见？
4. 问题格式是否暴露了答案的结构？

泄露类型分析：
- 直接泄露：答案明确出现在问题中
- 间接泄露：通过暗示或线索可以推出答案
- 结构泄露：问题格式暴露答案特征
- 上下文泄露：结合背景信息可得出答案

请以JSON格式返回检查结果：
{{
    "has_leakage": true|false,
    "leakage_type": "直接|间接|结构|上下文|无",
    "leakage_details": "具体泄露内容描述",
    "severity": "严重|中等|轻微|无",
    "improvement_suggestions": ["改进建议1", "改进建议2"],
    "revised_question": "修正后的问题（如有泄露）"
}}""",
            description="检查问题是否泄露答案信息",
            prompt_type=PromptType.TASK_VALIDATION,
            required_params=["question", "answer"]
        )
        
        # 任务质量综合评估模板
        templates["comprehensive_quality_assessment"] = PromptTemplate(
            name="comprehensive_quality_assessment",
            template="""你是一个任务质量评估专家。请对以下任务进行全面的质量评估。

任务信息：
问题: {question}
答案: {answer}
类型: {task_type}
领域: {domain}

评估维度：
1. 可执行性 (0-1)：任务是否可以被AI Agent执行
2. 难度适中性 (0-1)：任务难度是否合适
3. 答案唯一性 (0-1)：答案是否明确唯一
4. 工具需求合理性 (0-1)：工具选择是否合理
5. 语言质量 (0-1)：问题表述是否清晰
6. 认知复杂度 (0-1)：思维复杂度是否合适
7. 教学价值 (0-1)：是否具有学习价值

质量标准：
- 优秀 (0.8-1.0)：高质量任务，可直接使用
- 良好 (0.6-0.8)：较好任务，可能需要小幅调整
- 一般 (0.4-0.6)：需要改进的任务
- 较差 (0.2-0.4)：存在明显问题的任务
- 很差 (0.0-0.2)：不可用的任务

请以JSON格式返回评估结果：
{{
    "overall_score": 0.85,
    "dimension_scores": {{
        "executability": 0.9,
        "difficulty": 0.8,
        "answer_uniqueness": 0.9,
        "tool_requirements": 0.8,
        "language_quality": 0.9,
        "cognitive_complexity": 0.7,
        "educational_value": 0.8
    }},
    "quality_level": "优秀|良好|一般|较差|很差",
    "strengths": ["优点1", "优点2"],
    "weaknesses": ["不足1", "不足2"],
    "improvement_recommendations": ["建议1", "建议2"],
    "pass_threshold": 0.6,
    "recommendation": "通过|修改后通过|重新设计"
}}""",
            description="综合评估任务质量",
            prompt_type=PromptType.TASK_VALIDATION,
            required_params=["question", "answer", "task_type", "domain"]
        )
        
        return templates
    
    def get_templates(self) -> Dict[str, PromptTemplate]:
        """返回所有模板"""
        return self._templates
    
    def get_module_info(self) -> Dict[str, Any]:
        """返回模块信息"""
        return {
            "name": "TaskValidationPrompts",
            "description": "任务验证相关的 Prompt 模板集合",
            "version": "1.0",
            "template_count": len(self._templates),
            "categories": [
                "工具必要性检查",
                "推理充分性验证",
                "原子性检查",
                "超集关系验证",
                "信息泄露检查",
                "综合质量评估"
            ]
        }