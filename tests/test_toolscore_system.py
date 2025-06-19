#!/usr/bin/env python3
"""
ToolScore System 综合测试套件
测试ToolScore工具管理系统的核心功能，包括工具注册、发现、缓存、监控等
"""

import asyncio
import pytest
import time
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

# 配置pytest-asyncio
pytestmark = pytest.mark.asyncio

logger = __import__('logging').getLogger(__name__)


class TestToolScoreClient:
    """测试ToolScore客户端"""
    
    @pytest.fixture
    def toolscore_client(self, mock_config_manager):
        """创建ToolScore客户端实例"""
        from core.toolscore.toolscore_client import ToolScoreClient
        return ToolScoreClient(mock_config_manager)
    
    async def test_client_initialization(self, toolscore_client):
        """测试客户端初始化"""
        assert toolscore_client.config_manager is not None
        assert toolscore_client.tool_service_url is not None
        assert "localhost" in toolscore_client.tool_service_url
    
    @patch('aiohttp.ClientSession.get')
    async def test_get_available_tools(self, mock_get, toolscore_client):
        """测试获取可用工具"""
        # 模拟HTTP响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "success",
            "tools": [
                {
                    "tool_id": "test-tool",
                    "name": "Test Tool",
                    "description": "A test tool",
                    "capabilities": ["test_action"]
                }
            ]
        })
        mock_get.return_value.__aenter__.return_value = mock_response
        
        tools = await toolscore_client.get_available_tools()
        
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "test-tool"
        assert tools[0]["name"] == "Test Tool"
    
    @patch('aiohttp.ClientSession.post')
    async def test_request_tool_capability(self, mock_post, toolscore_client):
        """测试请求工具能力"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "success",
            "recommendation": "Use tool X for this task"
        })
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await toolscore_client.request_tool_capability("test task")
        
        assert result["status"] == "success"
        assert "recommendation" in result
    
    async def test_http_error_handling(self, toolscore_client):
        """测试HTTP错误处理"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = Exception("Connection error")
            
            tools = await toolscore_client.get_available_tools()
            assert tools == []


class TestUnifiedToolLibrary:
    """测试统一工具库"""
    
    @pytest.fixture
    async def tool_library(self, mock_redis_client):
        """创建工具库实例"""
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        
        library = UnifiedToolLibrary(redis_client=mock_redis_client)
        await library.initialize()
        return library
    
    async def test_library_initialization(self, tool_library):
        """测试工具库初始化"""
        assert tool_library.redis_client is not None
        assert tool_library.tools == {}
        assert tool_library.connectors == {}
    
    async def test_register_tool(self, tool_library):
        """测试工具注册"""
        from core.toolscore.interfaces import ToolSpec, ToolCapability, ToolType
        
        capability = ToolCapability(
            name="test_action",
            description="Test action",
            parameters={"param1": {"type": "string", "description": "Test parameter"}}
        )
        
        tool_spec = ToolSpec(
            tool_id="test-tool",
            name="Test Tool",
            description="A test tool",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[capability],
            tags=["test"],
            enabled=True
        )
        
        result = await tool_library.register_tool(tool_spec)
        
        assert result.success is True
        assert result.tool_id == "test-tool"
        assert "test-tool" in tool_library.tools
    
    async def test_search_tools(self, tool_library):
        """测试工具搜索"""
        # 首先注册一个工具
        from core.toolscore.interfaces import ToolSpec, ToolCapability, ToolType
        
        capability = ToolCapability(
            name="search_action",
            description="Search functionality",
            parameters={}
        )
        
        tool_spec = ToolSpec(
            tool_id="search-tool",
            name="Search Tool",
            description="A search tool for web content",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[capability],
            tags=["search", "web"],
            enabled=True
        )
        
        await tool_library.register_tool(tool_spec)
        
        # 测试按标签搜索
        results = await tool_library.search_tools(tags=["search"])
        assert len(results) == 1
        assert results[0].tool_id == "search-tool"
        
        # 测试按能力搜索
        results = await tool_library.search_tools(capabilities=["search_action"])
        assert len(results) == 1
        assert results[0].tool_id == "search-tool"
    
    async def test_get_library_stats(self, tool_library):
        """测试获取库统计信息"""
        stats = await tool_library.get_library_stats()
        
        assert "total_tools" in stats
        assert "active_tools" in stats
        assert "total_capabilities" in stats
        assert "connectors" in stats
        assert stats["initialized"] is True


class TestCoreManager:
    """测试核心管理器"""
    
    @pytest.fixture
    async def core_manager(self, mock_redis_client):
        """创建核心管理器实例"""
        from core.toolscore.core_manager import CoreManager
        
        manager = CoreManager(redis_url="redis://localhost:6379")
        manager.redis_client = mock_redis_client  # 注入模拟客户端
        await manager.initialize()
        return manager
    
    async def test_manager_initialization(self, core_manager):
        """测试管理器初始化"""
        assert core_manager.redis_client is not None
        assert core_manager.websocket_manager is not None
        assert core_manager.cache_manager is not None
        assert len(core_manager.predefined_servers) > 0
    
    async def test_register_tool_immediately(self, core_manager):
        """测试立即注册工具"""
        from core.toolscore.interfaces import MCPServerSpec, ToolCapability, ToolType
        
        capability = ToolCapability(
            name="immediate_action",
            description="Immediate action",
            parameters={}
        )
        
        server_spec = MCPServerSpec(
            tool_id="immediate-tool",
            name="Immediate Tool",
            description="Tool for immediate registration",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[capability],
            tags=["immediate"],
            enabled=True,
            endpoint="ws://localhost:8000"
        )
        
        result = await core_manager.register_tool_immediately(server_spec)
        assert result is True
        
        # 检查缓存
        assert "immediate-tool" in core_manager._tool_cache
    
    async def test_check_server_availability(self, core_manager):
        """测试服务器可用性检查"""
        # 测试不可达的端点
        is_available = await core_manager._check_server_availability("ws://localhost:9999")
        assert is_available is False
    
    async def test_websocket_connection_management(self, core_manager):
        """测试WebSocket连接管理"""
        mock_websocket = AsyncMock()
        
        # 添加连接
        await core_manager.add_websocket_connection(mock_websocket)
        assert mock_websocket in core_manager.websocket_connections
        
        # 移除连接
        await core_manager.remove_websocket_connection(mock_websocket)
        assert mock_websocket not in core_manager.websocket_connections
    
    async def test_cache_operations(self, core_manager):
        """测试缓存操作"""
        test_data = {"test": "data"}
        cache_key = "test_key"
        
        # 缓存数据
        await core_manager.cache_search_result(cache_key, test_data)
        
        # 验证Redis调用
        core_manager.redis_client.setex.assert_called_once()
        
        # 获取缓存数据
        core_manager.redis_client.get.return_value = json.dumps(test_data)
        cached_data = await core_manager.get_cached_result(cache_key)
        
        assert cached_data == test_data


class TestMonitoringAPI:
    """测试监控API"""
    
    @pytest.fixture
    async def monitoring_api(self, tool_library):
        """创建监控API实例"""
        from core.toolscore.monitoring_api import ToolScoreMonitoringAPI
        
        api = ToolScoreMonitoringAPI(tool_library=tool_library, port=8082)
        return api
    
    def test_api_initialization(self, monitoring_api):
        """测试API初始化"""
        assert monitoring_api.tool_library is not None
        assert monitoring_api.port == 8082
        assert monitoring_api.app is not None
    
    @patch('aiohttp.web.Application.router')
    def test_routes_setup(self, mock_router, monitoring_api):
        """测试路由设置"""
        # 验证路由已正确设置
        assert mock_router.add_get.call_count > 0
        assert mock_router.add_post.call_count > 0
    
    async def test_health_check_endpoint(self, monitoring_api):
        """测试健康检查端点"""
        from aiohttp.test_utils import make_mocked_request
        
        request = make_mocked_request('GET', '/health')
        response = await monitoring_api.health_check(request)
        
        assert response.status == 200
        response_data = json.loads(response.body)
        assert response_data["status"] == "healthy"


class TestDynamicMCPManager:
    """测试动态MCP管理器"""
    
    @pytest.fixture
    def dynamic_manager(self, mock_config_manager):
        """创建动态MCP管理器实例"""
        from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
        from core.toolscore.runners import ProcessRunner
        
        runner = ProcessRunner()
        return DynamicMCPManager(runner=runner, config_manager=mock_config_manager)
    
    def test_manager_initialization(self, dynamic_manager):
        """测试管理器初始化"""
        assert dynamic_manager.runner is not None
        assert dynamic_manager.config_manager is not None
        assert dynamic_manager.active_servers == {}
    
    @patch('core.toolscore.runners.ProcessRunner.install_server')
    async def test_install_mcp_server(self, mock_install, dynamic_manager):
        """测试MCP服务器安装"""
        mock_install.return_value = {
            "success": True,
            "server_id": "test-server",
            "endpoint": "ws://localhost:8000"
        }
        
        server_config = {
            "name": "test-server",
            "repo_url": "https://github.com/test/server",
            "project_type": "python",
            "entry_point": "main.py"
        }
        
        result = await dynamic_manager.install_mcp_server(server_config)
        
        assert result["success"] is True
        assert result["server_id"] == "test-server"
        mock_install.assert_called_once_with(server_config)
    
    async def test_get_server_status(self, dynamic_manager):
        """测试获取服务器状态"""
        # 添加一个活跃服务器
        dynamic_manager.active_servers["test-server"] = {
            "config": {"name": "test-server"},
            "endpoint": "ws://localhost:8000",
            "status": "running"
        }
        
        status = await dynamic_manager.get_server_status("test-server")
        
        assert status["server_id"] == "test-server"
        assert status["status"] == "running"
        assert status["endpoint"] == "ws://localhost:8000"
    
    async def test_list_servers(self, dynamic_manager):
        """测试列出服务器"""
        # 添加测试服务器
        dynamic_manager.active_servers["server1"] = {
            "config": {"name": "server1"},
            "endpoint": "ws://localhost:8001",
            "status": "running"
        }
        dynamic_manager.active_servers["server2"] = {
            "config": {"name": "server2"},
            "endpoint": "ws://localhost:8002",
            "status": "stopped"
        }
        
        servers = await dynamic_manager.list_servers()
        
        assert len(servers) == 2
        server_ids = [s["server_id"] for s in servers]
        assert "server1" in server_ids
        assert "server2" in server_ids


class TestPerformanceAndStress:
    """性能和压力测试"""
    
    @pytest.fixture
    async def tool_library(self, mock_redis_client):
        """创建工具库实例"""
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        
        library = UnifiedToolLibrary(redis_client=mock_redis_client)
        await library.initialize()
        return library
    
    async def test_concurrent_tool_registration(self, tool_library):
        """测试并发工具注册"""
        from core.toolscore.interfaces import ToolSpec, ToolCapability, ToolType
        
        async def register_tool(tool_id):
            capability = ToolCapability(
                name=f"action_{tool_id}",
                description=f"Action for tool {tool_id}",
                parameters={}
            )
            
            tool_spec = ToolSpec(
                tool_id=f"tool-{tool_id}",
                name=f"Tool {tool_id}",
                description=f"Test tool {tool_id}",
                tool_type=ToolType.MCP_SERVER,
                capabilities=[capability],
                tags=["test"],
                enabled=True
            )
            
            return await tool_library.register_tool(tool_spec)
        
        # 并发注册10个工具
        tasks = [register_tool(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有注册都成功
        for result in results:
            assert result.success is True
        
        # 验证工具库中有10个工具
        stats = await tool_library.get_library_stats()
        assert stats["total_tools"] == 10
    
    async def test_large_search_performance(self, tool_library):
        """测试大规模搜索性能"""
        from core.toolscore.interfaces import ToolSpec, ToolCapability, ToolType
        
        # 注册100个工具
        for i in range(100):
            capability = ToolCapability(
                name=f"search_action_{i}",
                description=f"Search action {i}",
                parameters={}
            )
            
            tool_spec = ToolSpec(
                tool_id=f"search-tool-{i}",
                name=f"Search Tool {i}",
                description=f"Search tool {i}",
                tool_type=ToolType.MCP_SERVER,
                capabilities=[capability],
                tags=["search", f"category_{i % 10}"],
                enabled=True
            )
            
            await tool_library.register_tool(tool_spec)
        
        # 测试搜索性能
        start_time = time.time()
        results = await tool_library.search_tools(tags=["search"])
        end_time = time.time()
        
        search_time = end_time - start_time
        assert search_time < 1.0  # 搜索应该在1秒内完成
        assert len(results) == 100


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])