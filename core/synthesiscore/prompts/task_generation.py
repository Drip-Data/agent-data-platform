#!/usr/bin/env python3
"""
任务生成相关的 Prompt 模板
包含原子任务生成、深度扩展、宽度扩展等相关模板
"""

from typing import Dict, Any
from .base import PromptTemplate, PromptModule, PromptType


class TaskGenerationPrompts(PromptModule):
    """任务生成 Prompt 模板集合"""
    
    def __init__(self):
        self._templates = self._initialize_templates()
    
    def _initialize_templates(self) -> Dict[str, PromptTemplate]:
        """初始化所有任务生成模板"""
        templates = {}
        
        # 深度结论提取模板（关系驱动）
        templates["extract_conclusions"] = PromptTemplate(
            name="extract_conclusions",
            template="""你是一个高级的知识工程师。请从以下轨迹数据中进行深度结论提取，重点分析实体间的结构化关系。

轨迹数据：
{trajectory_data}

**核心任务：不仅提取结论，更要深度挖掘结论中实体间的结构化关系**

请分析轨迹，提取出可以用于创造性任务生成的关键结论和关系。每个结论应该包含：
1. 结论内容（具体的知识点或解决方案）
2. 关键实体列表（参与关系的所有重要实体）
3. 结构化关系（实体间的深层逻辑联系）
4. 关系类型（标准化的关系分类）
5. 应用场景和难度等级

**高质量示例：**
📌 示例1：
- 结论: "BCA方法的参数比VeRA少14倍"
- 实体: ["BCA方法", "VeRA方法", "参数量", "14倍"]
- 关系: "方法A-参数量-对比-方法B-倍数关系"
- 关系类型: "quantitative_comparison"

📌 示例2：
- 结论: "苹果股价为150美元"
- 实体: ["苹果公司", "股价", "150美元", "当前时间"]
- 关系: "公司-财务属性-数值-时间点"
- 关系类型: "financial_attribute"

📌 示例3：
- 结论: "Transformer架构使用自注意力机制"
- 实体: ["Transformer", "自注意力机制", "架构设计"]
- 关系: "架构-核心技术-功能实现"
- 关系类型: "functional_component"

**关系类型参考清单：**
- quantitative_comparison: 数量对比（A比B多/少X倍）
- financial_attribute: 财务属性（公司-股价-数值）
- functional_component: 功能组件（系统-核心技术-作用）
- causal_relationship: 因果关系（原因-结果-条件）
- temporal_sequence: 时间序列（事件A-发生在-事件B之前）
- hierarchical_structure: 层次结构（父级-包含-子级）
- performance_metric: 性能指标（方法-指标-数值）
- technological_evolution: 技术演进（旧技术-改进为-新技术）

要求：
- 提取 {max_conclusions} 个最有价值的结论
- 关系描述要精准，体现实体间的深层逻辑联系
- 实体列表要完整，包含所有关键参与者
- 优先选择展示Agent核心推理能力的结论
- 确保关系类型分类准确
- 结论应该具有泛化潜力，便于实体替换

请以JSON格式返回结果：
{{
    "conclusions": [
        {{
            "content": "结论内容",
            "entities": ["实体1", "实体2", "实体3"],
            "relation": "实体间的关系描述",
            "relation_type": "关系类型",
            "scenario": "应用场景",
            "difficulty": "简单|中等|困难",
            "required_tools": ["工具1", "工具2"],
            "generalization_potential": "泛化潜力描述",
            "confidence": 0.95
        }}
    ]
}}""",
            description="从轨迹数据中提取关键结论和结构化关系",
            prompt_type=PromptType.CONCLUSION_EXTRACTION,
            required_params=["trajectory_data"],
            optional_params={"max_conclusions": 5}
        )
        
        # 关系驱动的原子任务生成模板
        templates["generate_atomic_tasks"] = PromptTemplate(
            name="generate_atomic_tasks",
            template="""你是一个创造性任务设计师。请基于以下结论和结构化关系，通过关系驱动的反向推理生成具有创造性的原子任务。

结论和关系：
{conclusion}

**🎯 核心使命：不是复述结论，而是基于关系创造新问题**

**🧠 关系驱动的问题生成策略：**
1. **关系模式提取**：从结论中识别出实体间的关系模式
2. **实体泛化替换**：将具体实体替换为同类型的其他实体
3. **反向推理设计**：基于关系，设计需要推理才能得到答案的问题
4. **创造性扩展**：在保持关系结构的前提下，创造全新的问题情境

**💡 生成示例演示：**

📌 输入示例1：
- 结论: "苹果股价为150美元"
- 实体: ["苹果公司", "股价", "150美元"]
- 关系: "公司-财务属性-数值"
- 关系类型: "financial_attribute"

📌 原子性输出示例1：
- 问题: "请搜索谷歌公司当前的股价。" ✅ 单一动作
- 关系应用: "公司-财务属性-数值"（实体替换：苹果→谷歌）
- 原子性检查: 单一动作"搜索"，无连接词 ✅
- 创造性: ★★★（需要搜索工具，实时查询）

📌 输入示例2：
- 结论: "BCA方法的参数比VeRA少14倍"
- 实体: ["BCA方法", "VeRA方法", "参数量"]
- 关系: "方法A-参数量-对比-方法B"
- 关系类型: "quantitative_comparison"

📌 原子性输出示例2：
- 问题: "请查询LoRA方法的最新参数量。" ✅ 单一动作
- 关系应用: "方法A-参数量-对比-方法B"（实体替换：BCA/VeRA→LoRA）
- 原子性检查: 单一动作"查询"，无连接词 ✅
- 创造性: ★★★★（需要文献搜索）

📌 输入示例3：
- 结论: "Transformer使用自注意力机制"
- 实体: ["Transformer", "自注意力机制"]
- 关系: "架构-核心技术"
- 关系类型: "functional_component"

📌 原子性输出示例3：
- 问题: "请获取ResNet架构的核心创新描述。" ✅ 单一动作
- 关系应用: "架构-核心技术"（实体替换：Transformer→ResNet）
- 原子性检查: 单一动作"获取"，无连接词 ✅
- 创造性: ★★★★★（需要技术文档搜索）

**❌ 错误示例（绝对禁止）：**
- "请搜索并比较谷歌和苹果的股价" ❌ （包含"并且"）
- "请查询LoRA方法参数量，然后进行对比" ❌ （包含"然后"）
- "请获取ResNet描述以及其优势分析" ❌ （包含"以及"）

**🎨 创造性要求等级（1-5星）：**
- ★：轻微变化（简单实体替换）
- ★★：中等变化（不同领域实体替换）
- ★★★：显著创新（需要多步推理）
- ★★★★：高度创新（跨域知识整合）
- ★★★★★：完全创新（复杂推理链条）

请生成最多{max_tasks}个原子任务，以JSON格式返回：
{{
    "atomic_tasks": [
        {{
            "question": "任务问题描述",
            "expected_answer": "预期答案类型描述",
            "task_type": "tool_required",
            "domain": "任务领域",
            "difficulty": "简单|中等|困难",
            "required_tools": ["工具名1", "工具名2"],
            "reasoning_steps": ["推理步骤1", "推理步骤2"],
            "relation_pattern": "应用的关系模式",
            "entity_generalization": "实体泛化说明",
            "creativity_level": "1-5",
            "creativity_explanation": "创造性体现说明",
            "reverse_reasoning": "反向推理过程描述"
        }}
    ]
}}

**🔥 原子性生成要求（严格执行）：**
1. **绝对原子性**：每个任务只能包含ONE个动作词，绝对禁止"并且"、"然后"、"接着"、"同时"、"以及"等连接词
2. **单一动作验证**：检查任务描述，必须只包含一个明确的动作，如：
   - ✅ 正确："请搜索谷歌公司当前的股价"
   - ❌ 错误："请搜索并比较谷歌和苹果的股价"
   - ❌ 错误："请查询并计算最新的数据"
   - ❌ 错误："请获取和分析相关信息"
3. **必须需要工具**：所有任务都必须标记为tool_required，需要Agent通过工具使用才能回答
4. **明确单一工具调用**：问题必须使用一个明确的动作词："搜索"、"查询"、"获取"、"下载"、"计算"
5. **要求实时信息**：任务必须明确需要获取"最新"、"当前"、"实时"信息，而非理论分析
6. **单一输出目标**：每个任务只能有一个明确的、可验证的输出目标
7. **避免概念性任务**：不要生成"请设计"、"请分析"等概念性任务，要生成"请搜索"、"请计算"等具体操作任务
8. **创造性等级≥3星**：确保足够的创新性和挑战性

**🚨 原子性检查清单：**
- [ ] 任务描述中是否只包含一个动作词？
- [ ] 是否完全避免了"并且"、"然后"、"接着"、"同时"、"以及"等连接词？
- [ ] 任务是否只需要一种工具来完成？
- [ ] 任务是否只有一个明确的输出结果？""",
            description="基于关系驱动的反向推理生成创造性原子任务",
            prompt_type=PromptType.TASK_GENERATION,
            required_params=["conclusion"],
            optional_params={"max_tasks": 3}
        )
        
        # 深度扩展模板
        templates["generate_depth_extension"] = PromptTemplate(
            name="generate_depth_extension",
            template="""你是一个任务扩展专家。请对以下原子任务进行深度扩展，创建更复杂的任务链。

原子任务：
问题: {base_question}
答案: {base_answer}
类型: {task_type}
领域: {domain}

深度扩展策略：
1. 寻找该任务的"超集"场景（包含原任务但更复杂）
2. 创建需要多步推理的任务
3. 添加前置条件或中间步骤
4. 保持逻辑连贯性

扩展要求：
- 生成的任务应该比原任务更复杂
- 包含原任务的核心要求
- 需要额外的推理或工具调用
- 答案应该综合考虑所有步骤

请以JSON格式返回：
{{
    "depth_extended_task": {{
        "combined_question": "扩展后的复合问题",
        "combined_answer": "综合答案",
        "superset_input": "超集输入描述",
        "intermediate_steps": [
            {{
                "step": 1,
                "description": "中间步骤描述",
                "expected_output": "步骤输出"
            }}
        ],
        "complexity_increase": "复杂度提升说明"
    }}
}}""",
            description="对原子任务进行深度扩展",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["base_question", "base_answer", "task_type", "domain"]
        )
        
        # 宽度扩展模板
        templates["generate_width_extension"] = PromptTemplate(
            name="generate_width_extension",
            template="""你是一个任务合并专家。请将以下多个相关的原子任务合并成一个综合任务。

原子任务列表：
{atomic_tasks_list}

宽度扩展策略：
1. 找出任务间的关联性和互补性
2. 设计合理的任务执行顺序
3. 确保任务组合有意义
4. 创建统一的问题描述

合并要求：
- 保持所有原子任务的核心要求
- 任务间应有逻辑关联
- 综合答案应涵盖所有子任务
- 避免简单的任务堆叠

请以JSON格式返回：
{{
    "width_extended_task": {{
        "merged_question": "合并后的综合问题",
        "merged_answer": "综合答案",
        "task_flow": [
            {{
                "step": 1,
                "original_task_id": "对应的原子任务ID",
                "description": "在综合任务中的角色"
            }}
        ],
        "merge_strategy": "合并策略说明",
        "synergy_explanation": "任务协同效应说明"
    }}
}}""",
            description="将多个原子任务合并成综合任务",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["atomic_tasks_list"]
        )
        
        # 任务优化模板
        templates["optimize_task"] = PromptTemplate(
            name="optimize_task",
            template="""你是一个任务优化专家。请对以下任务进行优化，提高其质量和实用性。

原始任务：
问题: {original_question}
答案: {original_answer}
类型: {task_type}

优化目标：
1. 提高问题的清晰度和具体性
2. 确保答案的准确性和完整性
3. 优化任务的教学价值
4. 改善任务的可执行性

优化要求：
- 保持任务的核心目标不变
- 提高问题描述的精确性
- 确保答案的可验证性
- 增强任务的实用价值

请以JSON格式返回：
{{
    "optimized_task": {{
        "improved_question": "优化后的问题",
        "improved_answer": "优化后的答案",
        "optimization_notes": "优化说明",
        "quality_score": 0.95,
        "improvements": [
            "改进点1：具体说明",
            "改进点2：具体说明"
        ]
    }}
}}""",
            description="优化任务质量",
            prompt_type=PromptType.TASK_GENERATION,
            required_params=["original_question", "original_answer", "task_type"]
        )
        
        # 反向搜索模板（深度扩展阶段1）
        templates["backward_search"] = PromptTemplate(
            name="backward_search",
            template="""你是一个知识架构师和研究专家。请采用反向推理的方式，为以下已知事实找到其更宏观的背景知识。

已知事实(A)：{known_fact}

**🔍 反向推理任务：**
请你扮演一个研究员，思考一下：
1. 要知道这个事实'{known_fact}'，你需要先知道哪个更宏观的背景知识(B)？
2. B和A之间的逻辑关系(R)是什么？
3. 为什么B是A的必要前提或背景信息？

**💡 反向推理的高质量示例：**

📌 示例1：
- A: "BCA方法的参数比VeRA少14倍"
- B: "一篇名为'Block Circulant Adapter for Large Language Models'的研究论文"
- R: "B中详细描述了BCA和VeRA两种方法的参数量对比结果，并给出了A中提到的具体数据"

📌 示例2：
- A: "苹果公司当前股价为150美元"
- B: "苹果公司在纳斯达克股票交易所的实时股票行情数据"
- R: "B提供了苹果公司(AAPL)在特定时间点的实时交易数据，包含A中提到的股价信息"

📌 示例3：
- A: "Transformer使用自注意力机制"
- B: "Google发表的'Attention Is All You Need'论文"
- R: "B是首次提出Transformer架构的经典论文，其中详细介绍了A中提到的自注意力机制的工作原理和设计细节"

**🎯 反向推理要求：**
1. **宏观性**：B应该比A更宏观、更基础，是知道A的必要背景
2. **逻辑必然性**：从逻辑上讲，不知道B就无法得到A
3. **信息源性**：B应该是A的数据来源或知识来源
4. **可操作性**：B应该是可以通过工具或方法获取的
5. **相关性**：B和A应该在同一个领域或硕强相关的领域

请以JSON格式返回：
{{
    "backward_search_result": {{
        "background_knowledge": "B：更宏观的背景知识",
        "logical_relation": "R：B和A之间的逻辑关系描述",
        "reasoning_path": "A←R←B 的推理路径说明",
        "necessity_explanation": "为什么B是A的必要前提",
        "information_type": "背景知识的类型（论文/数据库/文档/系统等）",
        "access_method": "获取B的方法（搜索/查询/访问等）",
        "domain_relevance": "领域相关性说明",
        "confidence": 0.95
    }}
}}""",
            description="通过反向推理找到已知事实的背景知识",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["known_fact"]
        )
        
        # 任务融合模板（深度扩展阶段2）
        templates["task_fusion"] = PromptTemplate(
            name="task_fusion",
            template="""你是一个任务融合架构师。请将以下有逻辑依赖关系的任务融合成一个自然连贯的复杂问题。

**任务信息：**
- 背景知识任务(Q1): {background_task}
- 核心事实任务(Q2): {core_task}
- 逻辑关系(R): {logical_relation}

**🧠 融合指导原则：**
1. **逻辑连贯性**：Q1和Q2应该在逻辑上环环相扣，不可分割
2. **自然性**：融合后的问题应该读起来自然，不是简单的两个问题拼接
3. **复杂性提升**：融合后的任务应该比单独的Q1或Q2更复杂
4. **目标统一性**：整个问题应该有一个清晰的最终目标
5. **实用性**：融合后的任务应该模拟真实世界的问题解决流程

**💡 融合示例演示：**

📌 示例1：
- Q1: "请找到名为'Block Circulant Adapter for Large Language Models'的论文"
- Q2: "验证BCA方法的参数比VeRA少14倍"
- R: "Q1中的论文包含了Q2中需要验证的参数对比数据"
- 融合结果: "请找到名为'Block Circulant Adapter for Large Language Models'的论文，并根据其内容，告诉我BCA方法和VeRA的参数量对比结果是什么？"

📌 示例2：
- Q1: "获取苹果公司在纳斯达克的实时股票行情数据"
- Q2: "分析苹果公司当前股价是否达到150美元"
- R: "Q1提供的实时数据是Q2中股价分析的数据基础"
- 融合结果: "请查询苹果公司(AAPL)在纳斯达克的实时股价，并分析其当前的交易价格是否达到或超过150美元。"

📌 示例3：
- Q1: "查找'Attention Is All You Need'论文的具体内容"
- Q2: "分析Transformer架构中自注意力机制的工作原理"
- R: "Q1中的论文是Q2中自注意力机制的原始技术文档和理论基础"
- 融合结果: "请从'Attention Is All You Need'论文中提取关于自注意力机制的核心概念，并根据论文内容详细解释Transformer架构中自注意力机制的具体工作原理。"

**🎯 融合要求：**
1. **必须保持依赖关系**：融合后的任务必须体现Q1→Q2的逻辑依赖
2. **避免简单拼接**：不是“请做一，然后做二”，而是融合成一个有机整体
3. **目标导向**：最终问题应该以Q2的目标为主，Q1为手段
4. **可执行性**：融合后的任务应该可以被Agent执行
5. **复杂度适中**：不要过于复杂，但也不能过于简单

请以JSON格式返回：
{{
    "task_fusion_result": {{
        "fused_question": "融合后的统一问题",
        "fused_answer": "预期的综合答案",
        "logical_flow": "逻辑流程描述",
        "dependency_explanation": "Q1如何支撑Q2的说明",
        "complexity_analysis": "复杂度分析和提升说明",
        "execution_steps": [
            {{
                "step": 1,
                "description": "执行步骤描述",
                "purpose": "该步骤的作用",
                "output": "预期输出"
            }}
        ],
        "fusion_quality": "融合质量评估(1-5)",
        "practical_value": "实用价值说明"
    }}
}}""",
            description="将有逻辑依赖关系的任务融合成连贯的复杂问题",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["background_task", "core_task", "logical_relation"]
        )
        
        # 主题感知合并模板（宽度扩展）
        templates["theme_aware_fusion"] = PromptTemplate(
            name="theme_aware_fusion",
            template="""你是一个主题融合专家。请将以下多个主题高度相关的任务融合成一个单一的、更高层次的综合性问题。

主题相关任务：
{related_tasks}

**🎯 主题融合目标：从“罗列”升级为“综合”**

输入任务主题分析：{theme_analysis}

**🧠 智能融合策略：**
1. **主题提取**：识别所有任务的共同主题和关注点
2. **对比分析**：设计一个需要对比、分析多个方面的高层次问题
3. **综合判断**：生成需要综合多个任务结果才能得出结论的问题
4. **深度洞察**：设计需要深度理解和洞察的问题

**💡 融合示例演示：**

📌 示例1：
- 输入任务: [T1='分析Pandas特点', T2='分析NumPy特点']
- 主题: "Python数据处理库"
- 融合结果: "请对比分析Python中Pandas和NumPy这两个数据处理库的核心特点、应用场景和性能差异，并推荐在不同情况下的最佳选择。"

📌 示例2：
- 输入任务: [T1='分析GPT-4性能', T2='分析Claude-3性能', T3='分析Gemini性能']
- 主题: "大语言模型性能评估"
- 融合结果: "请综合评估GPT-4、Claude-3和Gemini三个主流大语言模型在推理能力、代码生成、知识问答和创意写作等方面的性能表现，并给出在不同使用场景下的选择建议。"

📌 示例3：
- 输入任务: [T1='分析苹果公司财务', T2='分析谷歌公司财务', T3='分析微软公司财务']
- 主题: "科技巨头财务对比"
- 融合结果: "请深度对比苹果、谷歌和微软三家科技巨头的财务状况，分析其在收入结构、盈利能力、现金流和投资回报等方面的差异，并预测其未来发展趋势。"

**🎯 融合要求：**
1. **不是简单罗列**：不能是“请做一，并做二”的格式
2. **需要综合分析**：必须通过对比、综合分析才能得出结论
3. **高层次结论**：生成的问题应该导向更高层次的洞察和结论
4. **实用价值**：融合后的问题应该有明确的实用价值
5. **适中复杂度**：既不过于简单，也不过于复杂

请以JSON格式返回：
{{
    "theme_fusion_result": {{
        "fused_question": "融合后的综合问题",
        "fused_answer": "预期的综合答案类型",
        "common_theme": "共同主题描述",
        "comparison_aspects": ["对比维度1", "对比维度2"],
        "synthesis_requirement": "需要综合分析的方面",
        "higher_level_insight": "预期的高层次洞察",
        "practical_application": "实际应用价值",
        "execution_approach": "执行方法建议",
        "fusion_quality": "1-5",
        "complexity_level": "复杂度等级评估"
    }}
}}""",
            description="将主题相关的多个任务融合成高层次的综合性问题",
            prompt_type=PromptType.TASK_SYNTHESIS,
            required_params=["related_tasks", "theme_analysis"]
        )
        
        return templates
    
    def get_templates(self) -> Dict[str, PromptTemplate]:
        """返回所有模板"""
        return self._templates
    
    def get_module_info(self) -> Dict[str, Any]:
        """返回模块信息"""
        return {
            "name": "TaskGenerationPrompts",
            "description": "任务生成相关的 Prompt 模板集合",
            "version": "1.0",
            "template_count": len(self._templates),
            "categories": [
                "深度结论提取（关系驱动）",
                "关系驱动的原子任务生成", 
                "深度扩展（原始）",
                "宽度扩展（原始）",
                "任务优化",
                "反向搜索（TaskCraft算法）",
                "任务融合（TaskCraft算法）",
                "主题感知合并（TaskCraft算法）"
            ]
        }