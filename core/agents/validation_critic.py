"""
ValidationCritic Agent - 智能错误分析和修正代理
处理连续失败场景，提供智能的错误分析和修正建议
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import traceback

from core.llm_client import LLMClient
from core.toolscore.structured_tools import ToolValidationError
from core.recovery.intelligent_error_recovery import ErrorEvent, ErrorSeverity, ErrorCategory

logger = logging.getLogger(__name__)

class CriticStrategy(Enum):
    """批评策略"""
    TOOL_MISMATCH_ANALYSIS = "tool_mismatch_analysis"      # 工具不匹配分析
    PARAMETER_CORRECTION = "parameter_correction"          # 参数修正
    ALTERNATIVE_APPROACH = "alternative_approach"          # 替代方案
    CONTEXT_REFRAME = "context_reframe"                   # 上下文重构
    SKILL_GAP_IDENTIFICATION = "skill_gap_identification"  # 技能缺口识别

@dataclass
class FailurePattern:
    """失败模式"""
    pattern_id: str
    description: str
    frequency: int
    tool_id: str
    action: str
    error_type: str
    context_keywords: List[str] = field(default_factory=list)
    last_occurrence: datetime = field(default_factory=datetime.now)
    correction_success_rate: float = 0.0

@dataclass
class ExecutablePatch:
    """🔧 P1-2新增：可执行的修正patch"""
    patch_id: str
    patch_type: str  # 'action_correction', 'parameter_mapping', 'tool_substitution'
    original_action: Dict[str, Any]
    patched_action: Dict[str, Any]
    diff_details: str  # 具体的修改说明
    validation_steps: List[str] = field(default_factory=list)  # 验证步骤
    rollback_patch: Optional[Dict[str, Any]] = None  # 回滚patch

@dataclass 
class ExecutablePatch:
    """🔧 P1-2修复：可执行的修正补丁"""
    patch_id: str
    operation_type: str  # 'replace_action', 'fix_parameters', 'substitute_tool'
    target_field: str    # 要修改的字段名
    original_value: Any  # 原始值
    corrected_value: Any # 修正后的值
    validation_steps: List[str] = field(default_factory=list)  # 验证步骤
    rollback_instructions: str = ""  # 回滚指令

@dataclass
class CorrectionSuggestion:
    """修正建议 - 增强版支持可执行补丁"""
    suggestion_id: str
    strategy: CriticStrategy
    confidence: float
    original_request: Dict[str, Any]
    corrected_request: Dict[str, Any]
    reasoning: str
    alternative_options: List[Dict[str, Any]] = field(default_factory=list)
    estimated_success_rate: float = 0.0
    requires_tool_installation: bool = False
    suggested_tools: List[str] = field(default_factory=list)
    # 🔧 P1-2新增：可执行补丁支持
    executable_patches: List[ExecutablePatch] = field(default_factory=list)
    auto_apply: bool = False  # 是否可以自动应用
    # 🔧 P1-2新增：可执行patch
    executable_patch: Optional[ExecutablePatch] = None

@dataclass
class CriticAnalysis:
    """批评分析结果"""
    analysis_id: str
    error_root_cause: str
    failure_patterns: List[FailurePattern]
    suggestions: List[CorrectionSuggestion]
    overall_confidence: float
    analysis_time: float
    timestamp: datetime = field(default_factory=datetime.now)

class ValidationCritic:
    """
    验证批评家代理
    
    职责：
    1. 分析连续失败的模式
    2. 提供智能的修正建议  
    3. 学习失败模式以改进未来决策
    4. 识别系统性问题并提出解决方案
    """
    
    def __init__(self, llm_client: LLMClient, available_tools: List[str] = None):
        self.llm_client = llm_client
        self.available_tools = available_tools or []
        
        # 失败历史记录
        self.failure_history: List[ErrorEvent] = []
        self.failure_patterns: Dict[str, FailurePattern] = {}
        
        # 成功修正记录
        self.successful_corrections: List[CorrectionSuggestion] = []
        
        # 统计信息
        self.stats = {
            "total_analyses": 0,
            "successful_corrections": 0,
            "failed_corrections": 0,
            "patterns_identified": 0,
            "avg_analysis_time": 0.0
        }
        
        # 配置参数
        self.max_failure_history = 100
        self.pattern_min_frequency = 2
        self.high_confidence_threshold = 0.8
        
        logger.info("🎯 ValidationCritic Agent初始化完成")
    
    def update_available_tools(self, tools: List[str]):
        """更新可用工具列表"""
        self.available_tools = tools
        logger.info(f"🔄 ValidationCritic工具列表已更新: {len(tools)}个工具")
    
    def record_failure(self, error_event: ErrorEvent):
        """记录失败事件"""
        self.failure_history.append(error_event)
        
        # 限制历史记录长度
        if len(self.failure_history) > self.max_failure_history:
            self.failure_history = self.failure_history[-self.max_failure_history:]
        
        # 更新失败模式
        self._update_failure_patterns(error_event)
        
        logger.debug(f"📝 记录失败事件: {error_event.error_type} - {error_event.component}")
    
    def _update_failure_patterns(self, error_event: ErrorEvent):
        """更新失败模式"""
        # 生成模式ID
        pattern_id = f"{error_event.component}_{error_event.error_type}_{error_event.context.get('tool_id', 'unknown')}_{error_event.context.get('action', 'unknown')}"
        
        if pattern_id in self.failure_patterns:
            # 更新现有模式
            pattern = self.failure_patterns[pattern_id]
            pattern.frequency += 1
            pattern.last_occurrence = error_event.timestamp
        else:
            # 创建新模式
            pattern = FailurePattern(
                pattern_id=pattern_id,
                description=f"{error_event.error_type} in {error_event.component}",
                frequency=1,
                tool_id=error_event.context.get('tool_id', 'unknown'),
                action=error_event.context.get('action', 'unknown'),
                error_type=error_event.error_type,
                context_keywords=self._extract_keywords(error_event.error_message),
                last_occurrence=error_event.timestamp
            )
            self.failure_patterns[pattern_id] = pattern
            self.stats["patterns_identified"] += 1
    
    def _extract_keywords(self, error_message: str) -> List[str]:
        """从错误消息中提取关键词"""
        if not error_message:
            return []
        
        # 简单的关键词提取
        keywords = []
        
        # 常见错误关键词
        error_keywords = [
            "unsupported", "invalid", "missing", "timeout", "connection",
            "parameter", "argument", "schema", "format", "permission"
        ]
        
        message_lower = error_message.lower()
        for keyword in error_keywords:
            if keyword in message_lower:
                keywords.append(keyword)
        
        return keywords
    
    async def review_failed_action(self, error_history: List[ErrorEvent], context: Dict[str, Any] = None) -> CriticAnalysis:
        """
        审查失败的动作并提供修正建议
        
        Args:
            error_history: 最近的错误历史
            context: 额外的上下文信息
            
        Returns:
            CriticAnalysis: 分析结果和修正建议
        """
        start_time = asyncio.get_event_loop().time()
        self.stats["total_analyses"] += 1
        
        try:
            # 记录所有失败事件
            for error in error_history:
                self.record_failure(error)
            
            # 分析失败模式
            relevant_patterns = self._identify_relevant_patterns(error_history)
            
            # 生成修正建议
            suggestions = await self._generate_correction_suggestions(error_history, relevant_patterns, context)
            
            # 分析根本原因
            root_cause = await self._analyze_root_cause(error_history, relevant_patterns)
            
            # 计算整体置信度
            overall_confidence = self._calculate_overall_confidence(suggestions)
            
            analysis_time = asyncio.get_event_loop().time() - start_time
            self.stats["avg_analysis_time"] = (self.stats["avg_analysis_time"] * (self.stats["total_analyses"] - 1) + analysis_time) / self.stats["total_analyses"]
            
            analysis = CriticAnalysis(
                analysis_id=f"critic_analysis_{int(start_time)}",
                error_root_cause=root_cause,
                failure_patterns=relevant_patterns,
                suggestions=suggestions,
                overall_confidence=overall_confidence,
                analysis_time=analysis_time
            )
            
            logger.info(f"🎯 ValidationCritic分析完成: {len(suggestions)}个建议, 置信度: {overall_confidence:.2f}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ ValidationCritic分析失败: {e}")
            logger.error(traceback.format_exc())
            
            # 返回基础分析
            analysis_time = asyncio.get_event_loop().time() - start_time
            return CriticAnalysis(
                analysis_id=f"critic_analysis_error_{int(start_time)}",
                error_root_cause=f"分析过程出错: {str(e)}",
                failure_patterns=[],
                suggestions=[],
                overall_confidence=0.0,
                analysis_time=analysis_time
            )
    
    def _identify_relevant_patterns(self, error_history: List[ErrorEvent]) -> List[FailurePattern]:
        """识别相关的失败模式"""
        relevant_patterns = []
        
        # 获取最近的错误
        recent_errors = error_history[-5:] if len(error_history) > 5 else error_history
        
        for error in recent_errors:
            pattern_id = f"{error.component}_{error.error_type}_{error.context.get('tool_id', 'unknown')}_{error.context.get('action', 'unknown')}"
            
            if pattern_id in self.failure_patterns:
                pattern = self.failure_patterns[pattern_id]
                if pattern.frequency >= self.pattern_min_frequency:
                    relevant_patterns.append(pattern)
        
        # 按频率排序
        relevant_patterns.sort(key=lambda p: p.frequency, reverse=True)
        
        return relevant_patterns
    
    async def _generate_correction_suggestions(self, error_history: List[ErrorEvent], patterns: List[FailurePattern], context: Dict[str, Any] = None) -> List[CorrectionSuggestion]:
        """生成修正建议"""
        suggestions = []
        
        if not error_history:
            return suggestions
        
        latest_error = error_history[-1]
        
        # 策略1: 工具不匹配分析
        if "tool_id" in latest_error.context and "action" in latest_error.context:
            tool_suggestion = await self._suggest_tool_correction(latest_error)
            if tool_suggestion:
                suggestions.append(tool_suggestion)
        
        # 策略2: 参数修正
        if latest_error.context.get("parameters"):
            param_suggestion = await self._suggest_parameter_correction(latest_error)
            if param_suggestion:
                suggestions.append(param_suggestion)
        
        # 策略3: 替代方案
        alternative_suggestion = await self._suggest_alternative_approach(latest_error, patterns)
        if alternative_suggestion:
            suggestions.append(alternative_suggestion)
        
        # 策略4: 上下文重构
        if len(error_history) > 1:
            context_suggestion = await self._suggest_context_reframe(error_history)
            if context_suggestion:
                suggestions.append(context_suggestion)
        
        # 策略5: 技能缺口识别
        skill_suggestion = await self._identify_skill_gaps(latest_error)
        if skill_suggestion:
            suggestions.append(skill_suggestion)
        
        return suggestions
    
    async def _suggest_tool_correction(self, error: ErrorEvent) -> Optional[CorrectionSuggestion]:
        """建议工具修正"""
        try:
            tool_id = error.context.get("tool_id", "")
            action = error.context.get("action", "")
            
            if not tool_id or not action:
                return None
            
            # 检查工具是否存在
            if tool_id not in self.available_tools:
                # 寻找相似工具
                similar_tool = self._find_similar_tool(tool_id)
                if similar_tool:
                    corrected_request = error.context.copy()
                    corrected_request["tool_id"] = similar_tool
                    
                    return CorrectionSuggestion(
                        suggestion_id=f"tool_correction_{int(asyncio.get_event_loop().time())}",
                        strategy=CriticStrategy.TOOL_MISMATCH_ANALYSIS,
                        confidence=0.8,
                        original_request=error.context,
                        corrected_request=corrected_request,
                        reasoning=f"工具 '{tool_id}' 不存在，建议使用相似工具 '{similar_tool}'",
                        estimated_success_rate=0.7
                    )
            
            # 检查动作是否合适
            corrected_action = await self._suggest_action_correction(tool_id, action)
            if corrected_action and corrected_action != action:
                corrected_request = error.context.copy()
                corrected_request["action"] = corrected_action
                
                return CorrectionSuggestion(
                    suggestion_id=f"action_correction_{int(asyncio.get_event_loop().time())}",
                    strategy=CriticStrategy.TOOL_MISMATCH_ANALYSIS,
                    confidence=0.75,
                    original_request=error.context,
                    corrected_request=corrected_request,
                    reasoning=f"动作 '{action}' 可能不适合工具 '{tool_id}'，建议使用 '{corrected_action}'",
                    estimated_success_rate=0.6
                )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 工具修正建议失败: {e}")
            return None
    
    async def _suggest_parameter_correction(self, error: ErrorEvent) -> Optional[CorrectionSuggestion]:
        """建议参数修正"""
        try:
            parameters = error.context.get("parameters", {})
            if not parameters:
                return None
            
            # 使用LLM分析参数问题
            prompt = f"""
分析以下错误并建议参数修正：

错误信息: {error.error_message}
工具ID: {error.context.get('tool_id', '')}
动作: {error.context.get('action', '')}
当前参数: {json.dumps(parameters, ensure_ascii=False, indent=2)}

请提供修正后的参数，只返回JSON格式的参数对象。
"""
            
            try:
                response = await self.llm_client.generate_reasoning(prompt, [], [])
                # 尝试解析修正后的参数
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    corrected_params = json.loads(json_match.group(0))
                    
                    corrected_request = error.context.copy()
                    corrected_request["parameters"] = corrected_params
                    
                    return CorrectionSuggestion(
                        suggestion_id=f"param_correction_{int(asyncio.get_event_loop().time())}",
                        strategy=CriticStrategy.PARAMETER_CORRECTION,
                        confidence=0.7,
                        original_request=error.context,
                        corrected_request=corrected_request,
                        reasoning=f"LLM建议的参数修正：{response[:200]}...",
                        estimated_success_rate=0.6
                    )
            except Exception as llm_error:
                logger.warning(f"⚠️ LLM参数分析失败: {llm_error}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 参数修正建议失败: {e}")
            return None
    
    async def _suggest_alternative_approach(self, error: ErrorEvent, patterns: List[FailurePattern]) -> Optional[CorrectionSuggestion]:
        """建议替代方案"""
        try:
            # 分析常见的替代方案
            tool_id = error.context.get("tool_id", "")
            action = error.context.get("action", "")
            
            # 基于工具类型提供替代方案
            alternatives = []
            
            if "search" in tool_id.lower() or "search" in action.lower():
                # 搜索相关的替代方案
                alternatives = [
                    {"tool_id": "mcp-deepsearch", "action": "research"},
                    {"tool_id": "browser-use-mcp-server", "action": "browser_navigate"}
                ]
            elif "execute" in action.lower() or "sandbox" in tool_id.lower():
                # 代码执行的替代方案
                alternatives = [
                    {"tool_id": "microsandbox-mcp-server", "action": "microsandbox_execute"},
                    {"tool_id": "microsandbox-mcp-server", "action": "microsandbox_install_package"}
                ]
            elif "browser" in tool_id.lower() or "navigate" in action.lower():
                # 浏览器相关的替代方案
                alternatives = [
                    {"tool_id": "browser-use-mcp-server", "action": "browser_extract_content"},
                    {"tool_id": "browser-use-mcp-server", "action": "browser_click_element"}
                ]
            
            if alternatives:
                # 选择第一个可用的替代方案
                for alt in alternatives:
                    if alt["tool_id"] in self.available_tools:
                        corrected_request = error.context.copy()
                        corrected_request["tool_id"] = alt["tool_id"]
                        corrected_request["action"] = alt["action"]
                        
                        return CorrectionSuggestion(
                            suggestion_id=f"alternative_{int(asyncio.get_event_loop().time())}",
                            strategy=CriticStrategy.ALTERNATIVE_APPROACH,
                            confidence=0.6,
                            original_request=error.context,
                            corrected_request=corrected_request,
                            reasoning=f"建议使用替代工具 {alt['tool_id']} 和动作 {alt['action']}",
                            alternative_options=alternatives,
                            estimated_success_rate=0.5
                        )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 替代方案建议失败: {e}")
            return None
    
    async def _suggest_context_reframe(self, error_history: List[ErrorEvent]) -> Optional[CorrectionSuggestion]:
        """建议上下文重构"""
        try:
            if len(error_history) < 2:
                return None
            
            # 分析错误模式，建议重新构思问题
            recent_errors = error_history[-3:]
            error_summary = "; ".join([f"{err.error_type}: {err.error_message[:50]}" for err in recent_errors])
            
            # 这里可以使用LLM分析上下文重构建议
            # 简化版本：建议重置或简化任务
            
            return CorrectionSuggestion(
                suggestion_id=f"context_reframe_{int(asyncio.get_event_loop().time())}",
                strategy=CriticStrategy.CONTEXT_REFRAME,
                confidence=0.5,
                original_request=error_history[-1].context,
                corrected_request={"reframe": "建议重新分析任务需求"},
                reasoning=f"连续失败模式检测到，建议重新分析任务: {error_summary}",
                estimated_success_rate=0.4
            )
            
        except Exception as e:
            logger.error(f"❌ 上下文重构建议失败: {e}")
            return None
    
    async def _identify_skill_gaps(self, error: ErrorEvent) -> Optional[CorrectionSuggestion]:
        """识别技能缺口"""
        try:
            # 分析是否需要安装新工具
            error_message = error.error_message.lower()
            
            suggested_tools = []
            reasoning = ""
            
            if "pdf" in error_message:
                suggested_tools.append("pdf-tools-mcp-server")
                reasoning = "检测到PDF处理需求，建议安装PDF工具"
            elif "database" in error_message or "sql" in error_message:
                suggested_tools.append("database-mcp-server")
                reasoning = "检测到数据库操作需求，建议安装数据库工具"
            elif "image" in error_message or "vision" in error_message:
                suggested_tools.append("vision-mcp-server")
                reasoning = "检测到图像处理需求，建议安装视觉工具"
            
            if suggested_tools:
                return CorrectionSuggestion(
                    suggestion_id=f"skill_gap_{int(asyncio.get_event_loop().time())}",
                    strategy=CriticStrategy.SKILL_GAP_IDENTIFICATION,
                    confidence=0.7,
                    original_request=error.context,
                    corrected_request={"install_tools": suggested_tools},
                    reasoning=reasoning,
                    requires_tool_installation=True,
                    suggested_tools=suggested_tools,
                    estimated_success_rate=0.8
                )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 技能缺口识别失败: {e}")
            return None
    
    def _find_similar_tool(self, tool_id: str) -> Optional[str]:
        """查找相似工具"""
        tool_id_lower = tool_id.lower()
        
        for available_tool in self.available_tools:
            available_lower = available_tool.lower()
            
            # 简单的相似度匹配
            if (tool_id_lower in available_lower or 
                available_lower in tool_id_lower or
                self._calculate_similarity(tool_id_lower, available_lower) > 0.6):
                return available_tool
        
        return None
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """计算字符串相似度"""
        if not str1 or not str2:
            return 0.0
        
        # 简单的相似度计算（Jaccard相似度）
        set1 = set(str1.split('-'))
        set2 = set(str2.split('-'))
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    async def _suggest_action_correction(self, tool_id: str, action: str) -> Optional[str]:
        """建议动作修正"""
        # 基于工具ID的常见动作映射
        action_mappings = {
            "mcp-deepsearch": ["research", "quick_research", "comprehensive_research"],
            "microsandbox-mcp-server": ["microsandbox_execute", "microsandbox_install_package"],
            "browser-use-mcp-server": ["browser_navigate", "browser_extract_content", "browser_click_element"],
            "mcp-search-tool": ["analyze_tool_needs", "search_and_install_tools"]
        }
        
        if tool_id in action_mappings:
            valid_actions = action_mappings[tool_id]
            
            # 查找最相似的动作
            action_lower = action.lower()
            for valid_action in valid_actions:
                if action_lower in valid_action.lower() or valid_action.lower() in action_lower:
                    return valid_action
            
            # 如果没有相似的，返回第一个默认动作
            return valid_actions[0]
        
        return None
    
    async def _analyze_root_cause(self, error_history: List[ErrorEvent], patterns: List[FailurePattern]) -> str:
        """分析根本原因"""
        if not error_history:
            return "无错误历史数据"
        
        # 分析最常见的错误类型
        error_types = [err.error_type for err in error_history[-5:]]
        most_common_error = max(set(error_types), key=error_types.count) if error_types else "unknown"
        
        # 分析最常见的组件
        components = [err.component for err in error_history[-5:]]
        most_common_component = max(set(components), key=components.count) if components else "unknown"
        
        # 基于模式分析
        if patterns:
            pattern_analysis = f"检测到{len(patterns)}个重复失败模式，最频繁的是{patterns[0].description}(频率:{patterns[0].frequency})"
        else:
            pattern_analysis = "未检测到明显的重复失败模式"
        
        root_cause = f"根本原因分析：主要错误类型为{most_common_error}，发生在{most_common_component}组件。{pattern_analysis}"
        
        return root_cause
    
    def _calculate_overall_confidence(self, suggestions: List[CorrectionSuggestion]) -> float:
        """计算整体置信度"""
        if not suggestions:
            return 0.0
        
        # 加权平均置信度
        total_confidence = sum(s.confidence for s in suggestions)
        return total_confidence / len(suggestions)
    
    def record_correction_success(self, suggestion: CorrectionSuggestion, success: bool):
        """记录修正结果"""
        if success:
            self.successful_corrections.append(suggestion)
            self.stats["successful_corrections"] += 1
            
            # 更新相关模式的成功率
            if suggestion.original_request:
                self._update_pattern_success_rate(suggestion.original_request, True)
        else:
            self.stats["failed_corrections"] += 1
            
            # 更新相关模式的成功率
            if suggestion.original_request:
                self._update_pattern_success_rate(suggestion.original_request, False)
        
        logger.info(f"📊 修正结果记录: {'成功' if success else '失败'} - {suggestion.strategy.value}")
    
    def _update_pattern_success_rate(self, request: Dict[str, Any], success: bool):
        """更新模式成功率"""
        tool_id = request.get("tool_id", "unknown")
        action = request.get("action", "unknown")
        
        for pattern in self.failure_patterns.values():
            if pattern.tool_id == tool_id and pattern.action == action:
                # 简单的成功率更新
                if success:
                    pattern.correction_success_rate = min(1.0, pattern.correction_success_rate + 0.1)
                else:
                    pattern.correction_success_rate = max(0.0, pattern.correction_success_rate - 0.05)
                break
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "failure_patterns_count": len(self.failure_patterns),
            "total_failures_recorded": len(self.failure_history),
            "successful_corrections_count": len(self.successful_corrections),
            "high_confidence_suggestions": sum(1 for s in self.successful_corrections if s.confidence >= self.high_confidence_threshold)
        }
    
    def get_top_failure_patterns(self, limit: int = 5) -> List[FailurePattern]:
        """获取最常见的失败模式"""
        patterns = list(self.failure_patterns.values())
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns[:limit]
    
    def reset_history(self):
        """重置历史记录"""
        self.failure_history.clear()
        self.failure_patterns.clear()
        self.successful_corrections.clear()
        
        # 重置统计信息但保留总体趋势
        self.stats = {
            "total_analyses": 0,
            "successful_corrections": 0,
            "failed_corrections": 0,
            "patterns_identified": 0,
            "avg_analysis_time": 0.0
        }
        
        logger.info("🔄 ValidationCritic历史记录已重置")

# 创建全局ValidationCritic实例的便捷函数
def create_validation_critic(llm_client: LLMClient, available_tools: List[str] = None) -> ValidationCritic:
    """创建ValidationCritic实例"""
    return ValidationCritic(llm_client, available_tools)