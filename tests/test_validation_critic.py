"""
测试ValidationCritic Agent功能
验证智能错误分析和修正建议是否正常工作
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta

from core.agents.validation_critic import (
    ValidationCritic, 
    ErrorEvent, 
    ErrorSeverity, 
    ErrorCategory,
    CriticStrategy,
    CorrectionSuggestion,
    FailurePattern
)
from core.llm_client import LLMClient


class TestValidationCritic:
    """ValidationCritic Agent测试"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """创建模拟的LLM客户端"""
        client = Mock(spec=LLMClient)
        client.generate_reasoning = AsyncMock(return_value='{"corrected_param": "test_value"}')
        return client
    
    @pytest.fixture
    def validation_critic(self, mock_llm_client):
        """创建测试用的ValidationCritic"""
        available_tools = [
            "mcp-deepsearch", 
            "microsandbox-mcp-server", 
            "browser-use-mcp-server"
        ]
        return ValidationCritic(mock_llm_client, available_tools)
    
    @pytest.fixture
    def sample_error_event(self):
        """创建示例错误事件"""
        return ErrorEvent(
            error_id="test_error_001",
            timestamp=datetime.now(),
            component="enhanced_runtime",
            error_type="tool_execution_error",
            error_message="Unsupported action 'invalid_action' for tool 'mcp-deepsearch'",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.TOOL_ERROR,
            context={
                "tool_id": "mcp-deepsearch",
                "action": "invalid_action",
                "parameters": {"query": "test query"},
                "step_id": "step_001"
            }
        )
    
    def test_error_event_recording(self, validation_critic, sample_error_event):
        """测试错误事件记录"""
        initial_count = len(validation_critic.failure_history)
        
        validation_critic.record_failure(sample_error_event)
        
        assert len(validation_critic.failure_history) == initial_count + 1
        assert validation_critic.failure_history[-1] == sample_error_event
    
    def test_failure_pattern_creation(self, validation_critic, sample_error_event):
        """测试失败模式创建"""
        validation_critic.record_failure(sample_error_event)
        
        expected_pattern_id = "enhanced_runtime_tool_execution_error_mcp-deepsearch_invalid_action"
        assert expected_pattern_id in validation_critic.failure_patterns
        
        pattern = validation_critic.failure_patterns[expected_pattern_id]
        assert pattern.frequency == 1
        assert pattern.tool_id == "mcp-deepsearch"
        assert pattern.action == "invalid_action"
        assert pattern.error_type == "tool_execution_error"
    
    def test_failure_pattern_frequency_update(self, validation_critic, sample_error_event):
        """测试失败模式频率更新"""
        # 记录同样的错误两次
        validation_critic.record_failure(sample_error_event)
        validation_critic.record_failure(sample_error_event)
        
        expected_pattern_id = "enhanced_runtime_tool_execution_error_mcp-deepsearch_invalid_action"
        pattern = validation_critic.failure_patterns[expected_pattern_id]
        assert pattern.frequency == 2
    
    def test_keyword_extraction(self, validation_critic):
        """测试关键词提取"""
        error_message = "Unsupported action with invalid parameters causing timeout"
        keywords = validation_critic._extract_keywords(error_message)
        
        expected_keywords = ["unsupported", "invalid", "parameter", "timeout"]
        for keyword in expected_keywords:
            assert keyword in keywords
    
    def test_relevant_pattern_identification(self, validation_critic):
        """测试相关失败模式识别"""
        # 创建多个错误事件
        errors = []
        for i in range(3):
            error = ErrorEvent(
                error_id=f"error_{i}",
                timestamp=datetime.now(),
                component="test_component",
                error_type="test_error",
                error_message=f"Test error {i}",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.TOOL_ERROR,
                context={
                    "tool_id": "mcp-deepsearch",
                    "action": "test_action",
                    "parameters": {}
                }
            )
            errors.append(error)
            validation_critic.record_failure(error)
        
        relevant_patterns = validation_critic._identify_relevant_patterns(errors)
        
        # 应该识别出重复的失败模式
        assert len(relevant_patterns) > 0
        assert relevant_patterns[0].frequency >= validation_critic.pattern_min_frequency
    
    @pytest.mark.asyncio
    async def test_tool_correction_suggestion(self, validation_critic, sample_error_event):
        """测试工具修正建议"""
        # 测试不存在的工具ID
        error_with_invalid_tool = ErrorEvent(
            error_id="tool_error",
            timestamp=datetime.now(),
            component="test",
            error_type="tool_not_found",
            error_message="Tool 'deepsearch' not found",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.TOOL_ERROR,
            context={
                "tool_id": "deepsearch",  # 应该是 mcp-deepsearch
                "action": "research",
                "parameters": {"query": "test"}
            }
        )
        
        suggestion = await validation_critic._suggest_tool_correction(error_with_invalid_tool)
        
        assert suggestion is not None
        assert suggestion.strategy == CriticStrategy.TOOL_MISMATCH_ANALYSIS
        assert suggestion.corrected_request["tool_id"] == "mcp-deepsearch"
        assert suggestion.confidence > 0.5
    
    @pytest.mark.asyncio
    async def test_parameter_correction_suggestion(self, validation_critic, mock_llm_client):
        """测试参数修正建议"""
        error_with_bad_params = ErrorEvent(
            error_id="param_error",
            timestamp=datetime.now(),
            component="test",
            error_type="parameter_error",
            error_message="Invalid parameter format",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.VALIDATION_ERROR,
            context={
                "tool_id": "mcp-deepsearch",
                "action": "research",
                "parameters": {"invalid_param": "bad_value"}
            }
        )
        
        suggestion = await validation_critic._suggest_parameter_correction(error_with_bad_params)
        
        # 如果LLM返回了有效的JSON，应该有建议
        if suggestion:
            assert suggestion.strategy == CriticStrategy.PARAMETER_CORRECTION
            assert "parameters" in suggestion.corrected_request
    
    @pytest.mark.asyncio
    async def test_alternative_approach_suggestion(self, validation_critic):
        """测试替代方案建议"""
        search_error = ErrorEvent(
            error_id="search_error",
            timestamp=datetime.now(),
            component="test",
            error_type="action_failed",
            error_message="Search action failed",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.TOOL_ERROR,
            context={
                "tool_id": "unknown-search-tool",
                "action": "search",
                "parameters": {"query": "test"}
            }
        )
        
        suggestion = await validation_critic._suggest_alternative_approach(search_error, [])
        
        if suggestion:
            assert suggestion.strategy == CriticStrategy.ALTERNATIVE_APPROACH
            assert suggestion.corrected_request["tool_id"] in validation_critic.available_tools
    
    @pytest.mark.asyncio
    async def test_skill_gap_identification(self, validation_critic):
        """测试技能缺口识别"""
        pdf_error = ErrorEvent(
            error_id="pdf_error",
            timestamp=datetime.now(),
            component="test",
            error_type="unsupported_format",
            error_message="Cannot process PDF files",
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.CAPABILITY_ERROR,
            context={
                "tool_id": "file-processor",
                "action": "process_file",
                "parameters": {"file_type": "pdf"}
            }
        )
        
        suggestion = await validation_critic._identify_skill_gaps(pdf_error)
        
        assert suggestion is not None
        assert suggestion.strategy == CriticStrategy.SKILL_GAP_IDENTIFICATION
        assert suggestion.requires_tool_installation is True
        assert "pdf-tools-mcp-server" in suggestion.suggested_tools
    
    @pytest.mark.asyncio
    async def test_context_reframe_suggestion(self, validation_critic):
        """测试上下文重构建议"""
        # 创建多个连续失败事件
        error_history = []
        for i in range(3):
            error = ErrorEvent(
                error_id=f"context_error_{i}",
                timestamp=datetime.now() - timedelta(minutes=i),
                component="test",
                error_type="repeated_failure",
                error_message=f"Repeated failure {i}",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.LOGIC_ERROR,
                context={"attempt": i}
            )
            error_history.append(error)
        
        suggestion = await validation_critic._suggest_context_reframe(error_history)
        
        assert suggestion is not None
        assert suggestion.strategy == CriticStrategy.CONTEXT_REFRAME
        assert "重新分析任务" in suggestion.reasoning
    
    @pytest.mark.asyncio
    async def test_full_review_process(self, validation_critic, sample_error_event):
        """测试完整的审查流程"""
        error_history = [sample_error_event]
        context = {"task_description": "执行搜索任务"}
        
        analysis = await validation_critic.review_failed_action(error_history, context)
        
        assert analysis is not None
        assert analysis.analysis_id.startswith("critic_analysis_")
        assert analysis.error_root_cause is not None
        assert len(analysis.suggestions) > 0
        assert 0 <= analysis.overall_confidence <= 1.0
        assert analysis.analysis_time > 0
    
    def test_correction_success_recording(self, validation_critic):
        """测试修正成功记录"""
        suggestion = CorrectionSuggestion(
            suggestion_id="test_suggestion",
            strategy=CriticStrategy.TOOL_MISMATCH_ANALYSIS,
            confidence=0.8,
            original_request={"tool_id": "wrong_tool"},
            corrected_request={"tool_id": "correct_tool"},
            reasoning="Tool correction test"
        )
        
        initial_success_count = validation_critic.stats["successful_corrections"]
        validation_critic.record_correction_success(suggestion, True)
        
        assert validation_critic.stats["successful_corrections"] == initial_success_count + 1
        assert suggestion in validation_critic.successful_corrections
    
    def test_stats_tracking(self, validation_critic):
        """测试统计信息跟踪"""
        stats = validation_critic.get_stats()
        
        required_stats = [
            "total_analyses", "successful_corrections", "failed_corrections",
            "patterns_identified", "avg_analysis_time", "failure_patterns_count",
            "total_failures_recorded", "successful_corrections_count"
        ]
        
        for stat in required_stats:
            assert stat in stats
    
    def test_top_failure_patterns(self, validation_critic):
        """测试获取最常见失败模式"""
        # 创建多个不同的失败模式
        for i in range(5):
            for j in range(i + 1):  # 不同的频率
                error = ErrorEvent(
                    error_id=f"pattern_error_{i}_{j}",
                    timestamp=datetime.now(),
                    component="test",
                    error_type=f"error_type_{i}",
                    error_message=f"Error {i}",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.TOOL_ERROR,
                    context={
                        "tool_id": f"tool_{i}",
                        "action": f"action_{i}"
                    }
                )
                validation_critic.record_failure(error)
        
        top_patterns = validation_critic.get_top_failure_patterns(limit=3)
        
        assert len(top_patterns) <= 3
        # 验证按频率降序排列
        for i in range(len(top_patterns) - 1):
            assert top_patterns[i].frequency >= top_patterns[i + 1].frequency
    
    def test_history_reset(self, validation_critic, sample_error_event):
        """测试历史记录重置"""
        # 添加一些数据
        validation_critic.record_failure(sample_error_event)
        validation_critic.stats["total_analyses"] = 5
        
        validation_critic.reset_history()
        
        assert len(validation_critic.failure_history) == 0
        assert len(validation_critic.failure_patterns) == 0
        assert len(validation_critic.successful_corrections) == 0
        assert validation_critic.stats["total_analyses"] == 0
    
    def test_tool_similarity_calculation(self, validation_critic):
        """测试工具相似度计算"""
        # 测试相似度计算
        similarity = validation_critic._calculate_similarity("mcp-deepsearch", "deepsearch")
        assert similarity > 0
        
        similarity = validation_critic._calculate_similarity("completely-different", "nothing-similar")
        assert similarity == 0
    
    def test_action_correction_mappings(self, validation_critic):
        """测试动作修正映射"""
        # 测试已知工具的动作修正
        corrected = asyncio.run(validation_critic._suggest_action_correction("mcp-deepsearch", "invalid_action"))
        assert corrected in ["research", "quick_research", "comprehensive_research"]
        
        corrected = asyncio.run(validation_critic._suggest_action_correction("microsandbox-mcp-server", "run"))
        assert corrected in ["microsandbox_execute", "microsandbox_install_package"]

if __name__ == "__main__":
    # 运行特定测试
    pytest.main([__file__, "-v"])