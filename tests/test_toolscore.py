"""
Tests for ToolScore modules
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.toolscore.interfaces import ToolSpec, ToolType, ToolCapability
from core.toolscore.unified_tool_library import UnifiedToolLibrary
from core.toolscore.core_manager import CoreManager
from core.toolscore.tool_registry import ToolRegistry


class TestToolCapability:
    """Test ToolCapability dataclass"""
    
    def test_tool_capability_creation(self):
        """Test creating a ToolCapability"""
        capability = ToolCapability(
            name="execute_python",
            description="Execute Python code",
            parameters={
                "code": {"type": "string", "required": True},
                "timeout": {"type": "number", "default": 30}
            },
            examples=[
                {"code": "print('hello')", "timeout": 10}
            ]
        )
        
        assert capability.name == "execute_python"
        assert capability.description == "Execute Python code"
        assert capability.parameters["code"]["required"] is True
        assert len(capability.examples) == 1
    
    def test_tool_capability_to_dict(self):
        """Test converting ToolCapability to dictionary"""
        capability = ToolCapability(
            name="browse_web",
            description="Navigate web pages",
            parameters={"url": {"type": "string", "required": True}},
            examples=[]
        )
        
        cap_dict = capability.to_dict()
        
        assert cap_dict["name"] == "browse_web"
        assert cap_dict["description"] == "Navigate web pages"
        assert cap_dict["parameters"]["url"]["type"] == "string"


class TestToolRegistry:
    """Test ToolRegistry class"""
    
    @pytest.fixture
    def tool_registry(self):
        """Create ToolRegistry instance for testing"""
        return ToolRegistry()
    
    @pytest.mark.asyncio
    async def test_initialization(self, tool_registry):
        """Test ToolRegistry initialization"""
        assert tool_registry is not None
        assert hasattr(tool_registry, 'tools')
        assert hasattr(tool_registry, 'tool_types')
    
    @pytest.mark.asyncio
    async def test_register_tool(self, tool_registry):
        """Test registering a tool"""
        tool_spec = ToolSpec(
            tool_id="test_tool_001",
            name="Test Tool",
            description="A tool for testing",
            tool_type=ToolType.FUNCTION,
            capabilities=[
                ToolCapability(
                    name="test_action",
                    description="Test action",
                    parameters={},
                    examples=[]
                )
            ]
        )
        
        result = await tool_registry.register_tool(tool_spec)
        
        assert result.success is True
        assert tool_spec.tool_id in tool_registry.tools
    
    @pytest.mark.asyncio
    async def test_get_tool(self, tool_registry):
        """Test getting a tool"""
        tool_spec = ToolSpec(
            tool_id="test_tool_002",
            name="Another Test Tool",
            description="Another tool for testing",
            tool_type=ToolType.FUNCTION,
            capabilities=[]
        )
        
        await tool_registry.register_tool(tool_spec)
        retrieved_tool = await tool_registry.get_tool("test_tool_002")
        
        assert retrieved_tool is not None
        assert retrieved_tool.tool_id == "test_tool_002"
        assert retrieved_tool.name == "Another Test Tool"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_tool(self, tool_registry):
        """Test getting a non-existent tool"""
        tool = await tool_registry.get_tool("nonexistent_tool")
        assert tool is None
    
    @pytest.mark.asyncio
    async def test_list_tools(self, tool_registry):
        """Test listing all tools"""
        # Register multiple tools
        for i in range(3):
            tool_spec = ToolSpec(
                tool_id=f"test_tool_{i}",
                name=f"Test Tool {i}",
                description=f"Test tool number {i}",
                tool_type=ToolType.FUNCTION,
                capabilities=[]
            )
            await tool_registry.register_tool(tool_spec)
        
        tools = await tool_registry.list_tools()
        
        assert len(tools) >= 3
        tool_ids = [tool.tool_id for tool in tools]
        assert "test_tool_0" in tool_ids
        assert "test_tool_1" in tool_ids
        assert "test_tool_2" in tool_ids
    
    @pytest.mark.asyncio
    async def test_list_tools_by_type(self, tool_registry):
        """Test listing tools by type"""
        # Register function tool
        func_tool = ToolSpec(
            tool_id="function_tool",
            name="Function Tool",
            description="A function tool",
            tool_type=ToolType.FUNCTION,
            capabilities=[]
        )
        
        # Register MCP server tool
        mcp_tool = ToolSpec(
            tool_id="mcp_tool",
            name="MCP Tool",
            description="An MCP server tool",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[]
        )
        
        await tool_registry.register_tool(func_tool)
        await tool_registry.register_tool(mcp_tool)
        
        function_tools = await tool_registry.list_tools_by_type(ToolType.FUNCTION)
        mcp_tools = await tool_registry.list_tools_by_type(ToolType.MCP_SERVER)
        
        assert len(function_tools) >= 1
        assert len(mcp_tools) >= 1
        assert any(tool.tool_id == "function_tool" for tool in function_tools)
        assert any(tool.tool_id == "mcp_tool" for tool in mcp_tools)
    
    @pytest.mark.asyncio
    async def test_unregister_tool(self, tool_registry):
        """Test unregistering a tool"""
        tool_spec = ToolSpec(
            tool_id="temp_tool",
            name="Temporary Tool",
            description="A temporary tool",
            tool_type=ToolType.FUNCTION,
            capabilities=[]
        )
        
        await tool_registry.register_tool(tool_spec)
        assert await tool_registry.get_tool("temp_tool") is not None
        
        result = await tool_registry.unregister_tool("temp_tool")
        assert result is True
        assert await tool_registry.get_tool("temp_tool") is None
    
    @pytest.mark.asyncio
    async def test_search_tools(self, tool_registry):
        """Test searching tools"""
        # Register tools with specific descriptions
        search_tool = ToolSpec(
            tool_id="search_tool",
            name="Search Tool",
            description="Tool for searching information",
            tool_type=ToolType.FUNCTION,
            capabilities=[]
        )
        
        math_tool = ToolSpec(
            tool_id="math_tool",
            name="Math Tool",
            description="Tool for mathematical calculations",
            tool_type=ToolType.FUNCTION,
            capabilities=[]
        )
        
        await tool_registry.register_tool(search_tool)
        await tool_registry.register_tool(math_tool)
        
        # Search for tools containing "search"
        search_results = await tool_registry.search_tools("search")
        math_results = await tool_registry.search_tools("math")
        
        assert len(search_results) >= 1
        assert len(math_results) >= 1
        assert any(tool.tool_id == "search_tool" for tool in search_results)
        assert any(tool.tool_id == "math_tool" for tool in math_results)


class TestCoreManager:
    """Test CoreManager class"""
    
    @pytest.fixture
    def core_manager(self, mock_config_manager):
        """Create CoreManager instance for testing"""
        return CoreManager(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, core_manager):
        """Test CoreManager initialization"""
        assert core_manager is not None
        assert hasattr(core_manager, 'config_manager')
    
    @pytest.mark.asyncio
    async def test_start_manager(self, core_manager):
        """Test starting the CoreManager"""
        with patch.object(core_manager, '_initialize_components', new_callable=AsyncMock):
            result = await core_manager.start()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_stop_manager(self, core_manager):
        """Test stopping the CoreManager"""
        with patch.object(core_manager, '_cleanup_components', new_callable=AsyncMock):
            result = await core_manager.stop()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check(self, core_manager):
        """Test CoreManager health check"""
        health_status = await core_manager.health_check()
        
        assert isinstance(health_status, dict)
        assert 'status' in health_status
        assert 'components' in health_status
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, core_manager):
        """Test getting CoreManager metrics"""
        with patch.object(core_manager, '_collect_metrics', return_value={
            'tools_registered': 5,
            'active_connections': 3,
            'total_requests': 100
        }):
            metrics = await core_manager.get_metrics()
            
            assert 'tools_registered' in metrics
            assert 'active_connections' in metrics
            assert 'total_requests' in metrics


class TestUnifiedToolLibrary:
    """Test UnifiedToolLibrary class"""
    
    @pytest.fixture
    def tool_library(self, mock_config_manager):
        """Create UnifiedToolLibrary instance for testing"""
        with patch('core.toolscore.unified_tool_library.CoreManager'):
            return UnifiedToolLibrary()
    
    @pytest.mark.asyncio
    async def test_initialization(self, tool_library):
        """Test UnifiedToolLibrary initialization"""
        assert tool_library is not None
        assert hasattr(tool_library, 'core_manager')
        assert hasattr(tool_library, 'is_initialized')
    
    @pytest.mark.asyncio
    async def test_initialize_library(self, tool_library):
        """Test initializing the tool library"""
        with patch.object(tool_library.core_manager, 'start', new_callable=AsyncMock, return_value=True):
            await tool_library.initialize()
            assert tool_library.is_initialized is True
    
    @pytest.mark.asyncio
    async def test_register_function_tool(self, tool_library):
        """Test registering a function tool"""
        from core.toolscore.interfaces import FunctionToolSpec
        
        func_tool = FunctionToolSpec(
            tool_id="test_function",
            name="Test Function",
            description="A test function tool",
            tool_type=ToolType.FUNCTION,
            capabilities=[],
            module_path="test.module",
            class_name="TestClass",
            enabled=True,
            tags=["test"]
        )
        
        with patch.object(tool_library.core_manager.tool_registry, 'register_tool', new_callable=AsyncMock) as mock_register:
            mock_register.return_value = MagicMock(success=True)
            
            result = await tool_library.register_function_tool(func_tool)
            
            assert result.success is True
            mock_register.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_register_mcp_server(self, tool_library):
        """Test registering an MCP server"""
        from core.toolscore.interfaces import MCPServerSpec
        
        mcp_server = MCPServerSpec(
            tool_id="test_mcp_server",
            name="Test MCP Server",
            description="A test MCP server",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[],
            endpoint="ws://localhost:8080",
            connection_params={}
        )
        
        with patch.object(tool_library.core_manager.tool_registry, 'register_tool', new_callable=AsyncMock) as mock_register:
            mock_register.return_value = MagicMock(success=True)
            
            result = await tool_library.register_mcp_server(mcp_server)
            
            assert result.success is True
            mock_register.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_all_tools(self, tool_library):
        """Test getting all tools"""
        mock_tools = [
            MagicMock(tool_id="tool1", name="Tool 1"),
            MagicMock(tool_id="tool2", name="Tool 2")
        ]
        
        with patch.object(tool_library.core_manager.tool_registry, 'list_tools', new_callable=AsyncMock, return_value=mock_tools):
            tools = await tool_library.get_all_tools()
            
            assert len(tools) == 2
            assert tools[0].tool_id == "tool1"
            assert tools[1].tool_id == "tool2"
    
    @pytest.mark.asyncio
    async def test_get_tool_by_id(self, tool_library):
        """Test getting a tool by ID"""
        mock_tool = MagicMock(tool_id="specific_tool", name="Specific Tool")
        
        with patch.object(tool_library.core_manager.tool_registry, 'get_tool', new_callable=AsyncMock, return_value=mock_tool):
            tool = await tool_library.get_tool_by_id("specific_tool")
            
            assert tool is not None
            assert tool.tool_id == "specific_tool"
    
    @pytest.mark.asyncio
    async def test_execute_tool(self, tool_library):
        """Test executing a tool"""
        mock_execution_result = MagicMock(
            success=True,
            data={"output": "Tool executed successfully"},
            error_message=None
        )
        
        with patch.object(tool_library, '_execute_tool_internal', new_callable=AsyncMock, return_value=mock_execution_result):
            result = await tool_library.execute_tool("test_tool", "execute", {"param": "value"})
            
            assert result.success is True
            assert result.data["output"] == "Tool executed successfully"
    
    @pytest.mark.asyncio
    async def test_cleanup(self, tool_library):
        """Test cleaning up the tool library"""
        with patch.object(tool_library.core_manager, 'stop', new_callable=AsyncMock):
            await tool_library.cleanup()
            
            tool_library.core_manager.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_recommend_tools(self, tool_library):
        """Test tool recommendation"""
        from core.interfaces import TaskSpec, TaskType
        
        task = TaskSpec(
            task_id="recommendation_test",
            task_type=TaskType.CODE,
            description="Write Python code to calculate fibonacci"
        )
        
        mock_recommendations = [
            {"tool_id": "python_executor", "confidence": 0.9, "reason": "Python code execution"},
            {"tool_id": "code_generator", "confidence": 0.7, "reason": "Code generation"}
        ]
        
        with patch.object(tool_library, '_generate_recommendations', new_callable=AsyncMock, return_value=mock_recommendations):
            recommendations = await tool_library.recommend_tools(task)
            
            assert len(recommendations) == 2
            assert recommendations[0]["tool_id"] == "python_executor"
            assert recommendations[0]["confidence"] == 0.9