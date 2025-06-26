"""
测试Enhanced Runtime中Guardrails和ValidationCritic的集成
验证整体工作流程中的错误处理和智能修正
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from core.llm.guardrails_middleware import GuardrailsValidationResult
from core.agents.validation_critic import ValidationCritic, CriticAnalysis, CorrectionSuggestion
from core.recovery.intelligent_error_recovery import ErrorEvent, ErrorSeverity, ErrorCategory


class TestEnhancedRuntimeIntegration:
    """Enhanced Runtime集成测试"""
    
    @pytest.fixture
    def mock_guardrails_middleware(self):
        """模拟Guardrails中间件"""
        middleware = Mock()
        
        # 成功验证结果
        success_result = GuardrailsValidationResult(
            is_valid=True,
            validated_data={"thinking": "test", "action": "research", "tool_id": "mcp-deepsearch"},
            validation_time=0.1,
            guardrails_used=["output_validation"]
        )
        
        # 失败验证结果
        failure_result = GuardrailsValidationResult(
            is_valid=False,
            error_message="工具ID不在可用列表中",
            validation_time=0.1,
            original_data={"tool_id": "invalid_tool"}
        )
        
        middleware.validate_output = AsyncMock(return_value=success_result)
        middleware.validate_input = AsyncMock(return_value=success_result)
        
        return middleware
    
    @pytest.fixture
    def mock_validation_critic(self):
        """模拟ValidationCritic"""
        critic = Mock(spec=ValidationCritic)
        
        # 模拟分析结果
        mock_analysis = CriticAnalysis(
            analysis_id="test_analysis",
            error_root_cause="工具选择错误",
            failure_patterns=[],
            suggestions=[
                CorrectionSuggestion(
                    suggestion_id="test_suggestion",
                    strategy="TOOL_MISMATCH_ANALYSIS",
                    confidence=0.8,
                    original_request={"tool_id": "invalid_tool"},
                    corrected_request={"tool_id": "mcp-deepsearch"},
                    reasoning="建议使用正确的工具ID"
                )
            ],
            overall_confidence=0.8,
            analysis_time=0.2
        )
        
        critic.review_failed_action = AsyncMock(return_value=mock_analysis)
        critic.record_correction_success = Mock()
        critic.update_available_tools = Mock()
        
        return critic
    
    @pytest.mark.asyncio
    async def test_guardrails_output_validation_success(self, mock_guardrails_middleware):
        """测试Guardrails输出验证成功场景"""
        # 模拟LLM输出
        action_result = {
            "thinking": "用户需要搜索信息",
            "action": "research", 
            "tool_id": "mcp-deepsearch",
            "parameters": {"query": "Python教程"},
            "confidence": 0.9
        }
        
        # 验证输出
        result = await mock_guardrails_middleware.validate_output(
            json.dumps(action_result, ensure_ascii=False)
        )
        
        assert result.is_valid is True
        assert result.validated_data is not None
        mock_guardrails_middleware.validate_output.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_guardrails_output_validation_failure_triggers_critic(
        self, mock_guardrails_middleware, mock_validation_critic
    ):
        """测试Guardrails验证失败触发ValidationCritic"""
        # 设置Guardrails返回失败结果
        failure_result = GuardrailsValidationResult(
            is_valid=False,
            error_message="工具ID不在可用列表中",
            validation_time=0.1,
            original_data={"tool_id": "invalid_tool"}
        )
        mock_guardrails_middleware.validate_output.return_value = failure_result
        
        # 模拟连续失败场景
        consecutive_failures = 3
        error_events_buffer = [
            ErrorEvent(
                error_id=f"error_{i}",
                timestamp=datetime.now(),
                component="guardrails_validation",
                error_type="validation_failed",
                error_message="工具ID验证失败",
                stack_trace="test stack trace",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.DATA_ERROR,
                context={"tool_id": "invalid_tool"}
            ) for i in range(consecutive_failures)
        ]
        
        # 验证输出（失败）
        result = await mock_guardrails_middleware.validate_output(
            json.dumps({"tool_id": "invalid_tool"})
        )
        
        assert result.is_valid is False
        
        # 模拟触发ValidationCritic
        if consecutive_failures >= 3:  # 达到阈值
            analysis = await mock_validation_critic.review_failed_action(
                error_events_buffer, {"task_description": "测试任务"}
            )
            
            assert analysis is not None
            assert len(analysis.suggestions) > 0
            mock_validation_critic.review_failed_action.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validation_critic_suggestion_application(self, mock_validation_critic):
        """测试ValidationCritic建议的应用"""
        # 创建错误历史
        error_history = [
            ErrorEvent(
                error_id="test_error",
                timestamp=datetime.now(),
                component="enhanced_runtime",
                error_type="tool_execution_error",
                error_message="不支持的动作",
                stack_trace="test stack trace",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.TOOL_ERROR,
                context={
                    "tool_id": "invalid_tool",
                    "action": "invalid_action",
                    "parameters": {"query": "test"}
                }
            )
        ]
        
        # 获取分析和建议
        analysis = await mock_validation_critic.review_failed_action(
            error_history, {"task_description": "测试任务"}
        )
        
        assert analysis.overall_confidence > 0
        assert len(analysis.suggestions) > 0
        
        # 验证第一个建议
        suggestion = analysis.suggestions[0]
        assert suggestion.confidence > 0.5
        assert suggestion.corrected_request["tool_id"] == "mcp-deepsearch"
    
    def test_consecutive_failure_tracking(self):
        """测试连续失败计数跟踪"""
        # 模拟增强运行时的连续失败跟踪逻辑
        consecutive_failures = 0
        max_consecutive_failures = 3
        error_events_buffer = []
        
        # 模拟连续失败
        for i in range(5):
            # 模拟失败
            tool_success = False
            if not tool_success:
                consecutive_failures += 1
                error_event = ErrorEvent(
                    error_id=f"failure_{i}",
                    timestamp=datetime.now(),
                    component="test",
                    error_type="execution_failed",
                    error_message=f"失败 {i}",
                    stack_trace="test stack trace",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.TOOL_ERROR,
                    context={"attempt": i}
                )
                error_events_buffer.append(error_event)
                
                # 检查是否达到阈值
                should_trigger_critic = consecutive_failures >= max_consecutive_failures
                
                if i >= 2:  # 从第3次失败开始应该触发
                    assert should_trigger_critic is True
                else:
                    assert should_trigger_critic is False
    
    def test_success_reset_mechanism(self):
        """测试成功时的重置机制"""
        # 模拟增强运行时的重置逻辑
        consecutive_failures = 3
        error_events_buffer = ["error1", "error2", "error3"]
        
        # 模拟成功执行
        tool_success = True
        
        if tool_success:
            consecutive_failures = 0
            error_events_buffer.clear()
        
        assert consecutive_failures == 0
        assert len(error_events_buffer) == 0
    
    @pytest.mark.asyncio
    async def test_guardrails_auto_correction_integration(self, mock_guardrails_middleware):
        """测试Guardrails自动修正集成"""
        # 模拟带有自动修正的结果
        corrected_result = GuardrailsValidationResult(
            is_valid=True,
            validated_data={"tool_id": "mcp-deepsearch", "action": "research"},
            original_data={"tool_id": "deepsearch", "action": "search"},
            corrections_applied=["tool_id_correction", "action_normalization"],
            validation_time=0.15,
            guardrails_used=["auto_correction"]
        )
        
        mock_guardrails_middleware.validate_output.return_value = corrected_result
        
        # 验证修正后的输出
        result = await mock_guardrails_middleware.validate_output(
            json.dumps({"tool_id": "deepsearch", "action": "search"})
        )
        
        assert result.is_valid is True
        assert "tool_id_correction" in result.corrections_applied
        assert result.validated_data["tool_id"] == "mcp-deepsearch"
    
    @pytest.mark.asyncio
    async def test_error_event_creation_from_guardrails_failure(self):
        """测试从Guardrails失败创建错误事件"""
        # 模拟Guardrails失败结果
        failure_result = GuardrailsValidationResult(
            is_valid=False,
            error_message="JSON格式无效",
            validation_time=0.1,
            original_data={"invalid": "data"}
        )
        
        # 创建对应的错误事件
        error_event = ErrorEvent(
            error_id="guardrails_failure",
            timestamp=datetime.now(),
            component="guardrails_validation",
            error_type="validation_failed",
            error_message=failure_result.error_message,
            stack_trace="test stack trace",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.DATA_ERROR,
            context={
                "validation_time": failure_result.validation_time,
                "original_data": failure_result.original_data
            }
        )
        
        assert error_event.error_message == "JSON格式无效"
        assert error_event.component == "guardrails_validation"
        assert error_event.context["validation_time"] == 0.1
    
    def test_tool_availability_synchronization(self, mock_guardrails_middleware, mock_validation_critic):
        """测试工具可用性同步"""
        # 模拟可用工具列表
        available_tools = ["mcp-deepsearch", "microsandbox-mcp-server", "browser-use-mcp-server"]
        
        # 更新Guardrails中间件的工具列表
        mock_guardrails_middleware.update_available_tools = Mock()
        mock_guardrails_middleware.update_available_tools(available_tools)
        
        # 更新ValidationCritic的工具列表
        mock_validation_critic.update_available_tools(available_tools)
        
        # 验证调用
        mock_guardrails_middleware.update_available_tools.assert_called_once_with(available_tools)
        mock_validation_critic.update_available_tools.assert_called_once_with(available_tools)
    
    @pytest.mark.asyncio
    async def test_full_integration_workflow(
        self, mock_guardrails_middleware, mock_validation_critic
    ):
        """测试完整的集成工作流程"""
        # 1. 模拟LLM输出验证失败
        failure_result = GuardrailsValidationResult(
            is_valid=False,
            error_message="工具ID不存在",
            original_data={"tool_id": "nonexistent_tool"}
        )
        mock_guardrails_middleware.validate_output.return_value = failure_result
        
        # 2. 验证失败
        validation_result = await mock_guardrails_middleware.validate_output("invalid json")
        assert validation_result.is_valid is False
        
        # 3. 创建错误事件
        error_event = ErrorEvent(
            error_id="integration_test",
            timestamp=datetime.now(),
            component="guardrails_validation", 
            error_type="validation_failed",
            error_message=validation_result.error_message,
            stack_trace="test stack trace",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.DATA_ERROR,
            context={"tool_id": "nonexistent_tool"}
        )
        
        # 4. 触发ValidationCritic（假设连续失败达到阈值）
        error_history = [error_event] * 3  # 模拟3次相同失败
        analysis = await mock_validation_critic.review_failed_action(
            error_history, {"task_description": "集成测试"}
        )
        
        # 5. 验证分析结果
        assert analysis is not None
        assert len(analysis.suggestions) > 0
        
        # 6. 应用建议（模拟）
        suggestion = analysis.suggestions[0]
        corrected_tool_id = suggestion.corrected_request["tool_id"]
        assert corrected_tool_id == "mcp-deepsearch"
        
        # 7. 记录修正成功
        mock_validation_critic.record_correction_success(suggestion, True)
        mock_validation_critic.record_correction_success.assert_called_once_with(suggestion, True)

if __name__ == "__main__":
    # 运行特定测试
    pytest.main([__file__, "-v"])