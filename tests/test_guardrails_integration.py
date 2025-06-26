"""
测试Guardrails-AI集成功能
验证内容安全检查和输入输出验证是否正常工作
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch
from datetime import datetime

from core.llm.guardrails_middleware import GuardrailsLLMMiddleware, GuardrailsValidationResult


class TestGuardrailsIntegration:
    """Guardrails-AI集成测试"""
    
    @pytest.fixture
    def middleware(self):
        """创建测试用的Guardrails中间件"""
        available_tools = [
            "mcp-deepsearch", 
            "microsandbox-mcp-server", 
            "browser-use-mcp-server", 
            "mcp-search-tool"
        ]
        return GuardrailsLLMMiddleware(available_tools)
    
    @pytest.mark.asyncio
    async def test_valid_input_validation(self, middleware):
        """测试有效输入验证"""
        valid_input = {
            "thinking": "用户需要搜索信息，我需要使用深度搜索工具",
            "action": "research",
            "tool_id": "mcp-deepsearch",
            "parameters": {"query": "Python asyncio tutorial"},
            "confidence": 0.8
        }
        
        result = await middleware.validate_input(valid_input)
        
        assert result.is_valid is True
        assert result.validated_data is not None
        assert result.error_message is None
        assert "basic_validation" in result.guardrails_used or "input_safety_check" in result.guardrails_used
    
    @pytest.mark.asyncio
    async def test_invalid_input_with_suspicious_content(self, middleware):
        """测试包含可疑内容的输入"""
        suspicious_input = {
            "thinking": "DROP TABLE users; SELECT * FROM sensitive_data",
            "action": "research",
            "tool_id": "mcp-deepsearch",
            "parameters": {"query": "normal query"}
        }
        
        result = await middleware.validate_input(suspicious_input)
        
        assert result.is_valid is False
        assert "可疑内容" in result.error_message or "suspicious" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_missing_required_fields(self, middleware):
        """测试缺少必需字段的输入"""
        incomplete_input = {
            "thinking": "需要执行某个操作",
            # 缺少 action 和 tool_id
            "parameters": {"query": "test"}
        }
        
        result = await middleware.validate_input(incomplete_input)
        
        assert result.is_valid is False
        assert "缺少必需字段" in result.error_message or "missing" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_valid_output_validation(self, middleware):
        """测试有效输出验证"""
        valid_output = json.dumps({
            "thinking": "已完成搜索任务",
            "action": "research",
            "tool_id": "mcp-deepsearch",
            "parameters": {"query": "completed"},
            "confidence": 0.9
        })
        
        result = await middleware.validate_output(valid_output)
        
        assert result.is_valid is True
        assert result.validated_data is not None
        assert result.error_message is None
    
    @pytest.mark.asyncio
    async def test_invalid_json_output(self, middleware):
        """测试无效JSON输出"""
        invalid_json = "这不是一个有效的JSON格式 { incomplete"
        
        result = await middleware.validate_output(invalid_json)
        
        assert result.is_valid is False
        assert "JSON解析失败" in result.error_message or "JSON" in result.error_message
    
    @pytest.mark.asyncio
    async def test_auto_correction_tool_id(self, middleware):
        """测试工具ID自动修正功能"""
        output_with_wrong_tool = json.dumps({
            "thinking": "需要执行搜索",
            "action": "research", 
            "tool_id": "deepsearch",  # 错误的工具ID，应该是 mcp-deepsearch
            "parameters": {"query": "test"},
            "confidence": 0.7
        })
        
        result = await middleware.validate_output(output_with_wrong_tool)
        
        # 应该要么验证成功（经过自动修正），要么失败但有修正建议
        if result.is_valid:
            assert "tool_id_correction" in result.corrections_applied
            assert result.validated_data["tool_id"] == "mcp-deepsearch"
        else:
            assert "工具ID" in result.error_message
    
    @pytest.mark.asyncio
    async def test_action_normalization(self, middleware):
        """测试动作名称规范化"""
        output_with_wrong_action = json.dumps({
            "thinking": "需要执行搜索",
            "action": "search",  # 应该规范化为 research
            "tool_id": "mcp-deepsearch",
            "parameters": {"query": "test"},
            "confidence": 0.7
        })
        
        result = await middleware.validate_output(output_with_wrong_action)
        
        # 检查是否进行了动作规范化
        if result.is_valid and result.corrections_applied:
            assert result.validated_data["action"] == "research"
    
    def test_suspicious_content_detection(self, middleware):
        """测试可疑内容检测"""
        # SQL注入尝试
        assert middleware._contains_suspicious_content("SELECT * FROM users WHERE id = 1; DROP TABLE users;") is True
        
        # 脚本注入尝试
        assert middleware._contains_suspicious_content("<script>alert('xss')</script>") is True
        
        # 命令注入尝试
        assert middleware._contains_suspicious_content("rm -rf /") is True
        
        # 正常内容
        assert middleware._contains_suspicious_content("请帮我搜索Python教程") is False
    
    def test_tool_id_similarity_matching(self, middleware):
        """测试工具ID相似度匹配"""
        # 测试相似工具查找
        assert middleware._find_closest_tool_id("deepsearch") == "mcp-deepsearch"
        assert middleware._find_closest_tool_id("microsandbox") == "microsandbox-mcp-server"
        assert middleware._find_closest_tool_id("browser") == "browser-use-mcp-server"
        
        # 测试不存在的工具
        assert middleware._find_closest_tool_id("nonexistent-tool") is None
    
    def test_action_normalization_mappings(self, middleware):
        """测试动作名称映射"""
        assert middleware._normalize_action_name("search") == "research"
        assert middleware._normalize_action_name("browse") == "browser_navigate"
        assert middleware._normalize_action_name("execute") == "microsandbox_execute"
        assert middleware._normalize_action_name("install") == "microsandbox_install_package"
        
        # 测试未映射的动作保持不变
        assert middleware._normalize_action_name("custom_action") == "custom_action"
    
    def test_validation_stats_tracking(self, middleware):
        """测试验证统计信息跟踪"""
        initial_stats = middleware.get_validation_stats()
        assert initial_stats["total_validations"] == 0
        assert initial_stats["successful_validations"] == 0
        assert initial_stats["failed_validations"] == 0
    
    def test_stats_reset(self, middleware):
        """测试统计信息重置"""
        # 模拟一些验证操作
        middleware.validation_stats["total_validations"] = 10
        middleware.validation_stats["successful_validations"] = 8
        middleware.validation_stats["failed_validations"] = 2
        
        middleware.reset_stats()
        
        stats = middleware.get_validation_stats()
        assert stats["total_validations"] == 0
        assert stats["successful_validations"] == 0
        assert stats["failed_validations"] == 0
    
    @pytest.mark.asyncio
    async def test_update_available_tools(self, middleware):
        """测试更新可用工具列表"""
        new_tools = ["new-tool-1", "new-tool-2", "mcp-deepsearch"]
        middleware.update_available_tools(new_tools)
        
        assert middleware.available_tool_ids == new_tools
        
        # 测试新工具的验证
        output_with_new_tool = json.dumps({
            "thinking": "使用新工具",
            "action": "test_action",
            "tool_id": "new-tool-1",
            "parameters": {},
            "confidence": 0.8
        })
        
        result = await middleware.validate_output(output_with_new_tool)
        assert result.is_valid is True

if __name__ == "__main__":
    # 运行特定测试
    pytest.main([__file__, "-v"])