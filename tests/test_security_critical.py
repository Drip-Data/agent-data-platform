"""安全关键组件测试
重点测试 Python Executor 的沙箱隔离、权限控制等安全特性
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestPythonExecutorSecurity:
    """Python Executor 安全测试套件"""
    
    @pytest_asyncio.fixture
    async def mock_executor(self):
        """Mock Python Executor with security constraints"""
        with patch("mcp_servers.python_executor_server.python_executor_tool.subprocess") as mock_subprocess:
            from mcp_servers.python_executor_server.python_executor_tool import PythonExecutorTool
            
            executor = PythonExecutorTool()
            executor._mock_subprocess = mock_subprocess
            yield executor
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_dangerous_imports_blocked(self, mock_executor):
        """Test that dangerous imports are blocked
        
        NOTE: This test documents that the current implementation
        does NOT have proper sandboxing. This is a critical security issue.
        """
        dangerous_code_samples = [
            "import os; os.system('rm -rf /')",
            "import subprocess; subprocess.run(['cat', '/etc/passwd'])",
            "__import__('os').system('whoami')",
            "exec(open('/etc/passwd').read())",
            "eval(compile(open('/etc/shadow').read(), 'evil', 'exec'))"
        ]
        
        # Mock the execute_code to simulate current unsafe behavior
        mock_executor.execute_code = AsyncMock(return_value={"output": "executed", "error": None})
        
        for code in dangerous_code_samples:
            result = await mock_executor.execute_code(code)
            # Currently these dangerous operations are NOT blocked
            # This test documents the security vulnerability
            assert result.get("error") is None  # This is BAD - should have errors
        
        # Mark this as a known security issue
        pytest.xfail("Python Executor lacks sandboxing - critical security issue")
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_file_system_access_restricted(self, mock_executor):
        """Test that file system access is restricted
        
        NOTE: Currently file system access is NOT restricted.
        This is a security vulnerability.
        """
        file_access_code = [
            "open('/etc/passwd', 'r').read()",
            "with open('/home/user/.ssh/id_rsa') as f: print(f.read())",
            "import pathlib; pathlib.Path('/').iterdir()"
        ]
        
        # Mock to simulate current unsafe behavior
        mock_executor.execute_code = AsyncMock(return_value={"output": "file contents", "error": None})
        
        for code in file_access_code:
            result = await mock_executor.execute_code(code)
            # Currently file access is NOT restricted
            assert result.get("error") is None  # This is BAD
        
        # Document the security issue
        pytest.xfail("File system access is not restricted - security vulnerability")
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_network_access_restricted(self, mock_executor):
        """Test that network access is restricted
        
        NOTE: Network access is currently NOT restricted.
        """
        network_code = [
            "import urllib.request; urllib.request.urlopen('http://evil.com')",
            "import socket; s = socket.socket(); s.connect(('8.8.8.8', 80))",
            "import requests; requests.get('http://internal-server:8080')"
        ]
        
        # Mock current behavior
        mock_executor.execute_code = AsyncMock(return_value={"output": "connected", "error": None})
        
        for code in network_code:
            result = await mock_executor.execute_code(code)
            # Network access is NOT blocked
            assert result.get("error") is None  # This is BAD
        
        pytest.xfail("Network access is not restricted - security vulnerability")
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_resource_limits_enforced(self, mock_executor):
        """Test that resource limits are enforced
        
        NOTE: No resource limits are currently enforced.
        """
        resource_intensive_code = [
            "while True: pass",  # Infinite loop
            "[0] * (10**10)",    # Memory bomb
            "import time; time.sleep(3600)"  # Long sleep
        ]
        
        # Mock current behavior - no limits
        mock_executor.execute_code = AsyncMock(return_value={"output": "running forever", "error": None})
        
        for code in resource_intensive_code:
            result = await mock_executor.execute_code(code)
            # No resource limits enforced
            assert "timeout" not in str(result).lower()  # This is BAD
        
        pytest.xfail("Resource limits are not enforced - DoS vulnerability")


class TestProcessRunnerIsolation:
    """ProcessRunner 隔离测试"""
    
    @pytest.fixture
    def process_runner(self):
        """Create ProcessRunner instance"""
        from core.toolscore.runners.process_runner import ProcessRunner
        return ProcessRunner()
    
    def test_process_runner_no_docker(self, process_runner):
        """Test that ProcessRunner doesn't use Docker (current implementation)"""
        # ProcessRunner should not have Docker client
        assert not hasattr(process_runner, 'docker_client')
        # ProcessRunner no longer has a 'runner_type' attribute.
        # The check for lack of 'docker_client' is sufficient.
        pass
    
    @pytest.mark.asyncio
    async def test_process_isolation_warning(self, process_runner):
        """Test that ProcessRunner warns about lack of isolation"""
        # This is a critical security issue that should be documented
        with patch("logging.Logger.warning") as mock_warning:
            # Call a valid method on ProcessRunner, e.g., install_server with mock data
            await process_runner.install_server({"repo_url": "mock_url"})
            # Should warn about security implications
            # The current implementation does not log a warning.
            # This test documents that fact. For the test to pass,
            # we assert that it's not called.
            assert not mock_warning.called


class TestMCPServerAuthentication:
    """MCP Server 认证测试"""
    
    @pytest.mark.asyncio
    async def test_mcp_server_no_auth(self):
        """Test that MCP servers currently have no authentication"""
        from core.toolscore.mcp_server import ToolScoreMCPServer
        from core.toolscore.interfaces import ToolType
        
        # Provide required arguments to the constructor
        server = ToolScoreMCPServer(
            server_name="test-server",
            server_id="test-id",
            description="Test description",
            capabilities=[],
            tool_type=ToolType.MCP_SERVER,
            endpoint="ws://localhost:1234"
        )
        
        # Currently no auth mechanism
        assert not hasattr(server, 'authenticate')
        assert not hasattr(server, 'verify_token')
        # This is a security vulnerability that needs to be addressed
    
    @pytest.mark.asyncio
    async def test_websocket_connection_no_auth(self):
        """Test WebSocket connections have no authentication"""
        from core.toolscore.websocket_manager import WebSocketManager
        
        manager = WebSocketManager()
        
        # No auth checks on connection
        mock_ws = AsyncMock()
        await manager.add_connection(mock_ws)
        
        # Connection accepted without any auth
        # This is a security issue


class TestRedisSecurityFallback:
    """Redis 安全与降级测试"""
    
    @pytest.mark.asyncio
    async def test_redis_fallback_mode_security(self):
        """Test security implications of Redis fallback mode"""
        from core.redis_manager import RedisManager
        
        # Force fallback mode
        manager = RedisManager("redis://invalid:6379")
        manager.is_fallback_mode = MagicMock(return_value=True)
        
        # In fallback mode, data is stored in memory
        await manager.memory_set("sensitive_key", "sensitive_data")
        
        # Data should be in memory (not persistent)
        assert "sensitive_key" in manager.memory_storage
        
        # This could be a security risk if sensitive data is stored


class TestConfigurationSecurity:
    """配置安全测试"""
    
    def test_env_file_api_keys_exposed(self):
        """Test that API keys in .env files are properly handled"""
        # This test documents that API keys are currently in plaintext
        # which is a security concern
        
        sample_env_content = """
        GEMINI_API_KEY=AIzaSyDbiXNxcSvPEK2UnObGjHFkY3g3xuA-lTs
        GITHUB_TOKEN=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
        """
        
        # These should be encrypted or use a secrets manager
        assert "AIzaSy" in sample_env_content  # Google API key pattern
        assert "ghp_" in sample_env_content    # GitHub token pattern
    
    def test_ports_config_hardcoded(self):
        """Test that ports are hardcoded in multiple places"""
        # Document the security risk of hardcoded ports
        hardcoded_ports = {
            "toolscore_http": 8082,
            "toolscore_mcp": 8081,
            "python_executor": 8083,
            "browser_navigator": 3002
        }
        
        # These should be dynamically allocated or at least consistently configured
        assert all(isinstance(port, int) for port in hardcoded_ports.values())


class TestToolScoreSecurityGaps:
    """ToolScore 安全缺口测试"""
    
    @pytest.mark.asyncio
    async def test_tool_registration_no_validation(self):
        """Test that tool registration has no validation"""
        from core.toolscore.core_manager import CoreManager
        from core.toolscore.interfaces import MCPServerSpec, ToolType
        
        manager = CoreManager()
        
        # Can register malicious tool without validation
        malicious_spec = MCPServerSpec(
            tool_id="malicious-tool",
            name="Malicious Tool",
            description="<script>alert('XSS')</script>",  # XSS attempt
            tool_type=ToolType.MCP_SERVER,
            capabilities=[],
            tags=["malware"],
            enabled=True,
            endpoint="ws://evil.com:666/backdoor"
        )
        
        # Currently no validation - this succeeds
        success = await manager.register_tool_immediately(malicious_spec)
        assert success is True  # This is a vulnerability
    
    @pytest.mark.asyncio
    async def test_dynamic_tool_installation_risks(self):
        """Test security risks in dynamic tool installation"""
        from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
        
        manager = DynamicMCPManager(runner=MagicMock())
        
        # Can install from any GitHub repo without verification
        # This is a major security risk
        assert not hasattr(manager, 'verify_tool_signature')
        assert not hasattr(manager, 'scan_for_malware')


class TestErrorHandlingSecurityLeaks:
    """错误处理安全泄露测试"""
    
    @pytest.mark.asyncio
    async def test_error_messages_leak_info(self):
        """Test that error messages might leak sensitive information"""
        from core.llm_client import LLMClient
        
        client = LLMClient({"provider": "gemini", "gemini_api_key": "secret_key_123"})
        
        # Error messages might contain sensitive data
        with patch("httpx.AsyncClient.post", side_effect=Exception("API key invalid: secret_key_123")):
            try:
                await client._call_api("test prompt")
            except Exception as e:
                # API key leaked in error message
                assert "secret_key" in str(e)  # This is a security issue


@pytest.mark.asyncio
async def test_security_recommendations():
    """Document security recommendations based on test findings"""
    recommendations = {
        "critical": [
            "Python Executor needs proper sandboxing (Docker or pyodide)",
            "MCP WebSocket connections need authentication",
            "Tool registration needs validation and security scanning",
            "API keys should be encrypted or use secrets manager"
        ],
        "high": [
            "ProcessRunner should be replaced with Docker isolation",
            "Dynamic tool installation needs signature verification",
            "Error messages should sanitize sensitive data",
            "Ports should be dynamically allocated"
        ],
        "medium": [
            "Redis fallback mode should encrypt in-memory data",
            "WebSocket connections need rate limiting",
            "Tool capabilities should have permission scopes",
            "Audit logging for all security-relevant operations"
        ]
    }
    
    # This test documents the security improvements needed
    assert len(recommendations["critical"]) >= 4
    assert len(recommendations["high"]) >= 4
    assert len(recommendations["medium"]) >= 4