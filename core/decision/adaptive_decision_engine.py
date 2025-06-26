"""
自适应决策引擎
解决决策逻辑僵化问题，实现从失败中学习和适应
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import pickle
import hashlib
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class DecisionType(Enum):
    """决策类型"""
    TOOL_SELECTION = "tool_selection"
    STRATEGY_SELECTION = "strategy_selection"
    EXECUTION_PATH = "execution_path"
    RESOURCE_ALLOCATION = "resource_allocation"

class ContextType(Enum):
    """上下文类型"""
    TASK_CONTEXT = "task_context"
    SYSTEM_CONTEXT = "system_context"
    HISTORICAL_CONTEXT = "historical_context"
    PERFORMANCE_CONTEXT = "performance_context"

@dataclass
class DecisionContext:
    """决策上下文"""
    task_description: str
    task_type: str
    system_state: Dict[str, Any]
    historical_patterns: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    constraints: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DecisionResult:
    """决策结果"""
    decision_id: str
    decision_type: DecisionType
    selected_option: str
    confidence: float
    reasoning: str
    alternatives: List[str]
    context_hash: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class DecisionOutcome:
    """决策结果"""
    decision_id: str
    success: bool
    execution_time: float
    error_message: Optional[str] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

class AdaptiveDecisionEngine:
    """
    自适应决策引擎
    
    核心功能：
    1. 基于历史经验的智能决策
    2. 动态学习和适应
    3. 上下文感知决策
    4. 性能驱动的选择优化
    """
    
    def __init__(self, enhanced_tool_manager, fallback_strategy_manager):
        self.enhanced_tool_manager = enhanced_tool_manager
        self.fallback_strategy_manager = fallback_strategy_manager
        
        # 决策历史记录
        self.decision_history: Dict[str, DecisionResult] = {}
        self.outcome_history: Dict[str, DecisionOutcome] = {}
        
        # 学习存储
        self.pattern_memory: Dict[str, Dict[str, Any]] = {}
        self.success_patterns: Dict[str, List[str]] = defaultdict(list)
        self.failure_patterns: Dict[str, List[str]] = defaultdict(list)
        
        # 性能指标
        self.performance_cache: Dict[str, Dict[str, float]] = {}
        
        # 上下文特征提取器
        self.context_extractors = {
            ContextType.TASK_CONTEXT: self._extract_task_features,
            ContextType.SYSTEM_CONTEXT: self._extract_system_features,
            ContextType.HISTORICAL_CONTEXT: self._extract_historical_features,
            ContextType.PERFORMANCE_CONTEXT: self._extract_performance_features
        }
        
        # 决策权重（可以通过学习调整）
        self.decision_weights = {
            "historical_success": 0.4,
            "current_performance": 0.3,
            "context_similarity": 0.2,
            "tool_reliability": 0.1
        }
        
        # 最近决策队列（用于快速学习）
        self.recent_decisions = deque(maxlen=100)
    
    async def make_decision(self, decision_type: DecisionType, context: DecisionContext, 
                          options: List[str]) -> DecisionResult:
        """
        做出自适应决策
        
        Args:
            decision_type: 决策类型
            context: 决策上下文
            options: 可选选项
            
        Returns:
            决策结果
        """
        logger.info(f"开始决策: {decision_type.value}, 选项数量: {len(options)}")
        
        # 生成上下文特征
        context_features = await self._generate_context_features(context)
        context_hash = self._generate_context_hash(context_features)
        
        # 获取历史相似决策
        similar_decisions = self._find_similar_decisions(context_hash, context_features)
        
        # 计算每个选项的得分
        option_scores = {}
        for option in options:
            score = await self._calculate_option_score(
                option, decision_type, context_features, similar_decisions
            )
            option_scores[option] = score
        
        # 选择最佳选项
        best_option = max(option_scores.keys(), key=lambda x: option_scores[x])
        confidence = option_scores[best_option]
        
        # 排序其他选项作为备选
        alternatives = sorted(
            [opt for opt in options if opt != best_option],
            key=lambda x: option_scores[x],
            reverse=True
        )
        
        # 生成决策推理
        reasoning = self._generate_reasoning(
            best_option, option_scores, similar_decisions, context_features
        )
        
        # 创建决策结果
        decision_result = DecisionResult(
            decision_id=self._generate_decision_id(),
            decision_type=decision_type,
            selected_option=best_option,
            confidence=confidence,
            reasoning=reasoning,
            alternatives=alternatives,
            context_hash=context_hash
        )
        
        # 记录决策
        self.decision_history[decision_result.decision_id] = decision_result
        self.recent_decisions.append(decision_result)
        
        logger.info(f"决策完成: 选择 {best_option}, 置信度: {confidence:.3f}")
        
        return decision_result
    
    async def learn_from_outcome(self, decision_id: str, outcome: DecisionOutcome):
        """
        从决策结果中学习
        
        Args:
            decision_id: 决策ID
            outcome: 执行结果
        """
        if decision_id not in self.decision_history:
            logger.warning(f"未找到决策记录: {decision_id}")
            return
        
        decision = self.decision_history[decision_id]
        self.outcome_history[decision_id] = outcome
        
        logger.info(f"学习决策结果: {decision_id}, 成功: {outcome.success}")
        
        # 更新模式记忆
        await self._update_pattern_memory(decision, outcome)
        
        # 更新性能缓存
        self._update_performance_cache(decision.selected_option, outcome)
        
        # 调整决策权重
        self._adjust_decision_weights(decision, outcome)
        
        # 更新成功/失败模式
        self._update_success_failure_patterns(decision, outcome)
    
    async def _generate_context_features(self, context: DecisionContext) -> Dict[str, Any]:
        """生成上下文特征"""
        features = {}
        
        for context_type, extractor in self.context_extractors.items():
            try:
                features[context_type.value] = await extractor(context)
            except Exception as e:
                logger.warning(f"特征提取失败 {context_type.value}: {e}")
                features[context_type.value] = {}
        
        return features
    
    async def _extract_task_features(self, context: DecisionContext) -> Dict[str, Any]:
        """提取任务特征"""
        task_desc = context.task_description.lower()
        
        # 任务类型分析
        task_keywords = {
            "search": ["搜索", "查找", "search", "find"],
            "research": ["研究", "调研", "分析", "research", "analyze"],
            "execute": ["执行", "运行", "计算", "execute", "run", "compute"],
            "install": ["安装", "部署", "配置", "install", "setup", "configure"]
        }
        
        detected_types = []
        for task_type, keywords in task_keywords.items():
            if any(keyword in task_desc for keyword in keywords):
                detected_types.append(task_type)
        
        return {
            "task_type": context.task_type,
            "detected_types": detected_types,
            "task_length": len(context.task_description),
            "complexity_score": self._estimate_task_complexity(context.task_description),
            "priority": context.constraints.get("priority", "medium")
        }
    
    async def _extract_system_features(self, context: DecisionContext) -> Dict[str, Any]:
        """提取系统特征"""
        system_state = context.system_state
        
        return {
            "available_tools": system_state.get("available_tools", 0),
            "system_load": system_state.get("system_load", 0.5),
            "memory_usage": system_state.get("memory_usage", 0.5),
            "network_status": system_state.get("network_status", "unknown"),
            "time_of_day": datetime.now().hour,
            "weekday": datetime.now().weekday()
        }
    
    async def _extract_historical_features(self, context: DecisionContext) -> Dict[str, Any]:
        """提取历史特征"""
        historical = context.historical_patterns
        
        return {
            "similar_tasks_count": historical.get("similar_tasks_count", 0),
            "recent_success_rate": historical.get("recent_success_rate", 0.5),
            "preferred_tools": historical.get("preferred_tools", []),
            "common_failure_reasons": historical.get("common_failure_reasons", [])
        }
    
    async def _extract_performance_features(self, context: DecisionContext) -> Dict[str, Any]:
        """提取性能特征"""
        performance = context.performance_metrics
        
        return {
            "average_execution_time": performance.get("average_execution_time", 60.0),
            "success_rate": performance.get("success_rate", 0.5),
            "error_rate": performance.get("error_rate", 0.1),
            "resource_usage": performance.get("resource_usage", 0.5)
        }
    
    def _generate_context_hash(self, features: Dict[str, Any]) -> str:
        """生成上下文哈希"""
        # 提取关键特征生成哈希
        key_features = {
            "task_type": features.get("task_context", {}).get("task_type"),
            "detected_types": features.get("task_context", {}).get("detected_types"),
            "complexity": features.get("task_context", {}).get("complexity_score"),
            "system_load": features.get("system_context", {}).get("system_load")
        }
        
        return hashlib.md5(json.dumps(key_features, sort_keys=True).encode()).hexdigest()[:8]
    
    def _find_similar_decisions(self, context_hash: str, features: Dict[str, Any]) -> List[DecisionResult]:
        """查找相似的历史决策"""
        similar_decisions = []
        
        for decision in self.decision_history.values():
            if decision.context_hash == context_hash:
                similar_decisions.append(decision)
            else:
                # 计算特征相似度
                similarity = self._calculate_feature_similarity(decision, features)
                if similarity > 0.7:  # 相似度阈值
                    similar_decisions.append(decision)
        
        # 按时间排序，最近的决策权重更高
        return sorted(similar_decisions, key=lambda x: x.timestamp, reverse=True)[:10]
    
    async def _calculate_option_score(self, option: str, decision_type: DecisionType, 
                                    features: Dict[str, Any], similar_decisions: List[DecisionResult]) -> float:
        """计算选项得分"""
        score = 0.0
        
        # 1. 历史成功率
        historical_score = self._calculate_historical_score(option, similar_decisions)
        score += historical_score * self.decision_weights["historical_success"]
        
        # 2. 当前性能指标
        performance_score = self._calculate_performance_score(option)
        score += performance_score * self.decision_weights["current_performance"]
        
        # 3. 上下文相似度
        context_score = self._calculate_context_score(option, features)
        score += context_score * self.decision_weights["context_similarity"]
        
        # 4. 工具可靠性
        reliability_score = self._calculate_reliability_score(option)
        score += reliability_score * self.decision_weights["tool_reliability"]
        
        return min(score, 1.0)  # 确保得分不超过1.0
    
    def _calculate_historical_score(self, option: str, similar_decisions: List[DecisionResult]) -> float:
        """计算历史成功率得分"""
        if not similar_decisions:
            return 0.5  # 默认中等得分
        
        relevant_decisions = [d for d in similar_decisions if d.selected_option == option]
        if not relevant_decisions:
            return 0.3  # 没有历史记录时给较低得分
        
        # 计算成功率
        success_count = 0
        for decision in relevant_decisions:
            if decision.decision_id in self.outcome_history:
                outcome = self.outcome_history[decision.decision_id]
                if outcome.success:
                    success_count += 1
        
        return success_count / len(relevant_decisions) if relevant_decisions else 0.5
    
    def _calculate_performance_score(self, option: str) -> float:
        """计算当前性能得分"""
        if option not in self.performance_cache:
            return 0.5  # 默认中等得分
        
        metrics = self.performance_cache[option]
        
        # 综合多个性能指标
        success_rate = metrics.get("success_rate", 0.5)
        speed_score = 1.0 - min(metrics.get("average_time", 60.0) / 120.0, 1.0)  # 标准化到0-1
        reliability_score = 1.0 - metrics.get("error_rate", 0.1)
        
        return (success_rate * 0.5 + speed_score * 0.3 + reliability_score * 0.2)
    
    def _calculate_context_score(self, option: str, features: Dict[str, Any]) -> float:
        """计算上下文匹配得分"""
        # 基于任务类型匹配
        task_features = features.get("task_context", {})
        detected_types = task_features.get("detected_types", [])
        
        # 工具-任务类型匹配表
        tool_task_match = {
            "mcp-deepsearch": ["research", "search"],
            "microsandbox-mcp-server": ["execute", "compute"],
            "mcp-search-tool": ["install", "setup"],
            "basic_web_search": ["search", "simple"],
            "knowledge_synthesis": ["analyze", "research"]
        }
        
        if option in tool_task_match:
            matched_types = set(tool_task_match[option]) & set(detected_types)
            return len(matched_types) / max(len(detected_types), 1) if detected_types else 0.5
        
        return 0.4  # 未知选项的默认得分
    
    def _calculate_reliability_score(self, option: str) -> float:
        """计算工具可靠性得分"""
        # 从工具管理器获取可靠性信息
        if hasattr(self.enhanced_tool_manager, 'tool_registry'):
            if option in self.enhanced_tool_manager.tool_registry:
                tool_spec = self.enhanced_tool_manager.tool_registry[option]
                return tool_spec.reliability_score
        
        # 基于失败历史计算
        recent_failures = self.enhanced_tool_manager._get_recent_failures(option, 24)
        if recent_failures == 0:
            return 1.0
        elif recent_failures <= 2:
            return 0.7
        elif recent_failures <= 5:
            return 0.4
        else:
            return 0.1
    
    def _calculate_feature_similarity(self, decision: DecisionResult, current_features: Dict[str, Any]) -> float:
        """计算特征相似度"""
        # 简单的特征相似度计算
        # 实际应用中可以使用更复杂的相似度计算方法
        if decision.context_hash in self.pattern_memory:
            historical_features = self.pattern_memory[decision.context_hash]
            
            # 计算关键特征的相似度
            task_similarity = self._compare_task_features(
                current_features.get("task_context", {}),
                historical_features.get("task_context", {})
            )
            
            system_similarity = self._compare_system_features(
                current_features.get("system_context", {}),
                historical_features.get("system_context", {})
            )
            
            return (task_similarity * 0.7 + system_similarity * 0.3)
        
        return 0.0
    
    def _compare_task_features(self, current: Dict[str, Any], historical: Dict[str, Any]) -> float:
        """比较任务特征"""
        if not current or not historical:
            return 0.0
        
        # 任务类型匹配
        type_match = 1.0 if current.get("task_type") == historical.get("task_type") else 0.0
        
        # 检测类型匹配
        current_types = set(current.get("detected_types", []))
        historical_types = set(historical.get("detected_types", []))
        
        if current_types and historical_types:
            type_overlap = len(current_types & historical_types) / len(current_types | historical_types)
        else:
            type_overlap = 0.0
        
        # 复杂度相似性
        current_complexity = current.get("complexity_score", 0.5)
        historical_complexity = historical.get("complexity_score", 0.5)
        complexity_similarity = 1.0 - abs(current_complexity - historical_complexity)
        
        return (type_match * 0.4 + type_overlap * 0.4 + complexity_similarity * 0.2)
    
    def _compare_system_features(self, current: Dict[str, Any], historical: Dict[str, Any]) -> float:
        """比较系统特征"""
        if not current or not historical:
            return 0.0
        
        # 系统负载相似性
        current_load = current.get("system_load", 0.5)
        historical_load = historical.get("system_load", 0.5)
        load_similarity = 1.0 - abs(current_load - historical_load)
        
        # 可用工具数量相似性
        current_tools = current.get("available_tools", 0)
        historical_tools = historical.get("available_tools", 0)
        if max(current_tools, historical_tools) > 0:
            tools_similarity = min(current_tools, historical_tools) / max(current_tools, historical_tools)
        else:
            tools_similarity = 1.0
        
        return (load_similarity * 0.6 + tools_similarity * 0.4)
    
    def _estimate_task_complexity(self, task_description: str) -> float:
        """估算任务复杂度"""
        # 基于任务描述的复杂度估算
        complexity_indicators = {
            "简单": ["查看", "显示", "列出", "获取", "show", "list", "get"],
            "中等": ["分析", "比较", "搜索", "处理", "analyze", "compare", "search", "process"],
            "复杂": ["研究", "深度", "综合", "优化", "research", "deep", "comprehensive", "optimize"],
            "高复杂": ["架构", "设计", "重构", "全面", "architecture", "design", "refactor", "comprehensive"]
        }
        
        task_lower = task_description.lower()
        max_complexity = 0.0
        
        for level, keywords in complexity_indicators.items():
            if any(keyword in task_lower for keyword in keywords):
                if level == "简单":
                    max_complexity = max(max_complexity, 0.2)
                elif level == "中等":
                    max_complexity = max(max_complexity, 0.5)
                elif level == "复杂":
                    max_complexity = max(max_complexity, 0.8)
                elif level == "高复杂":
                    max_complexity = max(max_complexity, 1.0)
        
        # 考虑描述长度
        length_factor = min(len(task_description) / 200.0, 1.0)
        
        return max(max_complexity, length_factor * 0.3)
    
    def _generate_reasoning(self, selected_option: str, scores: Dict[str, float], 
                          similar_decisions: List[DecisionResult], features: Dict[str, Any]) -> str:
        """生成决策推理"""
        reasoning_parts = []
        
        # 选择原因
        score = scores[selected_option]
        reasoning_parts.append(f"选择 {selected_option}，综合得分: {score:.3f}")
        
        # 历史经验
        if similar_decisions:
            historical_success = len([d for d in similar_decisions 
                                    if d.selected_option == selected_option and 
                                    d.decision_id in self.outcome_history and 
                                    self.outcome_history[d.decision_id].success])
            reasoning_parts.append(f"历史类似决策: {len(similar_decisions)}次，{selected_option}成功: {historical_success}次")
        
        # 任务特征匹配
        task_features = features.get("task_context", {})
        if task_features:
            detected_types = task_features.get("detected_types", [])
            if detected_types:
                reasoning_parts.append(f"任务类型匹配: {', '.join(detected_types)}")
        
        # 性能考虑
        if selected_option in self.performance_cache:
            perf = self.performance_cache[selected_option]
            reasoning_parts.append(f"性能指标 - 成功率: {perf.get('success_rate', 0):.2f}, 平均时间: {perf.get('average_time', 0):.1f}s")
        
        return "; ".join(reasoning_parts)
    
    async def _update_pattern_memory(self, decision: DecisionResult, outcome: DecisionOutcome):
        """更新模式记忆"""
        context_hash = decision.context_hash
        
        if context_hash not in self.pattern_memory:
            self.pattern_memory[context_hash] = {
                "decisions": [],
                "outcomes": [],
                "patterns": {}
            }
        
        memory = self.pattern_memory[context_hash]
        memory["decisions"].append({
            "option": decision.selected_option,
            "confidence": decision.confidence,
            "timestamp": decision.timestamp
        })
        memory["outcomes"].append({
            "success": outcome.success,
            "execution_time": outcome.execution_time,
            "timestamp": outcome.timestamp
        })
        
        # 更新模式统计
        self._update_pattern_statistics(memory)
    
    def _update_pattern_statistics(self, memory: Dict[str, Any]):
        """更新模式统计"""
        decisions = memory["decisions"]
        outcomes = memory["outcomes"]
        
        if len(decisions) != len(outcomes):
            return
        
        # 计算成功率
        success_rate = sum(1 for o in outcomes if o["success"]) / len(outcomes)
        
        # 计算平均执行时间
        avg_time = sum(o["execution_time"] for o in outcomes) / len(outcomes)
        
        # 最常用的选项
        option_counts = defaultdict(int)
        for d in decisions:
            option_counts[d["option"]] += 1
        
        most_used_option = max(option_counts.keys(), key=lambda x: option_counts[x]) if option_counts else None
        
        memory["patterns"] = {
            "success_rate": success_rate,
            "average_execution_time": avg_time,
            "most_used_option": most_used_option,
            "total_decisions": len(decisions),
            "last_updated": datetime.now()
        }
    
    def _update_performance_cache(self, option: str, outcome: DecisionOutcome):
        """更新性能缓存"""
        if option not in self.performance_cache:
            self.performance_cache[option] = {
                "success_count": 0,
                "total_count": 0,
                "total_time": 0.0,
                "error_count": 0
            }
        
        cache = self.performance_cache[option]
        cache["total_count"] += 1
        cache["total_time"] += outcome.execution_time
        
        if outcome.success:
            cache["success_count"] += 1
        else:
            cache["error_count"] += 1
        
        # 计算派生指标
        cache["success_rate"] = cache["success_count"] / cache["total_count"]
        cache["average_time"] = cache["total_time"] / cache["total_count"]
        cache["error_rate"] = cache["error_count"] / cache["total_count"]
    
    def _update_success_failure_patterns(self, decision: DecisionResult, outcome: DecisionOutcome):
        """更新成功/失败模式"""
        option = decision.selected_option
        
        if outcome.success:
            self.success_patterns[option].append(decision.context_hash)
        else:
            self.failure_patterns[option].append(decision.context_hash)
        
        # 保持最近100个记录
        self.success_patterns[option] = self.success_patterns[option][-100:]
        self.failure_patterns[option] = self.failure_patterns[option][-100:]
    
    def _adjust_decision_weights(self, decision: DecisionResult, outcome: DecisionOutcome):
        """调整决策权重"""
        # 基于结果调整权重（简单的强化学习）
        if outcome.success:
            # 成功时增加权重
            if decision.confidence > 0.8:
                self.decision_weights["historical_success"] *= 1.01
            if outcome.execution_time < 30:  # 快速执行
                self.decision_weights["current_performance"] *= 1.01
        else:
            # 失败时减少权重
            if decision.confidence > 0.8:  # 高置信度但失败
                self.decision_weights["historical_success"] *= 0.99
            if outcome.execution_time > 60:  # 执行时间长
                self.decision_weights["current_performance"] *= 0.99
        
        # 归一化权重
        total_weight = sum(self.decision_weights.values())
        for key in self.decision_weights:
            self.decision_weights[key] /= total_weight
    
    def _generate_decision_id(self) -> str:
        """生成决策ID"""
        return f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.decision_history)}"
    
    def get_learning_report(self) -> Dict[str, Any]:
        """获取学习报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_decisions": len(self.decision_history),
            "total_outcomes": len(self.outcome_history),
            "success_rate": self._calculate_overall_success_rate(),
            "decision_weights": self.decision_weights.copy(),
            "pattern_memory_size": len(self.pattern_memory),
            "performance_cache_size": len(self.performance_cache),
            "top_performing_options": self._get_top_performing_options(),
            "recent_learning_trends": self._analyze_recent_trends()
        }
    
    def _calculate_overall_success_rate(self) -> float:
        """计算整体成功率"""
        if not self.outcome_history:
            return 0.0
        
        successful_outcomes = sum(1 for o in self.outcome_history.values() if o.success)
        return successful_outcomes / len(self.outcome_history)
    
    def _get_top_performing_options(self) -> List[Dict[str, Any]]:
        """获取表现最佳的选项"""
        options_performance = []
        
        for option, cache in self.performance_cache.items():
            if cache["total_count"] >= 3:  # 至少有3次执行记录
                options_performance.append({
                    "option": option,
                    "success_rate": cache["success_rate"],
                    "average_time": cache["average_time"],
                    "total_executions": cache["total_count"]
                })
        
        return sorted(options_performance, key=lambda x: x["success_rate"], reverse=True)[:5]
    
    def _analyze_recent_trends(self) -> Dict[str, Any]:
        """分析最近的学习趋势"""
        if len(self.recent_decisions) < 10:
            return {"message": "数据不足以分析趋势"}
        
        recent_20 = list(self.recent_decisions)[-20:]
        recent_10 = list(self.recent_decisions)[-10:]
        
        # 计算最近的成功率趋势
        success_rate_20 = sum(1 for d in recent_20 
                             if d.decision_id in self.outcome_history and 
                             self.outcome_history[d.decision_id].success) / len(recent_20)
        
        success_rate_10 = sum(1 for d in recent_10 
                             if d.decision_id in self.outcome_history and 
                             self.outcome_history[d.decision_id].success) / len(recent_10)
        
        # 计算置信度趋势
        avg_confidence_20 = sum(d.confidence for d in recent_20) / len(recent_20)
        avg_confidence_10 = sum(d.confidence for d in recent_10) / len(recent_10)
        
        return {
            "success_rate_trend": success_rate_10 - success_rate_20,
            "confidence_trend": avg_confidence_10 - avg_confidence_20,
            "recent_success_rate": success_rate_10,
            "recent_avg_confidence": avg_confidence_10,
            "learning_direction": "improving" if success_rate_10 > success_rate_20 else "declining"
        }