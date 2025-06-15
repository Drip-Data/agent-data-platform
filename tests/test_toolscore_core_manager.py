"""ToolScore CoreManager 综合测试
覆盖工具注册、缓存、WebSocket通知、动态安装等核心功能
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio

from core.toolscore.interfaces import (
    MCPServerSpec, ToolCapability, ToolType, ToolSpec
)


@pytest_asyncio.fixture
async def mock_dependencies():
    """Mock all CoreManager dependencies"""
    with patch("core.toolscore.core_manager.redis") as mock_redis, \
         patch("core.toolscore.core_manager.ProcessRunner") as MockRunner, \
         patch("core.toolscore.core_manager.WebSocketManager") as MockWSMgr, \
         patch("core.toolscore.dynamic_mcp_manager.DynamicMCPManager") as MockDynamic, \
         patch("core.toolscore.monitoring_api.ToolScoreMonitoringAPI") as MockAPI, \
         patch("core.toolscore.core_manager.websockets") as mock_websockets:
        
        # Redis mock
        redis_instance = AsyncMock()
        redis_instance.ping = AsyncMock(return_value=True)
        redis_instance.publish = AsyncMock()
        redis_instance.setex = AsyncMock()
        redis_instance.get = AsyncMock(return_value=None)
        mock_redis.from_url.return_value = redis_instance
        
        # ProcessRunner mock

        runner_instance = MagicMock()
        MockRunner.return_value = runner_instance        # WebSocketManager mock
        ws_manager_instance = MagicMock()
        ws_manager_instance.broadcast = AsyncMock() # Ensure broadcast is an AsyncMock
        MockWSMgr.return_value = ws_manager_instance
        
        # DynamicMCPManager mock
        dynamic_manager = MagicMock()
        dynamic_manager.search_and_install = AsyncMock()
        MockDynamic.return_value = dynamic_manager
        
        # MonitoringAPI mock
        monitoring_api = MagicMock()
        MockAPI.return_value = monitoring_api
        
        # websockets mock for server availability check
        mock_websockets.connect = AsyncMock()
        
        yield {
            "redis": redis_instance,
            "runner": runner_instance,
            "ws_manager": ws_manager_instance, # Corrected: yield the instance
            "dynamic_manager": dynamic_manager,
            "monitoring_api": monitoring_api,
            "websockets": mock_websockets
        }


@pytest_asyncio.fixture
async def core_manager(mock_dependencies):
    """Create CoreManager instance with mocked dependencies"""
    from core.toolscore.core_manager import CoreManager
    
    manager = CoreManager()
    await manager.initialize()
    
    # Inject mocked dependencies for testing
    manager._test_deps = mock_dependencies
    
    yield manager


@pytest.mark.asyncio
async def test_initialization(core_manager, mock_dependencies):
    """Test CoreManager initialization"""
    assert core_manager.runner is not None
    assert core_manager.websocket_manager is not None
    assert core_manager.dynamic_mcp_manager is not None
    assert core_manager.monitoring_api is not None
    assert core_manager.is_running is False
    
    # Check Redis connection was attempted
    if core_manager.redis_client:
        mock_dependencies["redis"].ping.assert_called()


@pytest.mark.asyncio
async def test_register_tool_immediately_success(core_manager, mock_dependencies):
    """Test immediate tool registration with all notifications"""
    # Create test server spec
    server_spec = MCPServerSpec(
        tool_id="test-tool",
        name="Test Tool",
        description="A test tool",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[
            ToolCapability(
                name="test_capability",
                description="Test capability",
                parameters={"param1": {"type": "string", "required": True}}
            )
        ],
        tags=["test"],
        enabled=True,
        endpoint="ws://localhost:8999/mcp"
    )
    
    # Add a mock WebSocket connection
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    core_manager.websocket_connections.add(mock_ws)
    
    # Register tool
    success = await core_manager.register_tool_immediately(server_spec)
    
    assert success is True
    
    # Check local cache was updated
    assert "test-tool" in core_manager._tool_cache
    cached_tool = core_manager._tool_cache["test-tool"]
    assert cached_tool["name"] == "Test Tool"
    assert cached_tool["capabilities"] == ["test_capability"]
    
    # Check Redis events were published
    if core_manager.redis_client:
        assert mock_dependencies["redis"].publish.call_count == 2
        
        # Check event content
        calls = mock_dependencies["redis"].publish.call_args_list
        assert calls[0][0][0] == "tool_events"
        assert calls[1][0][0] == "immediate_tool_updates"
        
        event_data = json.loads(calls[0][0][1])
        assert event_data["event_type"] == "tool_available"
        assert event_data["tool_id"] == "test-tool"
    
    # Check WebSocket notification via WebSocketManager
    # Construct the expected notification content based on how _notify_websocket_clients is called
    expected_notification_content = {
        "type": "tool_installed",
        "tool_id": server_spec.tool_id,
        "name": server_spec.name,
        "description": server_spec.description,
        "capabilities": [cap.name for cap in server_spec.capabilities],
        "tags": server_spec.tags,
        "endpoint": server_spec.endpoint,
        "status": "ready"
    }
    mock_dependencies["ws_manager"].broadcast.assert_called_once_with(expected_notification_content)


@pytest.mark.asyncio
async def test_register_tool_immediately_failure(core_manager, mock_dependencies):
    """Test tool registration when Redis publish fails"""
    server_spec = MCPServerSpec(
        tool_id="fail-tool",
        name="Fail Tool",
        description="This will fail",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[],
        tags=[],
        enabled=True,
        endpoint="ws://localhost:9000/mcp"
    )
    
    # Make Redis publish fail
    mock_dependencies["redis"].publish.side_effect = Exception("Redis error")
    
    # Should still succeed (graceful degradation)
    success = await core_manager.register_tool_immediately(server_spec)
    assert success is True
    
    # Tool should still be in local cache
    assert "fail-tool" in core_manager._tool_cache


@pytest.mark.asyncio
async def test_websocket_notification_with_disconnected_clients(core_manager):
    """Test WebSocket notification handles disconnected clients gracefully"""
    # Add multiple WebSocket connections
    mock_ws1 = AsyncMock()
    mock_ws1.send = AsyncMock()
    
    mock_ws2 = AsyncMock()
    mock_ws2.send = AsyncMock(side_effect=Exception("Connection closed"))
    
    mock_ws3 = AsyncMock()
    mock_ws3.send_str = AsyncMock()  # aiohttp style
    
    core_manager.websocket_connections.add(mock_ws1)
    core_manager.websocket_connections.add(mock_ws2)
    core_manager.websocket_connections.add(mock_ws3)
    
    test_notification = {"type": "test_event", "data": "test"}
    # Send notification
    await core_manager._notify_websocket_clients(test_notification)
    
    # Assert that the broadcast method on the websocket_manager was called
    core_manager._test_deps["ws_manager"].broadcast.assert_called_once_with(test_notification)
    
    # CoreManager._notify_websocket_clients no longer directly manages self.websocket_connections removal on send error.
    # This responsibility is delegated or handled by WebSocketManager or connection lifecycle management.
    # Thus, the connections list in CoreManager should remain unchanged by this specific call.
    assert mock_ws1 in core_manager.websocket_connections
    assert mock_ws2 in core_manager.websocket_connections # Still present as CoreManager doesn't remove on send error now
    assert mock_ws3 in core_manager.websocket_connections
    assert len(core_manager.websocket_connections) == 3 # Length remains 3


@pytest.mark.asyncio
async def test_cache_operations(core_manager, mock_dependencies):
    """Test cache set and get operations"""
    test_data = {"tools": ["tool1", "tool2"], "timestamp": 123456}
    cache_key = "test:cache:key"
    
    # Test cache set
    await core_manager.cache_search_result(cache_key, test_data, ttl=3600)
    
    if core_manager.redis_client:
        mock_dependencies["redis"].setex.assert_called_once_with(
            cache_key, 3600, json.dumps(test_data)
        )
    
    # Test cache get - cache hit
    mock_dependencies["redis"].get.return_value = json.dumps(test_data)
    result = await core_manager.get_cached_result(cache_key)
    assert result == test_data
    
    # Test cache get - cache miss
    mock_dependencies["redis"].get.return_value = None
    result = await core_manager.get_cached_result(cache_key)
    assert result is None
    
    # Test cache get - Redis error
    mock_dependencies["redis"].get.side_effect = Exception("Redis error")
    result = await core_manager.get_cached_result(cache_key)
    assert result is None


@pytest.mark.asyncio
async def test_check_server_availability(core_manager, mock_dependencies):
    """Test MCP server availability check"""
    endpoint = "ws://localhost:8080/mcp"
    
    # Mock successful connection
    mock_ws_cm = AsyncMock()
    mock_ws_cm.send = AsyncMock()
    mock_ws_cm.recv = AsyncMock(return_value='{"result": "pong"}')
    
    # Create a proper async context manager mock
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_ws_cm)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    
    # Set up the websockets mock properly - connect should return the context manager directly
    mock_dependencies["websockets"].connect = MagicMock(return_value=mock_context_manager)
    
    # Ensure the core_manager uses the mocked websockets
    core_manager._test_deps = mock_dependencies
    
    # Check availability
    is_available = await core_manager._check_server_availability(endpoint)
    
    assert is_available is True
    
    # Verify ping was sent
    mock_ws_cm.send.assert_called_once_with(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
    # Ensure recv was called
    mock_ws_cm.recv.assert_called_once()


@pytest.mark.asyncio
async def test_check_server_availability_timeout(core_manager, mock_dependencies):
    """Test server availability check with timeout"""
    endpoint = "ws://localhost:8081/mcp"
    
    # Mock connection that times out on recv
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
    
    mock_dependencies["websockets"].connect.return_value.__aenter__.return_value = mock_ws
    
    # Connection succeeded but recv timed out, so server is not considered fully available for ping-pong.
    is_available = await core_manager._check_server_availability(endpoint)
    assert is_available is False


@pytest.mark.asyncio
async def test_check_server_availability_connection_failed(core_manager, mock_dependencies):
    """Test server availability check when connection fails"""
    endpoint = "ws://localhost:8082/mcp"
    
    # Mock connection failure
    mock_dependencies["websockets"].connect.side_effect = Exception("Connection refused")
    
    # Should return False
    is_available = await core_manager._check_server_availability(endpoint)
    assert is_available is False


@pytest.mark.asyncio
async def test_create_server_spec_from_config(core_manager):
    """Test creating MCPServerSpec from configuration"""
    config = {
        "tool_id": "config-tool",
        "name": "Config Tool",
        "description": "Tool from config",
        "capabilities": [
            {
                "name": "cap1",
                "description": "Capability 1",
                "parameters": {"p1": {"type": "string"}}
            },
            {
                "name": "cap2",
                "description": "Capability 2",
                "parameters": {}
            }
        ],
        "tags": ["config", "test"],
        "endpoint": "ws://localhost:9999/mcp"
    }
    
    spec = await core_manager._create_server_spec_from_config(config)
    
    assert spec.tool_id == "config-tool"
    assert spec.name == "Config Tool"
    assert spec.description == "Tool from config"
    assert spec.tool_type == ToolType.MCP_SERVER
    assert len(spec.capabilities) == 2
    assert spec.capabilities[0].name == "cap1"
    assert spec.capabilities[1].name == "cap2"
    assert spec.tags == ["config", "test"]
    assert spec.enabled is True
    assert spec.endpoint == "ws://localhost:9999/mcp"


@pytest.mark.asyncio
async def test_save_mcp_server(core_manager):
    """Test saving MCP server to persistent storage"""
    server_spec = MCPServerSpec(
        tool_id="persist-tool",
        name="Persistent Tool",
        description="Tool to persist",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[],
        tags=["persistent"],
        enabled=True,
        endpoint="ws://localhost:7777/mcp"
    )
    
    install_result = {
        "container_id": "abc123",
        "port": 7777,
        "status": "running"
    }
    
    # Save server
    await core_manager.save_mcp_server(server_spec, install_result)
    
    # Check it was added to persistent servers
    assert "persist-tool" in core_manager.persistent_servers
    saved = core_manager.persistent_servers["persist-tool"]
    # Compare with the dictionary representation, as that's what's stored
    assert saved["spec"] == server_spec.to_dict() 
    assert saved["install_result"] == install_result
    # If image_id is part of the spec and should be persisted, ensure it's handled
    # For example, if server_spec could have an image_id attribute:
    expected_image_id = getattr(server_spec, 'image_id', None) 
    assert saved.get("image_id") == expected_image_id


@pytest.mark.asyncio
async def test_set_tool_library_for_monitoring(core_manager):
    """Test setting tool library for monitoring API"""
    mock_tool_library = MagicMock()
    
    await core_manager.set_tool_library_for_monitoring(mock_tool_library)
    
    assert core_manager.monitoring_api.tool_library == mock_tool_library


@pytest.mark.asyncio
async def test_recover_all_containers_process_runner(core_manager):
    """Test container recovery with ProcessRunner (should skip)"""
    # ProcessRunner doesn't manage Docker containers
    recovered = await core_manager._recover_all_containers()
    assert recovered == 0


@pytest.mark.asyncio
async def test_create_persistent_container_process_runner(core_manager):
    """Test container creation with ProcessRunner (should return mock ID)"""
    server_spec = MCPServerSpec(
        tool_id="container-tool",
        name="Container Tool",
        description="Tool in container",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[],
        tags=[],
        enabled=True,
        endpoint="ws://localhost:8888/mcp"
    )
    
    container_id = await core_manager.create_persistent_container(
        "image-id", server_spec, 8888
    )
    
    # ProcessRunner returns a mock container ID
    assert container_id == "process-runner-no-container"


@pytest.mark.asyncio
async def test_websocket_connection_management(core_manager):
    """Test adding and removing WebSocket connections"""
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    
    # Add connections
    await core_manager.add_websocket_connection(mock_ws1)
    await core_manager.add_websocket_connection(mock_ws2)
    
    assert len(core_manager.websocket_connections) == 2
    assert mock_ws1 in core_manager.websocket_connections
    assert mock_ws2 in core_manager.websocket_connections
    
    # Remove one connection
    await core_manager.remove_websocket_connection(mock_ws1)
    
    assert len(core_manager.websocket_connections) == 1
    assert mock_ws1 not in core_manager.websocket_connections
    assert mock_ws2 in core_manager.websocket_connections
    
    # Remove non-existent connection (should not error)
    await core_manager.remove_websocket_connection(mock_ws1)
    assert len(core_manager.websocket_connections) == 1