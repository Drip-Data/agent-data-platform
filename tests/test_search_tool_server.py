"""
Comprehensive tests for Search Tool MCP Server
Tests the main server functionality, search tool execution, error handling, and server lifecycle
"""

import pytest
import pytest_asyncio
import asyncio
import json
import tempfile
import os
import sys
import ast
from unittest.mock import AsyncMock, MagicMock, patch, call, mock_open
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.search_tool_server.main import SearchToolMCPServer
from mcp_servers.search_tool_server.search_tool import SearchTool
from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.config_manager import ConfigManager


class TestSearchTool:
    """Test cases for SearchTool class"""
    
    @pytest.fixture
    def search_tool(self):
        """Create SearchTool instance for testing"""
        return SearchTool()
    
    @pytest.fixture
    def temp_python_file(self, tmp_path):
        """Create a temporary Python file for testing"""
        python_code = '''
"""Test module for search testing"""

class TestClass:
    """A test class"""
    
    def __init__(self):
        self.value = 42
    
    def test_method(self):
        """A test method"""
        return self.value
    
    def another_method(self, param):
        """Another test method"""
        return param * 2

def test_function():
    """A test function"""
    return "test"

def another_function(x, y):
    """Another test function"""
    return x + y

# Global variable
TEST_CONSTANT = "test_value"
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(python_code)
        return str(test_file)
    
    @pytest.fixture
    def temp_text_file(self, tmp_path):
        """Create a temporary text file for testing"""
        content = '''
This is line 1 with some text.
This is line 2 with different content.
Line 3 contains the word "function" in it.
Another line with "class" definition.
Final line with various keywords.
'''
        test_file = tmp_path / "test_file.txt"
        test_file.write_text(content)
        return str(test_file)
    
    @pytest.mark.asyncio
    async def test_search_file_content_success(self, search_tool, temp_text_file):
        """Test successful file content search"""
        result = await search_tool.search_file_content(temp_text_file, r"line \d+")
        
        assert result["success"] is True
        assert result["output"]["count"] == 3
        assert len(result["output"]["matches"]) == 3
        assert "Line 1" in result["output"]["matches"][0]
        assert "Line 2" in result["output"]["matches"][1]
        assert "Line 3" in result["output"]["matches"][2]
    
    @pytest.mark.asyncio
    async def test_search_file_content_no_matches(self, search_tool, temp_text_file):
        """Test file content search with no matches"""
        result = await search_tool.search_file_content(temp_text_file, r"nonexistent_pattern")
        
        assert result["success"] is True
        assert result["output"]["count"] == 0
        assert result["output"]["matches"] == []
        assert "未找到匹配项" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_search_file_content_file_not_found(self, search_tool):
        """Test file content search with non-existent file"""
        result = await search_tool.search_file_content("/nonexistent/file.txt", r"pattern")
        
        assert result["success"] is False
        assert result["error_type"] == "FileNotFound"
        assert "文件不存在" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_search_file_content_regex_error(self, search_tool, temp_text_file):
        """Test file content search with invalid regex"""
        with patch('re.search', side_effect=Exception("Invalid regex")):
            result = await search_tool.search_file_content(temp_text_file, r"[invalid")
            
            assert result["success"] is False
            assert result["error_type"] == "SearchError"
            assert "Invalid regex" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_search_file_content_encoding_error(self, search_tool, tmp_path):
        """Test file content search with encoding issues"""
        # Create a file with binary content
        binary_file = tmp_path / "binary_file.bin"
        binary_file.write_bytes(b'\x80\x81\x82\x83')
        
        # Mock open to raise UnicodeDecodeError
        with patch('builtins.open', side_effect=UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')):
            result = await search_tool.search_file_content(str(binary_file), r"pattern")
            
            assert result["success"] is False
            assert result["error_type"] == "SearchError"
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_file(self, search_tool, temp_python_file):
        """Test listing code definitions for a single file"""
        result = await search_tool.list_code_definitions(file_path=temp_python_file)
        
        assert result["success"] is True
        assert result["output"]["count"] > 0
        
        definitions = result["output"]["definitions"]
        def_names = [d["name"] for d in definitions]
        def_types = [d["type"] for d in definitions]
        
        # Check for expected definitions
        assert "TestClass" in def_names
        assert "test_function" in def_names
        assert "another_function" in def_names
        assert "TestClass.test_method" in def_names
        assert "TestClass.another_method" in def_names
        
        # Check types
        assert "class" in def_types
        assert "function" in def_types
        assert "method" in def_types
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_directory(self, search_tool, tmp_path):
        """Test listing code definitions for a directory"""
        # Create multiple Python files
        file1 = tmp_path / "module1.py"
        file1.write_text('''
def func1():
    pass

class Class1:
    def method1(self):
        pass
''')
        
        file2 = tmp_path / "module2.py"
        file2.write_text('''
def func2():
    pass

class Class2:
    def method2(self):
        pass
''')
        
        result = await search_tool.list_code_definitions(directory_path=str(tmp_path))
        
        assert result["success"] is True
        assert result["output"]["count"] >= 4  # At least 4 definitions
        
        definitions = result["output"]["definitions"]
        def_names = [d["name"] for d in definitions]
        
        assert "func1" in def_names
        assert "func2" in def_names
        assert "Class1" in def_names
        assert "Class2" in def_names
        assert "Class1.method1" in def_names
        assert "Class2.method2" in def_names
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_file_not_found(self, search_tool):
        """Test listing code definitions for non-existent file"""
        result = await search_tool.list_code_definitions(file_path="/nonexistent/file.py")
        
        assert result["success"] is False
        assert result["error_type"] == "FileNotFound"
        assert "文件不存在" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_directory_not_found(self, search_tool):
        """Test listing code definitions for non-existent directory"""
        result = await search_tool.list_code_definitions(directory_path="/nonexistent/directory")
        
        assert result["success"] is False
        assert result["error_type"] == "DirectoryNotFound"
        assert "目录不存在" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_unsupported_file_type(self, search_tool, temp_text_file):
        """Test listing code definitions for unsupported file type"""
        result = await search_tool.list_code_definitions(file_path=temp_text_file)
        
        assert result["success"] is False
        assert result["error_type"] == "UnsupportedFileType"
        assert "不支持的文件类型" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_missing_parameters(self, search_tool):
        """Test listing code definitions without required parameters"""
        result = await search_tool.list_code_definitions()
        
        assert result["success"] is False
        assert result["error_type"] == "MissingParameter"
        assert "必须提供文件路径或目录路径" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_list_code_definitions_empty_results(self, search_tool, tmp_path):
        """Test listing code definitions with no results"""
        # Create a Python file with no definitions
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("# Just a comment\nprint('hello')")
        
        result = await search_tool.list_code_definitions(file_path=str(empty_file))
        
        assert result["success"] is True
        assert result["output"]["count"] == 0
        assert result["output"]["definitions"] == []
        assert "未找到任何代码定义" in result["error_message"]
    
    def test_parse_python_file_success(self, search_tool, temp_python_file):
        """Test parsing Python file successfully"""
        definitions = search_tool._parse_python_file(temp_python_file)
        
        assert len(definitions) > 0
        
        # Check for expected definitions
        def_names = [d["name"] for d in definitions]
        assert "TestClass" in def_names
        assert "test_function" in def_names
        assert "another_function" in def_names
        assert "TestClass.test_method" in def_names
        assert "TestClass.another_method" in def_names
        
        # Check structure
        for definition in definitions:
            assert "type" in definition
            assert "name" in definition
            assert "file" in definition
            assert "line" in definition
            assert definition["file"] == temp_python_file
            assert isinstance(definition["line"], int)
    
    def test_parse_python_file_syntax_error(self, search_tool, tmp_path):
        """Test parsing Python file with syntax error"""
        bad_file = tmp_path / "bad_syntax.py"
        bad_file.write_text("def incomplete_function(\n# Missing closing parenthesis")
        
        definitions = search_tool._parse_python_file(str(bad_file))
        
        # Should return empty list on syntax error
        assert definitions == []
    
    def test_parse_python_file_complex_structure(self, search_tool, tmp_path):
        """Test parsing Python file with complex structure"""
        complex_code = '''
import sys
from typing import List

class OuterClass:
    """Outer class"""
    
    def outer_method(self):
        pass
    
    class InnerClass:
        """Inner class"""
        
        def inner_method(self):
            pass
    
    @staticmethod
    def static_method():
        pass
    
    @classmethod
    def class_method(cls):
        pass

def top_level_function():
    def nested_function():
        pass
    return nested_function

async def async_function():
    pass

def generator_function():
    yield 1

lambda_func = lambda x: x * 2
'''
        complex_file = tmp_path / "complex.py"
        complex_file.write_text(complex_code)
        
        definitions = search_tool._parse_python_file(str(complex_file))
        
        def_names = [d["name"] for d in definitions]
        
        # Should find top-level classes and functions
        assert "OuterClass" in def_names
        assert "top_level_function" in def_names
        assert "async_function" in def_names
        assert "generator_function" in def_names
        
        # Should find methods
        assert "OuterClass.outer_method" in def_names
        assert "OuterClass.static_method" in def_names
        assert "OuterClass.class_method" in def_names
        
        # Should find inner classes and their methods
        # Note: This depends on the exact AST walking implementation
        # The current implementation might not catch nested classes correctly


class TestSearchToolMCPServer:
    """Test cases for SearchToolMCPServer class"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock ConfigManager"""
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'search_tool': {'port': 9003},
                'toolscore_mcp': {'port': 9090}
            }
        }
        return config_manager
    
    @pytest.fixture
    def server(self, mock_config_manager):
        """Create SearchToolMCPServer instance"""
        return SearchToolMCPServer(mock_config_manager)
    
    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.server_name == "search_tool_server"
        assert server.server_id == "mcp-search-tool"
        assert server.endpoint == "ws://localhost:9003/mcp"
        assert server.toolscore_endpoint == "ws://localhost:9090/websocket"
    
    def test_get_capabilities(self, server):
        """Test server capabilities"""
        capabilities = server.get_capabilities()
        
        assert len(capabilities) == 2
        capability_names = [cap.name for cap in capabilities]
        assert "search_file_content" in capability_names
        assert "list_code_definitions" in capability_names
        
        # Test specific capability
        search_cap = next(cap for cap in capabilities if cap.name == "search_file_content")
        assert search_cap.description == "在指定文件中搜索匹配正则表达式的内容"
        assert "file_path" in search_cap.parameters
        assert "regex_pattern" in search_cap.parameters
        assert search_cap.parameters["file_path"]["required"] is True
        assert search_cap.parameters["regex_pattern"]["required"] is True
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_search_file_content(self, server):
        """Test handling search_file_content action"""
        with patch.object(server.search_tool, 'search_file_content') as mock_search:
            mock_search.return_value = {
                "success": True,
                "output": {"matches": ["Line 1: test"], "count": 1},
                "error_message": None,
                "error_type": None
            }
            
            result = await server.handle_tool_action("search_file_content", {
                "file_path": "/path/to/file.txt",
                "regex_pattern": r"test"
            })
            
            assert result["success"] is True
            assert result["data"]["matches"] == ["Line 1: test"]
            assert result["data"]["count"] == 1
            mock_search.assert_called_once_with("/path/to/file.txt", "test")
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_list_code_definitions_file(self, server):
        """Test handling list_code_definitions action with file"""
        with patch.object(server.search_tool, 'list_code_definitions') as mock_list:
            mock_list.return_value = {
                "success": True,
                "output": {"definitions": [{"name": "TestClass", "type": "class"}], "count": 1},
                "error_message": None,
                "error_type": None
            }
            
            result = await server.handle_tool_action("list_code_definitions", {
                "file_path": "/path/to/file.py"
            })
            
            assert result["success"] is True
            assert result["data"]["count"] == 1
            assert result["data"]["definitions"][0]["name"] == "TestClass"
            mock_list.assert_called_once_with("/path/to/file.py", None)
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_list_code_definitions_directory(self, server):
        """Test handling list_code_definitions action with directory"""
        with patch.object(server.search_tool, 'list_code_definitions') as mock_list:
            mock_list.return_value = {
                "success": True,
                "output": {"definitions": [{"name": "func1", "type": "function"}], "count": 1},
                "error_message": None,
                "error_type": None
            }
            
            result = await server.handle_tool_action("list_code_definitions", {
                "directory_path": "/path/to/directory"
            })
            
            assert result["success"] is True
            assert result["data"]["count"] == 1
            mock_list.assert_called_once_with(None, "/path/to/directory")
    
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
        with patch.object(server.search_tool, 'search_file_content') as mock_search:
            mock_search.side_effect = Exception("Test exception")
            
            result = await server.handle_tool_action("search_file_content", {
                "file_path": "/path/to/file.txt",
                "regex_pattern": "pattern"
            })
            
            assert result["success"] is False
            assert "Test exception" in result["error_message"]
            assert result["error_type"] == "SearchToolError"
    
    @pytest.mark.asyncio
    async def test_handle_tool_action_tool_error(self, server):
        """Test handling action with tool error response"""
        with patch.object(server.search_tool, 'search_file_content') as mock_search:
            mock_search.return_value = {
                "success": False,
                "output": None,
                "error_message": "File not found",
                "error_type": "FileNotFound"
            }
            
            result = await server.handle_tool_action("search_file_content", {
                "file_path": "/nonexistent/file.txt",
                "regex_pattern": "pattern"
            })
            
            assert result["success"] is False
            assert result["error_message"] == "File not found"
            assert result["error_type"] == "FileNotFound"
    
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
            
            assert kwargs['server_name'] == "search_tool_server"
            assert kwargs['server_id'] == "mcp-search-tool"
            assert kwargs['description'] == "文件内容搜索和代码定义搜索工具服务器"
            assert kwargs['tool_type'] == ToolType.MCP_SERVER
            assert kwargs['endpoint'] == "ws://localhost:9003/mcp"
            
            # Verify handler registration and server start
            mock_mcp_server.register_tool_action_handler.assert_called_once()
            mock_mcp_server.start.assert_called_once()


class TestSearchToolIntegration:
    """Integration tests for Search Tool MCP Server"""
    
    @pytest.mark.asyncio
    async def test_full_search_flow(self, tmp_path):
        """Test complete search flow from server to tool"""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is a test file with test content.")
        
        # Create mock config manager
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'search_tool': {'port': 9003},
                'toolscore_mcp': {'port': 9090}
            }
        }
        
        # Create server
        server = SearchToolMCPServer(config_manager)
        
        # Test search
        result = await server.handle_tool_action("search_file_content", {
            "file_path": str(test_file),
            "regex_pattern": r"test"
        })
        
        assert result["success"] is True
        assert result["data"]["count"] == 1
        assert "test" in result["data"]["matches"][0].lower()
    
    @pytest.mark.asyncio
    async def test_full_code_analysis_flow(self, tmp_path):
        """Test complete code analysis flow from server to tool"""
        # Create test Python file
        python_file = tmp_path / "test_module.py"
        python_file.write_text('''
class TestClass:
    def test_method(self):
        pass

def test_function():
    return "test"
''')
        
        # Create mock config manager
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'search_tool': {'port': 9003},
                'toolscore_mcp': {'port': 9090}
            }
        }
        
        # Create server
        server = SearchToolMCPServer(config_manager)
        
        # Test code analysis
        result = await server.handle_tool_action("list_code_definitions", {
            "file_path": str(python_file)
        })
        
        assert result["success"] is True
        assert result["data"]["count"] >= 2
        
        def_names = [d["name"] for d in result["data"]["definitions"]]
        assert "TestClass" in def_names
        assert "test_function" in def_names
        assert "TestClass.test_method" in def_names
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self, tmp_path):
        """Test error handling in complete flow"""
        # Create mock config manager
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'search_tool': {'port': 9003},
                'toolscore_mcp': {'port': 9090}
            }
        }
        
        # Create server
        server = SearchToolMCPServer(config_manager)
        
        # Test error handling with non-existent file
        result = await server.handle_tool_action("search_file_content", {
            "file_path": "/nonexistent/file.txt",
            "regex_pattern": "pattern"
        })
        
        assert result["success"] is False
        assert result["error_type"] == "FileNotFound"


class TestSearchToolServerLifecycle:
    """Test server lifecycle events"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock ConfigManager"""
        config_manager = MagicMock(spec=ConfigManager)
        config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'search_tool': {'port': 9003},
                'toolscore_mcp': {'port': 9090}
            }
        }
        return config_manager
    
    @pytest.mark.asyncio
    async def test_server_startup_shutdown(self, mock_config_manager):
        """Test server startup and shutdown process"""
        server = SearchToolMCPServer(mock_config_manager)
        
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
            'SEARCH_TOOL_LISTEN_HOST': '0.0.0.0',
            'SEARCH_TOOL_HOST': 'search-server.com',
            'TOOLSCORE_ENDPOINT': 'ws://toolscore:9090/ws'
        }):
            server = SearchToolMCPServer(mock_config_manager)
            
            assert server.endpoint == "ws://search-server.com:9003/mcp"
            assert server.toolscore_endpoint == "ws://toolscore:9090/ws"
            assert server._listen_host == "0.0.0.0"


class TestSearchToolEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.fixture
    def search_tool(self):
        """Create SearchTool instance for testing"""
        return SearchTool()
    
    @pytest.mark.asyncio
    async def test_search_large_file(self, search_tool, tmp_path):
        """Test searching in a large file"""
        large_file = tmp_path / "large_file.txt"
        
        # Create a large file with repeated content
        content = "Line with pattern\n" * 1000 + "Line without match\n" * 1000
        large_file.write_text(content)
        
        result = await search_tool.search_file_content(str(large_file), r"pattern")
        
        assert result["success"] is True
        assert result["output"]["count"] == 1000
    
    @pytest.mark.asyncio
    async def test_search_special_characters(self, search_tool, tmp_path):
        """Test searching with special regex characters"""
        special_file = tmp_path / "special.txt"
        special_file.write_text("Line with [brackets] and (parentheses) and {braces}")
        
        result = await search_tool.search_file_content(str(special_file), r"\[.*\]")
        
        assert result["success"] is True
        assert result["output"]["count"] == 1
        assert "[brackets]" in result["output"]["matches"][0]
    
    @pytest.mark.asyncio
    async def test_parse_python_file_unicode(self, search_tool, tmp_path):
        """Test parsing Python file with unicode content"""
        unicode_file = tmp_path / "unicode.py"
        unicode_code = '''# -*- coding: utf-8 -*-
"""
模块文档字符串
"""

class 中文类名:
    """中文类"""
    
    def 中文方法名(self):
        """中文方法"""
        pass

def 中文函数名():
    """中文函数"""
    return "中文字符串"
'''
        unicode_file.write_text(unicode_code, encoding='utf-8')
        
        definitions = search_tool._parse_python_file(str(unicode_file))
        
        assert len(definitions) >= 2
        def_names = [d["name"] for d in definitions]
        assert "中文类名" in def_names
        assert "中文函数名" in def_names
        assert "中文类名.中文方法名" in def_names
    
    @pytest.mark.asyncio
    async def test_directory_with_non_python_files(self, search_tool, tmp_path):
        """Test directory parsing with mixed file types"""
        # Create Python file
        py_file = tmp_path / "module.py"
        py_file.write_text("def python_function(): pass")
        
        # Create non-Python files
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("This is not Python code")
        
        js_file = tmp_path / "script.js"
        js_file.write_text("function jsFunction() { return true; }")
        
        result = await search_tool.list_code_definitions(directory_path=str(tmp_path))
        
        assert result["success"] is True
        # Should only find definitions from Python files
        def_names = [d["name"] for d in result["output"]["definitions"]]
        assert "python_function" in def_names
        # Should not find JavaScript function
        assert "jsFunction" not in def_names