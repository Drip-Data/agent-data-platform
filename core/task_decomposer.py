#!/usr/bin/env python3
"""
🚀 Stage 3: 任务分解器 (Task Decomposer)
智能任务分解和执行协调模块
"""

import logging
import re
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度等级"""
    SIMPLE = "simple"          # 简单任务，1-2步完成
    MODERATE = "moderate"      # 中等任务，3-5步完成  
    COMPLEX = "complex"        # 复杂任务，6-10步完成
    VERY_COMPLEX = "very_complex"  # 极复杂任务，10+步完成


@dataclass
class TaskStep:
    """任务步骤定义"""
    step_id: str
    description: str
    action_type: str  # search, analyze, browse, execute等
    dependencies: List[str]  # 依赖的前置步骤
    expected_output: str
    priority: int = 1
    estimated_duration: float = 30.0  # 估计耗时（秒）


@dataclass
class DecompositionResult:
    """任务分解结果"""
    original_task: str
    complexity: TaskComplexity
    steps: List[TaskStep]
    execution_strategy: str  # sequential, parallel, hybrid
    estimated_total_duration: float
    success_criteria: List[str]


class TaskDecomposer:
    """
    🎯 智能任务分解器
    
    功能：
    1. 分析任务复杂度
    2. 智能分解为可执行步骤
    3. 生成执行策略
    4. 协调步骤依赖关系
    """
    
    def __init__(self):
        """初始化任务分解器"""
        self.complexity_patterns = self._load_complexity_patterns()
        self.action_patterns = self._load_action_patterns()
        
    def _load_complexity_patterns(self) -> Dict[TaskComplexity, List[str]]:
        """加载复杂度识别模式"""
        return {
            TaskComplexity.SIMPLE: [
                r'查找', r'搜索', r'获取', r'计算(?!.*复杂)', r'简单',
                r'single', r'find', r'get', r'calculate(?!.*complex)', r'lookup'
            ],
            TaskComplexity.MODERATE: [
                r'比较', r'分析(?!.*综合|.*全面)', r'总结', r'研究.*应用',
                r'compare', r'analyze(?!.*comprehensive)', r'summarize', r'research.*application'
            ],
            TaskComplexity.COMPLEX: [
                r'综合.*分析', r'深入.*研究', r'全面.*评估', r'详细.*调研', r'详细.*评估',
                r'comprehensive.*analysis', r'detailed.*research', r'detailed.*evaluat', r'thorough.*evaluation'
            ],
            TaskComplexity.VERY_COMPLEX: [
                r'多维度.*分析', r'系统性.*研究', r'跨领域.*调研', r'战略.*规划', r'多.*技术.*融合',
                r'multi.*dimensional.*analysis', r'systematic.*research', r'strategic.*planning', r'multiple.*technologies'
            ]
        }
    
    def _load_action_patterns(self) -> Dict[str, List[str]]:
        """加载动作类型识别模式"""
        return {
            'search': [
                r'搜索', r'查找', r'获取.*信息', r'收集.*数据',
                r'search', r'find', r'gather.*information', r'collect.*data'
            ],
            'analyze': [
                r'分析', r'评估', r'比较', r'解读',
                r'analyze', r'evaluate', r'compare', r'interpret'
            ],
            'browse': [
                r'浏览', r'访问.*网站', r'查看.*页面',
                r'browse', r'visit.*website', r'view.*page'
            ],
            'execute': [
                r'计算', r'执行', r'运行', r'处理',
                r'calculate', r'execute', r'run', r'process'
            ],
            'synthesize': [
                r'综合', r'整理', r'汇总', r'生成.*报告',
                r'synthesize', r'compile', r'generate.*report'
            ]
        }
    
    def decompose_task(self, task_description: str) -> DecompositionResult:
        """
        🎯 主要方法：分解任务
        
        Args:
            task_description: 任务描述
            
        Returns:
            DecompositionResult: 分解结果
        """
        logger.info(f"🔍 开始分解任务: {task_description}")
        
        # 1. 分析任务复杂度
        complexity = self._analyze_complexity(task_description)
        logger.info(f"📊 任务复杂度: {complexity.value}")
        
        # 2. 识别关键要素
        key_elements = self._extract_key_elements(task_description)
        logger.info(f"🔑 关键要素: {key_elements}")
        
        # 3. 生成步骤序列
        steps = self._generate_steps(task_description, complexity, key_elements)
        logger.info(f"📋 生成 {len(steps)} 个执行步骤")
        
        # 4. 确定执行策略
        execution_strategy = self._determine_execution_strategy(steps, complexity)
        logger.info(f"⚡ 执行策略: {execution_strategy}")
        
        # 5. 估算总耗时
        total_duration = sum(step.estimated_duration for step in steps)
        
        # 6. 定义成功标准
        success_criteria = self._define_success_criteria(task_description, steps)
        
        result = DecompositionResult(
            original_task=task_description,
            complexity=complexity,
            steps=steps,
            execution_strategy=execution_strategy,
            estimated_total_duration=total_duration,
            success_criteria=success_criteria
        )
        
        logger.info(f"✅ 任务分解完成，预计耗时 {total_duration:.1f}秒")
        return result
    
    def _analyze_complexity(self, task_description: str) -> TaskComplexity:
        """分析任务复杂度"""
        task_lower = task_description.lower()
        
        # 从高到低检查复杂度
        for complexity in [TaskComplexity.VERY_COMPLEX, TaskComplexity.COMPLEX, 
                          TaskComplexity.MODERATE, TaskComplexity.SIMPLE]:
            patterns = self.complexity_patterns[complexity]
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    return complexity
        
        # 基于长度的后备判断
        if len(task_description) > 200:
            return TaskComplexity.COMPLEX
        elif len(task_description) > 100:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE
    
    def _extract_key_elements(self, task_description: str) -> Dict[str, List[str]]:
        """提取任务关键要素"""
        elements = {
            'topics': [],  # 主题
            'actions': [], # 动作
            'targets': [], # 目标对象
            'constraints': []  # 约束条件
        }
        
        # 提取主题（专业术语、领域关键词）
        topic_patterns = [
            r'人工智能|AI|机器学习|深度学习',
            r'医疗|诊断|健康|疾病',
            r'金融|投资|股票|市场',
            r'科技|技术|创新|发展',
            r'quantum|blockchain|cloud|IoT'
        ]
        
        for pattern in topic_patterns:
            matches = re.findall(pattern, task_description, re.IGNORECASE)
            elements['topics'].extend(matches)
        
        # 提取动作类型
        for action_type, patterns in self.action_patterns.items():
            for pattern in patterns:
                if re.search(pattern, task_description, re.IGNORECASE):
                    elements['actions'].append(action_type)
        
        # 提取约束条件
        constraint_patterns = [
            r'最新|latest|recent',
            r'详细|detailed|comprehensive',
            r'简要|brief|summary',
            r'准确|accurate|precise'
        ]
        
        for pattern in constraint_patterns:
            if re.search(pattern, task_description, re.IGNORECASE):
                elements['constraints'].append(pattern)
        
        return elements
    
    def _generate_steps(self, task_description: str, complexity: TaskComplexity, 
                       key_elements: Dict[str, List[str]]) -> List[TaskStep]:
        """生成执行步骤"""
        steps = []
        
        # 根据复杂度和要素生成步骤
        if complexity == TaskComplexity.SIMPLE:
            steps = self._generate_simple_steps(task_description, key_elements)
        elif complexity == TaskComplexity.MODERATE:
            steps = self._generate_moderate_steps(task_description, key_elements)
        elif complexity == TaskComplexity.COMPLEX:
            steps = self._generate_complex_steps(task_description, key_elements)
        else:  # VERY_COMPLEX
            steps = self._generate_very_complex_steps(task_description, key_elements)
        
        return steps
    
    def _generate_simple_steps(self, task_description: str, key_elements: Dict) -> List[TaskStep]:
        """生成简单任务步骤"""
        steps = []
        
        # 简单任务通常是1-2步
        if 'search' in key_elements['actions']:
            steps.append(TaskStep(
                step_id="step_1",
                description=f"搜索相关信息: {', '.join(key_elements['topics'])}",
                action_type="search",
                dependencies=[],
                expected_output="获取基础信息和数据",
                estimated_duration=30.0
            ))
        else:
            # 默认分析步骤
            steps.append(TaskStep(
                step_id="step_1", 
                description=f"分析任务要求: {task_description[:50]}...",
                action_type="analyze",
                dependencies=[],
                expected_output="理解任务需求并确定解决方案",
                estimated_duration=20.0
            ))
        
        return steps
    
    def _generate_moderate_steps(self, task_description: str, key_elements: Dict) -> List[TaskStep]:
        """生成中等任务步骤"""
        steps = []
        
        # 第一步：信息收集
        steps.append(TaskStep(
            step_id="step_1",
            description=f"收集基础信息: {', '.join(key_elements['topics'])}",
            action_type="search",
            dependencies=[],
            expected_output="获取相关的基础数据和信息",
            estimated_duration=45.0
        ))
        
        # 第二步：深入分析
        steps.append(TaskStep(
            step_id="step_2", 
            description="深入分析收集到的信息",
            action_type="analyze",
            dependencies=["step_1"],
            expected_output="形成初步的分析结果",
            estimated_duration=60.0
        ))
        
        # 第三步：结果综合
        if 'synthesize' in key_elements['actions'] or '综合' in task_description:
            steps.append(TaskStep(
                step_id="step_3",
                description="综合分析结果并形成结论",
                action_type="synthesize", 
                dependencies=["step_2"],
                expected_output="完整的分析报告或结论",
                estimated_duration=30.0
            ))
        
        return steps
    
    def _generate_complex_steps(self, task_description: str, key_elements: Dict) -> List[TaskStep]:
        """生成复杂任务步骤"""
        steps = []
        
        # 第一步：需求分析
        steps.append(TaskStep(
            step_id="step_1",
            description="分析任务需求和范围",
            action_type="analyze",
            dependencies=[],
            expected_output="明确的任务范围和要求",
            estimated_duration=30.0
        ))
        
        # 第二步：信息搜索
        steps.append(TaskStep(
            step_id="step_2",
            description=f"搜索核心主题信息: {', '.join(key_elements['topics'])}",
            action_type="search",
            dependencies=["step_1"],
            expected_output="相关领域的基础信息",
            estimated_duration=60.0
        ))
        
        # 第三步：深度研究
        steps.append(TaskStep(
            step_id="step_3",
            description="深度研究具体应用和案例",
            action_type="browse",
            dependencies=["step_2"],
            expected_output="详细的应用案例和技术细节",
            estimated_duration=90.0
        ))
        
        # 第四步：数据分析
        steps.append(TaskStep(
            step_id="step_4",
            description="分析数据和趋势模式",
            action_type="execute",
            dependencies=["step_3"],
            expected_output="数据分析结果和趋势图表",
            estimated_duration=75.0
        ))
        
        # 第五步：综合评估
        steps.append(TaskStep(
            step_id="step_5",
            description="综合评估和结论生成",
            action_type="synthesize",
            dependencies=["step_4"],
            expected_output="完整的评估报告",
            estimated_duration=45.0
        ))
        
        return steps
    
    def _generate_very_complex_steps(self, task_description: str, key_elements: Dict) -> List[TaskStep]:
        """生成极复杂任务步骤"""
        steps = []
        
        # 前期准备阶段
        steps.extend([
            TaskStep(
                step_id="step_1",
                description="任务分解和规划",
                action_type="analyze",
                dependencies=[],
                expected_output="详细的执行计划",
                estimated_duration=45.0
            ),
            TaskStep(
                step_id="step_2",
                description="文献调研和背景分析",
                action_type="search",
                dependencies=["step_1"],
                expected_output="领域背景和研究现状",
                estimated_duration=90.0
            )
        ])
        
        # 核心研究阶段
        steps.extend([
            TaskStep(
                step_id="step_3",
                description="核心技术深度调研",
                action_type="browse",
                dependencies=["step_2"],
                expected_output="技术细节和实现方案",
                estimated_duration=120.0
            ),
            TaskStep(
                step_id="step_4",
                description="市场和应用分析",
                action_type="search",
                dependencies=["step_2"],
                expected_output="市场趋势和应用现状",
                estimated_duration=90.0
            ),
            TaskStep(
                step_id="step_5",
                description="数据收集和处理",
                action_type="execute",
                dependencies=["step_3", "step_4"],
                expected_output="处理后的分析数据",
                estimated_duration=75.0
            )
        ])
        
        # 分析综合阶段
        steps.extend([
            TaskStep(
                step_id="step_6",
                description="多维度对比分析",
                action_type="analyze",
                dependencies=["step_5"],
                expected_output="对比分析结果",
                estimated_duration=90.0
            ),
            TaskStep(
                step_id="step_7",
                description="趋势预测和建议",
                action_type="synthesize",
                dependencies=["step_6"],
                expected_output="预测结果和发展建议",
                estimated_duration=60.0
            )
        ])
        
        return steps
    
    def _determine_execution_strategy(self, steps: List[TaskStep], 
                                    complexity: TaskComplexity) -> str:
        """确定执行策略"""
        # 检查步骤依赖关系
        has_dependencies = any(step.dependencies for step in steps)
        
        if not has_dependencies and len(steps) <= 3:
            return "parallel"  # 无依赖的简单任务可并行
        elif has_dependencies and complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
            return "hybrid"  # 复杂任务采用混合策略
        else:
            return "sequential"  # 默认顺序执行
    
    def _define_success_criteria(self, task_description: str, 
                               steps: List[TaskStep]) -> List[str]:
        """定义成功标准"""
        criteria = []
        
        # 基于任务描述的通用标准
        if '分析' in task_description or 'analysis' in task_description.lower():
            criteria.append("完成全面的分析并得出明确结论")
        
        if '研究' in task_description or 'research' in task_description.lower():
            criteria.append("收集充分的研究资料和数据")
        
        if '报告' in task_description or 'report' in task_description.lower():
            criteria.append("生成结构化的报告文档")
        
        # 基于步骤的具体标准
        for step in steps:
            if step.action_type == "search":
                criteria.append(f"成功获取 {step.description} 的相关信息")
            elif step.action_type == "analyze":
                criteria.append(f"完成 {step.description} 并得出有价值的洞察")
            elif step.action_type == "synthesize":
                criteria.append(f"生成综合性的 {step.description} 结果")
        
        # 默认标准
        if not criteria:
            criteria = [
                "任务执行过程无严重错误",
                "生成了有意义的输出结果",
                "满足了用户的基本需求"
            ]
        
        return criteria
    
    def optimize_execution_order(self, steps: List[TaskStep]) -> List[TaskStep]:
        """
        🔄 优化执行顺序
        
        基于依赖关系和优先级重新排序步骤
        """
        # 拓扑排序处理依赖关系
        sorted_steps = []
        remaining_steps = steps.copy()
        
        while remaining_steps:
            # 找到没有未满足依赖的步骤
            ready_steps = []
            for step in remaining_steps:
                deps_satisfied = all(
                    any(s.step_id == dep for s in sorted_steps) 
                    for dep in step.dependencies
                )
                if deps_satisfied:
                    ready_steps.append(step)
            
            if not ready_steps:
                # 处理循环依赖 - 选择优先级最高的
                ready_steps = [max(remaining_steps, key=lambda x: x.priority)]
                logger.warning(f"检测到可能的循环依赖，强制选择步骤: {ready_steps[0].step_id}")
            
            # 按优先级排序就绪的步骤
            ready_steps.sort(key=lambda x: x.priority, reverse=True)
            
            # 添加到结果中
            for step in ready_steps:
                sorted_steps.append(step)
                remaining_steps.remove(step)
        
        logger.info(f"🔄 执行顺序优化完成，重新排序了 {len(steps)} 个步骤")
        return sorted_steps
    
    def estimate_parallel_opportunities(self, steps: List[TaskStep]) -> List[List[str]]:
        """
        ⚡ 识别并行执行机会
        
        Returns:
            List[List[str]]: 可以并行执行的步骤组
        """
        parallel_groups = []
        processed_steps = set()
        
        for step in steps:
            if step.step_id in processed_steps:
                continue
                
            # 找到所有可以与当前步骤并行的步骤
            parallel_candidates = [step.step_id]
            
            for other_step in steps:
                if (other_step.step_id != step.step_id and 
                    other_step.step_id not in processed_steps):
                    
                    # 检查是否可以并行
                    can_parallel = (
                        # 没有直接依赖关系
                        step.step_id not in other_step.dependencies and
                        other_step.step_id not in step.dependencies and
                        # 类型适合并行（搜索和浏览可以并行）
                        self._can_run_parallel(step.action_type, other_step.action_type)
                    )
                    
                    if can_parallel:
                        parallel_candidates.append(other_step.step_id)
            
            if len(parallel_candidates) > 1:
                parallel_groups.append(parallel_candidates)
                processed_steps.update(parallel_candidates)
        
        logger.info(f"⚡ 识别到 {len(parallel_groups)} 个并行执行组")
        return parallel_groups
    
    def _can_run_parallel(self, action_type1: str, action_type2: str) -> bool:
        """判断两种动作类型是否可以并行执行"""
        # 搜索类动作可以并行
        search_actions = {'search', 'browse'}
        if action_type1 in search_actions and action_type2 in search_actions:
            return True
        
        # 分析和执行不能并行（需要依赖数据）
        if action_type1 in {'analyze', 'execute'} or action_type2 in {'analyze', 'execute'}:
            return False
        
        return True