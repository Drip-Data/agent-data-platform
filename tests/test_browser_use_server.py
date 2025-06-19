#!/usr/bin/env python3
"""
Browser-Use MCP Server Tests (Fixed)
测试Browser-Use服务器的完整功能，验证与browser-use库的集成
"""

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 测试依赖检查
browser_use_available = True
langchain_available = True

try:
    from core.config_manager import ConfigManager
    from core.llm_client import LLMClient
    from mcp_servers.browser_use_server.main import BrowserUseMCPServer, BrowserUseLLMAdapter
except ImportError as e:
    browser_use_available = False
    logger.warning(f"Browser-Use components not available: {e}")

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    langchain_available = False
    logger.warning("LangChain not available")


@pytest.mark.skipif(not browser_use_available or not langchain_available, 
                   reason="Browser-Use or LangChain dependencies not available")
class TestBrowserUseLLMAdapter:
    """测试Browser-Use LLM适配器"""
    
    def test_adapter_creation(self):
        """测试适配器创建"""
        mock_llm_client = MagicMock()
        mock_llm_client.provider = MagicMock()
        mock_llm_client.provider.value = "test_provider"
        
        adapter = BrowserUseLLMAdapter(mock_llm_client)
        assert adapter._llm_type == "browser_use_adapter_test_provider"
    
    def test_predict_sync(self):
        """测试同步预测 - 简化版本"""
        mock_llm_client = MagicMock()
        mock_llm_client.provider = MagicMock()
        mock_llm_client.provider.value = "test_provider"
        
        adapter = BrowserUseLLMAdapter(mock_llm_client)
        
        # 直接测试模拟的部分，避免复杂的事件循环mocking
        with patch.object(adapter, '_generate') as mock_generate:
            from langchain_core.outputs import LLMResult, Generation
            
            # 模拟_generate返回值
            mock_generation = Generation(text="Test response")
            mock_result = LLMResult(generations=[[mock_generation]])
            mock_generate.return_value = mock_result
            
            result = adapter.predict("Test input")
            assert result == "Test response"


@pytest.mark.skipif(not browser_use_available, 
                   reason="Browser-Use dependencies not available")
class TestBrowserUseMCPServer:
    """测试Browser-Use MCP服务器"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """模拟配置管理器"""
        mock_config = MagicMock(spec=ConfigManager)
        
        # 模拟LLM配置
        mock_config.get_llm_config.return_value = {
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "test_key"
        }
        
        # 模拟端口配置
        mock_config.get_ports_config.return_value = {
            "mcp_servers": {
                "browser_use": {"port": 8003},
                "toolscore_mcp": {"port": 8000}
            }
        }
        
        return mock_config
    
    def test_server_initialization(self, mock_config_manager):
        """测试服务器初始化"""
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            server = BrowserUseMCPServer(mock_config_manager)
            
            assert server.server_name == "browser_use_server"
            assert server.server_id == "browser-use-mcp-server"
            assert "ws://localhost:8003" in server.endpoint
            assert server.browser_session is None
            assert server.controller is None
    
    def test_get_capabilities(self, mock_config_manager):
        """测试获取功能列表"""
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            server = BrowserUseMCPServer(mock_config_manager)
            capabilities = server.get_capabilities()
            
            # 验证核心功能
            capability_names = [cap.name for cap in capabilities]
            
            # 核心功能检查
            expected_features = [
                "browser_use_execute_task",
                "browser_navigate", 
                "browser_search_google",
                "browser_click_element",
                "browser_screenshot",
                "browser_get_page_info"
            ]
            
            for feature in expected_features:
                assert feature in capability_names, f"Missing feature: {feature}"
                
            # 验证总数
            assert len(capabilities) >= 20, f"Expected at least 20 capabilities, got {len(capabilities)}"
    
    @pytest.mark.asyncio
    async def test_handle_unsupported_action(self, mock_config_manager):
        """测试不支持的动作"""
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            server = BrowserUseMCPServer(mock_config_manager)
            result = await server.handle_tool_action("unsupported_action", {})
            
            assert result["success"] is False
            assert "Unsupported action" in result["error_message"]
            assert result["error_type"] == "UnsupportedAction"
    
    @pytest.mark.asyncio
    async def test_get_page_info_no_session(self, mock_config_manager):
        """测试无会话时获取页面信息"""
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            server = BrowserUseMCPServer(mock_config_manager)
            result = await server._get_page_info()
            
            assert result["success"] is False
            assert result["error_type"] == "SessionError"
    
    @pytest.mark.asyncio
    async def test_close_session_no_session(self, mock_config_manager):
        """测试关闭空会话"""
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            server = BrowserUseMCPServer(mock_config_manager)
            result = await server._close_session()
            
            assert result["success"] is True
            assert "closed successfully" in result["data"]["message"]


@pytest.mark.skipif(not browser_use_available, 
                   reason="Browser-Use dependencies not available")
class TestBrowserUseVsBrowserNavigator:
    """比较Browser-Use服务器与Browser Navigator服务器"""
    
    def test_capability_comparison(self):
        """比较两个服务器的功能"""
        # 创建模拟配置
        mock_config = MagicMock(spec=ConfigManager)
        mock_config.get_llm_config.return_value = {"provider": "openai"}
        mock_config.get_ports_config.return_value = {
            "mcp_servers": {
                "browser_use": {"port": 8003},
                "browser_navigator": {"port": 8002},
                "toolscore_mcp": {"port": 8000}
            }
        }
        
        # 创建Browser-Use服务器实例
        with patch.dict(os.environ, {"BROWSER_USE_SERVER_PORT": "8003"}):
            browser_use_server = BrowserUseMCPServer(mock_config)
        
        # 尝试导入browser navigator服务器
        try:
            from mcp_servers.browser_navigator_server.main import BrowserNavigatorMCPServer
            browser_nav_server = BrowserNavigatorMCPServer(mock_config)
            
            # 获取功能列表
            browser_use_caps = [cap.name for cap in browser_use_server.get_capabilities()]
            browser_nav_caps = [cap.name for cap in browser_nav_server.get_capabilities()]
            
            # Browser-Use应该包含更多功能
            assert len(browser_use_caps) > len(browser_nav_caps)
            
            # Browser-Use应该包含AI任务执行功能
            assert "browser_use_execute_task" in browser_use_caps
            assert "browser_use_execute_task" not in browser_nav_caps
            
            logger.info(f"Browser-Use功能数量: {len(browser_use_caps)}")
            logger.info(f"Browser Navigator功能数量: {len(browser_nav_caps)}")
            
        except ImportError:
            pytest.skip("Browser Navigator not available for comparison")


class TestBasicFunctionality:
    """基础功能测试，不依赖外部库"""
    
    def test_project_structure(self):
        """测试项目结构"""
        # 检查重要文件是否存在
        important_files = [
            project_root / "mcp_servers" / "browser_use_server" / "main.py",
            project_root / "mcp_servers" / "browser_use_server" / "__init__.py",
            project_root / "tests" / "test_browser_use_server.py"
        ]
        
        for file_path in important_files:
            assert file_path.exists(), f"Missing important file: {file_path}"
    
    def test_imports_work(self):
        """测试基本导入是否工作"""
        # 这个测试在模块级别已经运行了
        if not browser_use_available:
            pytest.skip("Browser-Use not available")
        
        # 如果到了这里，说明导入成功
        assert browser_use_available is True


if __name__ == "__main__":
    # 运行测试
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--disable-warnings"
    ])