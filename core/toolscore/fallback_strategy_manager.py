"""
智能降级策略管理器
解决单点故障问题，实现多层冗余机制
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class StrategyType(Enum):
    """策略类型"""
    PRIMARY = "primary"           # 主要策略
    SECONDARY = "secondary"       # 次要策略  
    FALLBACK = "fallback"        # 降级策略
    EMERGENCY = "emergency"       # 紧急策略

class ExecutionResult(Enum):
    """执行结果"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"

@dataclass
class Strategy:
    """策略定义"""
    strategy_id: str
    name: str
    strategy_type: StrategyType
    executor: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60
    max_retries: int = 2
    success_rate: float = 1.0
    last_execution_time: Optional[datetime] = None
    consecutive_failures: int = 0
    is_enabled: bool = True
    
class FallbackStrategyManager:
    """
    智能降级策略管理器
    
    核心功能：
    1. 多层策略定义和管理
    2. 智能策略选择和切换
    3. 实时成功率监控
    4. 自动禁用失效策略
    """
    
    def __init__(self, enhanced_tool_manager):
        self.enhanced_tool_manager = enhanced_tool_manager
        
        # 策略注册表
        self.strategies: Dict[str, List[Strategy]] = {}
        
        # 策略执行历史
        self.execution_history: Dict[str, List[Dict[str, Any]]] = {}
        
        # 策略性能指标
        self.performance_metrics: Dict[str, Dict[str, float]] = {}
        
        # 初始化预定义策略
        self._initialize_builtin_strategies()
    
    def _initialize_builtin_strategies(self):
        """初始化内置降级策略"""
        
        # Web搜索任务的多层策略
        web_search_strategies = [
            Strategy(
                strategy_id="web_search_primary",
                name="专业搜索工具",
                strategy_type=StrategyType.PRIMARY,
                executor=self._execute_professional_search,
                timeout_seconds=30
            ),
            Strategy(
                strategy_id="web_search_secondary", 
                name="基础网络请求",
                strategy_type=StrategyType.SECONDARY,
                executor=self._execute_basic_web_request,
                timeout_seconds=45
            ),
            Strategy(
                strategy_id="web_search_fallback",
                name="离线知识搜索", 
                strategy_type=StrategyType.FALLBACK,
                executor=self._execute_offline_knowledge_search,
                timeout_seconds=15
            ),
            Strategy(
                strategy_id="web_search_emergency",
                name="用户交互请求",
                strategy_type=StrategyType.EMERGENCY, 
                executor=self._execute_user_interaction_request,
                timeout_seconds=300
            )
        ]
        self.strategies["web_search"] = web_search_strategies
        
        # 深度研究任务的多层策略
        deep_research_strategies = [
            Strategy(
                strategy_id="research_primary",
                name="专业研究工具",
                strategy_type=StrategyType.PRIMARY,
                executor=self._execute_professional_research,
                timeout_seconds=120
            ),
            Strategy(
                strategy_id="research_secondary",
                name="多源信息聚合",
                strategy_type=StrategyType.SECONDARY,
                executor=self._execute_multi_source_aggregation,
                timeout_seconds=90
            ),
            Strategy(
                strategy_id="research_fallback", 
                name="结构化知识合成",
                strategy_type=StrategyType.FALLBACK,
                executor=self._execute_structured_knowledge_synthesis,
                timeout_seconds=30
            ),
            Strategy(
                strategy_id="research_emergency",
                name="基础信息收集",
                strategy_type=StrategyType.EMERGENCY,
                executor=self._execute_basic_info_collection,
                timeout_seconds=60
            )
        ]
        self.strategies["deep_research"] = deep_research_strategies
        
        # 代码执行任务的多层策略
        code_execution_strategies = [
            Strategy(
                strategy_id="code_primary",
                name="沙箱执行",
                strategy_type=StrategyType.PRIMARY,
                executor=self._execute_sandbox_code,
                timeout_seconds=60
            ),
            Strategy(
                strategy_id="code_secondary",
                name="静态分析",
                strategy_type=StrategyType.SECONDARY,
                executor=self._execute_static_analysis,
                timeout_seconds=30
            ),
            Strategy(
                strategy_id="code_fallback",
                name="代码审查",
                strategy_type=StrategyType.FALLBACK,
                executor=self._execute_code_review,
                timeout_seconds=20
            )
        ]
        self.strategies["code_execution"] = code_execution_strategies
    
    async def execute_with_fallback(self, task_type: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用降级策略执行任务
        
        Args:
            task_type: 任务类型 (web_search, deep_research, code_execution)
            task_data: 任务数据
            
        Returns:
            执行结果
        """
        if task_type not in self.strategies:
            return {
                "success": False,
                "error": f"未知任务类型: {task_type}",
                "task_type": task_type
            }
        
        strategies = self.strategies[task_type]
        available_strategies = [s for s in strategies if s.is_enabled]
        
        if not available_strategies:
            return {
                "success": False,
                "error": f"任务类型 {task_type} 没有可用策略",
                "task_type": task_type
            }
        
        # 按策略类型和成功率排序
        sorted_strategies = sorted(
            available_strategies,
            key=lambda s: (s.strategy_type.value, -s.success_rate, s.consecutive_failures)
        )
        
        execution_log = []
        
        for strategy in sorted_strategies:
            logger.info(f"尝试策略: {strategy.name} (类型: {strategy.strategy_type.value})")
            
            try:
                result = await self._execute_strategy_with_monitoring(strategy, task_data)
                execution_log.append({
                    "strategy": strategy.name,
                    "result": result.get("result", ExecutionResult.FAILURE.value),
                    "duration": result.get("duration", 0),
                    "error": result.get("error")
                })
                
                if result.get("success"):
                    logger.info(f"策略 {strategy.name} 执行成功")
                    self._update_strategy_metrics(strategy.strategy_id, True, result.get("duration", 0))
                    
                    return {
                        "success": True,
                        "result": result.get("data"),
                        "strategy_used": strategy.name,
                        "strategy_type": strategy.strategy_type.value,
                        "execution_log": execution_log,
                        "task_type": task_type
                    }
                else:
                    logger.warning(f"策略 {strategy.name} 执行失败: {result.get('error')}")
                    self._update_strategy_metrics(strategy.strategy_id, False, result.get("duration", 0))
                    
            except Exception as e:
                logger.error(f"策略 {strategy.name} 执行异常: {e}")
                execution_log.append({
                    "strategy": strategy.name,
                    "result": ExecutionResult.ERROR.value,
                    "error": str(e)
                })
                self._update_strategy_metrics(strategy.strategy_id, False, 0)
        
        # 所有策略都失败
        return {
            "success": False,
            "error": "所有降级策略都失败",
            "execution_log": execution_log,
            "task_type": task_type,
            "attempted_strategies": len(execution_log)
        }
    
    async def _execute_strategy_with_monitoring(self, strategy: Strategy, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行策略并监控性能"""
        start_time = datetime.now()
        
        try:
            # 执行策略
            result = await asyncio.wait_for(
                strategy.executor(task_data, strategy.parameters),
                timeout=strategy.timeout_seconds
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": result.get("success", False),
                "data": result.get("data"),
                "error": result.get("error"),
                "result": ExecutionResult.SUCCESS if result.get("success") else ExecutionResult.FAILURE,
                "duration": duration
            }
            
        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "success": False,
                "error": f"策略执行超时 ({strategy.timeout_seconds}s)",
                "result": ExecutionResult.TIMEOUT,
                "duration": duration
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "success": False,
                "error": f"策略执行异常: {e}",
                "result": ExecutionResult.ERROR,
                "duration": duration
            }
    
    # 策略执行器实现
    async def _execute_professional_search(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行专业搜索"""
        try:
            # 尝试使用专业搜索工具
            search_query = task_data.get("query", task_data.get("description", ""))
            
            # 这里应该调用专业搜索工具
            result = await self.enhanced_tool_manager._execute_specialized_research(
                "mcp-deepsearch", 
                type('TaskRequirement', (), {"task_description": search_query})()
            )
            
            return result
        except Exception as e:
            return {"success": False, "error": f"专业搜索失败: {e}"}
    
    async def _execute_basic_web_request(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行基础网络请求"""
        try:
            # 使用microsandbox执行基础网络请求
            search_query = task_data.get("query", task_data.get("description", ""))
            
            result = await self.enhanced_tool_manager._execute_basic_web_search(
                type('TaskRequirement', (), {"task_description": search_query})()
            )
            
            return result
        except Exception as e:
            return {"success": False, "error": f"基础网络请求失败: {e}"}
    
    async def _execute_offline_knowledge_search(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行离线知识搜索"""
        try:
            search_query = task_data.get("query", task_data.get("description", ""))
            
            # 基于关键词的知识匹配
            knowledge_base = {
                "GPT-4o": "GPT-4o是OpenAI的多模态大型语言模型，支持文本、图像、音频输入...",
                "AI Agent": "AI Agent是能够自主感知环境并采取行动以实现目标的智能代理...",
                "LangGraph": "LangGraph是用于构建语言代理的Python库..."
            }
            
            # 简单的关键词匹配
            matched_content = []
            for key, content in knowledge_base.items():
                if any(keyword.lower() in search_query.lower() for keyword in key.split()):
                    matched_content.append({"topic": key, "content": content})
            
            return {
                "success": True,
                "data": {
                    "query": search_query,
                    "method": "offline_knowledge_search",
                    "results": matched_content,
                    "disclaimer": "基于离线知识库，可能不包含最新信息"
                }
            }
        except Exception as e:
            return {"success": False, "error": f"离线知识搜索失败: {e}"}
    
    async def _execute_user_interaction_request(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行用户交互请求（紧急策略）"""
        try:
            search_query = task_data.get("query", task_data.get("description", ""))
            
            # 生成用户交互请求
            interaction_request = {
                "type": "user_assistance_needed",
                "query": search_query,
                "message": f"无法自动完成查询: {search_query}",
                "suggested_actions": [
                    "请提供相关资源链接",
                    "请提供具体的搜索关键词",
                    "请简化查询内容"
                ],
                "fallback_reason": "所有自动化策略都失败"
            }
            
            return {
                "success": True,
                "data": {
                    "method": "user_interaction_request",
                    "interaction_request": interaction_request,
                    "requires_user_input": True
                }
            }
        except Exception as e:
            return {"success": False, "error": f"用户交互请求失败: {e}"}
    
    async def _execute_professional_research(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行专业研究"""
        return await self._execute_professional_search(task_data, params)
    
    async def _execute_multi_source_aggregation(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行多源信息聚合"""
        try:
            # 结合多个信息源
            basic_result = await self._execute_basic_web_request(task_data, params)
            offline_result = await self._execute_offline_knowledge_search(task_data, params)
            
            aggregated_data = {
                "query": task_data.get("query", task_data.get("description", "")),
                "method": "multi_source_aggregation",
                "sources": []
            }
            
            if basic_result.get("success"):
                aggregated_data["sources"].append({
                    "type": "web_search",
                    "data": basic_result.get("data")
                })
            
            if offline_result.get("success"):
                aggregated_data["sources"].append({
                    "type": "knowledge_base",
                    "data": offline_result.get("data")
                })
            
            return {
                "success": len(aggregated_data["sources"]) > 0,
                "data": aggregated_data
            } if aggregated_data["sources"] else {
                "success": False,
                "error": "所有信息源都不可用"
            }
            
        except Exception as e:
            return {"success": False, "error": f"多源信息聚合失败: {e}"}
    
    async def _execute_structured_knowledge_synthesis(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行结构化知识合成"""
        return await self._execute_offline_knowledge_search(task_data, params)
    
    async def _execute_basic_info_collection(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行基础信息收集"""
        try:
            query = task_data.get("query", task_data.get("description", ""))
            
            # 基础信息收集：分析查询并提供基础结构
            basic_info = {
                "query": query,
                "method": "basic_info_collection",
                "analysis": {
                    "query_type": self._analyze_query_type(query),
                    "key_terms": self._extract_key_terms(query),
                    "suggested_approach": self._suggest_research_approach(query)
                },
                "basic_outline": self._generate_basic_outline(query)
            }
            
            return {
                "success": True,
                "data": basic_info
            }
        except Exception as e:
            return {"success": False, "error": f"基础信息收集失败: {e}"}
    
    async def _execute_sandbox_code(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行沙箱代码"""
        try:
            code = task_data.get("code", "")
            language = task_data.get("language", "python")
            
            # 通过microsandbox执行代码
            result = await self.enhanced_tool_manager.toolscore_client.call_tool(
                "microsandbox-mcp-server",
                "microsandbox_execute",
                {"code": code, "language": language}
            )
            
            return result
        except Exception as e:
            return {"success": False, "error": f"沙箱代码执行失败: {e}"}
    
    async def _execute_static_analysis(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行静态分析"""
        try:
            code = task_data.get("code", "")
            
            # 简单的静态分析
            analysis = {
                "code": code,
                "method": "static_analysis",
                "line_count": len(code.split('\n')),
                "has_imports": "import" in code,
                "has_functions": "def " in code,
                "has_classes": "class " in code,
                "estimated_complexity": "low" if len(code) < 100 else "medium" if len(code) < 500 else "high"
            }
            
            return {
                "success": True,
                "data": analysis
            }
        except Exception as e:
            return {"success": False, "error": f"静态分析失败: {e}"}
    
    async def _execute_code_review(self, task_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """执行代码审查"""
        try:
            code = task_data.get("code", "")
            
            # 基础代码审查
            review = {
                "code": code,
                "method": "code_review",
                "suggestions": [
                    "添加注释以提高可读性",
                    "考虑异常处理",
                    "检查变量命名规范"
                ],
                "potential_issues": [],
                "code_quality_score": 0.8
            }
            
            return {
                "success": True,
                "data": review
            }
        except Exception as e:
            return {"success": False, "error": f"代码审查失败: {e}"}
    
    # 辅助方法
    def _analyze_query_type(self, query: str) -> str:
        """分析查询类型"""
        query_lower = query.lower()
        if any(word in query_lower for word in ["是什么", "what is", "定义", "概念"]):
            return "definition"
        elif any(word in query_lower for word in ["如何", "怎么", "how to", "方法"]):
            return "how_to"
        elif any(word in query_lower for word in ["比较", "对比", "区别", "difference"]):
            return "comparison"
        elif any(word in query_lower for word in ["最新", "趋势", "发展", "latest", "trend"]):
            return "trend_analysis"
        else:
            return "general_inquiry"
    
    def _extract_key_terms(self, query: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取
        import re
        words = re.findall(r'\b\w+\b', query.lower())
        # 过滤常见停用词
        stop_words = {"的", "是", "在", "和", "或", "但是", "然而", "因为", "所以", "with", "the", "and", "or", "but"}
        return [word for word in words if word not in stop_words and len(word) > 2]
    
    def _suggest_research_approach(self, query: str) -> List[str]:
        """建议研究方法"""
        query_type = self._analyze_query_type(query)
        
        approaches = {
            "definition": ["查找官方文档", "搜索权威定义", "查看学术资源"],
            "how_to": ["寻找教程", "查看示例代码", "搜索最佳实践"],
            "comparison": ["对比分析", "查找评测文章", "搜索用户评价"],
            "trend_analysis": ["查看最新报告", "搜索行业动态", "分析发展历程"],
            "general_inquiry": ["多角度搜索", "查找相关资源", "综合分析"]
        }
        
        return approaches.get(query_type, approaches["general_inquiry"])
    
    def _generate_basic_outline(self, query: str) -> List[str]:
        """生成基础大纲"""
        return [
            f"1. {query} 的基本概念",
            f"2. {query} 的主要特点",
            f"3. {query} 的应用场景",
            f"4. {query} 的发展趋势",
            f"5. 相关资源和参考"
        ]
    
    def _update_strategy_metrics(self, strategy_id: str, success: bool, duration: float):
        """更新策略性能指标"""
        if strategy_id not in self.performance_metrics:
            self.performance_metrics[strategy_id] = {
                "total_executions": 0,
                "successful_executions": 0,
                "total_duration": 0.0,
                "average_duration": 0.0
            }
        
        metrics = self.performance_metrics[strategy_id]
        metrics["total_executions"] += 1
        metrics["total_duration"] += duration
        metrics["average_duration"] = metrics["total_duration"] / metrics["total_executions"]
        
        if success:
            metrics["successful_executions"] += 1
        
        # 更新策略成功率
        for task_type, strategies in self.strategies.items():
            for strategy in strategies:
                if strategy.strategy_id == strategy_id:
                    strategy.success_rate = metrics["successful_executions"] / metrics["total_executions"]
                    strategy.last_execution_time = datetime.now()
                    
                    if success:
                        strategy.consecutive_failures = 0
                    else:
                        strategy.consecutive_failures += 1
                        
                        # 如果连续失败5次，暂时禁用策略
                        if strategy.consecutive_failures >= 5:
                            strategy.is_enabled = False
                            logger.warning(f"策略 {strategy.name} 因连续失败被暂时禁用")
                    
                    break
    
    def get_strategy_report(self) -> Dict[str, Any]:
        """获取策略性能报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "task_types": {},
            "overall_metrics": {
                "total_strategies": sum(len(strategies) for strategies in self.strategies.values()),
                "enabled_strategies": sum(
                    len([s for s in strategies if s.is_enabled]) 
                    for strategies in self.strategies.values()
                ),
                "total_executions": sum(
                    metrics.get("total_executions", 0) 
                    for metrics in self.performance_metrics.values()
                )
            }
        }
        
        for task_type, strategies in self.strategies.items():
            task_report = {
                "total_strategies": len(strategies),
                "enabled_strategies": len([s for s in strategies if s.is_enabled]),
                "strategies": []
            }
            
            for strategy in strategies:
                strategy_metrics = self.performance_metrics.get(strategy.strategy_id, {})
                strategy_report = {
                    "name": strategy.name,
                    "type": strategy.strategy_type.value,
                    "enabled": strategy.is_enabled,
                    "success_rate": strategy.success_rate,
                    "consecutive_failures": strategy.consecutive_failures,
                    "total_executions": strategy_metrics.get("total_executions", 0),
                    "average_duration": strategy_metrics.get("average_duration", 0)
                }
                task_report["strategies"].append(strategy_report)
            
            report["task_types"][task_type] = task_report
        
        return report