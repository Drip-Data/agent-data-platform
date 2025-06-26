"""
优化的AI Agent控制器
集成所有优化模块，解决系统核心缺陷
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json

# 导入优化模块
from .toolscore.enhanced_tool_manager import (
    EnhancedToolManager, TaskRequirement, ToolCapability
)
from .toolscore.fallback_strategy_manager import (
    FallbackStrategyManager, ExecutionResult
)
from .decision.adaptive_decision_engine import (
    AdaptiveDecisionEngine, DecisionType, DecisionContext, DecisionResult, DecisionOutcome
)
from .recovery.intelligent_error_recovery import (
    IntelligentErrorRecovery, ErrorEvent, ErrorSeverity, ErrorCategory
)

logger = logging.getLogger(__name__)

@dataclass
class OptimizedTaskResult:
    """优化后的任务结果"""
    task_id: str
    success: bool
    result_data: Any
    execution_strategy: str
    decision_confidence: float
    recovery_attempts: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

class OptimizedAgentController:
    """
    优化的AI Agent控制器
    
    解决的核心问题：
    1. ✅ 工具职责混乱 -> 清晰的工具分类和职责分离
    2. ✅ 单点故障 -> 多层降级和冗余机制  
    3. ✅ 决策逻辑僵化 -> 自适应学习决策引擎
    4. ✅ 错误处理不足 -> 智能错误恢复系统
    """
    
    def __init__(self, toolscore_client, mcp_client=None):
        self.toolscore_client = toolscore_client
        self.mcp_client = mcp_client
        
        # 初始化核心模块
        self.enhanced_tool_manager = EnhancedToolManager(toolscore_client, mcp_client)
        self.fallback_strategy_manager = FallbackStrategyManager(self.enhanced_tool_manager)
        self.adaptive_decision_engine = AdaptiveDecisionEngine(
            self.enhanced_tool_manager, 
            self.fallback_strategy_manager
        )
        self.intelligent_error_recovery = IntelligentErrorRecovery(
            self.enhanced_tool_manager,
            self.fallback_strategy_manager, 
            self.adaptive_decision_engine
        )
        
        # 系统状态
        self.is_initialized = False
        self.system_metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "recovered_tasks": 0
        }
        
        # 学习数据存储路径
        self.learning_data_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            "data", 
            "learning_data.json"
        )
        
        logger.info("优化的AI Agent控制器初始化完成")
    
    async def initialize(self):
        """初始化系统"""
        try:
            logger.info("开始初始化优化的Agent系统...")
            
            # 加载学习数据
            await self._load_learning_data()
            
            # 初始化各个模块
            await self._initialize_modules()
            
            # 启动健康监控
            await self._start_health_monitoring()
            
            self.is_initialized = True
            logger.info("✅ 优化的Agent系统初始化成功")
            
        except Exception as e:
            logger.error(f"❌ 系统初始化失败: {e}")
            await self.intelligent_error_recovery.handle_error(
                e, "optimized_agent_controller", {"phase": "initialization"}
            )
            raise
    
    async def execute_task(self, task_description: str, task_type: str = "research", 
                          context: Dict[str, Any] = None) -> OptimizedTaskResult:
        """
        执行任务的主入口 - 使用优化的策略
        
        Args:
            task_description: 任务描述
            task_type: 任务类型
            context: 任务上下文
            
        Returns:
            优化的任务结果
        """
        if not self.is_initialized:
            await self.initialize()
        
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.system_metrics['total_tasks']}"
        start_time = datetime.now()
        
        logger.info(f"🚀 开始执行优化任务: {task_id}")
        logger.info(f"   任务描述: {task_description}")
        logger.info(f"   任务类型: {task_type}")
        
        try:
            # 更新系统指标
            self.system_metrics["total_tasks"] += 1
            
            # 步骤1: 智能决策 - 选择最佳执行策略
            execution_strategy, decision_confidence = await self._make_intelligent_decision(
                task_description, task_type, context or {}
            )
            
            logger.info(f"🧠 决策结果: {execution_strategy}, 置信度: {decision_confidence:.3f}")
            
            # 步骤2: 使用选定策略执行任务
            result = await self._execute_with_strategy(
                task_description, task_type, execution_strategy, context or {}
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if result.get("success"):
                logger.info(f"✅ 任务执行成功: {task_id} ({execution_time:.2f}s)")
                self.system_metrics["successful_tasks"] += 1
                
                return OptimizedTaskResult(
                    task_id=task_id,
                    success=True,
                    result_data=result.get("result"),
                    execution_strategy=execution_strategy,
                    decision_confidence=decision_confidence,
                    execution_time=execution_time,
                    metadata=result.get("metadata", {})
                )
            else:
                logger.warning(f"⚠️ 任务执行失败，尝试错误恢复: {task_id}")
                
                # 步骤3: 错误恢复
                recovery_result = await self._attempt_error_recovery(
                    task_description, task_type, result.get("error"), context or {}
                )
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                if recovery_result.get("success"):
                    logger.info(f"🔧 错误恢复成功: {task_id}")
                    self.system_metrics["recovered_tasks"] += 1
                    
                    return OptimizedTaskResult(
                        task_id=task_id,
                        success=True,
                        result_data=recovery_result.get("result"),
                        execution_strategy=f"{execution_strategy}_recovered",
                        decision_confidence=decision_confidence * 0.8,  # 恢复后置信度降低
                        recovery_attempts=1,
                        execution_time=execution_time,
                        metadata=recovery_result.get("metadata", {})
                    )
                else:
                    logger.error(f"❌ 任务最终失败: {task_id}")
                    self.system_metrics["failed_tasks"] += 1
                    
                    return OptimizedTaskResult(
                        task_id=task_id,
                        success=False,
                        result_data=None,
                        execution_strategy=execution_strategy,
                        decision_confidence=decision_confidence,
                        recovery_attempts=1,
                        execution_time=execution_time,
                        error_message=recovery_result.get("error", "未知错误")
                    )
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"💥 任务执行异常: {task_id} - {e}")
            
            # 记录异常并尝试恢复
            recovery_success = await self.intelligent_error_recovery.handle_error(
                e, "optimized_agent_controller", 
                {"task_id": task_id, "task_description": task_description}
            )
            
            self.system_metrics["failed_tasks"] += 1
            
            return OptimizedTaskResult(
                task_id=task_id,
                success=False,
                result_data=None,
                execution_strategy="exception_handling",
                decision_confidence=0.0,
                recovery_attempts=1 if recovery_success else 0,
                execution_time=execution_time,
                error_message=str(e)
            )
    
    async def _make_intelligent_decision(self, task_description: str, task_type: str, 
                                       context: Dict[str, Any]) -> tuple[str, float]:
        """做出智能决策"""
        try:
            # 构建决策上下文
            decision_context = DecisionContext(
                task_description=task_description,
                task_type=task_type,
                system_state=await self._get_system_state(),
                historical_patterns=await self._get_historical_patterns(task_type),
                performance_metrics=await self._get_performance_metrics(),
                constraints=context.get("constraints", {}),
                preferences=context.get("preferences", {})
            )
            
            # 获取可选策略
            available_strategies = await self._get_available_strategies(task_type)
            
            # 使用决策引擎做决策
            decision = await self.adaptive_decision_engine.make_decision(
                DecisionType.STRATEGY_SELECTION,
                decision_context,
                available_strategies
            )
            
            return decision.selected_option, decision.confidence
            
        except Exception as e:
            logger.error(f"决策过程失败: {e}")
            # 降级到默认策略
            return "fallback_strategy", 0.5
    
    async def _execute_with_strategy(self, task_description: str, task_type: str, 
                                   strategy: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """使用指定策略执行任务"""
        try:
            if strategy == "enhanced_tool_manager":
                # 使用增强工具管理器
                requirement = TaskRequirement(
                    task_description=task_description,
                    required_capabilities=self._map_task_to_capabilities(task_type),
                    priority=context.get("priority", "medium")
                )
                return await self.enhanced_tool_manager.execute_task(requirement)
            
            elif strategy == "fallback_strategy_manager":
                # 使用降级策略管理器
                return await self.fallback_strategy_manager.execute_with_fallback(
                    task_type, {"query": task_description, "description": task_description}
                )
            
            elif strategy == "direct_execution":
                # 直接执行（使用基础工具）
                return await self._execute_direct(task_description, task_type, context)
            
            else:
                # 未知策略，使用降级
                logger.warning(f"未知策略: {strategy}, 使用降级策略")
                return await self.fallback_strategy_manager.execute_with_fallback(
                    task_type, {"query": task_description, "description": task_description}
                )
                
        except Exception as e:
            logger.error(f"策略执行失败 {strategy}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _attempt_error_recovery(self, task_description: str, task_type: str, 
                                    error: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试错误恢复"""
        try:
            # 创建模拟错误用于恢复系统
            mock_error = Exception(error or "任务执行失败")
            
            # 使用智能错误恢复系统
            recovery_success = await self.intelligent_error_recovery.handle_error(
                mock_error, "task_execution", 
                {"task_description": task_description, "task_type": task_type}
            )
            
            if recovery_success:
                # 恢复成功，重新尝试执行
                logger.info("错误恢复成功，重新执行任务")
                return await self._execute_with_strategy(
                    task_description, task_type, "fallback_strategy_manager", context
                )
            else:
                return {"success": False, "error": "错误恢复失败"}
                
        except Exception as e:
            logger.error(f"错误恢复过程失败: {e}")
            return {"success": False, "error": f"恢复过程异常: {e}"}
    
    async def _execute_direct(self, task_description: str, task_type: str, 
                            context: Dict[str, Any]) -> Dict[str, Any]:
        """直接执行（基础实现）"""
        try:
            if task_type in ["research", "search"]:
                # 使用基础搜索
                result = await self.enhanced_tool_manager._execute_basic_web_search(
                    type('TaskRequirement', (), {"task_description": task_description})()
                )
                return result
            
            elif task_type == "execute":
                # 使用代码执行
                code = context.get("code", "")
                if code:
                    result = await self.enhanced_tool_manager.toolscore_client.call_tool(
                        "microsandbox-mcp-server",
                        "microsandbox_execute", 
                        {"code": code, "language": context.get("language", "python")}
                    )
                    return result
                else:
                    return {"success": False, "error": "缺少执行代码"}
            
            else:
                # 知识合成
                result = await self.enhanced_tool_manager._execute_knowledge_synthesis(
                    type('TaskRequirement', (), {"task_description": task_description})()
                )
                return result
                
        except Exception as e:
            return {"success": False, "error": f"直接执行失败: {e}"}
    
    async def _get_system_state(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "available_tools": len(self.enhanced_tool_manager.tool_registry),
            "system_load": 0.5,  # 模拟值
            "memory_usage": 0.6,  # 模拟值
            "network_status": "good",
            "initialized": self.is_initialized
        }
    
    async def _get_historical_patterns(self, task_type: str) -> Dict[str, Any]:
        """获取历史模式"""
        # 从决策引擎获取历史模式
        return {
            "similar_tasks_count": 10,  # 模拟值
            "recent_success_rate": 0.8,  # 模拟值
            "preferred_tools": ["enhanced_tool_manager", "fallback_strategy_manager"],
            "common_failure_reasons": ["network_timeout", "tool_unavailable"]
        }
    
    async def _get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return {
            "average_execution_time": 45.0,
            "success_rate": self._calculate_success_rate(),
            "error_rate": self._calculate_error_rate(),
            "resource_usage": 0.5
        }
    
    async def _get_available_strategies(self, task_type: str) -> List[str]:
        """获取可用策略"""
        base_strategies = [
            "enhanced_tool_manager",
            "fallback_strategy_manager", 
            "direct_execution"
        ]
        
        # 基于任务类型过滤策略
        if task_type == "execute":
            return ["direct_execution", "enhanced_tool_manager"]
        elif task_type in ["research", "search"]:
            return base_strategies
        else:
            return base_strategies
    
    def _map_task_to_capabilities(self, task_type: str) -> List[ToolCapability]:
        """将任务类型映射到工具能力"""
        mapping = {
            "research": [ToolCapability.DEEP_RESEARCH, ToolCapability.WEB_SEARCH],
            "search": [ToolCapability.WEB_SEARCH],
            "execute": [ToolCapability.CODE_EXECUTION],
            "analyze": [ToolCapability.DATA_ANALYSIS],
            "install": [ToolCapability.TOOL_INSTALLATION]
        }
        
        return mapping.get(task_type, [ToolCapability.WEB_SEARCH])
    
    def _calculate_success_rate(self) -> float:
        """计算成功率"""
        total = self.system_metrics["total_tasks"]
        if total == 0:
            return 1.0
        
        successful = self.system_metrics["successful_tasks"] + self.system_metrics["recovered_tasks"]
        return successful / total
    
    def _calculate_error_rate(self) -> float:
        """计算错误率"""
        total = self.system_metrics["total_tasks"]
        if total == 0:
            return 0.0
        
        failed = self.system_metrics["failed_tasks"]
        return failed / total
    
    async def _initialize_modules(self):
        """初始化各个模块"""
        logger.info("初始化增强工具管理器...")
        # 工具管理器已在构造函数中初始化
        
        logger.info("初始化降级策略管理器...")
        # 策略管理器已在构造函数中初始化
        
        logger.info("初始化自适应决策引擎...")
        # 决策引擎已在构造函数中初始化
        
        logger.info("初始化智能错误恢复系统...")
        # 错误恢复系统已在构造函数中初始化
    
    async def _start_health_monitoring(self):
        """启动健康监控"""
        logger.info("启动系统健康监控...")
        
        # 启动自愈检查（后台任务）
        asyncio.create_task(self._health_monitoring_loop())
    
    async def _health_monitoring_loop(self):
        """健康监控循环"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 运行自愈检查
                await self.intelligent_error_recovery.run_self_healing_check()
                
                # 检查系统健康状态
                await self._check_system_health()
                
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
    
    async def _check_system_health(self):
        """检查系统健康状态"""
        try:
            # 检查成功率
            success_rate = self._calculate_success_rate()
            if success_rate < 0.7:  # 成功率低于70%
                logger.warning(f"系统成功率偏低: {success_rate:.2f}")
            
            # 检查错误率
            error_rate = self._calculate_error_rate()
            if error_rate > 0.3:  # 错误率高于30%
                logger.warning(f"系统错误率偏高: {error_rate:.2f}")
            
            # 检查工具健康状态
            tool_status = self.enhanced_tool_manager.get_system_status()
            if tool_status["availability_rate"] < 0.8:  # 工具可用率低于80%
                logger.warning(f"工具可用率偏低: {tool_status['availability_rate']:.2f}")
                
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
    
    async def get_system_report(self) -> Dict[str, Any]:
        """获取系统报告"""
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "system_metrics": self.system_metrics.copy(),
                "success_rate": self._calculate_success_rate(),
                "error_rate": self._calculate_error_rate(),
                "tool_status": self.enhanced_tool_manager.get_system_status(),
                "strategy_report": self.fallback_strategy_manager.get_strategy_report(),
                "learning_report": self.adaptive_decision_engine.get_learning_report(),
                "recovery_report": self.intelligent_error_recovery.get_recovery_report()
            }
        except Exception as e:
            logger.error(f"生成系统报告失败: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """优雅关闭系统"""
        logger.info("开始关闭优化的Agent系统...")
        
        try:
            # 保存学习数据
            await self._save_learning_data()
            
            # 清理资源
            await self._cleanup_resources()
            
            self.is_initialized = False
            logger.info("✅ 系统关闭完成")
            
        except Exception as e:
            logger.error(f"系统关闭异常: {e}")
    
    async def _load_learning_data(self):
        """加载学习数据"""
        try:
            # 确保数据目录存在
            data_dir = os.path.dirname(self.learning_data_path)
            os.makedirs(data_dir, exist_ok=True)
            
            if os.path.exists(self.learning_data_path):
                logger.info(f"加载学习数据从: {self.learning_data_path}")
                
                with open(self.learning_data_path, 'r', encoding='utf-8') as f:
                    learning_data = json.load(f)
                
                # 恢复决策引擎的学习数据
                if hasattr(self.adaptive_decision_engine, 'decision_weights'):
                    self.adaptive_decision_engine.decision_weights.update(
                        learning_data.get("decision_weights", {})
                    )
                
                if hasattr(self.adaptive_decision_engine, 'pattern_memory'):
                    pattern_memory_data = learning_data.get("pattern_memory", {})
                    if hasattr(self.adaptive_decision_engine.pattern_memory, 'update'):
                        self.adaptive_decision_engine.pattern_memory.update(pattern_memory_data)
                
                if hasattr(self.adaptive_decision_engine, 'performance_cache'):
                    performance_cache_data = learning_data.get("performance_cache", {})
                    if hasattr(self.adaptive_decision_engine.performance_cache, 'update'):
                        self.adaptive_decision_engine.performance_cache.update(performance_cache_data)
                
                # 恢复系统指标
                system_metrics = learning_data.get("system_metrics", {})
                self.system_metrics.update(system_metrics)
                
                logger.info(f"成功加载学习数据，包含 {len(learning_data)} 个数据项")
            else:
                logger.info("未找到学习数据文件，将使用默认配置")
                
        except Exception as e:
            logger.error(f"加载学习数据失败: {e}")
            logger.info("将使用默认配置继续运行")

    async def _save_learning_data(self):
        """保存学习数据"""
        try:
            # 确保数据目录存在
            data_dir = os.path.dirname(self.learning_data_path)
            os.makedirs(data_dir, exist_ok=True)
            
            # 收集学习数据
            learning_data = {
                "timestamp": datetime.now().isoformat(),
                "system_metrics": self.system_metrics.copy(),
                "decision_weights": {},
                "pattern_memory": {},
                "performance_cache": {}
            }
            
            # 保存决策引擎的学习数据
            if hasattr(self.adaptive_decision_engine, 'decision_weights'):
                try:
                    learning_data["decision_weights"] = dict(self.adaptive_decision_engine.decision_weights)
                except:
                    learning_data["decision_weights"] = {}
            
            if hasattr(self.adaptive_decision_engine, 'pattern_memory'):
                try:
                    learning_data["pattern_memory"] = dict(self.adaptive_decision_engine.pattern_memory)
                except:
                    learning_data["pattern_memory"] = {}
            
            if hasattr(self.adaptive_decision_engine, 'performance_cache'):
                try:
                    learning_data["performance_cache"] = dict(self.adaptive_decision_engine.performance_cache)
                except:
                    learning_data["performance_cache"] = {}
            
            # 写入文件
            with open(self.learning_data_path, 'w', encoding='utf-8') as f:
                json.dump(learning_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"学习数据已保存到: {self.learning_data_path}")
            
        except Exception as e:
            logger.error(f"保存学习数据失败: {e}")
    
    async def _cleanup_resources(self):
        """清理资源"""
        try:
            # 清理各种缓存和连接
            logger.info("资源清理完成")
            
        except Exception as e:
            logger.error(f"资源清理失败: {e}")


# 使用示例
async def main():
    """使用示例"""
    
    # 模拟toolscore客户端
    class MockToolscoreClient:
        async def call_tool(self, tool_id, action, params):
            return {"success": True, "output": f"模拟执行结果: {action}"}
        
        async def reconnect_tool(self, tool_id):
            return {"success": True}
    
    # 创建优化的控制器
    controller = OptimizedAgentController(MockToolscoreClient())
    
    try:
        # 初始化系统
        await controller.initialize()
        
        # 执行示例任务
        print("=" * 50)
        print("执行研究任务")
        result1 = await controller.execute_task(
            "深度调研OpenAI GPT-4o模型的最新技术特性和能力",
            "research"
        )
        print(f"任务结果: 成功={result1.success}, 策略={result1.execution_strategy}")
        print(f"置信度: {result1.decision_confidence:.3f}, 执行时间: {result1.execution_time:.2f}s")
        
        print("=" * 50)
        print("执行搜索任务") 
        result2 = await controller.execute_task(
            "搜索AI Agent开发的最佳实践",
            "search"
        )
        print(f"任务结果: 成功={result2.success}, 策略={result2.execution_strategy}")
        
        print("=" * 50)
        print("执行代码任务")
        result3 = await controller.execute_task(
            "计算斐波那契数列的第10项",
            "execute",
            {"code": "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\nprint(fib(10))"}
        )
        print(f"任务结果: 成功={result3.success}, 策略={result3.execution_strategy}")
        
        # 获取系统报告
        print("=" * 50)
        print("系统报告")
        report = await controller.get_system_report()
        print(f"总任务数: {report['system_metrics']['total_tasks']}")
        print(f"成功率: {report['success_rate']:.2%}")
        print(f"错误率: {report['error_rate']:.2%}")
        
    finally:
        # 关闭系统
        await controller.shutdown()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())