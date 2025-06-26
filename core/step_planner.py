"""
步骤规划器 - 多步推理和动态计划生成
Step Planner - Multi-step reasoning and dynamic plan generation
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .interfaces import ExecutionStep, TaskSpec, ActionType, ErrorType
from .memory_manager import MemoryManager

logger = logging.getLogger(__name__)

class PlanningStrategy(Enum):
    """规划策略"""
    SEQUENTIAL = "sequential"        # 顺序执行
    ADAPTIVE = "adaptive"           # 自适应调整
    PARALLEL = "parallel"           # 并行执行
    ITERATIVE = "iterative"         # 迭代优化

class StepPriority(Enum):
    """步骤优先级"""
    CRITICAL = "critical"           # 关键步骤，必须成功
    HIGH = "high"                   # 高优先级
    MEDIUM = "medium"               # 中等优先级
    LOW = "low"                     # 低优先级
    OPTIONAL = "optional"           # 可选步骤

@dataclass
class PlannedStep:
    """规划的步骤"""
    step_id: str
    action: str
    tool_id: str
    parameters: Dict[str, Any]
    priority: StepPriority
    estimated_duration: float = 30.0
    prerequisites: List[str] = None
    success_criteria: str = ""
    fallback_actions: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []
        if self.fallback_actions is None:
            self.fallback_actions = []
        if self.metadata is None:
            self.metadata = {}

@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    task_id: str
    strategy: PlanningStrategy
    planned_steps: List[PlannedStep]
    max_steps: int
    estimated_total_duration: float
    confidence: float
    reasoning: str
    created_at: float
    can_continue: bool = True
    completion_criteria: str = ""

    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()

class StepPlanner:
    """
    步骤规划器 - 负责多步推理和动态计划生成
    
    功能:
    1. 分析任务状态和执行历史
    2. 生成下一步或多步执行计划
    3. 动态调整计划基于执行结果
    4. 判断任务完成条件
    5. 提供智能的步骤优先级和依赖管理
    """
    
    def __init__(self, llm_client, memory_manager: MemoryManager = None, 
                 default_max_steps: int = 10):
        """
        初始化步骤规划器
        
        Args:
            llm_client: LLM客户端，用于生成规划
            memory_manager: 记忆管理器，用于上下文获取
            default_max_steps: 默认最大步骤数
        """
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.default_max_steps = default_max_steps
        
        # 规划缓存和历史
        self._plan_cache: Dict[str, ExecutionPlan] = {}
        self._execution_history: Dict[str, List[ExecutionStep]] = {}
        
        # 统计信息
        self._stats = {
            "total_plans_generated": 0,
            "successful_plans": 0,
            "adaptive_adjustments": 0,
            "completed_tasks": 0
        }
        
        logger.info(f"StepPlanner initialized with max_steps={default_max_steps}")
    
    async def generate_initial_plan(self, task: TaskSpec, 
                                  available_tools: List[str],
                                  session_id: str = None) -> ExecutionPlan:
        """
        生成初始执行计划
        
        Args:
            task: 任务规范
            available_tools: 可用工具列表
            session_id: 会话ID（用于记忆获取）
            
        Returns:
            执行计划
        """
        try:
            logger.info(f"生成初始计划: {task.task_id}")
            
            # 获取上下文记忆（如果有）
            context_memory = ""
            if self.memory_manager and session_id:
                context_memory = await self.memory_manager.generate_context_summary(
                    session_id, max_steps=5
                )
            
            # 构建规划prompt
            planning_prompt = await self._build_planning_prompt(
                task, available_tools, context_memory, []
            )
            
            # 使用LLM生成计划
            plan_response = await self.llm_client.generate_reasoning(
                planning_prompt, available_tools, []
            )
            
            # 解析规划响应
            plan = await self._parse_planning_response(
                task, plan_response, PlanningStrategy.ADAPTIVE
            )
            
            # 缓存计划
            self._plan_cache[task.task_id] = plan
            self._stats["total_plans_generated"] += 1
            
            logger.info(f"生成计划成功: {len(plan.planned_steps)} 步骤, 置信度: {plan.confidence:.3f}")
            return plan
            
        except Exception as e:
            logger.error(f"生成初始计划失败: {e}")
            # 返回后备计划
            return self._create_fallback_plan(task, available_tools)
    
    async def plan_next_step(self, task: TaskSpec, 
                           executed_steps: List[ExecutionStep],
                           available_tools: List[str],
                           session_id: str = None) -> Optional[PlannedStep]:
        """
        规划下一步
        
        Args:
            task: 任务规范
            executed_steps: 已执行的步骤
            available_tools: 可用工具列表
            session_id: 会话ID
            
        Returns:
            规划的下一步，如果任务完成则返回None
        """
        try:
            logger.debug(f"规划下一步: {task.task_id}, 已执行 {len(executed_steps)} 步")
            
            # 检查是否有现有计划
            current_plan = self._plan_cache.get(task.task_id)
            
            # 如果有计划，检查是否需要调整
            if current_plan:
                next_step = await self._get_next_step_from_plan(
                    current_plan, executed_steps
                )
                
                if next_step:
                    return next_step
                
                # 检查是否需要调整计划
                should_adjust = await self._should_adjust_plan(
                    current_plan, executed_steps
                )
                
                if should_adjust:
                    logger.info("检测到需要调整执行计划")
                    current_plan = await self._adjust_plan(
                        current_plan, executed_steps, available_tools, session_id
                    )
                    self._stats["adaptive_adjustments"] += 1
            
            # 如果没有计划或需要重新生成
            if not current_plan:
                current_plan = await self.generate_initial_plan(
                    task, available_tools, session_id
                )
            
            # 获取下一步
            next_step = await self._get_next_step_from_plan(
                current_plan, executed_steps
            )
            
            # 检查是否达到最大步骤数
            if len(executed_steps) >= current_plan.max_steps:
                logger.info(f"达到最大步骤数 {current_plan.max_steps}，终止规划")
                return None
            
            return next_step
            
        except Exception as e:
            logger.error(f"规划下一步失败: {e}")
            return None
    
    async def check_completion(self, task: TaskSpec, 
                             executed_steps: List[ExecutionStep],
                             current_outputs: List[str]) -> Tuple[bool, str]:
        """
        检查任务是否完成
        
        Args:
            task: 任务规范
            executed_steps: 已执行的步骤
            current_outputs: 当前输出
            
        Returns:
            (是否完成, 完成原因/下一步建议)
        """
        try:
            # 获取当前计划
            current_plan = self._plan_cache.get(task.task_id)
            
            # 构建完成检查prompt
            completion_prompt = await self._build_completion_check_prompt(
                task, executed_steps, current_outputs, current_plan
            )
            
            # 使用LLM检查完成状态
            completion_response = await self.llm_client.check_task_completion(
                task.description, 
                [step.__dict__ for step in executed_steps],
                current_outputs
            )
            
            is_completed = completion_response.get('completed', False)
            reason = completion_response.get('reason', '')
            
            if is_completed:
                self._stats["completed_tasks"] += 1
                if current_plan:
                    self._stats["successful_plans"] += 1
                
                logger.info(f"任务完成: {task.task_id}, 原因: {reason}")
            
            return is_completed, reason
            
        except Exception as e:
            logger.error(f"检查任务完成状态失败: {e}")
            # 基于简单规则判断
            return self._simple_completion_check(executed_steps, current_outputs)
    
    async def _build_planning_prompt(self, task: TaskSpec, 
                                   available_tools: List[str],
                                   context_memory: str,
                                   executed_steps: List[ExecutionStep]) -> str:
        """构建规划prompt"""
        
        prompt_parts = [
            "你是一个智能任务规划器，需要为给定任务生成详细的执行计划。",
            "",
            f"任务描述: {task.description}",
            f"最大步骤数: {task.max_steps or self.default_max_steps}",
            "",
            "可用工具:",
        ]
        
        for tool in available_tools[:10]:  # 限制显示的工具数量
            prompt_parts.append(f"- {tool}")
        
        if context_memory:
            prompt_parts.extend([
                "",
                "上下文记忆:",
                context_memory
            ])
        
        if executed_steps:
            prompt_parts.extend([
                "",
                "已执行步骤:",
                f"共 {len(executed_steps)} 步"
            ])
            
            for step in executed_steps[-3:]:  # 显示最近3步
                status = "✅" if step.success else "❌"
                prompt_parts.append(f"{status} 步骤{step.step_id}: {step.observation[:100]}...")
        
        prompt_parts.extend([
            "",
            "请生成一个JSON格式的执行计划，包含以下字段:",
            "{",
            "  \"strategy\": \"adaptive\",",
            "  \"max_steps\": 数字,",
            "  \"confidence\": 0.0-1.0,",
            "  \"reasoning\": \"规划理由\",",
            "  \"planned_steps\": [",
            "    {",
            "      \"action\": \"动作名称\",",
            "      \"tool_id\": \"工具ID\",",
            "      \"parameters\": {参数对象},",
            "      \"priority\": \"high|medium|low\",",
            "      \"success_criteria\": \"成功标准\"",
            "    }",
            "  ]",
            "}",
            "",
            "⚠️ 重要约束:",
            "1. 只返回JSON对象，不要任何其他文字！",
            "2. 不要添加解释、注释或描述性文本",
            "3. 必须是有效的JSON格式",
            "4. NO other text outside the JSON object!",
            "**只返回JSON，不要其他内容！**",
            "",
            "规划注意事项:",
            "1. 计划应该循序渐进，每步都有明确目标",
            "2. 优先使用可用工具",
            "3. 考虑步骤间的依赖关系",
            "4. 设定合理的成功标准"
        ])
        
        return "\n".join(prompt_parts)
    
    async def _parse_planning_response(self, task: TaskSpec, 
                                     response: str,
                                     strategy: PlanningStrategy) -> ExecutionPlan:
        """解析规划响应"""
        try:
            # 尝试提取JSON
            plan_data = {}
            if isinstance(response, dict):
                plan_data = response
            else:
                # 从文本中提取JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    plan_data = json.loads(json_match.group())
            
            # 解析步骤
            planned_steps = []
            steps_data = plan_data.get("planned_steps", [])
            
            for i, step_data in enumerate(steps_data):
                step = PlannedStep(
                    step_id=f"plan_{task.task_id}_{i+1}",
                    action=step_data.get("action", "unknown"),
                    tool_id=step_data.get("tool_id", ""),
                    parameters=step_data.get("parameters", {}),
                    priority=StepPriority(step_data.get("priority", "medium")),
                    success_criteria=step_data.get("success_criteria", "")
                )
                planned_steps.append(step)
            
            # 创建执行计划
            plan = ExecutionPlan(
                plan_id=f"plan_{task.task_id}_{int(time.time())}",
                task_id=task.task_id,
                strategy=PlanningStrategy(plan_data.get("strategy", "adaptive")),
                planned_steps=planned_steps,
                max_steps=plan_data.get("max_steps", task.max_steps or self.default_max_steps),
                estimated_total_duration=len(planned_steps) * 30.0,
                confidence=plan_data.get("confidence", 0.8),
                reasoning=plan_data.get("reasoning", ""),
                created_at=time.time()
            )
            
            return plan
            
        except Exception as e:
            logger.error(f"解析规划响应失败: {e}")
            return self._create_fallback_plan(task, [])
    
    async def _get_next_step_from_plan(self, plan: ExecutionPlan, 
                                     executed_steps: List[ExecutionStep]) -> Optional[PlannedStep]:
        """从计划中获取下一步"""
        try:
            executed_step_count = len([s for s in executed_steps if s.success])
            
            if executed_step_count < len(plan.planned_steps):
                next_planned = plan.planned_steps[executed_step_count]
                logger.debug(f"从计划获取下一步: {next_planned.action}")
                return next_planned
            
            return None
            
        except Exception as e:
            logger.error(f"获取下一步失败: {e}")
            return None
    
    async def _should_adjust_plan(self, plan: ExecutionPlan, 
                                executed_steps: List[ExecutionStep]) -> bool:
        """检查是否需要调整计划"""
        try:
            # 检查失败率
            failed_steps = [s for s in executed_steps if not s.success]
            if len(failed_steps) > len(executed_steps) * 0.3:  # 失败率超过30%
                return True
            
            # 检查是否偏离预期
            successful_steps = [s for s in executed_steps if s.success]
            if len(successful_steps) > len(plan.planned_steps):  # 超出计划步骤
                return True
            
            # 检查时间是否超预期
            total_duration = sum(s.duration for s in executed_steps if hasattr(s, 'duration'))
            if total_duration > plan.estimated_total_duration * 1.5:  # 超时50%
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查计划调整需求失败: {e}")
            return False
    
    async def _adjust_plan(self, plan: ExecutionPlan, 
                         executed_steps: List[ExecutionStep],
                         available_tools: List[str],
                         session_id: str = None) -> ExecutionPlan:
        """调整执行计划"""
        try:
            logger.info("调整执行计划...")
            
            # 分析执行结果
            successful_steps = [s for s in executed_steps if s.success]
            failed_steps = [s for s in executed_steps if not s.success]
            
            # 构建调整prompt
            adjustment_prompt = self._build_adjustment_prompt(
                plan, successful_steps, failed_steps, available_tools
            )
            
            # 使用LLM生成调整后的计划
            adjustment_response = await self.llm_client.generate_reasoning(
                adjustment_prompt, available_tools, []
            )
            
            # 解析新计划
            from .interfaces import TaskType
            adjusted_plan = await self._parse_planning_response(
                TaskSpec(
                    task_id=plan.task_id, 
                    task_type=TaskType.REASONING,  # 添加必需的task_type参数
                    description="",
                    max_steps=plan.max_steps
                ),
                adjustment_response,
                plan.strategy
            )
            
            # 更新计划ID和缓存
            adjusted_plan.plan_id = f"{plan.plan_id}_adjusted_{int(time.time())}"
            self._plan_cache[plan.task_id] = adjusted_plan
            
            return adjusted_plan
            
        except Exception as e:
            logger.error(f"调整计划失败: {e}")
            return plan
    
    def _build_adjustment_prompt(self, plan: ExecutionPlan,
                               successful_steps: List[ExecutionStep],
                               failed_steps: List[ExecutionStep],
                               available_tools: List[str]) -> str:
        """构建计划调整prompt"""
        
        prompt_parts = [
            "需要调整现有执行计划。分析执行情况并生成优化的计划。",
            "",
            f"原始计划策略: {plan.strategy.value}",
            f"原始置信度: {plan.confidence:.3f}",
            f"原始推理: {plan.reasoning}",
            "",
            f"执行统计:",
            f"- 成功步骤: {len(successful_steps)}",
            f"- 失败步骤: {len(failed_steps)}",
            f"- 总步骤: {len(successful_steps) + len(failed_steps)}",
            ""
        ]
        
        if failed_steps:
            prompt_parts.extend([
                "失败步骤分析:",
                *[f"- {step.error_type}: {step.error_message}" for step in failed_steps[-3:]]
            ])
        
        prompt_parts.extend([
            "",
            "请生成调整后的执行计划（JSON格式），重点考虑:",
            "1. 避免之前失败的操作模式",
            "2. 利用成功步骤的经验",
            "3. 调整步骤优先级和策略",
            "4. 提供更合适的后备方案",
            "",
            "⚠️ 重要约束:",
            "1. 只返回JSON对象，不要任何其他文字！",
            "2. 不要添加解释、注释或描述性文本",
            "3. 必须是有效的JSON格式",
            "4. NO other text outside the JSON object!",
            "**只返回JSON，不要其他内容！**"
        ])
        
        return "\n".join(prompt_parts)
    
    async def _build_completion_check_prompt(self, task: TaskSpec,
                                           executed_steps: List[ExecutionStep],
                                           current_outputs: List[str],
                                           plan: ExecutionPlan = None) -> str:
        """构建完成检查prompt"""
        
        prompt_parts = [
            "检查任务是否已完成。",
            "",
            f"任务描述: {task.description}",
            f"已执行步骤数: {len(executed_steps)}",
            f"当前输出数: {len(current_outputs)}",
            ""
        ]
        
        if plan:
            prompt_parts.extend([
                f"原计划步骤数: {len(plan.planned_steps)}",
                f"完成标准: {plan.completion_criteria}",
                ""
            ])
        
        # 最近的成功步骤
        successful_steps = [s for s in executed_steps if s.success]
        if successful_steps:
            prompt_parts.extend([
                "最近成功步骤:",
                *[f"- {step.observation[:100]}..." for step in successful_steps[-3:]]
            ])
        
        # 当前输出
        if current_outputs:
            prompt_parts.extend([
                "",
                "当前输出:",
                *[f"- {output[:100]}..." for output in current_outputs[-3:]]
            ])
        
        prompt_parts.extend([
            "",
            "基于以上信息，判断任务是否完成。返回布尔值和简短原因。"
        ])
        
        return "\n".join(prompt_parts)
    
    def _simple_completion_check(self, executed_steps: List[ExecutionStep],
                               current_outputs: List[str]) -> Tuple[bool, str]:
        """简单的完成检查（后备方案）"""
        try:
            # 基本规则 - 更加严格的检查
            successful_steps = [s for s in executed_steps if s.success]
            tool_steps = [s for s in executed_steps if hasattr(s, 'action_type') and 'TOOL_CALL' in str(s.action_type)]
            successful_tool_steps = [s for s in tool_steps if s.success]
            
            # 检查是否有有意义的工具执行
            has_meaningful_execution = len(successful_tool_steps) >= 2
            
            # 检查输出质量 - 不仅要有输出，还要有足够的内容
            has_substantial_output = (
                len(current_outputs) > 0 and 
                any(len(output) > 100 for output in current_outputs)  # 至少有一个输出超过100字符
            )
            
            # 检查执行多样性 - 是否使用了不同的工具
            unique_tools = set()
            for step in successful_tool_steps:
                if hasattr(step, 'tool_id') and step.tool_id:
                    unique_tools.add(step.tool_id)
            
            has_tool_diversity = len(unique_tools) >= 2  # 至少使用了2个不同的工具
            
            # 成功率检查
            success_rate = len(successful_steps) / len(executed_steps) if executed_steps else 0
            
            # 更严格的完成条件
            if (has_meaningful_execution and 
                has_substantial_output and 
                has_tool_diversity and 
                success_rate >= 0.7):
                return True, f"基于严格检查判断任务已完成: {len(successful_tool_steps)}个工具成功执行，使用了{len(unique_tools)}个不同工具，成功率{success_rate:.1%}"
            
            # 检查是否应该停止（避免无限循环）
            if len(executed_steps) > 8:
                if success_rate < 0.3:
                    return True, f"执行步骤过多({len(executed_steps)})且成功率低({success_rate:.1%})，建议停止"
                elif len(successful_tool_steps) == 0:
                    return True, "没有成功的工具执行，建议停止"
            
            # 分析未完成的原因
            missing_reasons = []
            if not has_meaningful_execution:
                missing_reasons.append(f"工具执行不足(仅{len(successful_tool_steps)}个)")
            if not has_substantial_output:
                missing_reasons.append("输出内容不足")
            if not has_tool_diversity:
                missing_reasons.append(f"工具使用单一(仅{len(unique_tools)}种)")
            if success_rate < 0.7:
                missing_reasons.append(f"成功率过低({success_rate:.1%})")
            
            return False, f"任务尚未完成: {', '.join(missing_reasons)}"
            
        except Exception as e:
            logger.error(f"简单完成检查失败: {e}")
            return False, "无法判断完成状态"
    
    def _create_fallback_plan(self, task: TaskSpec, 
                            available_tools: List[str]) -> ExecutionPlan:
        """创建后备计划"""
        try:
            # 创建基本的执行步骤
            fallback_steps = []
            
            # 分析任务类型并创建对应步骤
            if any(word in task.description.lower() for word in ['搜索', 'search', '查找', '调研']):
                fallback_steps.append(PlannedStep(
                    step_id=f"fallback_{task.task_id}_1",
                    action="research",
                    tool_id="mcp-deepsearch" if "mcp-deepsearch" in available_tools else "web-search",
                    parameters={"question": task.description},
                    priority=StepPriority.HIGH,
                    success_criteria="获得相关搜索结果"
                ))
            
            if any(word in task.description.lower() for word in ['计算', 'calculate', '代码', 'code']):
                fallback_steps.append(PlannedStep(
                    step_id=f"fallback_{task.task_id}_2",
                    action="microsandbox_execute",
                    tool_id="microsandbox-mcp-server" if "microsandbox-mcp-server" in available_tools else "python",
                    parameters={"code": "# 分析任务并执行相关计算"},
                    priority=StepPriority.MEDIUM,
                    success_criteria="代码执行成功"
                ))
            
            # 如果没有特定类型，添加通用分析步骤
            if not fallback_steps:
                fallback_steps.extend([
                    PlannedStep(
                        step_id=f"fallback_{task.task_id}_1",
                        action="analyze_tool_needs",
                        tool_id=available_tools[0] if available_tools else "mcp-search-tool",
                        parameters={"task_description": task.description},
                        priority=StepPriority.MEDIUM,
                        success_criteria="完成任务分析"
                    ),
                    PlannedStep(
                        step_id=f"fallback_{task.task_id}_2",
                        action="search_and_install_tools",
                        tool_id="mcp-search-tool",
                        parameters={"task_description": task.description[:200]},
                        priority=StepPriority.HIGH,
                        success_criteria="找到并安装相关工具"
                    ),
                    PlannedStep(
                        step_id=f"fallback_{task.task_id}_3",
                        action="research",
                        tool_id=available_tools[0] if available_tools else "mcp-deepsearch",
                        parameters={"question": task.description},
                        priority=StepPriority.MEDIUM,
                        success_criteria="完成任务并生成结果"
                    )
                ])
            
            plan = ExecutionPlan(
                plan_id=f"fallback_{task.task_id}_{int(time.time())}",
                task_id=task.task_id,
                strategy=PlanningStrategy.SEQUENTIAL,
                planned_steps=fallback_steps,
                max_steps=max(len(fallback_steps), task.max_steps or self.default_max_steps),
                estimated_total_duration=len(fallback_steps) * 30.0,
                confidence=0.6,
                reasoning="后备计划：基于任务描述的基本步骤",
                created_at=time.time()
            )
            
            return plan
            
        except Exception as e:
            logger.error(f"创建后备计划失败: {e}")
            # 最基本的计划 - 确保至少有一个步骤
            minimal_steps = [
                PlannedStep(
                    step_id=f"minimal_{task.task_id}_1",
                    action="search_and_install_tools",
                    tool_id="mcp-search-tool",
                    parameters={"task_description": task.description[:100] if task.description else "general task"},
                    priority=StepPriority.HIGH,
                    success_criteria="完成基本任务分析"
                )
            ]
            
            return ExecutionPlan(
                plan_id=f"minimal_{task.task_id}_{int(time.time())}",
                task_id=task.task_id,
                strategy=PlanningStrategy.SEQUENTIAL,
                planned_steps=minimal_steps,
                max_steps=max(1, task.max_steps or self.default_max_steps),
                estimated_total_duration=60.0,
                confidence=0.3,
                reasoning="最小化后备计划 - 包含基本步骤",
                created_at=time.time()
            )
    
    def get_planning_stats(self) -> Dict[str, Any]:
        """获取规划统计信息"""
        return {
            "total_plans_generated": self._stats["total_plans_generated"],
            "successful_plans": self._stats["successful_plans"],
            "adaptive_adjustments": self._stats["adaptive_adjustments"],
            "completed_tasks": self._stats["completed_tasks"],
            "success_rate": (
                self._stats["successful_plans"] / max(1, self._stats["total_plans_generated"])
            ),
            "cached_plans": len(self._plan_cache),
            "default_max_steps": self.default_max_steps
        }
    
    def clear_cache(self, task_id: str = None):
        """清理缓存"""
        if task_id:
            self._plan_cache.pop(task_id, None)
            self._execution_history.pop(task_id, None)
        else:
            self._plan_cache.clear()
            self._execution_history.clear()
        
        logger.info(f"已清理规划缓存: {task_id or 'all'}")
    
    def _evaluate_output_quality(self, outputs: List[str]) -> float:
        """评估输出质量，返回0-1的分数"""
        if not outputs:
            return 0.0
        
        total_length = sum(len(output) for output in outputs)
        avg_length = total_length / len(outputs)
        
        # 基于输出数量和质量的综合评分
        quantity_score = min(1.0, len(outputs) / 3)  # 3个输出为满分
        length_score = min(1.0, avg_length / 200)  # 200字符为满分
        
        # 检查内容质量
        quality_indicators = 0
        for output in outputs:
            content = output.lower()
            # 正面指标
            if any(indicator in content for indicator in ['成功', '完成', '结果', 'success', 'result', 'output']):
                quality_indicators += 0.3
            # 数据指标
            if any(indicator in content for indicator in ['数据', '信息', '内容', 'data', 'information', 'content']):
                quality_indicators += 0.2
            # 避免错误指标
            if any(indicator in content for indicator in ['错误', '失败', 'error', 'failed', 'exception']):
                quality_indicators -= 0.2
        
        content_score = min(1.0, quality_indicators / len(outputs))
        
        # 综合评分
        final_score = (quantity_score * 0.3 + length_score * 0.4 + content_score * 0.3)
        return max(0.0, min(1.0, final_score))
    
    def _evaluate_step_quality(self, step: ExecutionStep, outputs: List[str]) -> float:
        """评估单个步骤的质量"""
        score = 0.0
        
        # 基础成功分
        if step.success:
            score += 0.4
        
        # 步骤输出质量
        if hasattr(step, 'observation') and step.observation:
            obs_length = len(step.observation)
            if obs_length > 100:
                score += 0.3
            elif obs_length > 50:
                score += 0.2
            else:
                score += 0.1
        
        # 执行时间合理性
        if hasattr(step, 'duration') and step.duration:
            if 1 <= step.duration <= 30:  # 合理时间范围
                score += 0.1
        
        # 输出关联性
        if outputs and hasattr(step, 'observation'):
            for output in outputs:
                if step.observation and len(step.observation) > 20:
                    score += 0.2
                    break
        
        return min(1.0, score)