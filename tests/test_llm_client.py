# -*- coding: utf-8 -*-
"""
测试 llm_client.py 模块 - LLM客户端统一接口

覆盖功能:
1. LLMProvider枚举和提供商检测
2. LLMClient初始化和配置
3. 代码生成功能
4. Web操作生成
5. 推理生成
6. 任务分析
7. 多提供商API调用
8. 错误处理和降级机制
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx


@pytest.fixture
def base_config():
    """基础LLM配置"""
    return {
        "provider": "vllm",
        "disable_cache": True,
        "timeout": 30.0
    }


@pytest.fixture
def openai_config():
    """OpenAI配置"""
    return {
        "provider": "openai",
        "api_key": "test-openai-key",
        "model": "gpt-4",
        "base_url": "https://api.openai.com/v1"
    }


@pytest.fixture
def gemini_config():
    """Gemini配置"""
    return {
        "provider": "gemini",
        "api_key": "test-gemini-key",
        "model": "gemini-pro"
    }


@pytest.fixture
def deepseek_config():
    """DeepSeek配置"""
    return {
        "provider": "deepseek",
        "api_key": "test-deepseek-key",
        "model": "deepseek-coder"
    }


class TestLLMProvider:
    """LLMProvider枚举测试"""
    
    def test_llm_provider_enum_values(self):
        """测试LLMProvider枚举值"""
        from core.llm_client import LLMProvider
        
        assert LLMProvider.VLLM.value == "vllm"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.GEMINI.value == "gemini"
        assert LLMProvider.DEEPSEEK.value == "deepseek"
    
    def test_llm_provider_enum_members(self):
        """测试LLMProvider枚举成员"""
        from core.llm_client import LLMProvider
        
        providers = list(LLMProvider)
        assert len(providers) == 4
        assert LLMProvider.VLLM in providers
        assert LLMProvider.OPENAI in providers
        assert LLMProvider.GEMINI in providers
        assert LLMProvider.DEEPSEEK in providers


class TestLLMClientInit:
    """LLMClient初始化测试"""
    
    @patch("httpx.AsyncClient")
    def test_init_with_explicit_provider(self, mock_httpx, base_config):
        """测试使用明确指定的提供商初始化"""
        from core.llm_client import LLMClient, LLMProvider
        
        client = LLMClient(base_config)
        
        assert client.provider == LLMProvider.VLLM
        assert client.config == base_config
        mock_httpx.assert_called_once_with(timeout=60.0)
    
    @patch("httpx.AsyncClient")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True)
    def test_init_auto_detect_gemini(self, mock_httpx):
        """测试自动检测Gemini提供商"""
        from core.llm_client import LLMClient, LLMProvider
        
        config = {}  # 没有指定provider
        client = LLMClient(config)
        
        assert client.provider == LLMProvider.GEMINI
    
    @patch("httpx.AsyncClient")
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    def test_init_auto_detect_deepseek(self, mock_httpx):
        """测试自动检测DeepSeek提供商"""
        from core.llm_client import LLMClient, LLMProvider
        
        config = {}  # 没有指定provider
        client = LLMClient(config)
        
        assert client.provider == LLMProvider.DEEPSEEK
    
    @patch("httpx.AsyncClient")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_init_auto_detect_openai(self, mock_httpx):
        """测试自动检测OpenAI提供商"""
        from core.llm_client import LLMClient, LLMProvider
        
        config = {}  # 没有指定provider
        client = LLMClient(config)
        
        assert client.provider == LLMProvider.OPENAI
    
    @patch("httpx.AsyncClient")
    @patch.dict(os.environ, {}, clear=True)
    def test_init_auto_detect_fallback_vllm(self, mock_httpx):
        """测试自动检测回退到vLLM"""
        from core.llm_client import LLMClient, LLMProvider
        
        config = {}  # 没有指定provider，也没有环境变量
        client = LLMClient(config)
        
        assert client.provider == LLMProvider.VLLM
    
    @patch("httpx.AsyncClient")
    def test_init_unknown_provider_fallback(self, mock_httpx):
        """测试未知提供商回退到自动检测"""
        from core.llm_client import LLMClient, LLMProvider
        
        config = {"provider": "unknown_provider"}
        
        with patch.dict(os.environ, {}, clear=True):
            client = LLMClient(config)
            assert client.provider == LLMProvider.VLLM  # 回退到vLLM


class TestLLMClientCodeGeneration:
    """LLMClient代码生成测试"""
    
    @pytest_asyncio.fixture
    async def llm_client(self, base_config):
        """创建LLMClient实例"""
        with patch("httpx.AsyncClient"):
            from core.llm_client import LLMClient
            client = LLMClient(base_config)
            
            # Mock _call_api方法
            client._call_api = AsyncMock()
            client._extract_code = MagicMock()
            client._build_code_prompt = MagicMock()
            
            return client
    
    @pytest.mark.asyncio
    async def test_generate_code_success(self, llm_client):
        """测试成功生成代码"""
        # Mock返回值
        mock_response = "思考过程：这是一个简单的Python函数\n\n```python\ndef hello():\n    print('Hello, World!')\n```"
        mock_code = "def hello():\n    print('Hello, World!')"
        
        llm_client._call_api.return_value = mock_response
        llm_client._extract_code.return_value = mock_code
        llm_client._build_code_prompt.return_value = "生成一个Hello World函数"
        
        result = await llm_client.generate_code("生成一个Hello World函数", "python")
        
        assert result["success"] == True
        assert result["code"] == mock_code
        assert "思考过程" in result["thinking"]
        
        # 验证方法调用
        llm_client._build_code_prompt.assert_called_once_with("生成一个Hello World函数", "python")
        llm_client._call_api.assert_called_once()
        llm_client._extract_code.assert_called_once_with(mock_response, "python")
    
    @pytest.mark.asyncio
    async def test_generate_code_long_thinking(self, llm_client):
        """测试长思考过程的截断"""
        # 创建超长的响应
        long_response = "思考过程：" + "x" * 3000 + "结束"
        mock_code = "def test(): pass"
        
        llm_client._call_api.return_value = long_response
        llm_client._extract_code.return_value = mock_code
        
        result = await llm_client.generate_code("测试", "python")
        
        # 验证思考过程被截断
        thinking = result["thinking"]
        assert len(thinking) <= 2100  # 1000 + 截断信息 + 1000
        assert "内容过长，已截断" in thinking
    
    @pytest.mark.asyncio
    async def test_generate_code_api_error(self, llm_client):
        """测试API调用错误"""
        # Mock API调用失败
        llm_client._call_api.side_effect = Exception("API调用失败")
        
        with pytest.raises(RuntimeError, match="无法生成代码"):
            await llm_client.generate_code("测试", "python")
    
    @pytest.mark.asyncio
    async def test_generate_code_with_cache_disabled(self, llm_client):
        """测试禁用缓存的代码生成"""
        # 设置环境变量
        with patch.dict(os.environ, {"DISABLE_CACHE": "true"}):
            mock_response = "简单的代码"
            mock_code = "print('test')"
            
            llm_client._call_api.return_value = mock_response
            llm_client._extract_code.return_value = mock_code
            
            result = await llm_client.generate_code("测试", "python")
            
            assert result["success"] == True
            assert result["code"] == mock_code


class TestLLMClientWebActions:
    """LLMClient Web操作生成测试"""
    
    @pytest_asyncio.fixture
    async def llm_client(self, base_config):
        """创建LLMClient实例"""
        with patch("httpx.AsyncClient"):
            from core.llm_client import LLMClient
            client = LLMClient(base_config)
            
            # Mock相关方法
            client._call_api = AsyncMock()
            client._build_web_prompt = MagicMock()
            client._extract_web_actions = MagicMock()
            client._fallback_web_actions = MagicMock()
            
            return client
    
    @pytest.mark.asyncio
    async def test_generate_web_actions_success(self, llm_client):
        """测试成功生成Web操作"""
        mock_response = "导航到网站，点击登录按钮"
        mock_actions = [
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "selector": "#login-btn"}
        ]
        
        llm_client._call_api.return_value = mock_response
        llm_client._extract_web_actions.return_value = mock_actions
        llm_client._build_web_prompt.return_value = "生成登录操作"
        
        result = await llm_client.generate_web_actions("登录到网站", "<html>...</html>")
        
        assert result == mock_actions
        assert len(result) == 2
        assert result[0]["action"] == "navigate"
        assert result[1]["action"] == "click"
        
        # 验证方法调用
        llm_client._build_web_prompt.assert_called_once_with("登录到网站", "<html>...</html>")
        llm_client._call_api.assert_called_once()
        llm_client._extract_web_actions.assert_called_once_with(mock_response)
    
    @pytest.mark.asyncio
    async def test_generate_web_actions_api_error(self, llm_client):
        """测试Web操作生成API错误"""
        # Mock API调用失败
        llm_client._call_api.side_effect = Exception("网络错误")
        
        # Mock fallback返回值
        fallback_actions = [{"action": "error", "message": "fallback"}]
        llm_client._fallback_web_actions.return_value = fallback_actions
        
        result = await llm_client.generate_web_actions("测试", "")
        
        assert result == fallback_actions
        llm_client._fallback_web_actions.assert_called_once_with("测试")


class TestLLMClientReasoning:
    """LLMClient推理生成测试"""
    
    @pytest_asyncio.fixture
    async def llm_client(self, base_config):
        """创建LLMClient实例"""
        with patch("httpx.AsyncClient"):
            from core.llm_client import LLMClient
            client = LLMClient(base_config)
            
            # Mock相关方法
            client._call_api = AsyncMock()
            client._build_reasoning_prompt = MagicMock()
            client._parse_reasoning_response = MagicMock()
            
            return client
    
    @pytest.mark.asyncio
    async def test_generate_reasoning_success(self, llm_client):
        """测试成功生成推理"""
        mock_response = "分析任务，选择工具"
        mock_parsed = {
            "thinking": "需要使用Python执行器",
            "action": "execute_code",
            "tool": "python-executor",
            "parameters": {"code": "print('hello')"},
            "confidence": 0.9
        }
        
        llm_client._call_api.return_value = mock_response
        llm_client._parse_reasoning_response.return_value = mock_parsed
        
        available_tools = ["python-executor", "web-navigator"]
        previous_steps = [{"step": 1, "action": "start"}]
        browser_context = {"url": "https://example.com"}
        
        result = await llm_client.generate_reasoning(
            "执行Python代码", available_tools, previous_steps, browser_context
        )
        
        assert result == mock_parsed
        assert result["action"] == "execute_code"
        assert result["confidence"] == 0.9
        
        # 验证方法调用
        llm_client._build_reasoning_prompt.assert_called_once_with(
            "执行Python代码", available_tools, previous_steps, browser_context
        )
    
    @pytest.mark.asyncio
    async def test_generate_reasoning_api_error(self, llm_client):
        """测试推理生成API错误"""
        # Mock API调用失败
        llm_client._call_api.side_effect = Exception("推理失败")
        
        result = await llm_client.generate_reasoning("测试任务", ["tool1"])
        
        assert result["action"] == "error"
        assert result["confidence"] == 0.0
        assert "推理失败" in result["thinking"]
    
    @pytest.mark.asyncio
    async def test_generate_enhanced_reasoning_success(self, llm_client):
        """测试增强推理生成"""
        # Mock相关方法
        llm_client._build_enhanced_reasoning_prompt = MagicMock()
        
        mock_response = "增强推理结果"
        mock_parsed = {
            "thinking": "使用增强推理",
            "action": "enhanced_action",
            "tool": "enhanced-tool",
            "parameters": {},
            "confidence": 0.95
        }
        
        llm_client._call_api.return_value = mock_response
        llm_client._parse_reasoning_response.return_value = mock_parsed
        
        result = await llm_client.generate_enhanced_reasoning(
            "复杂任务", ["tool1", "tool2"], "工具描述", [], {"context": "test"}
        )
        
        assert result == mock_parsed
        assert result["confidence"] == 0.95


class TestLLMClientTaskAnalysis:
    """LLMClient任务分析测试"""
    
    @pytest_asyncio.fixture
    async def llm_client(self, base_config):
        """创建LLMClient实例"""
        with patch("httpx.AsyncClient"):
            from core.llm_client import LLMClient
            client = LLMClient(base_config)
            
            # Mock相关方法
            client._call_api = AsyncMock()
            client._build_task_analysis_prompt = MagicMock()
            client._parse_task_requirements_response = MagicMock()
            
            return client
    
    @pytest.mark.asyncio
    async def test_analyze_task_requirements_success(self, llm_client):
        """测试成功分析任务需求"""
        mock_response = "任务分析结果"
        mock_analysis = {
            "task_type": "code_execution",
            "required_capabilities": ["python", "file_io"],
            "tools_needed": ["python-executor", "file-manager"],
            "reasoning": "需要执行Python代码并处理文件",
            "confidence": 0.85
        }
        
        llm_client._call_api.return_value = mock_response
        llm_client._parse_task_requirements_response.return_value = mock_analysis
        
        result = await llm_client.analyze_task_requirements("编写并执行Python脚本处理CSV文件")
        
        assert result == mock_analysis
        assert result["task_type"] == "code_execution"
        assert "python-executor" in result["tools_needed"]
        assert result["confidence"] == 0.85
        
        # 验证方法调用
        llm_client._build_task_analysis_prompt.assert_called_once_with(
            "编写并执行Python脚本处理CSV文件"
        )
    
    @pytest.mark.asyncio
    async def test_analyze_task_requirements_api_error(self, llm_client):
        """测试任务分析API错误"""
        # Mock API调用失败
        llm_client._call_api.side_effect = Exception("分析失败")
        
        result = await llm_client.analyze_task_requirements("测试任务")
        
        assert result["task_type"] == "unknown"
        assert result["required_capabilities"] == []
        assert result["tools_needed"] == []
        assert result["confidence"] == 0.0
        assert "分析失败" in result["reasoning"]


class TestLLMClientUtilityMethods:
    """LLMClient工具方法测试"""
    
    @pytest_asyncio.fixture
    async def llm_client(self, base_config):
        """创建LLMClient实例"""
        with patch("httpx.AsyncClient"):
            from core.llm_client import LLMClient
            client = LLMClient(base_config)
            
            # Mock相关方法
            client._call_api = AsyncMock()
            client._build_summary_prompt = MagicMock()
            client._build_completion_check_prompt = MagicMock()
            client._parse_completion_response = MagicMock()
            
            return client
    
    @pytest.mark.asyncio
    async def test_generate_task_summary_success(self, llm_client):
        """测试生成任务总结"""
        mock_response = "任务成功完成，执行了3个步骤，生成了预期的输出结果。"
        llm_client._call_api.return_value = mock_response
        
        task_description = "计算斐波那契数列"
        steps = [{"step": 1}, {"step": 2}, {"step": 3}]
        final_outputs = ["结果: 55"]
        
        result = await llm_client.generate_task_summary(task_description, steps, final_outputs)
        
        assert result == mock_response
        llm_client._build_summary_prompt.assert_called_once_with(task_description, steps, final_outputs)
    
    @pytest.mark.asyncio
    async def test_generate_task_summary_api_error(self, llm_client):
        """测试任务总结API错误"""
        llm_client._call_api.side_effect = Exception("总结失败")
        
        result = await llm_client.generate_task_summary("测试", [], ["output1", "output2"])
        
        # 验证返回默认总结
        assert "Task completed with 0 steps" in result
        assert "output1" in result
    
    @pytest.mark.asyncio
    async def test_check_task_completion_success(self, llm_client):
        """测试检查任务完成状态"""
        mock_response = "任务已完成"
        mock_parsed = {
            "completed": True,
            "confidence": 0.9,
            "reason": "所有目标已达成"
        }
        
        llm_client._call_api.return_value = mock_response
        llm_client._parse_completion_response.return_value = mock_parsed
        
        result = await llm_client.check_task_completion("测试任务", [], ["输出"])
        
        assert result == mock_parsed
        assert result["completed"] == True
        assert result["confidence"] == 0.9
    
    @pytest.mark.asyncio
    async def test_check_task_completion_api_error(self, llm_client):
        """测试任务完成检查API错误"""
        llm_client._call_api.side_effect = Exception("检查失败")
        
        result = await llm_client.check_task_completion("测试", [], [])
        
        assert result["completed"] == False
        assert result["confidence"] == 0.0
        assert "检查失败" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_get_next_action_unified_interface(self, llm_client):
        """测试统一的下一步行动接口"""
        # Mock generate_enhanced_reasoning方法
        llm_client.generate_enhanced_reasoning = AsyncMock()
        mock_result = {
            "thinking": "统一接口测试",
            "action": "test_action",
            "tool": "test-tool",
            "parameters": {},
            "confidence": 0.8
        }
        llm_client.generate_enhanced_reasoning.return_value = mock_result
        
        result = await llm_client.get_next_action(
            "测试任务", ["tool1"], "工具描述", [], {"context": "test"}
        )
        
        assert result == mock_result
        
        # 验证调用了generate_enhanced_reasoning
        llm_client.generate_enhanced_reasoning.assert_called_once_with(
            task_description="测试任务",
            available_tools=["tool1"],
            tool_descriptions="工具描述",
            previous_steps=[],
            execution_context={"context": "test"}
        )


if __name__ == "__main__":
    pytest.main(["-v", __file__])