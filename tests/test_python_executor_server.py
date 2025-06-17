"""
Comprehensive tests for Python Executor MCP Server
Tests the main server functionality, tool execution, error handling, and server lifecycle
"""

import pytest
import pytest_asyncio
import asyncio
import json
import tempfile
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.python_executor_server.main import PythonExecutorMCPServer
from mcp_servers.python_executor_server.python_executor_tool import PythonExecutorTool
from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.config_manager import ConfigManager


class TestPythonExecutorTool:
    """Test cases for PythonExecutorTool class"""
    
    @pytest_asyncio.fixture
    async def python_tool(self):
        """Create PythonExecutorTool instance for testing"""
        with patch('mcp_servers.python_executor_server.python_executor_tool.get_python_execution_dir') as mock_get_dir:
            mock_get_dir.return_value = Path(tempfile.mkdtemp())
            tool = PythonExecutorTool()
            yield tool
            # Cleanup
            try:
                tool.cleanup()
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_execute_code_success(self, python_tool):
        """Test successful code execution"""
        code = "print('Hello, World!')"
        result = await python_tool.execute_code(code)
        
        assert result["success"] is True
        assert "Hello, World!" in result["stdout"]
        assert result["return_code"] == 0
    
    @pytest.mark.asyncio
    async def test_execute_code_with_error(self, python_tool):
        """Test code execution with syntax error"""
        code = "print('Missing quote)"
        result = await python_tool.execute_code(code)
        
        assert result["success"] is False
        assert result["return_code"] != 0
        assert "SyntaxError" in result["stderr"] or len(result["stderr"]) > 0
    
    @pytest.mark.asyncio
    async def test_execute_code_timeout(self, python_tool):
        """Test code execution timeout"""
        code = "import time; time.sleep(10)"
        result = await python_tool.execute_code(code, timeout=1)
        
        assert result["success"] is False
        assert "timeout" in result.get("error", "").lower()
    
    @pytest.mark.asyncio
    async def test_code_safety_check(self, python_tool):
        """Test code safety validation"""
        dangerous_code = "import os; os.system('rm -rf /')"
        result = await python_tool.execute_code(dangerous_code)
        
        assert result["success"] is False
        assert "blocked" in result.get("error", "").lower()
    
    @pytest.mark.asyncio
    async def test_analyze_data_list(self, python_tool):
        """Test data analysis with list input"""
        with patch('mcp_servers.python_executor_server.python_executor_tool._get_pandas') as mock_pd:
            mock_pandas = MagicMock()
            mock_df = MagicMock()
            mock_df.describe.return_value.to_string.return_value = "Test description"
            mock_df.shape = (5, 1)
            mock_df.columns.tolist.return_value = ["0"]
            mock_pandas.DataFrame.return_value = mock_df
            mock_pd.return_value = mock_pandas
            
            data = [1, 2, 3, 4, 5]
            result = await python_tool.analyze_data(data, "describe")
            
            assert result["success"] is True
            assert "result" in result
            assert result["data_shape"] == (5, 1)
    
    @pytest.mark.asyncio
    async def test_analyze_data_pandas_unavailable(self, python_tool):
        """Test data analysis when pandas is not available"""
        with patch('mcp_servers.python_executor_server.python_executor_tool._get_pandas') as mock_pd:
            mock_pd.return_value = None
            
            data = [1, 2, 3, 4, 5]
            result = await python_tool.analyze_data(data)
            
            assert result["success"] is False
            assert "pandas not available" in result["error"]
    
    @pytest.mark.asyncio
    async def test_create_visualization(self, python_tool):
        """Test visualization creation"""
        with patch('mcp_servers.python_executor_server.python_executor_tool._get_matplotlib') as mock_mpl:
            mock_matplotlib = MagicMock()
            mock_plt = MagicMock()
            mock_mpl.return_value = (mock_matplotlib, mock_plt)
            
            data = [1, 2, 3, 4, 5]
            result = await python_tool.create_visualization(data, "line", "Test Plot")
            
            assert result["success"] is True
            assert "plot_path" in result
            assert result["plot_type"] == "line"
            mock_plt.plot.assert_called_once_with(data)
            mock_plt.savefig.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_visualization_matplotlib_unavailable(self, python_tool):
        """Test visualization when matplotlib is not available"""
        with patch('mcp_servers.python_executor_server.python_executor_tool._get_matplotlib') as mock_mpl:
            mock_mpl.return_value = (None, None)
            
            data = [1, 2, 3, 4, 5]
            result = await python_tool.create_visualization(data)
            
            assert result["success"] is False
            assert "matplotlib not available" in result["error"]
    
    @pytest.mark.asyncio
    async def test_install_package_success(self, python_tool):
        """Test successful package installation"""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"Successfully installed", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            result = await python_tool.install_package("requests")
            
            assert result["success"] is True
            assert result["package"] == "requests"
            assert result["return_code"] == 0
    
    @pytest.mark.asyncio
    async def test_install_package_invalid_name(self, python_tool):
        """Test package installation with invalid name"""
        result = await python_tool.install_package("invalid|package")
        
        assert result["success"] is False
        assert "Invalid or potentially unsafe" in result["error"]
    
    def test_is_safe_package_name(self, python_tool):
        """Test package name validation"""
        assert python_tool._is_safe_package_name("requests") is True
        assert python_tool._is_safe_package_name("django-rest-framework") is True
        assert python_tool._is_safe_package_name("numpy") is True
        assert python_tool._is_safe_package_name("invalid|package") is False
        assert python_tool._is_safe_package_name("package;rm") is False
        assert python_tool._is_safe_package_name("") is False


class TestPythonExecutorMCPServer:
    """Test cases for PythonExecutorMCPServer class"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock ConfigManager"""
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'python_executor': {'port': 9083},
                'toolscore_mcp': {'port': 9090}
            }
        }
        return config_manager
    
    @pytest.fixture
    def server(self, mock_config_manager):
        """Create PythonExecutorMCPServer instance"""
        return PythonExecutorMCPServer(mock_config_manager)
    
    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.server_name == "python_executor_server"
        assert server.server_id == "python-executor-mcp-server"
        assert server.endpoint == "ws://localhost:9083"
        assert server.toolscore_endpoint == "ws://localhost:9090/websocket"
    
    def test_get_capabilities(self, server):
        """Test server capabilities"""
        capabilities = server.get_capabilities()
        
        assert len(capabilities) == 4
        capability_names = [cap.name for cap in capabilities]
        assert "python_execute" in capability_names
        assert "python_analyze" in capability_names
        assert "python_visualize" in capability_names
        assert "python_install_package" in capability_names
        
        # Test specific capability
        execute_cap = next(cap for cap in capabilities if cap.name == "python_execute")
        assert execute_cap.description == "执行Python代码"
        assert "code" in execute_cap.parameters
        assert execute_cap.parameters["code"]["required"] is True
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_python_execute(self, server):
        """Test handling python_execute action"""
        with patch.object(server.python_tool, 'execute_code', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "stdout": "Hello, World!",
                "stderr": "",
                "return_code": 0
            }
            
            result = await server.handle_tool_action("python_execute", {
                "code": "print('Hello, World!')",
                "timeout": 30
            })
            
            assert result["success"] is True
            assert result["data"]["stdout"] == "Hello, World!"
            assert result["data"]["return_code"] == 0
            mock_execute.assert_called_once_with("print('Hello, World!')", 30)
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_python_analyze(self, server):
        """Test handling python_analyze action"""
        with patch.object(server.python_tool, 'analyze_data', new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {
                "success": True,
                "result": "Analysis result"
            }
            
            result = await server.handle_tool_action("python_analyze", {
                "data": [1, 2, 3, 4, 5],
                "operation": "describe"
            })
            
            assert result["success"] is True
            assert result["data"]["result"] == "Analysis result"
            mock_analyze.assert_called_once_with([1, 2, 3, 4, 5], "describe")
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_python_visualize(self, server):
        """Test handling python_visualize action"""
        with patch.object(server.python_tool, 'create_visualization', new_callable=AsyncMock) as mock_viz:
            # Mock return value with 'result' field to match server expectation
            mock_viz.return_value = {
                "success": True,
                "result": {
                    "plot_path": "/path/to/plot.png",
                    "plot_type": "line",
                    "message": "Visualization saved to /path/to/plot.png"
                }
            }
            
            result = await server.handle_tool_action("python_visualize", {
                "data": [1, 2, 3, 4, 5],
                "plot_type": "line"
            })
            
            assert result["success"] is True
            assert result["data"]["result"]["plot_path"] == "/path/to/plot.png"
            assert result["data"]["result"]["plot_type"] == "line"
            mock_viz.assert_called_once_with([1, 2, 3, 4, 5], "line", "Data Visualization", None)
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_python_install_package(self, server):
        """Test handling python_install_package action"""
        with patch.object(server.python_tool, 'install_package', new_callable=AsyncMock) as mock_install:
            mock_install.return_value = {
                "success": True,
                "result": {
                    "package": "requests",
                    "stdout": "Successfully installed requests",
                    "return_code": 0
                }
            }
            
            result = await server.handle_tool_action("python_install_package", {
                "package_name": "requests"
            })
            
            assert result["success"] is True
            assert result["data"]["result"]["package"] == "requests"
            mock_install.assert_called_once_with("requests")
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_unsupported(self, server):
        """Test handling unsupported action"""
        result = await server.handle_tool_action("unsupported_action", {})
        
        assert result["success"] is False
        assert "Unsupported action" in result["error_message"]
        assert result["error_type"] == "UnsupportedAction"
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_exception(self, server):
        """Test handling action with exception"""
        with patch.object(server.python_tool, 'execute_code', new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Test exception")
            
            result = await server.handle_tool_action("python_execute", {
                "code": "print('test')"
            })
            
            assert result["success"] is False
            assert "Test exception" in result["error_message"]
            assert result["error_type"] == "PythonToolError"
    
    @pytest.mark.asyncio
    async def test_run_server(self, server):
        """Test running the MCP server"""
        with patch('core.toolscore.mcp_server.MCPServer') as mock_mcp_server_class:
            mock_mcp_server = AsyncMock()
            mock_mcp_server_class.return_value = mock_mcp_server
            
            # Mock the server.start() to avoid actual server startup
            mock_mcp_server.start = AsyncMock()
            
            # Mock os.environ to avoid modifying real environment
            with patch.dict(os.environ, {}, clear=False):
                await server.run()
            
            # Verify MCPServer was created with correct parameters
            mock_mcp_server_class.assert_called_once()
            args, kwargs = mock_mcp_server_class.call_args
            
            assert kwargs['server_name'] == "python_executor_server"
            assert kwargs['server_id'] == "python-executor-mcp-server"
            assert kwargs['description'] == "Python代码执行和数据分析工具服务器"
            assert kwargs['tool_type'] == ToolType.MCP_SERVER
            assert kwargs['endpoint'] == "ws://localhost:9083"
            
            # Verify handler registration and server start
            mock_mcp_server.register_tool_action_handler.assert_called_once()
            mock_mcp_server.start.assert_called_once()


class TestPythonExecutorIntegration:
    """Integration tests for Python Executor MCP Server"""
    
    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Test complete execution flow from server to tool"""
        with patch('mcp_servers.python_executor_server.python_executor_tool.get_python_execution_dir') as mock_get_dir:
            mock_get_dir.return_value = Path(tempfile.mkdtemp())
            
            # Create mock config manager
            config_manager = MagicMock(spec=ConfigManager)
            config_manager.get_ports_config.return_value = {
                'mcp_servers': {
                    'python_executor': {'port': 9083},
                    'toolscore_mcp': {'port': 9090}
                }
            }
            
            # Create server
            server = PythonExecutorMCPServer(config_manager)
            
            # Test execution
            result = await server.handle_tool_action("python_execute", {
                "code": "result = 2 + 2\nprint(f'Result: {result}')",
                "timeout": 10
            })
            
            assert result["success"] is True
            assert "Result: 4" in result["data"]["stdout"]
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self):
        """Test error handling in complete flow"""
        with patch('mcp_servers.python_executor_server.python_executor_tool.get_python_execution_dir') as mock_get_dir:
            mock_get_dir.return_value = Path(tempfile.mkdtemp())
            
            # Create mock config manager
            config_manager = MagicMock(spec=ConfigManager)
            config_manager.get_ports_config.return_value = {
                'mcp_servers': {
                    'python_executor': {'port': 9083},
                    'toolscore_mcp': {'port': 9090}
                }
            }
            
            # Create server
            server = PythonExecutorMCPServer(config_manager)
            
            # Test error handling
            result = await server.handle_tool_action("python_execute", {
                "code": "import invalid_module_that_does_not_exist",
                "timeout": 10
            })
            
            assert result["success"] is False
            assert "ModuleNotFoundError" in result["data"]["stderr"] or result["error_message"]


class TestPythonExecutorServerLifecycle:
    """Test server lifecycle events"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock ConfigManager"""
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'python_executor': {'port': 9083},
                'toolscore_mcp': {'port': 9090}
            }
        }
        return config_manager
    
    @pytest.mark.asyncio
    async def test_server_startup_shutdown(self, mock_config_manager):
        """Test server startup and shutdown process"""
        server = PythonExecutorMCPServer(mock_config_manager)
        
        # Mock the MCPServer to avoid actual network operations
        with patch('core.toolscore.mcp_server.MCPServer') as mock_mcp_server_class:
            mock_mcp_server = AsyncMock()
            mock_mcp_server_class.return_value = mock_mcp_server
            
            # Test startup
            await server.run()
            
            # Verify initialization
            assert mock_mcp_server_class.called
            mock_mcp_server.register_tool_action_handler.assert_called_once()
            mock_mcp_server.start.assert_called_once()
    
    def test_environment_variable_handling(self, mock_config_manager):
        """Test environment variable configuration"""
        with patch.dict(os.environ, {
            'PYTHON_EXECUTOR_LISTEN_HOST': '127.0.0.1',
            'PYTHON_EXECUTOR_HOST': 'example.com',
            'TOOLSCORE_ENDPOINT': 'ws://custom:8080/ws'
        }):
            server = PythonExecutorMCPServer(mock_config_manager)
            
            assert server.endpoint == "ws://example.com:9083"
            assert server.toolscore_endpoint == "ws://custom:8080/ws"
            assert server._listen_host == "127.0.0.1"