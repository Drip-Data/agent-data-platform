#!/usr/bin/env python3
"""
MicroSandbox MCP Server 综合测试套件
测试MicroSandbox服务器的完整功能，包括安全执行、会话管理、错误处理等
"""

import asyncio
import pytest
import time
import logging
from unittest.mock import Mock, AsyncMock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer

# 配置pytest-asyncio
pytestmark = pytest.mark.asyncio

logger = logging.getLogger(__name__)

class TestMicroSandboxServer:
    """MicroSandbox服务器综合测试套件"""
    
    @pytest.fixture
    def server(self, mock_config_manager):
        """创建测试服务器实例"""
        return MicroSandboxMCPServer(mock_config_manager)
    
    # 1. 输入验证测试
    async def test_empty_code_execution(self, server):
        """测试空代码执行"""
        result = await server.handle_tool_action("microsandbox_execute", {"code": ""})
        assert result["success"] is False
        assert "代码不能为空" in result["error_message"]
        assert result["error_type"] == "InvalidInput"
    
    async def test_none_code_execution(self, server):
        """测试None代码执行"""
        result = await server.handle_tool_action("microsandbox_execute", {})
        assert result["success"] is False
        assert result["error_type"] == "InvalidInput"
    
    async def test_empty_package_name(self, server):
        """测试空包名安装"""
        result = await server.handle_tool_action("microsandbox_install_package", {"package_name": ""})
        assert result["success"] is False
        assert "包名不能为空" in result["error_message"]
        assert result["error_type"] == "InvalidInput"
    
    async def test_empty_session_id_close(self, server):
        """测试关闭空会话ID"""
        result = await server.handle_tool_action("microsandbox_close_session", {"session_id": ""})
        assert result["success"] is False
        assert "会话ID不能为空" in result["error_message"]
        assert result["error_type"] == "InvalidInput"
    
    # 2. 会话管理测试
    async def test_nonexistent_session_close(self, server):
        """测试关闭不存在的会话"""
        result = await server.handle_tool_action("microsandbox_close_session", {"session_id": "nonexistent"})
        assert result["success"] is False
        assert "会话不存在" in result["error_message"]
        assert result["error_type"] == "SessionNotFound"
    
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_session_creation_failure(self, mock_sandbox, server):
        """测试会话创建失败"""
        # 模拟沙箱创建失败
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = Exception("沙箱创建失败")
        mock_sandbox.create.return_value = mock_context
        
        result = await server.handle_tool_action("microsandbox_execute", {
            "code": "print('test')",
            "session_id": "test_session"
        })
        
        assert result["success"] is False
        assert "沙箱创建失败" in result["error_message"]
    
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_session_cleanup_failure(self, mock_sandbox, server):
        """测试会话清理失败"""
        # 创建一个模拟会话
        server.active_sessions["test_session"] = {
            "sandbox": AsyncMock(),
            "sandbox_instance": AsyncMock(),
            "created_at": time.time(),
            "last_accessed": time.time()
        }
        
        # 模拟清理失败
        server.active_sessions["test_session"]["sandbox"].__aexit__.side_effect = Exception("清理失败")
        
        result = await server.handle_tool_action("microsandbox_close_session", {"session_id": "test_session"})
        
        assert result["success"] is False
        assert "关闭会话失败" in result["error_message"]
        assert result["error_type"] == "SessionCloseError"
    
    # 3. 代码执行异常测试
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_code_execution_timeout(self, mock_sandbox, server):
        """测试代码执行超时"""
        # 模拟超时
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_sandbox_instance.run.side_effect = asyncio.TimeoutError("执行超时")
        
        result = await server.handle_tool_action("microsandbox_execute", {
            "code": "while True: pass",  # 无限循环
            "timeout": 1
        })
        
        assert result["success"] is False
        assert result["error_type"] == "SandboxError"
    
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_malformed_code_execution(self, mock_sandbox, server):
        """测试格式错误的代码"""
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_output = Mock()
        mock_output.exit_code = 1
        mock_output.stdout = ""
        mock_output.stderr = "SyntaxError: invalid syntax"
        mock_result.output.return_value = mock_output
        mock_sandbox_instance.run.return_value = mock_result
        
        result = await server.handle_tool_action("microsandbox_execute", {
            "code": "print('hello world'"  # 缺少右括号
        })
        
        assert result["success"] is False
        assert result["data"]["return_code"] == 1
        assert "SyntaxError" in result["data"]["stderr"]
    
    # 4. 资源泄漏测试
    async def test_session_expiry_cleanup(self, server):
        """测试过期会话清理"""
        # 创建过期会话
        old_time = time.time() - 7200  # 2小时前
        server.active_sessions["expired_session"] = {
            "sandbox": AsyncMock(),
            "sandbox_instance": AsyncMock(),
            "created_at": old_time,
            "last_accessed": old_time
        }
        
        result = await server.handle_tool_action("microsandbox_cleanup_expired", {"max_age": 3600})
        
        assert result["success"] is True
        assert "expired_session" in result["data"]["cleaned_sessions"]
        assert result["data"]["count"] == 1
        assert "expired_session" not in server.active_sessions
    
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_concurrent_session_access(self, mock_sandbox, server):
        """测试并发会话访问"""
        session_id = "concurrent_test"
        
        # 模拟并发访问同一会话
        async def access_session():
            return await server.handle_tool_action("microsandbox_execute", {
                "code": "x = 1",
                "session_id": session_id
            })
        
        # 并发执行多个请求
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_output = Mock()
        mock_output.exit_code = 0
        mock_output.stdout = ""
        mock_output.stderr = ""
        mock_result.output.return_value = mock_output
        mock_sandbox_instance.run.return_value = mock_result
        
        tasks = [access_session() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有请求都成功
        for result in results:
            assert result["success"] is True
        
        # 验证只创建了一个会话
        assert len(server.active_sessions) == 1
    
    # 5. 错误处理测试
    async def test_unsupported_action(self, server):
        """测试不支持的操作"""
        result = await server.handle_tool_action("unsupported_action", {})
        assert result["success"] is False
        assert result["error_type"] == "UnsupportedAction"
        assert "Unsupported action" in result["error_message"]
    
    async def test_invalid_parameters(self, server):
        """测试无效参数"""
        result = await server.handle_tool_action("microsandbox_execute", {
            "code": "print('test')",
            "timeout": "invalid"  # 应该是整数
        })
        # 服务器应该能处理类型错误
        assert isinstance(result, dict)
        assert "success" in result
    
    # 6. 包安装测试
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_package_installation_failure(self, mock_sandbox, server):
        """测试包安装失败"""
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_output = Mock()
        mock_output.exit_code = 1
        mock_output.stdout = ""
        mock_output.stderr = "ERROR: Could not find a version that satisfies the requirement"
        mock_result.output.return_value = mock_output
        mock_sandbox_instance.run.return_value = mock_result
        
        result = await server.handle_tool_action("microsandbox_install_package", {
            "package_name": "nonexistent-package-12345"
        })
        
        assert result["success"] is False
        assert result["data"]["return_code"] == 1
    
    # 7. 内存压力测试
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_memory_intensive_code(self, mock_sandbox, server):
        """测试内存密集型代码"""
        memory_code = """
import sys
# 尝试分配大量内存
try:
    data = [0] * (10**7)  # 约40MB
    print(f"分配内存成功: {len(data)} 个元素")
    del data
    print("内存释放成功")
except MemoryError:
    print("内存不足")
except Exception as e:
    print(f"其他错误: {e}")
"""
        
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_output = Mock()
        mock_output.exit_code = 0
        mock_output.stdout = "分配内存成功: 10000000 个元素\n内存释放成功"
        mock_output.stderr = ""
        mock_result.output.return_value = mock_output
        mock_sandbox_instance.run.return_value = mock_result
        
        result = await server.handle_tool_action("microsandbox_execute", {
            "code": memory_code
        })
        
        assert isinstance(result, dict)
        assert "success" in result
    
    # 8. 会话状态一致性测试
    @patch('mcp_servers.microsandbox_server.main.PythonSandbox')
    async def test_session_state_consistency(self, mock_sandbox, server):
        """测试会话状态一致性"""
        session_id = "state_test"
        
        mock_context = AsyncMock()
        mock_sandbox_instance = AsyncMock()
        mock_context.__aenter__.return_value = mock_sandbox_instance
        mock_sandbox.create.return_value = mock_context
        
        mock_result = AsyncMock()
        mock_output = Mock()
        mock_output.exit_code = 0
        mock_output.stdout = ""
        mock_output.stderr = ""
        mock_result.output.return_value = mock_output
        mock_sandbox_instance.run.return_value = mock_result
        
        # 第一次执行：设置变量
        result1 = await server.handle_tool_action("microsandbox_execute", {
            "code": "x = 42",
            "session_id": session_id
        })
        
        # 第二次执行：使用变量
        result2 = await server.handle_tool_action("microsandbox_execute", {
            "code": "print(x)",
            "session_id": session_id
        })
        
        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["data"]["session_id"] == session_id
        assert result2["data"]["session_id"] == session_id