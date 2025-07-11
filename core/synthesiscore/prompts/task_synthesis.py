#!/usr/bin/env python3
"""
任务合成相关的 Prompt 模板
包含任务合并、策略优化、质量控制等
"""

from typing import Dict, Any
from .base import PromptTemplate, PromptModule, PromptType


class TaskSynthesisPrompts(PromptModule):
    """任务合成 Prompt 模板集合"""
    
    def __init__(self):
        self._templates = self._initialize_templates()
    
    def _initialize_templates(self) -> Dict[str, PromptTemplate]:
        """初始化所有任务合成模板"""
        templates = {}
        
        # 任务合并合理性检查模板
        templates["check_merge_reasonableness"] = PromptTemplate(
            name="check_merge_reasonableness",
            template="""你是一个任务设计专家。请判断以下任务合并是否合理和有效。

原始任务列表：
{component_questions}

合并后任务：
{merged_question}

合理性评估标准：
1. 逻辑连贯性：任务间是否有逻辑关联？
2. 目标一致性：合并后是否保持了所有原始目标？
3. 复杂度控制：合并是否增加了合理的复杂度？
4. 实用价值：合并后的任务是否比单独执行更有价值？
5. 可执行性：合并后的任务是否仍然可执行？

评估维度：
- 任务关联度：原始任务间的相关性
- 合并效果：是否产生了协同效应
- 执行效率：合并是否提高了执行效率
- 学习价值：是否增强了教学效果

请以JSON格式返回评估结果：
{{
    "is_reasonable": true|false,
    "logic_coherence": 0.9,
    "goal_preservation": 0.95,
    "complexity_control": 0.8,
    "practical_value": 0.85,
    "executability": 0.9,
    "overall_score": 0.88,
    "merge_benefits": ["收益1", "收益2"],
    "potential_issues": ["问题1", "问题2"],
    "improvement_suggestions": ["建议1", "建议2"]
}}""",
            description="检查任务合并的合理性",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["component_questions", "merged_question"]
        )
        
        # 答案组合验证模板
        templates["validate_answer_combination"] = PromptTemplate(
            name="validate_answer_combination",
            template="""你是一个答案质量检查专家。请验证合并答案是否正确整合了所有组件答案。

组件答案列表：
{component_answers}

合并答案：
{merged_answer}

验证标准：
1. 完整性：是否包含了所有组件答案的核心内容？
2. 一致性：答案间是否存在冲突或矛盾？
3. 逻辑性：合并后的答案是否逻辑清晰？
4. 准确性：合并过程是否保持了原始答案的准确性？
5. 增值性：合并是否产生了额外的价值？

组合策略分析：
- 并行组合：答案并列展示
- 串行组合：答案按顺序整合
- 层次组合：答案分层次展示
- 综合组合：答案深度融合

请以JSON格式返回验证结果：
{{
    "is_valid_combination": true|false,
    "completeness_score": 0.95,
    "consistency_score": 0.9,
    "logic_score": 0.88,
    "accuracy_score": 0.92,
    "value_added_score": 0.85,
    "combination_strategy": "并行|串行|层次|综合",
    "missing_elements": ["缺失元素1"],
    "conflicting_elements": ["冲突元素1"],
    "integration_quality": "优秀|良好|一般|较差"
}}""",
            description="验证答案组合的正确性",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["component_answers", "merged_answer"]
        )
        
        # 任务复杂度评估模板
        templates["assess_task_complexity"] = PromptTemplate(
            name="assess_task_complexity",
            template="""你是一个认知复杂度评估专家。请评估以下任务的复杂度水平。

任务描述：
{task_description}

复杂度维度：
1. 认知负荷：需要多少认知资源？
2. 步骤数量：需要多少个执行步骤？
3. 概念深度：涉及多深层次的概念？
4. 关联广度：涉及多少个知识领域？
5. 推理难度：需要多复杂的推理？

布鲁姆分类学层次：
- 记忆 (1分)：回忆基本信息
- 理解 (2分)：解释概念含义
- 应用 (3分)：在新情况中应用
- 分析 (4分)：分解和检查元素
- 评价 (5分)：判断和评估
- 创造 (6分)：组合创新解决方案

请以JSON格式返回评估结果：
{{
    "complexity_level": "简单|中等|复杂|非常复杂",
    "cognitive_load": 0.7,
    "step_count": 5,
    "concept_depth": "浅层|中层|深层",
    "knowledge_breadth": "单领域|跨领域|多领域",
    "reasoning_difficulty": "简单|中等|困难",
    "bloom_level": 4,
    "complexity_score": 0.75,
    "complexity_factors": ["因素1", "因素2"],
    "difficulty_justification": "复杂度判断理由"
}}""",
            description="评估任务的认知复杂度",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["task_description"]
        )
        
        # 任务相似度分析模板
        templates["analyze_task_similarity"] = PromptTemplate(
            name="analyze_task_similarity",
            template="""你是一个任务相似度分析专家。请分析以下任务间的相似度和关联性。

任务A：
{task_a}

任务B：
{task_b}

相似度分析维度：
1. 语义相似度：问题表述的相似程度
2. 目标相似度：要达成目标的相似程度
3. 方法相似度：解决方法的相似程度
4. 领域相似度：所属领域的相似程度
5. 难度相似度：复杂度的相似程度

关联类型：
- 同类任务：解决同一类问题
- 互补任务：可以相互补充
- 递进任务：有难度层次关系
- 并行任务：可以同时执行
- 无关任务：没有明显关联

请以JSON格式返回分析结果：
{{
    "overall_similarity": 0.75,
    "semantic_similarity": 0.8,
    "goal_similarity": 0.7,
    "method_similarity": 0.8,
    "domain_similarity": 0.9,
    "difficulty_similarity": 0.6,
    "relationship_type": "同类|互补|递进|并行|无关",
    "similarity_level": "高|中|低",
    "connection_points": ["连接点1", "连接点2"],
    "merge_potential": true|false,
    "merge_strategy": "合并策略建议"
}}""",
            description="分析任务间的相似度和关联性",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["task_a", "task_b"]
        )
        
        # 合成策略优化模板
        templates["optimize_synthesis_strategy"] = PromptTemplate(
            name="optimize_synthesis_strategy",
            template="""你是一个任务合成策略专家。请为以下任务合成场景提供最优策略。

合成场景：
原子任务数量: {atomic_task_count}
任务类型分布: {task_type_distribution}
难度分布: {difficulty_distribution}
领域分布: {domain_distribution}

合成目标：
目标任务数量: {target_task_count}
期望复杂度: {desired_complexity}
合成类型偏好: {synthesis_preference}

策略考虑因素：
1. 任务多样性：确保生成任务的多样性
2. 难度梯度：保持合理的难度分布
3. 质量控制：确保合成质量
4. 效率优化：提高合成效率
5. 实用价值：确保实际应用价值

请以JSON格式返回优化策略：
{{
    "recommended_strategy": {{
        "depth_extension_ratio": 0.4,
        "width_extension_ratio": 0.3,
        "direct_optimization_ratio": 0.3
    }},
    "priority_order": ["策略1", "策略2", "策略3"],
    "quality_thresholds": {{
        "minimum_score": 0.6,
        "target_score": 0.8
    }},
    "diversity_requirements": {{
        "domain_coverage": 0.8,
        "difficulty_spread": 0.7,
        "type_balance": 0.6
    }},
    "efficiency_optimizations": ["优化点1", "优化点2"],
    "risk_mitigation": ["风险控制措施1", "风险控制措施2"]
}}""",
            description="优化任务合成策略",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["atomic_task_count", "task_type_distribution", "difficulty_distribution", "domain_distribution"],
            optional_params={
                "target_task_count": 20,
                "desired_complexity": "中等",
                "synthesis_preference": "平衡"
            }
        )
        
        return templates
    
    def get_templates(self) -> Dict[str, PromptTemplate]:
        """返回所有模板"""
        return self._templates
    
    def get_module_info(self) -> Dict[str, Any]:
        """返回模块信息"""
        return {
            "name": "TaskSynthesisPrompts",
            "description": "任务合成相关的 Prompt 模板集合",
            "version": "1.0",
            "template_count": len(self._templates),
            "categories": [
                "任务合并合理性检查",
                "答案组合验证",
                "任务复杂度评估",
                "任务相似度分析",
                "合成策略优化"
            ]
        }