#!/usr/bin/env python3
"""
增强的任务扩展算法
实现真正的深度扩展和宽度扩展，提升综合任务的复杂度和实用性
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
import uuid
from datetime import datetime

from .interfaces import AtomicTask, DepthExtendedTask, WidthExtendedTask, SynthesisInput, SynthesisRelation, TaskComplexity, TaskType

logger = logging.getLogger(__name__)

class EnhancedTaskExtensions:
    """增强的任务扩展算法"""
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.complexity_thresholds = {
            "simple": 1,
            "moderate": 3, 
            "complex": 6,
            "comprehensive": 10
        }
    
    async def generate_enhanced_depth_extensions(self, atomic_tasks: List[AtomicTask], max_extensions: int = 5) -> List[DepthExtendedTask]:
        """生成增强的深度扩展任务"""
        logger.info(f"🚀 开始生成增强深度扩展任务，原子任务数量: {len(atomic_tasks)}")
        
        depth_tasks = []
        
        # 按复杂度和工具需求筛选适合扩展的任务
        suitable_tasks = self._select_suitable_tasks_for_depth(atomic_tasks)
        
        for task in suitable_tasks[:max_extensions]:
            try:
                # 使用LLM生成真正的深度扩展
                if self.llm_client:
                    enhanced_task = await self._generate_llm_depth_extension(task)
                else:
                    enhanced_task = await self._generate_enhanced_depth_extension_fallback(task)
                
                if enhanced_task:
                    depth_tasks.append(enhanced_task)
                    logger.info(f"✅ 生成深度扩展任务: {enhanced_task.task_id}")
                    
            except Exception as e:
                logger.error(f"❌ 深度扩展失败 {task.task_id}: {e}")
                continue
        
        logger.info(f"📈 完成深度扩展生成: {len(depth_tasks)} 个增强任务")
        return depth_tasks
    
    async def generate_enhanced_width_extensions(self, atomic_tasks: List[AtomicTask], max_extensions: int = 3) -> List[WidthExtendedTask]:
        """生成增强的宽度扩展任务"""
        logger.info(f"🚀 开始生成增强宽度扩展任务，原子任务数量: {len(atomic_tasks)}")
        
        width_tasks = []
        
        # 智能任务分组和协同分析
        task_clusters = self._perform_intelligent_task_clustering(atomic_tasks)
        
        for cluster_id, cluster_tasks in task_clusters.items():
            if len(width_tasks) >= max_extensions:
                break
                
            if len(cluster_tasks) >= 2:
                try:
                    # 使用LLM生成协同扩展任务
                    if self.llm_client:
                        enhanced_task = await self._generate_llm_width_extension(cluster_tasks)
                    else:
                        enhanced_task = await self._generate_enhanced_width_extension_fallback(cluster_tasks)
                    
                    if enhanced_task:
                        width_tasks.append(enhanced_task)
                        logger.info(f"✅ 生成宽度扩展任务: {enhanced_task.task_id}")
                        
                except Exception as e:
                    logger.error(f"❌ 宽度扩展失败 cluster {cluster_id}: {e}")
                    continue
        
        logger.info(f"📊 完成宽度扩展生成: {len(width_tasks)} 个协同任务")
        return width_tasks
    
    def _select_suitable_tasks_for_depth(self, atomic_tasks: List[AtomicTask]) -> List[AtomicTask]:
        """选择适合深度扩展的原子任务"""
        suitable_tasks = []
        
        for task in atomic_tasks:
            # 评估任务的扩展潜力
            expansion_score = self._calculate_expansion_potential(task)
            
            if expansion_score >= 3:  # 设定阈值
                suitable_tasks.append(task)
        
        # 按扩展潜力排序
        suitable_tasks.sort(key=self._calculate_expansion_potential, reverse=True)
        return suitable_tasks
    
    def _calculate_expansion_potential(self, task: AtomicTask) -> int:
        """计算任务的扩展潜力"""
        score = 0
        
        # 工具需求加分
        if task.requires_tool:
            score += 2
        
        # 多工具加分
        if hasattr(task, 'expected_tools') and len(task.expected_tools) > 1:
            score += 3
        
        # 复杂领域加分
        complex_domains = ["科学研究", "金融", "软件开发", "数据分析"]
        if task.domain in complex_domains:
            score += 2
        
        # 问题长度加分（更详细的问题通常有更大扩展空间）
        if len(task.question) > 30:
            score += 1
        
        return score
    
    def _perform_intelligent_task_clustering(self, atomic_tasks: List[AtomicTask]) -> Dict[str, List[AtomicTask]]:
        """智能任务聚类，发现协同机会"""
        clusters = {}
        
        # 基于多维度进行聚类
        domain_clusters = self._cluster_by_domain(atomic_tasks)
        tool_clusters = self._cluster_by_tools(atomic_tasks)
        semantic_clusters = self._cluster_by_semantic_similarity(atomic_tasks)
        
        # 合并聚类结果，优先考虑跨工具协同
        cluster_id = 0
        for domain, tasks in domain_clusters.items():
            if len(tasks) >= 2:
                # 检查是否有跨工具的协同机会
                tools_in_cluster = set()
                for task in tasks:
                    if hasattr(task, 'expected_tools'):
                        tools_in_cluster.update(task.expected_tools)
                
                # 如果有多种工具，这是很好的协同机会
                if len(tools_in_cluster) >= 2:
                    clusters[f"cross_tool_{cluster_id}"] = tasks[:3]  # 限制为3个任务
                    cluster_id += 1
                elif len(tasks) >= 3:  # 同域任务也可以形成协同
                    clusters[f"domain_{domain}"] = tasks[:2]
        
        return clusters
    
    def _cluster_by_domain(self, tasks: List[AtomicTask]) -> Dict[str, List[AtomicTask]]:
        """按领域聚类"""
        domain_groups = {}
        for task in tasks:
            domain = task.domain
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(task)
        return domain_groups
    
    def _cluster_by_tools(self, tasks: List[AtomicTask]) -> Dict[str, List[AtomicTask]]:
        """按工具需求聚类"""
        tool_groups = {}
        for task in tasks:
            if hasattr(task, 'expected_tools') and task.expected_tools:
                tool_key = "_".join(sorted(task.expected_tools[:2]))  # 取前两个工具
                if tool_key not in tool_groups:
                    tool_groups[tool_key] = []
                tool_groups[tool_key].append(task)
        return tool_groups
    
    def _cluster_by_semantic_similarity(self, tasks: List[AtomicTask]) -> Dict[str, List[AtomicTask]]:
        """基于语义相似性聚类（简化实现）"""
        # 简化的语义聚类：基于关键词
        keyword_groups = {}
        
        for task in tasks:
            question_words = set(task.question.lower().split())
            
            # 寻找相似任务
            for key, group in keyword_groups.items():
                if self._calculate_word_overlap(question_words, key) > 0.3:
                    group.append(task)
                    break
            else:
                # 创建新组
                keyword_groups[frozenset(question_words)] = [task]
        
        # 转换为字符串键
        return {f"semantic_{i}": tasks for i, tasks in enumerate(keyword_groups.values()) if len(tasks) > 1}
    
    def _calculate_word_overlap(self, words1: set, words2: frozenset) -> float:
        """计算词汇重叠度"""
        if not words1 or not words2:
            return 0.0
        return len(words1.intersection(words2)) / len(words1.union(words2))
    
    async def _generate_llm_depth_extension(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """使用LLM生成深度扩展任务"""
        prompt = self._create_depth_extension_prompt(task)
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages, timeout=60)
            
            if response and isinstance(response, str):
                # 解析LLM响应
                extension_data = self._parse_llm_depth_response(response)
                
                if extension_data:
                    return self._create_depth_extended_task(task, extension_data)
            
        except Exception as e:
            logger.error(f"LLM深度扩展失败: {e}")
        
        return None
    
    async def _generate_llm_width_extension(self, tasks: List[AtomicTask]) -> Optional[WidthExtendedTask]:
        """使用LLM生成宽度扩展任务"""
        prompt = self._create_width_extension_prompt(tasks)
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages, timeout=60)
            
            if response and isinstance(response, str):
                # 解析LLM响应
                extension_data = self._parse_llm_width_response(response)
                
                if extension_data:
                    return self._create_width_extended_task(tasks, extension_data)
            
        except Exception as e:
            logger.error(f"LLM宽度扩展失败: {e}")
        
        return None
    
    def _create_depth_extension_prompt(self, task: AtomicTask) -> str:
        """创建深度扩展的few-shot prompt"""
        
        few_shot_examples = """
示例1 - 简单搜索任务的深度扩展:
原子任务: "搜索特斯拉公司最新股价"
深度扩展: "请综合分析特斯拉公司的投资价值：1) 搜索并获取特斯拉最新股价和财务数据，2) 分析其相对于同行业(如比亚迪、蔚来)的估值水平，3) 基于技术指标(移动平均线、RSI)判断当前股价趋势，4) 结合最新财报和行业新闻，评估未来3-6个月的投资风险和机会，5) 生成包含数据图表和投资建议的综合分析报告"

示例2 - 代码任务的深度扩展:
原子任务: "编写冒泡排序算法"
深度扩展: "请设计一个完整的排序算法比较系统：1) 实现多种排序算法(冒泡、快速、归并、堆排序)，2) 设计性能测试框架，对不同规模数据集(100, 1000, 10000元素)进行基准测试，3) 分析各算法的时间复杂度和空间复杂度，4) 可视化性能对比结果，5) 基于测试结果推荐不同场景下的最优排序策略，6) 生成技术文档说明算法选择的决策逻辑"

示例3 - 学术搜索的深度扩展:
原子任务: "搜索量子计算在机器学习中的应用"
深度扩展: "请进行量子机器学习领域的深度研究分析：1) 系统搜索2022-2024年该领域的顶级会议论文(ICML, NeurIPS, ICLR)，2) 识别并分析3-5个核心技术突破，3) 比较IBM、Google、微软等公司的技术路线差异，4) 评估当前技术的实用化程度和商业前景，5) 预测未来2-3年的发展趋势，6) 生成包含技术图谱、公司竞争分析和趋势预测的研究报告"
"""
        
        return f"""你是任务复杂化专家。请对给定的原子任务进行深度扩展，创建真正有挑战性的综合任务。

深度扩展原则:
1. **多步骤推理**: 将单一任务扩展为需要3-6个步骤的任务链
2. **工具协同**: 结合多种工具(搜索、代码执行、数据分析、可视化)
3. **领域深化**: 从表面查询深入到专业分析
4. **实用价值**: 生成的任务应该有实际应用价值
5. **逻辑连贯**: 各步骤之间有清晰的逻辑关系

{few_shot_examples}

现在请对以下原子任务进行深度扩展:

原子任务信息:
- 问题: {task.question}
- 领域: {task.domain}
- 当前工具: {getattr(task, 'expected_tools', ['通用工具'])}
- 答案示例: {task.answer.answer}

请生成深度扩展任务，要求:
1. 包含原子任务的核心需求
2. 扩展为包含4-6个逻辑步骤的综合任务
3. 整合多种工具和分析方法
4. 最终产出应该是有价值的分析报告或解决方案

请以JSON格式返回:
{{
    "extended_question": "完整的深度扩展问题描述",
    "extended_answer": "预期的综合答案描述", 
    "reasoning_steps": [
        {{"step": 1, "description": "步骤描述", "tools": ["所需工具"], "output": "步骤输出"}},
        ...
    ],
    "complexity_level": "comprehensive",
    "added_value": "相比原子任务增加的价值"
}}"""

    def _create_width_extension_prompt(self, tasks: List[AtomicTask]) -> str:
        """创建宽度扩展的few-shot prompt"""
        
        few_shot_examples = """
示例1 - 跨工具协同任务:
原子任务组合: ["搜索苹果公司股价", "分析股票技术指标"]
协同扩展: "请构建苹果公司投资决策支持系统：1) 搜索苹果公司最新股价、财报和新闻，2) 下载历史股价数据并计算技术指标(RSI、MACD、布林带)，3) 分析市场情绪和分析师评级，4) 整合基本面和技术面分析，生成投资评级和价格目标，5) 创建交互式Dashboard展示分析结果和风险提示"

示例2 - 学术研究协同:
原子任务组合: ["搜索AI论文", "分析代码实现"]
协同扩展: "请建立AI技术趋势分析平台：1) 搜索顶级AI会议的最新论文，2) 分析热点技术的代码实现和性能指标，3) 构建技术关系图谱，识别技术演进路径，4) 对比不同技术方案的优劣势，5) 预测未来6个月的技术热点，6) 生成面向技术决策者的趋势分析报告"

示例3 - 教育信息协同:
原子任务组合: ["搜索大学信息", "查询专业设置"]  
协同扩展: "请开发个性化留学申请策略系统：1) 搜索目标国家和地区的顶级大学信息，2) 分析各校专业设置、录取要求和就业数据，3) 根据学生背景匹配最适合的学校和专业，4) 分析申请时间线和准备要求，5) 计算申请成功概率和预期ROI，6) 生成包含学校对比、申请策略和时间规划的个性化留学方案"
"""
        
        tasks_info = []
        for i, task in enumerate(tasks):
            tasks_info.append(f"任务{i+1}: {task.question} (领域: {task.domain}, 工具: {getattr(task, 'expected_tools', ['通用'])})")
        
        return f"""你是任务协同专家。请将给定的多个原子任务整合为一个高价值的协同任务。

协同扩展原则:
1. **工具协同**: 充分利用不同任务所需的各种工具
2. **信息流转**: 前一步的输出成为后续步骤的输入
3. **价值倍增**: 整合后的价值远超各任务的简单相加
4. **决策支持**: 最终产出应支持实际决策
5. **系统性思维**: 构建完整的解决方案而非碎片化操作

{few_shot_examples}

现在请对以下原子任务进行协同扩展:

原子任务列表:
{chr(10).join(tasks_info)}

请生成协同扩展任务，要求:
1. 将所有原子任务的核心价值整合到一个系统性方案中
2. 设计清晰的信息流转和协同逻辑
3. 最终产出应该是决策支持系统或完整解决方案
4. 体现"1+1>2"的协同效应

请以JSON格式返回:
{{
    "synergy_question": "协同任务的完整描述",
    "synergy_answer": "预期的系统性解决方案描述",
    "workflow_steps": [
        {{"step": 1, "description": "步骤描述", "input_from": "数据来源", "output_to": "输出给谁", "tools": ["所需工具"]}},
        ...
    ],
    "synergy_value": "相比独立任务的协同价值",
    "decision_support": "如何支持实际决策"
}}"""

    def _parse_llm_depth_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM深度扩展响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"解析深度扩展响应失败: {e}")
        return None
    
    def _parse_llm_width_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM宽度扩展响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"解析宽度扩展响应失败: {e}")
        return None
    
    def _create_depth_extended_task(self, base_task: AtomicTask, extension_data: Dict[str, Any]) -> DepthExtendedTask:
        """创建深度扩展任务对象"""
        task_id = f"enhanced_depth_{uuid.uuid4().hex[:8]}"
        
        # 创建超集输入
        superset_input = SynthesisInput(
            input_id=f"enhanced_superset_{base_task.task_id}",
            content=extension_data.get("extended_question", base_task.question),
            metadata={"enhancement_type": "llm_depth_extension", "steps": len(extension_data.get("reasoning_steps", []))}
        )
        
        # 创建超集关系
        superset_relation = SynthesisRelation(
            relation_id=f"enhanced_relation_{base_task.task_id}",
            relation_type="enhanced_depth_extension",
            description=extension_data.get("added_value", "LLM增强的深度扩展"),
            parameters={"complexity_level": extension_data.get("complexity_level", "comprehensive")}
        )
        
        # 创建中间任务（基于推理步骤）
        reasoning_steps = extension_data.get("reasoning_steps", [])
        intermediate_question = reasoning_steps[0]["description"] if reasoning_steps else f"准备执行：{base_task.question}"
        
        intermediate_task = AtomicTask(
            task_id=f"enhanced_intermediate_{uuid.uuid4().hex[:8]}",
            task_type=base_task.task_type,
            complexity=TaskComplexity.ATOMIC,
            input_info=superset_input,
            answer=base_task.answer,
            relation=superset_relation,
            question=intermediate_question,
            domain=base_task.domain,
            requires_tool=True,
            expected_tools=base_task.expected_tools if hasattr(base_task, 'expected_tools') else [],
            created_at=datetime.now(),
            source_trajectory_id=None
        )
        
        # 创建深度扩展任务
        return DepthExtendedTask(
            task_id=task_id,
            complexity=TaskComplexity.DEPTH,
            base_task=base_task,
            intermediate_task=intermediate_task,
            superset_input=superset_input,
            superset_relation=superset_relation,
            combined_question=extension_data.get("extended_question", base_task.question),
            combined_answer=extension_data.get("extended_answer", base_task.answer.answer),
            created_at=datetime.now()
        )
    
    def _create_width_extended_task(self, component_tasks: List[AtomicTask], extension_data: Dict[str, Any]) -> WidthExtendedTask:
        """创建宽度扩展任务对象"""
        task_id = f"enhanced_width_{uuid.uuid4().hex[:8]}"
        
        return WidthExtendedTask(
            task_id=task_id,
            complexity=TaskComplexity.WIDTH,
            component_tasks=component_tasks,
            merged_question=extension_data.get("synergy_question", "协同任务"),
            merged_answer=extension_data.get("synergy_answer", "协同解决方案"),
            merge_strategy="enhanced_synergy",
            created_at=datetime.now()
        )
    
    async def _generate_enhanced_depth_extension_fallback(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """增强深度扩展的回退实现（无LLM）"""
        # 基于任务特征的规则化扩展
        enhancement_strategies = {
            "搜索": self._enhance_search_task,
            "代码": self._enhance_code_task,
            "分析": self._enhance_analysis_task,
            "查询": self._enhance_query_task
        }
        
        # 识别任务类型
        task_type = self._identify_task_category(task)
        
        if task_type in enhancement_strategies:
            return await enhancement_strategies[task_type](task)
        
        return None
    
    async def _generate_enhanced_width_extension_fallback(self, tasks: List[AtomicTask]) -> Optional[WidthExtendedTask]:
        """增强宽度扩展的回退实现（无LLM）"""
        # 基于任务组合的规则化协同
        if len(tasks) < 2:
            return None
        
        # 分析任务组合类型
        combination_type = self._analyze_task_combination(tasks)
        
        # 生成协同任务
        synergy_data = self._generate_synergy_by_type(tasks, combination_type)
        
        if synergy_data:
            return self._create_width_extended_task(tasks, synergy_data)
        
        return None
    
    def _identify_task_category(self, task: AtomicTask) -> str:
        """识别任务类别"""
        question_lower = task.question.lower()
        
        if any(keyword in question_lower for keyword in ["搜索", "查找", "search"]):
            return "搜索"
        elif any(keyword in question_lower for keyword in ["代码", "编写", "实现", "code"]):
            return "代码"
        elif any(keyword in question_lower for keyword in ["分析", "计算", "评估"]):
            return "分析"
        elif any(keyword in question_lower for keyword in ["查询", "获取", "下载"]):
            return "查询"
        else:
            return "通用"
    
    def _analyze_task_combination(self, tasks: List[AtomicTask]) -> str:
        """分析任务组合类型"""
        domains = [task.domain for task in tasks]
        tools = []
        for task in tasks:
            if hasattr(task, 'expected_tools'):
                tools.extend(task.expected_tools)
        
        if len(set(domains)) > 1:
            return "跨领域协同"
        elif len(set(tools)) > 1:
            return "跨工具协同"
        elif "金融" in domains:
            return "金融分析系统"
        elif "教育" in domains:
            return "教育决策系统"
        else:
            return "领域深化"
    
    async def _enhance_search_task(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """增强搜索类任务"""
        base_content = task.question
        
        enhanced_question = f"""请构建基于"{base_content}"的深度研究分析系统：
1) 执行多维度搜索，收集相关的最新信息、数据和观点
2) 对搜索结果进行分类整理和可信度评估
3) 识别信息中的关键趋势、模式和异常点
4) 进行比较分析，找出不同信息源之间的一致性和分歧
5) 综合分析结果，形成有洞察力的结论和预测
6) 生成包含数据支撑和可视化图表的专业研究报告"""
        
        enhanced_answer = f"基于'{base_content}'的多维度深度研究分析报告，包含趋势分析、比较研究和预测建议"
        
        extension_data = {
            "extended_question": enhanced_question,
            "extended_answer": enhanced_answer,
            "complexity_level": "comprehensive",
            "added_value": "从简单搜索升级为系统性研究分析"
        }
        
        return self._create_depth_extended_task(task, extension_data)
    
    async def _enhance_code_task(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """增强代码类任务"""
        base_content = task.question
        
        enhanced_question = f"""请设计完整的软件解决方案，基于"{base_content}"需求：
1) 分析需求并设计系统架构和模块划分
2) 实现核心算法和功能模块，包含错误处理和边界条件
3) 编写全面的单元测试和集成测试用例
4) 进行性能基准测试和优化分析
5) 生成技术文档，包含API说明和使用示例
6) 部署演示环境并提供完整的使用指南"""
        
        enhanced_answer = f"基于'{base_content}'的完整软件解决方案，包含代码实现、测试、文档和部署指南"
        
        extension_data = {
            "extended_question": enhanced_question,
            "extended_answer": enhanced_answer,
            "complexity_level": "comprehensive",
            "added_value": "从简单代码编写升级为完整软件解决方案"
        }
        
        return self._create_depth_extended_task(task, extension_data)
    
    async def _enhance_analysis_task(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """增强分析类任务"""
        base_content = task.question
        
        enhanced_question = f"""请建立基于"{base_content}"的综合分析决策系统：
1) 收集和准备相关数据，包含历史数据和实时数据
2) 应用多种分析方法(统计分析、机器学习、趋势分析)
3) 构建预测模型并验证模型的准确性和可靠性
4) 进行敏感性分析和风险评估
5) 生成可视化报告，包含关键指标和趋势图表
6) 提供基于分析结果的决策建议和行动方案"""
        
        enhanced_answer = f"基于'{base_content}'的综合分析决策系统，包含预测模型、风险评估和决策建议"
        
        extension_data = {
            "extended_question": enhanced_question,
            "extended_answer": enhanced_answer,
            "complexity_level": "comprehensive",
            "added_value": "从简单分析升级为综合决策支持系统"
        }
        
        return self._create_depth_extended_task(task, extension_data)
    
    async def _enhance_query_task(self, task: AtomicTask) -> Optional[DepthExtendedTask]:
        """增强查询类任务"""
        base_content = task.question
        
        enhanced_question = f"""请构建基于"{base_content}"的智能信息系统：
1) 执行多源数据查询和收集，确保数据的完整性和准确性
2) 建立数据质量检查和验证机制
3) 构建数据关联分析，发现隐藏的模式和关系
4) 实现自动化数据更新和监控机制
5) 设计用户友好的查询界面和可视化展示
6) 提供数据解读和洞察分析报告"""
        
        enhanced_answer = f"基于'{base_content}'的智能信息系统，包含数据收集、分析和可视化功能"
        
        extension_data = {
            "extended_question": enhanced_question,
            "extended_answer": enhanced_answer,
            "complexity_level": "comprehensive",
            "added_value": "从简单查询升级为智能信息系统"
        }
        
        return self._create_depth_extended_task(task, extension_data)
    
    def _generate_synergy_by_type(self, tasks: List[AtomicTask], combination_type: str) -> Optional[Dict[str, Any]]:
        """根据组合类型生成协同方案"""
        
        synergy_templates = {
            "跨领域协同": {
                "synergy_question": f"请构建跨领域综合分析平台，整合{', '.join([task.domain for task in tasks])}等多个领域的信息和分析能力，形成系统性的决策支持方案",
                "synergy_answer": "跨领域综合分析平台，提供系统性的决策支持和洞察分析",
                "synergy_value": "通过跨领域信息整合，提供更全面和准确的分析视角"
            },
            "跨工具协同": {
                "synergy_question": f"请设计多工具协同的自动化解决方案，整合搜索、分析、可视化等多种工具能力，实现端到端的问题解决流程",
                "synergy_answer": "多工具协同的自动化解决方案，实现端到端的问题解决",
                "synergy_value": "通过工具协同，实现自动化和高效的问题解决流程"
            },
            "金融分析系统": {
                "synergy_question": f"请构建智能投资决策系统，整合市场数据分析、风险评估、投资组合优化等功能，提供全面的投资决策支持",
                "synergy_answer": "智能投资决策系统，提供数据驱动的投资建议和风险管理",
                "synergy_value": "通过数据整合和模型分析，提升投资决策的科学性和准确性"
            },
            "教育决策系统": {
                "synergy_question": f"请开发个性化教育规划系统，整合院校信息、专业分析、就业数据等，为学生提供定制化的教育路径建议",
                "synergy_answer": "个性化教育规划系统，提供定制化的学习和职业发展建议",
                "synergy_value": "通过数据驱动分析，为教育选择提供科学依据和个性化建议"
            }
        }
        
        return synergy_templates.get(combination_type, synergy_templates["跨领域协同"])