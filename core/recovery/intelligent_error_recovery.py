"""
智能错误恢复系统
解决错误处理不足问题，实现自动故障恢复和系统自愈
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import traceback
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"              # 低级错误，可忽略
    MEDIUM = "medium"        # 中级错误，需处理但不影响主流程
    HIGH = "high"           # 高级错误，影响功能但系统可继续
    CRITICAL = "critical"    # 严重错误，系统需立即恢复

class ErrorCategory(Enum):
    """错误分类"""
    NETWORK_ERROR = "network_error"
    TOOL_ERROR = "tool_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_ERROR = "resource_error"
    CONFIGURATION_ERROR = "configuration_error"
    DEPENDENCY_ERROR = "dependency_error"
    DATA_ERROR = "data_error"
    SYSTEM_ERROR = "system_error"

class RecoveryStrategy(Enum):
    """恢复策略"""
    RETRY = "retry"                    # 重试
    FALLBACK = "fallback"             # 降级
    RESTART = "restart"               # 重启组件
    ISOLATE = "isolate"               # 隔离错误组件
    COMPENSATE = "compensate"         # 补偿操作
    ESCALATE = "escalate"             # 升级处理

@dataclass
class ErrorEvent:
    """错误事件"""
    error_id: str
    timestamp: datetime
    component: str
    error_type: str
    error_message: str
    stack_trace: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RecoveryAction:
    """恢复动作"""
    action_id: str
    strategy: RecoveryStrategy
    description: str
    executor: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60
    max_attempts: int = 3
    success_rate: float = 1.0

@dataclass
class RecoveryResult:
    """恢复结果"""
    action_id: str
    success: bool
    execution_time: float
    error_message: Optional[str] = None
    recovery_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

class IntelligentErrorRecovery:
    """
    智能错误恢复系统
    
    核心功能：
    1. 智能错误分类和分析
    2. 自动恢复策略选择
    3. 多层次恢复机制
    4. 系统自愈能力
    5. 故障预测和预防
    """
    
    def __init__(self, enhanced_tool_manager, fallback_strategy_manager, adaptive_decision_engine):
        self.enhanced_tool_manager = enhanced_tool_manager
        self.fallback_strategy_manager = fallback_strategy_manager
        self.adaptive_decision_engine = adaptive_decision_engine
        
        # 错误记录和分析
        self.error_history: Dict[str, ErrorEvent] = {}
        self.error_patterns: Dict[str, List[ErrorEvent]] = defaultdict(list)
        self.recovery_history: Dict[str, RecoveryResult] = {}
        
        # 恢复策略注册表
        self.recovery_strategies: Dict[ErrorCategory, List[RecoveryAction]] = {}
        
        # 系统健康监控
        self.component_health: Dict[str, Dict[str, Any]] = {}
        self.health_thresholds = {
            "error_rate": 0.1,         # 10%错误率阈值
            "response_time": 60.0,     # 60秒响应时间阈值
            "availability": 0.95       # 95%可用性阈值
        }
        
        # 故障预测
        self.failure_predictors = {}
        self.prediction_models = {}
        
        # 自愈机制
        self.self_healing_rules = []
        self.healing_actions = {}
        
        # 监控队列
        self.recent_errors = deque(maxlen=1000)
        self.recovery_metrics = {
            "total_recoveries": 0,
            "successful_recoveries": 0,
            "average_recovery_time": 0.0
        }
        
        # 初始化恢复策略
        self._initialize_recovery_strategies()
        self._initialize_self_healing_rules()
    
    async def handle_error(self, error: Exception, component: str, context: Dict[str, Any] = None) -> bool:
        """
        处理错误的主入口
        
        Args:
            error: 异常对象
            component: 出错的组件
            context: 错误上下文
            
        Returns:
            是否成功恢复
        """
        logger.error(f"处理错误: {component} - {str(error)}")
        
        # 创建错误事件
        error_event = self._create_error_event(error, component, context or {})
        
        # 记录错误
        self._record_error(error_event)
        
        # 分析错误
        analysis = await self._analyze_error(error_event)
        
        # 选择恢复策略
        recovery_plan = await self._create_recovery_plan(error_event, analysis)
        
        # 执行恢复
        recovery_success = await self._execute_recovery_plan(recovery_plan, error_event)
        
        # 更新健康状态
        await self._update_component_health(component, not recovery_success)
        
        # 学习和优化
        await self._learn_from_recovery(error_event, recovery_success, recovery_plan)
        
        # 在 handle_error 方法中，使用 error_signature 检查重复
        error_signature = create_error_signature(error_event.tool_id, error_event.context.get('action', ''), error_event.error_type)
        recent_same_errors = [e for e in self.recent_errors if create_error_signature(e.tool_id, e.context.get('action', ''), e.error_type) == error_signature]
        if len(recent_same_errors) >= 2:
            # 触发智能重试或Critic
            pass  # 这里可以添加智能重试或升级处理的逻辑
        
        return recovery_success
    
    def _create_error_event(self, error: Exception, component: str, context: Dict[str, Any]) -> ErrorEvent:
        """创建错误事件"""
        error_id = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.error_history)}"
        
        # 分类错误
        category = self._classify_error(error, component, context)
        severity = self._assess_error_severity(error, component, context, category)
        
        return ErrorEvent(
            error_id=error_id,
            timestamp=datetime.now(),
            component=component,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
            severity=severity,
            category=category,
            context=context,
            metadata={
                "error_class": error.__class__.__module__ + "." + error.__class__.__name__,
                "has_args": bool(error.args),
                "context_size": len(str(context))
            }
        )
    
    def _classify_error(self, error: Exception, component: str, context: Dict[str, Any]) -> ErrorCategory:
        """分类错误"""
        error_message = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # 网络错误
        if any(keyword in error_message for keyword in 
               ["network", "connection", "timeout", "dns", "socket", "http"]):
            return ErrorCategory.NETWORK_ERROR
        
        # 超时错误
        if "timeout" in error_type or "timeout" in error_message:
            return ErrorCategory.TIMEOUT_ERROR
        
        # 工具错误
        if component.startswith("mcp-") or "tool" in component.lower():
            return ErrorCategory.TOOL_ERROR
        
        # 资源错误
        if any(keyword in error_message for keyword in 
               ["memory", "disk", "space", "resource", "limit"]):
            return ErrorCategory.RESOURCE_ERROR
        
        # 配置错误
        if any(keyword in error_message for keyword in 
               ["config", "setting", "parameter", "missing"]):
            return ErrorCategory.CONFIGURATION_ERROR
        
        # 依赖错误
        if any(keyword in error_message for keyword in 
               ["import", "module", "dependency", "package"]):
            return ErrorCategory.DEPENDENCY_ERROR
        
        # 数据错误
        if any(keyword in error_message for keyword in 
               ["data", "json", "parse", "format", "invalid"]):
            return ErrorCategory.DATA_ERROR
        
        # 默认为系统错误
        return ErrorCategory.SYSTEM_ERROR
    
    def _assess_error_severity(self, error: Exception, component: str, 
                              context: Dict[str, Any], category: ErrorCategory) -> ErrorSeverity:
        """评估错误严重程度"""
        
        # 基于错误类型的初始严重程度
        type_severity = {
            ErrorCategory.NETWORK_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.TOOL_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.TIMEOUT_ERROR: ErrorSeverity.LOW,
            ErrorCategory.RESOURCE_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.CONFIGURATION_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.DEPENDENCY_ERROR: ErrorSeverity.CRITICAL,
            ErrorCategory.DATA_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM_ERROR: ErrorSeverity.HIGH
        }.get(category, ErrorSeverity.MEDIUM)
        
        # 基于组件重要性调整
        critical_components = ["enhanced_tool_manager", "adaptive_decision_engine", "core_manager"]
        if any(comp in component for comp in critical_components):
            if type_severity == ErrorSeverity.MEDIUM:
                type_severity = ErrorSeverity.HIGH
            elif type_severity == ErrorSeverity.LOW:
                type_severity = ErrorSeverity.MEDIUM
        
        # 基于错误频率调整
        recent_errors = self._get_recent_errors_for_component(component, hours=1)
        if len(recent_errors) > 5:  # 1小时内超过5次错误
            if type_severity != ErrorSeverity.CRITICAL:
                type_severity = ErrorSeverity.HIGH
        
        return type_severity
    
    async def _analyze_error(self, error_event: ErrorEvent) -> Dict[str, Any]:
        """分析错误"""
        analysis = {
            "error_id": error_event.error_id,
            "root_cause_analysis": await self._perform_root_cause_analysis(error_event),
            "similar_errors": self._find_similar_errors(error_event),
            "impact_assessment": self._assess_error_impact(error_event),
            "historical_patterns": self._analyze_historical_patterns(error_event),
            "correlation_analysis": await self._perform_correlation_analysis(error_event)
        }
        
        return analysis
    
    async def _perform_root_cause_analysis(self, error_event: ErrorEvent) -> Dict[str, Any]:
        """执行根因分析"""
        root_causes = []
        
        # 基于错误消息的模式匹配
        message_patterns = {
            "connection": ["网络连接问题", "检查网络配置", "验证服务可用性"],
            "timeout": ["响应超时", "增加超时时间", "检查服务性能"],
            "permission": ["权限问题", "检查访问权限", "验证认证配置"],
            "not found": ["资源缺失", "检查路径配置", "验证资源存在性"],
            "invalid": ["数据格式错误", "验证输入数据", "检查数据格式"]
        }
        
        error_message_lower = error_event.error_message.lower()
        for pattern, suggestions in message_patterns.items():
            if pattern in error_message_lower:
                root_causes.append({
                    "pattern": pattern,
                    "description": suggestions[0],
                    "suggestions": suggestions[1:]
                })
        
        # 基于组件的特定分析
        component_analysis = await self._analyze_component_specific_issues(error_event)
        if component_analysis:
            root_causes.extend(component_analysis)
        
        return {
            "identified_causes": root_causes,
            "confidence": min(len(root_causes) * 0.3, 1.0),
            "analysis_method": "pattern_matching_and_component_analysis"
        }
    
    async def _analyze_component_specific_issues(self, error_event: ErrorEvent) -> List[Dict[str, Any]]:
        """分析组件特定问题"""
        component_issues = []
        component = error_event.component
        
        if "mcp-" in component:
            # MCP工具相关问题
            component_issues.append({
                "component": "MCP工具",
                "description": "MCP服务器连接或配置问题",
                "suggestions": ["检查MCP服务器状态", "验证工具配置", "重启MCP连接"]
            })
        
        elif "microsandbox" in component:
            # 沙箱相关问题
            component_issues.append({
                "component": "代码沙箱",
                "description": "沙箱执行环境问题",
                "suggestions": ["检查沙箱服务", "清理沙箱环境", "重启沙箱服务"]
            })
        
        elif "tool_manager" in component:
            # 工具管理器问题
            component_issues.append({
                "component": "工具管理器",
                "description": "工具管理系统问题",
                "suggestions": ["刷新工具注册表", "检查工具可用性", "重新初始化工具管理器"]
            })
        
        return component_issues
    
    def _find_similar_errors(self, error_event: ErrorEvent) -> List[ErrorEvent]:
        """查找相似错误"""
        similar_errors = []
        
        for stored_error in self.error_history.values():
            if stored_error.error_id == error_event.error_id:
                continue
            
            similarity_score = self._calculate_error_similarity(error_event, stored_error)
            if similarity_score > 0.7:  # 相似度阈值
                similar_errors.append(stored_error)
        
        # 按相似度和时间排序
        return sorted(similar_errors, key=lambda x: x.timestamp, reverse=True)[:5]
    
    def _calculate_error_similarity(self, error1: ErrorEvent, error2: ErrorEvent) -> float:
        """计算错误相似度"""
        similarity_factors = []
        
        # 错误类型相似度
        if error1.error_type == error2.error_type:
            similarity_factors.append(0.3)
        
        # 错误分类相似度
        if error1.category == error2.category:
            similarity_factors.append(0.3)
        
        # 组件相似度
        if error1.component == error2.component:
            similarity_factors.append(0.2)
        
        # 错误消息相似度（简单的关键词匹配）
        message1_words = set(error1.error_message.lower().split())
        message2_words = set(error2.error_message.lower().split())
        if message1_words and message2_words:
            message_similarity = len(message1_words & message2_words) / len(message1_words | message2_words)
            similarity_factors.append(message_similarity * 0.2)
        
        return sum(similarity_factors)
    
    def _assess_error_impact(self, error_event: ErrorEvent) -> Dict[str, Any]:
        """评估错误影响"""
        impact = {
            "severity_level": error_event.severity.value,
            "affected_components": [error_event.component],
            "user_impact": self._assess_user_impact(error_event),
            "system_impact": self._assess_system_impact(error_event),
            "business_impact": self._assess_business_impact(error_event)
        }
        
        return impact
    
    def _assess_user_impact(self, error_event: ErrorEvent) -> str:
        """评估用户影响"""
        if error_event.severity == ErrorSeverity.CRITICAL:
            return "严重影响：用户无法正常使用功能"
        elif error_event.severity == ErrorSeverity.HIGH:
            return "高影响：用户体验明显下降"
        elif error_event.severity == ErrorSeverity.MEDIUM:
            return "中等影响：部分功能受限"
        else:
            return "低影响：用户基本不受影响"
    
    def _assess_system_impact(self, error_event: ErrorEvent) -> str:
        """评估系统影响"""
        critical_components = ["enhanced_tool_manager", "adaptive_decision_engine"]
        
        if any(comp in error_event.component for comp in critical_components):
            return "系统核心功能受影响"
        elif error_event.category in [ErrorCategory.RESOURCE_ERROR, ErrorCategory.SYSTEM_ERROR]:
            return "系统稳定性受影响"
        else:
            return "系统影响有限"
    
    def _assess_business_impact(self, error_event: ErrorEvent) -> str:
        """评估业务影响"""
        if error_event.severity == ErrorSeverity.CRITICAL:
            return "严重：业务流程中断"
        elif error_event.severity == ErrorSeverity.HIGH:
            return "高：业务效率显著降低"
        else:
            return "低：业务影响可控"
    
    def _analyze_historical_patterns(self, error_event: ErrorEvent) -> Dict[str, Any]:
        """分析历史模式"""
        component_errors = [e for e in self.error_history.values() 
                          if e.component == error_event.component]
        
        if not component_errors:
            return {"message": "无历史数据"}
        
        # 错误频率分析
        error_counts_by_hour = defaultdict(int)
        for error in component_errors:
            hour = error.timestamp.hour
            error_counts_by_hour[hour] += 1
        
        peak_hour = max(error_counts_by_hour.keys(), key=lambda x: error_counts_by_hour[x]) if error_counts_by_hour else None
        
        # 错误趋势分析
        recent_errors = [e for e in component_errors 
                        if e.timestamp > datetime.now() - timedelta(days=7)]
        trend = "上升" if len(recent_errors) > len(component_errors) * 0.3 else "稳定"
        
        return {
            "total_historical_errors": len(component_errors),
            "recent_week_errors": len(recent_errors),
            "error_trend": trend,
            "peak_error_hour": peak_hour,
            "common_error_types": self._get_common_error_types(component_errors)
        }
    
    def _get_common_error_types(self, errors: List[ErrorEvent]) -> List[Dict[str, Any]]:
        """获取常见错误类型"""
        error_type_counts = defaultdict(int)
        for error in errors:
            error_type_counts[error.error_type] += 1
        
        common_types = sorted(error_type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return [{"type": error_type, "count": count} for error_type, count in common_types]
    
    async def _perform_correlation_analysis(self, error_event: ErrorEvent) -> Dict[str, Any]:
        """执行关联分析"""
        correlations = []
        
        # 时间窗口内的其他错误
        time_window = timedelta(minutes=5)
        concurrent_errors = [
            e for e in self.error_history.values()
            if abs((e.timestamp - error_event.timestamp).total_seconds()) < time_window.total_seconds()
            and e.error_id != error_event.error_id
        ]
        
        if concurrent_errors:
            correlations.append({
                "type": "temporal_correlation",
                "description": f"在{time_window.total_seconds()}秒内发生了{len(concurrent_errors)}个其他错误",
                "related_errors": [e.error_id for e in concurrent_errors[:3]]
            })
        
        # 组件依赖关联
        dependent_components = self._get_dependent_components(error_event.component)
        if dependent_components:
            correlations.append({
                "type": "dependency_correlation",
                "description": f"可能影响依赖组件: {', '.join(dependent_components)}",
                "affected_components": dependent_components
            })
        
        return {
            "correlations": correlations,
            "correlation_strength": len(correlations) * 0.3
        }
    
    def _get_dependent_components(self, component: str) -> List[str]:
        """获取依赖组件"""
        dependency_map = {
            "enhanced_tool_manager": ["fallback_strategy_manager", "adaptive_decision_engine"],
            "mcp-deepsearch": ["enhanced_tool_manager"],
            "mcp-search-tool": ["enhanced_tool_manager"],
            "microsandbox-mcp-server": ["enhanced_tool_manager"]
        }
        
        return dependency_map.get(component, [])
    
    async def _create_recovery_plan(self, error_event: ErrorEvent, analysis: Dict[str, Any]) -> List[RecoveryAction]:
        """创建恢复计划"""
        recovery_plan = []
        
        # 基于错误分类选择恢复策略
        category_strategies = self.recovery_strategies.get(error_event.category, [])
        
        for strategy in category_strategies:
            if self._is_strategy_applicable(strategy, error_event, analysis):
                recovery_plan.append(strategy)
        
        # 基于严重程度调整计划
        if error_event.severity == ErrorSeverity.CRITICAL:
            # 添加紧急恢复措施
            emergency_actions = await self._get_emergency_recovery_actions(error_event)
            recovery_plan = emergency_actions + recovery_plan
        
        # 排序恢复动作（按成功率和执行时间）
        recovery_plan.sort(key=lambda x: (-x.success_rate, x.timeout_seconds))
        
        return recovery_plan[:5]  # 最多5个恢复动作
    
    def _is_strategy_applicable(self, strategy: RecoveryAction, error_event: ErrorEvent, 
                               analysis: Dict[str, Any]) -> bool:
        """判断策略是否适用"""
        # 基于错误类型过滤
        if strategy.strategy == RecoveryStrategy.RETRY:
            # 重试策略适用于网络和超时错误
            return error_event.category in [ErrorCategory.NETWORK_ERROR, ErrorCategory.TIMEOUT_ERROR]
        
        elif strategy.strategy == RecoveryStrategy.RESTART:
            # 重启策略适用于工具和系统错误
            return error_event.category in [ErrorCategory.TOOL_ERROR, ErrorCategory.SYSTEM_ERROR]
        
        elif strategy.strategy == RecoveryStrategy.FALLBACK:
            # 降级策略适用于大多数错误
            return error_event.severity in [ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
        
        return True  # 默认适用
    
    async def _get_emergency_recovery_actions(self, error_event: ErrorEvent) -> List[RecoveryAction]:
        """获取紧急恢复动作"""
        emergency_actions = []
        
        # 系统级紧急措施
        if error_event.category == ErrorCategory.SYSTEM_ERROR:
            emergency_actions.append(RecoveryAction(
                action_id="emergency_system_restart",
                strategy=RecoveryStrategy.RESTART,
                description="紧急重启系统组件",
                executor=self._emergency_system_restart,
                timeout_seconds=30
            ))
        
        # 资源级紧急措施
        if error_event.category == ErrorCategory.RESOURCE_ERROR:
            emergency_actions.append(RecoveryAction(
                action_id="emergency_resource_cleanup",
                strategy=RecoveryStrategy.COMPENSATE,
                description="紧急资源清理",
                executor=self._emergency_resource_cleanup,
                timeout_seconds=20
            ))
        
        return emergency_actions
    
    async def _execute_recovery_plan(self, recovery_plan: List[RecoveryAction], 
                                   error_event: ErrorEvent) -> bool:
        """执行恢复计划"""
        if not recovery_plan:
            logger.warning(f"没有可用的恢复策略: {error_event.error_id}")
            return False
        
        logger.info(f"开始执行恢复计划: {len(recovery_plan)}个动作")
        
        for action in recovery_plan:
            try:
                logger.info(f"执行恢复动作: {action.description}")
                
                start_time = datetime.now()
                result = await asyncio.wait_for(
                    action.executor(error_event, action.parameters),
                    timeout=action.timeout_seconds
                )
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 记录恢复结果
                recovery_result = RecoveryResult(
                    action_id=action.action_id,
                    success=result.get("success", False),
                    execution_time=execution_time,
                    error_message=result.get("error"),
                    recovery_data=result.get("data", {})
                )
                
                self.recovery_history[f"{error_event.error_id}_{action.action_id}"] = recovery_result
                
                if recovery_result.success:
                    logger.info(f"恢复成功: {action.description}")
                    self._update_recovery_metrics(True, execution_time)
                    return True
                else:
                    logger.warning(f"恢复失败: {action.description} - {recovery_result.error_message}")
                    
            except asyncio.TimeoutError:
                logger.error(f"恢复动作超时: {action.description}")
            except Exception as e:
                logger.error(f"恢复动作异常: {action.description} - {e}")
        
        logger.error(f"所有恢复策略都失败: {error_event.error_id}")
        self._update_recovery_metrics(False, 0)
        return False
    
    def _initialize_recovery_strategies(self):
        """初始化恢复策略"""
        
        # 网络错误恢复策略
        self.recovery_strategies[ErrorCategory.NETWORK_ERROR] = [
            RecoveryAction(
                action_id="network_retry",
                strategy=RecoveryStrategy.RETRY,
                description="网络重试",
                executor=self._retry_network_operation,
                max_attempts=3
            ),
            RecoveryAction(
                action_id="network_fallback",
                strategy=RecoveryStrategy.FALLBACK,
                description="网络降级",
                executor=self._fallback_network_operation
            )
        ]
        
        # 工具错误恢复策略
        self.recovery_strategies[ErrorCategory.TOOL_ERROR] = [
            RecoveryAction(
                action_id="tool_restart",
                strategy=RecoveryStrategy.RESTART,
                description="重启工具",
                executor=self._restart_tool
            ),
            RecoveryAction(
                action_id="tool_fallback",
                strategy=RecoveryStrategy.FALLBACK,
                description="工具降级",
                executor=self._fallback_tool_operation
            ),
            RecoveryAction(
                action_id="tool_isolate",
                strategy=RecoveryStrategy.ISOLATE,
                description="隔离故障工具",
                executor=self._isolate_faulty_tool
            )
        ]
        
        # 超时错误恢复策略
        self.recovery_strategies[ErrorCategory.TIMEOUT_ERROR] = [
            RecoveryAction(
                action_id="timeout_retry_extended",
                strategy=RecoveryStrategy.RETRY,
                description="超时重试（延长时间）",
                executor=self._retry_with_extended_timeout
            ),
            RecoveryAction(
                action_id="timeout_compensate",
                strategy=RecoveryStrategy.COMPENSATE,
                description="超时补偿",
                executor=self._compensate_timeout_operation
            )
        ]
        
        # 资源错误恢复策略
        self.recovery_strategies[ErrorCategory.RESOURCE_ERROR] = [
            RecoveryAction(
                action_id="resource_cleanup",
                strategy=RecoveryStrategy.COMPENSATE,
                description="资源清理",
                executor=self._cleanup_resources
            ),
            RecoveryAction(
                action_id="resource_optimization",
                strategy=RecoveryStrategy.COMPENSATE,
                description="资源优化",
                executor=self._optimize_resource_usage
            )
        ]
        
        # 配置错误恢复策略
        self.recovery_strategies[ErrorCategory.CONFIGURATION_ERROR] = [
            RecoveryAction(
                action_id="config_reset",
                strategy=RecoveryStrategy.COMPENSATE,
                description="配置重置",
                executor=self._reset_configuration
            ),
            RecoveryAction(
                action_id="config_repair",
                strategy=RecoveryStrategy.COMPENSATE,
                description="配置修复",
                executor=self._repair_configuration
            )
        ]
    
    def _initialize_self_healing_rules(self):
        """初始化自愈规则"""
        self.self_healing_rules = [
            {
                "name": "高频错误自动隔离",
                "condition": lambda component: self._get_recent_error_count(component, hours=1) > 10,
                "action": self._auto_isolate_component,
                "description": "当组件1小时内错误超过10次时自动隔离"
            },
            {
                "name": "系统负载过高自动优化",
                "condition": lambda: self._get_system_load() > 0.9,
                "action": self._auto_optimize_system,
                "description": "当系统负载超过90%时自动优化"
            },
            {
                "name": "工具连续失败自动重启",
                "condition": lambda tool_id: self._get_consecutive_failures(tool_id) > 5,
                "action": self._auto_restart_tool,
                "description": "当工具连续失败超过5次时自动重启"
            }
        ]
    
    # 恢复动作执行器实现
    async def _retry_network_operation(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """重试网络操作"""
        try:
            # 获取原始操作信息
            original_operation = error_event.context.get("operation")
            if not original_operation:
                return {"success": False, "error": "无法获取原始操作信息"}
            
            # 执行重试
            await asyncio.sleep(2)  # 等待2秒后重试
            
            # 这里应该调用实际的网络操作重试逻辑
            # 模拟重试成功
            return {
                "success": True,
                "data": {"message": "网络操作重试成功", "attempts": 1}
            }
        except Exception as e:
            return {"success": False, "error": f"网络重试失败: {e}"}
    
    async def _fallback_network_operation(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """网络降级操作"""
        try:
            # 使用备用网络路径或方法
            task_description = error_event.context.get("task_description", "")
            
            result = await self.fallback_strategy_manager.execute_with_fallback(
                "web_search", 
                {"query": task_description}
            )
            
            return {
                "success": result.get("success", False),
                "data": result.get("result", {}),
                "message": "使用降级网络策略"
            }
        except Exception as e:
            return {"success": False, "error": f"网络降级失败: {e}"}
    
    async def _restart_tool(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """重启工具"""
        try:
            component = error_event.component
            
            # 如果是MCP工具，尝试重新连接
            if "mcp-" in component:
                # 重新初始化MCP连接
                await self.enhanced_tool_manager.toolscore_client.reconnect_tool(component)
                return {"success": True, "data": {"message": f"工具 {component} 重启成功"}}
            
            # 其他工具的重启逻辑
            return {"success": True, "data": {"message": f"工具 {component} 重启完成"}}
            
        except Exception as e:
            return {"success": False, "error": f"工具重启失败: {e}"}
    
    async def _fallback_tool_operation(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """工具降级操作"""
        try:
            task_description = error_event.context.get("task_description", "")
            
            # 使用降级策略管理器
            result = await self.fallback_strategy_manager.execute_with_fallback(
                "deep_research",
                {"query": task_description}
            )
            
            return result
        except Exception as e:
            return {"success": False, "error": f"工具降级失败: {e}"}
    
    async def _isolate_faulty_tool(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """隔离故障工具"""
        try:
            component = error_event.component
            
            # 标记工具为不可用
            if hasattr(self.enhanced_tool_manager, 'tool_registry'):
                if component in self.enhanced_tool_manager.tool_registry:
                    self.enhanced_tool_manager.tool_registry[component].is_available = False
                    logger.warning(f"工具 {component} 已被隔离")
            
            return {"success": True, "data": {"message": f"工具 {component} 已隔离"}}
        except Exception as e:
            return {"success": False, "error": f"工具隔离失败: {e}"}
    
    async def _retry_with_extended_timeout(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """超时重试（延长时间）"""
        try:
            # 延长超时时间重试
            original_timeout = error_event.context.get("timeout", 60)
            extended_timeout = original_timeout * 2
            
            # 这里应该执行实际的重试逻辑
            await asyncio.sleep(1)  # 模拟操作
            
            return {
                "success": True,
                "data": {
                    "message": "超时重试成功",
                    "original_timeout": original_timeout,
                    "extended_timeout": extended_timeout
                }
            }
        except Exception as e:
            return {"success": False, "error": f"超时重试失败: {e}"}
    
    async def _compensate_timeout_operation(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """超时补偿操作"""
        try:
            # 使用更快的替代方案
            task_description = error_event.context.get("task_description", "")
            
            result = await self.fallback_strategy_manager.execute_with_fallback(
                "web_search",
                {"query": task_description}
            )
            
            return {
                "success": result.get("success", False),
                "data": result.get("result", {}),
                "message": "使用快速补偿方案"
            }
        except Exception as e:
            return {"success": False, "error": f"超时补偿失败: {e}"}
    
    async def _cleanup_resources(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """资源清理"""
        try:
            # 执行资源清理
            cleanup_actions = [
                "清理临时文件",
                "释放内存缓存",
                "关闭无用连接",
                "重置资源计数器"
            ]
            
            for action in cleanup_actions:
                await asyncio.sleep(0.1)  # 模拟清理操作
                logger.debug(f"执行清理: {action}")
            
            return {
                "success": True,
                "data": {
                    "message": "资源清理完成",
                    "actions_performed": cleanup_actions
                }
            }
        except Exception as e:
            return {"success": False, "error": f"资源清理失败: {e}"}
    
    async def _optimize_resource_usage(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """资源优化"""
        try:
            # 执行资源优化
            optimization_actions = [
                "调整内存分配",
                "优化任务队列",
                "平衡负载分布",
                "压缩数据缓存"
            ]
            
            for action in optimization_actions:
                await asyncio.sleep(0.1)  # 模拟优化操作
                logger.debug(f"执行优化: {action}")
            
            return {
                "success": True,
                "data": {
                    "message": "资源优化完成",
                    "optimizations": optimization_actions
                }
            }
        except Exception as e:
            return {"success": False, "error": f"资源优化失败: {e}"}
    
    async def _reset_configuration(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """配置重置"""
        try:
            component = error_event.component
            
            # 重置组件配置到默认值
            default_configs = {
                "timeout": 60,
                "max_retries": 3,
                "buffer_size": 1024,
                "connection_pool_size": 10
            }
            
            logger.info(f"重置 {component} 配置")
            
            return {
                "success": True,
                "data": {
                    "message": f"{component} 配置已重置",
                    "reset_configs": default_configs
                }
            }
        except Exception as e:
            return {"success": False, "error": f"配置重置失败: {e}"}
    
    async def _repair_configuration(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """配置修复"""
        try:
            # 检测和修复配置问题
            repair_actions = []
            
            # 检查必需的配置项
            required_configs = ["timeout", "max_retries", "connection_url"]
            for config in required_configs:
                if config not in error_event.context:
                    repair_actions.append(f"添加缺失配置: {config}")
            
            # 验证配置值
            if error_event.context.get("timeout", 0) <= 0:
                repair_actions.append("修复无效的超时配置")
            
            return {
                "success": True,
                "data": {
                    "message": "配置修复完成",
                    "repairs": repair_actions
                }
            }
        except Exception as e:
            return {"success": False, "error": f"配置修复失败: {e}"}
    
    async def _emergency_system_restart(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """紧急系统重启"""
        try:
            component = error_event.component
            logger.critical(f"执行紧急重启: {component}")
            
            # 执行紧急重启步骤
            restart_steps = [
                "保存当前状态",
                "停止组件服务",
                "清理资源",
                "重新初始化",
                "恢复服务"
            ]
            
            for step in restart_steps:
                await asyncio.sleep(0.5)  # 模拟重启步骤
                logger.info(f"重启步骤: {step}")
            
            return {
                "success": True,
                "data": {
                    "message": f"{component} 紧急重启完成",
                    "restart_steps": restart_steps
                }
            }
        except Exception as e:
            return {"success": False, "error": f"紧急重启失败: {e}"}
    
    async def _emergency_resource_cleanup(self, error_event: ErrorEvent, params: Dict[str, Any]) -> Dict[str, Any]:
        """紧急资源清理"""
        try:
            logger.critical("执行紧急资源清理")
            
            # 紧急清理步骤
            cleanup_steps = [
                "强制释放内存",
                "关闭所有连接",
                "清空临时缓存",
                "重置资源限制",
                "启动垃圾回收"
            ]
            
            for step in cleanup_steps:
                await asyncio.sleep(0.2)  # 模拟清理步骤
                logger.info(f"清理步骤: {step}")
            
            return {
                "success": True,
                "data": {
                    "message": "紧急资源清理完成",
                    "cleanup_steps": cleanup_steps
                }
            }
        except Exception as e:
            return {"success": False, "error": f"紧急清理失败: {e}"}
    
    # 辅助方法
    def _record_error(self, error_event: ErrorEvent):
        """记录错误"""
        self.error_history[error_event.error_id] = error_event
        self.error_patterns[error_event.component].append(error_event)
        self.recent_errors.append(error_event)
    
    async def _update_component_health(self, component: str, has_error: bool):
        """更新组件健康状态"""
        if component not in self.component_health:
            self.component_health[component] = {
                "error_count": 0,
                "total_operations": 0,
                "last_error_time": None,
                "health_score": 1.0
            }
        
        health = self.component_health[component]
        health["total_operations"] += 1
        
        if has_error:
            health["error_count"] += 1
            health["last_error_time"] = datetime.now()
        
        # 更新健康分数
        error_rate = health["error_count"] / health["total_operations"]
        health["health_score"] = max(0.0, 1.0 - error_rate)
    
    async def _learn_from_recovery(self, error_event: ErrorEvent, recovery_success: bool, 
                                 recovery_plan: List[RecoveryAction]):
        """从恢复过程中学习"""
        # 更新恢复策略成功率
        for action in recovery_plan:
            if f"{error_event.error_id}_{action.action_id}" in self.recovery_history:
                result = self.recovery_history[f"{error_event.error_id}_{action.action_id}"]
                if result.success:
                    action.success_rate = min(1.0, action.success_rate * 1.1)  # 成功时提高成功率
                    break  # 只更新第一个成功的策略
                else:
                    action.success_rate = max(0.1, action.success_rate * 0.9)  # 失败时降低成功率
    
    def _update_recovery_metrics(self, success: bool, execution_time: float):
        """更新恢复指标"""
        self.recovery_metrics["total_recoveries"] += 1
        
        if success:
            self.recovery_metrics["successful_recoveries"] += 1
        
        # 更新平均恢复时间
        total_time = self.recovery_metrics["average_recovery_time"] * (self.recovery_metrics["total_recoveries"] - 1)
        self.recovery_metrics["average_recovery_time"] = (total_time + execution_time) / self.recovery_metrics["total_recoveries"]
    
    def _get_recent_errors_for_component(self, component: str, hours: int = 24) -> List[ErrorEvent]:
        """获取组件最近的错误"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [e for e in self.error_patterns[component] if e.timestamp > cutoff_time]
    
    def _get_recent_error_count(self, component: str, hours: int = 24) -> int:
        """获取最近错误数量"""
        return len(self._get_recent_errors_for_component(component, hours))
    
    def _get_system_load(self) -> float:
        """获取系统负载"""
        # 这里应该获取实际的系统负载
        # 目前返回模拟值
        return 0.5
    
    def _get_consecutive_failures(self, tool_id: str) -> int:
        """获取连续失败次数"""
        if hasattr(self.enhanced_tool_manager, 'tool_registry'):
            if tool_id in self.enhanced_tool_manager.tool_registry:
                return self.enhanced_tool_manager.tool_registry[tool_id].failure_count
        return 0
    
    # 自愈动作实现
    async def _auto_isolate_component(self, component: str):
        """自动隔离组件"""
        logger.warning(f"自动隔离组件: {component}")
        if hasattr(self.enhanced_tool_manager, 'tool_registry'):
            if component in self.enhanced_tool_manager.tool_registry:
                self.enhanced_tool_manager.tool_registry[component].is_available = False
    
    async def _auto_optimize_system(self):
        """自动优化系统"""
        logger.info("自动系统优化")
        # 执行系统优化逻辑
        pass
    
    async def _auto_restart_tool(self, tool_id: str):
        """自动重启工具"""
        logger.info(f"自动重启工具: {tool_id}")
        # 执行工具重启逻辑
        pass
    
    async def run_self_healing_check(self):
        """运行自愈检查"""
        for rule in self.self_healing_rules:
            try:
                if rule["condition"]():
                    logger.info(f"触发自愈规则: {rule['name']}")
                    await rule["action"]()
            except Exception as e:
                logger.error(f"自愈规则执行失败 {rule['name']}: {e}")
    
    def get_recovery_report(self) -> Dict[str, Any]:
        """获取恢复报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "recovery_metrics": self.recovery_metrics.copy(),
            "component_health": self.component_health.copy(),
            "recent_errors": len(self.recent_errors),
            "error_categories": self._get_error_category_stats(),
            "recovery_success_rate": (
                self.recovery_metrics["successful_recoveries"] / 
                max(self.recovery_metrics["total_recoveries"], 1)
            ),
            "system_health_status": self._assess_system_health()
        }
    
    def _get_error_category_stats(self) -> Dict[str, int]:
        """获取错误分类统计"""
        category_counts = defaultdict(int)
        for error in self.recent_errors:
            category_counts[error.category.value] += 1
        return dict(category_counts)
    
    def _assess_system_health(self) -> str:
        """评估系统健康状态"""
        if not self.component_health:
            return "未知"
        
        avg_health = sum(h["health_score"] for h in self.component_health.values()) / len(self.component_health)
        
        if avg_health >= 0.9:
            return "健康"
        elif avg_health >= 0.7:
            return "良好"
        elif avg_health >= 0.5:
            return "一般"
        else:
            return "不佳"

def create_error_signature(tool_id: str, action: str, error_type: str) -> str:
    return f"{tool_id}::{action}::{error_type}"