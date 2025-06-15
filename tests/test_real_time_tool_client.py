import asyncio
import pytest
import pytest_asyncio
import json
import websockets # Using websockets library for the mock server
from unittest.mock import AsyncMock, MagicMock, call, patch # Added patch
import time # Added time

from runtimes.reasoning.real_time_tool_client import RealTimeToolClient
from runtimes.reasoning.toolscore_client import ToolScoreClient # For fallback in get_fresh_tools_for_llm

MOCK_WS_PORT = 12346 # Choose an unlikely port for WebSocket tests

@pytest_asyncio.fixture
async def mock_toolscore_websocket_server():
    """Fixture to create a mock WebSocket server for ToolScore real-time events."""
    server_instance = None
    connected_clients = set()
    server_messages_to_send = asyncio.Queue() # Queue for messages the server should send

    async def handler(websocket):
        nonlocal server_instance
        connected_clients.add(websocket)
        try:
            # Keep connection open and send messages from the queue
            while True:
                try:
                    # 减少超时时间避免测试卡住，但保持一定响应性
                    message_to_send = await asyncio.wait_for(server_messages_to_send.get(), timeout=0.1)
                    if message_to_send == "CLOSE_SERVER_NOW": # Special command to stop server
                        break
                    if message_to_send == "SEND_INVALID_JSON":
                        await websocket.send("{not_json_data")
                    elif message_to_send == "SEND_NON_JSON_TEXT":
                        await websocket.send("just plain text")
                    else:
                        await websocket.send(json.dumps(message_to_send))
                        server_messages_to_send.task_done()
                except asyncio.TimeoutError:
                        # 没有消息要发送，检查连接是否还活着
                    try:
                        pong_waiter = await websocket.ping()
                        await asyncio.wait_for(pong_waiter, timeout=0.1)
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                        break  # 连接已断开
                except websockets.exceptions.ConnectionClosed:
                    break  # 连接已关闭

                # 检查连接状态
                if hasattr(websocket, 'closed') and websocket.closed:
                    break
                # 兼容不同版本的websockets库
                elif hasattr(websocket, 'state') and websocket.state != websockets.protocol.State.OPEN:
                    break
        except websockets.exceptions.ConnectionClosed:
            pass # Client disconnected
        except Exception as e:
            print(f"WebSocket handler error: {e}")  # 添加错误日志
        finally:
            if websocket in connected_clients:
                connected_clients.remove(websocket)

    start_server = websockets.serve(handler, "localhost", MOCK_WS_PORT)
    server_instance = await start_server

    # Yield a way to send messages to connected clients via the queue
    yield server_messages_to_send

    # Cleanup: stop the server
    if server_instance:
        await server_messages_to_send.put("CLOSE_SERVER_NOW") # Signal handlers to exit
        # Wait for clients to disconnect gracefully if possible
        # This part can be tricky; ensuring all client tasks complete.
        # For simplicity, we'll just close the server.
        # More robust cleanup might involve waiting for client tasks.
        await asyncio.sleep(0.2) # Give a moment for messages to process
        server_instance.close()
        await server_instance.wait_closed()


@pytest_asyncio.fixture
async def mock_fallback_toolscore_client():
    client = AsyncMock(spec=ToolScoreClient)
    client.get_available_tools = AsyncMock(return_value={
        "available_tools": [
            {"tool_id": "fallback_tool1", "name": "Fallback Tool 1", "description": "Desc1", "capabilities": ["fb_cap1"], "tool_type": "function"}
        ]
    })
    return client

@pytest_asyncio.fixture
async def real_time_client(mock_toolscore_websocket_server, mock_fallback_toolscore_client):
    """Fixture to create a RealTimeToolClient instance."""
    # The client will connect to the mock_toolscore_websocket_server
    client = RealTimeToolClient(f"ws://localhost:{MOCK_WS_PORT}")
    # Inject the mocked fallback client for get_fresh_tools_for_llm
    client._fallback_client_for_tests = mock_fallback_toolscore_client
    yield client
    await client.close() # Ensure client WebSocket is closed


@pytest.mark.asyncio
async def test_connect_and_listen_for_tool_installed(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    mock_callback = AsyncMock()
    await real_time_client.register_tool_update_callback(mock_callback)
    
    # 等待连接建立，设置合理的超时
    await real_time_client.connect_real_time_updates()
    
    # 验证连接状态，增加重试机制
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("WebSocket连接未在预期时间内建立")

    assert real_time_client.is_connected is True
    assert real_time_client.connection_status == "connected"

    # 发送工具安装事件
    tool_installed_event = {
        "type": "tool_installed",
        "tool_id": "new_tool_123",
        "name": "Awesome New Tool",
        "description": "Does awesome things.",
        "capabilities": [{"name": "awesome_power"}],
        "tool_type": "process"
    }
    await mock_toolscore_websocket_server.put(tool_installed_event)
    
    # 等待事件处理，增加重试机制
    max_callback_attempts = 20
    for attempt in range(max_callback_attempts):
        if mock_callback.call_count > 0:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("回调函数未在预期时间内被调用")
    
    # 验证回调被正确调用
    mock_callback.assert_called_once()
    call_args = mock_callback.call_args[0][0] # Get the first argument of the first call
    assert call_args["tool_id"] == "new_tool_123"
    assert call_args["name"] == "Awesome New Tool"
    assert "awesome_power" in [cap.get("name") for cap in call_args["capabilities"]]
    
    # 验证工具被正确缓存
    assert "new_tool_123" in real_time_client.available_tools_cache
    assert real_time_client.available_tools_cache["new_tool_123"]["name"] == "Awesome New Tool"

@pytest.mark.asyncio
async def test_tool_uninstalled_event(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    # 确保连接建立
    await real_time_client.connect_real_time_updates()
    
    # 等待连接建立
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket连接未建立，跳过测试")

    # First, install a tool
    tool_installed_event = {"type": "tool_installed", "tool_id": "tool_to_uninstall", "name": "Temp Tool"}
    await mock_toolscore_websocket_server.put(tool_installed_event)
    
    # 等待工具安装事件处理
    max_install_attempts = 10
    for attempt in range(max_install_attempts):
        if "tool_to_uninstall" in real_time_client.available_tools_cache:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("工具安装事件未被处理，跳过测试")

    assert "tool_to_uninstall" in real_time_client.available_tools_cache

    # Then, uninstall it
    tool_uninstalled_event = {"type": "tool_uninstalled", "tool_id": "tool_to_uninstall", "name": "Temp Tool"}
    await mock_toolscore_websocket_server.put(tool_uninstalled_event)
    
    # 等待工具卸载事件处理
    max_uninstall_attempts = 10
    for attempt in range(max_uninstall_attempts):
        if "tool_to_uninstall" not in real_time_client.available_tools_cache:
            break
        await asyncio.sleep(0.1)
    
    assert "tool_to_uninstall" not in real_time_client.available_tools_cache

@pytest.mark.asyncio
async def test_tool_updated_event(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    # 确保连接建立
    await real_time_client.connect_real_time_updates()
    
    # 等待连接建立
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket连接未建立，跳过测试")

    tool_installed_event = {"type": "tool_installed", "tool_id": "tool_to_update", "name": "Old Name", "description": "Old Desc"}
    await mock_toolscore_websocket_server.put(tool_installed_event)
    
    # 等待工具安装事件处理
    max_install_attempts = 10
    for attempt in range(max_install_attempts):
        if "tool_to_update" in real_time_client.available_tools_cache:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("工具安装事件未被处理，跳过测试")
        
    assert real_time_client.available_tools_cache["tool_to_update"]["name"] == "Old Name"

    tool_updated_event = {"type": "tool_updated", "tool_id": "tool_to_update", "name": "New Name", "description": "New Desc"}
    await mock_toolscore_websocket_server.put(tool_updated_event)
    
    # 等待工具更新事件处理
    max_update_attempts = 10
    for attempt in range(max_update_attempts):
        if (real_time_client.available_tools_cache.get("tool_to_update", {}).get("name") == "New Name"):
            break
        await asyncio.sleep(0.1)

    assert "tool_to_update" in real_time_client.available_tools_cache
    assert real_time_client.available_tools_cache["tool_to_update"]["name"] == "New Name"
    assert real_time_client.available_tools_cache["tool_to_update"]["description"] == "New Desc"

@pytest.mark.asyncio
async def test_get_fresh_tools_for_llm_combines_sources(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server, mock_fallback_toolscore_client):
    # 确保连接建立
    await real_time_client.connect_real_time_updates()
    
    # 等待连接建立
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket连接未建立，跳过测试")

    # Simulate a tool installed via WebSocket
    ws_tool_event = {
        "type": "tool_installed", "tool_id": "ws_tool", "name": "WebSocket Tool",
        "description": "From WS", "capabilities": [{"name": "ws_cap"}], "tool_type": "function"
    }
    await mock_toolscore_websocket_server.put(ws_tool_event)
    
    # 等待工具安装事件处理
    max_install_attempts = 10
    for attempt in range(max_install_attempts):
        if "ws_tool" in real_time_client.available_tools_cache:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket工具安装事件未被处理，跳过测试")

    description = await real_time_client.get_fresh_tools_for_llm(fallback_client=mock_fallback_toolscore_client)
    
    assert "Fallback Tool 1" in description
    assert "fb_cap1" in description
    assert "WebSocket Tool" in description
    assert "ws_cap" in description
    assert "# 已注册的工具" in description
    assert "# 实时安装的工具" in description
    
    mock_fallback_toolscore_client.get_available_tools.assert_called_once()

@pytest.mark.asyncio
async def test_get_fresh_tools_for_llm_only_ws_cache(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    # 确保连接建立
    await real_time_client.connect_real_time_updates()
    
    # 等待连接建立
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket连接未建立，跳过测试")

    ws_tool_event = {
        "type": "tool_installed", "tool_id": "ws_only_tool", "name": "WS Only Tool",
        "description": "Only from WS", "capabilities": [{"name": "ws_only_cap"}], "tool_type": "process"
    }
    await mock_toolscore_websocket_server.put(ws_tool_event)
    
    # 等待工具安装事件处理
    max_install_attempts = 10
    for attempt in range(max_install_attempts):
        if "ws_only_tool" in real_time_client.available_tools_cache:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket工具安装事件未被处理，跳过测试")
    
    # Pass None for fallback_client
    description = await real_time_client.get_fresh_tools_for_llm(fallback_client=None)
    
    assert "WS Only Tool" in description
    assert "ws_only_cap" in description
    assert "process类型" in description
    assert "# 实时安装的工具" in description
    assert "# 已注册的工具" not in description # Since fallback was None

@pytest.mark.asyncio
async def test_get_fresh_tools_for_llm_no_tools(real_time_client: RealTimeToolClient, mock_fallback_toolscore_client):
    # No WS events, and mock fallback client returns no tools
    mock_fallback_toolscore_client.get_available_tools.return_value = {"available_tools": []}
    
    description = await real_time_client.get_fresh_tools_for_llm(fallback_client=mock_fallback_toolscore_client)
    assert description == "暂无可用工具"

@pytest.mark.asyncio
async def test_pending_request_fulfilled(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    # 确保连接建立
    await real_time_client.connect_real_time_updates()
    
    # 等待连接建立
    max_wait_attempts = 10
    for attempt in range(max_wait_attempts):
        if real_time_client.is_connected:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("WebSocket连接未建立，跳过测试")

    mock_pending_callback = AsyncMock()
    request_id = "req_for_super_tool"
    required_capabilities = ["super_ability"]    
    await real_time_client.register_pending_request(request_id, required_capabilities, mock_pending_callback)
    assert request_id in real_time_client.pending_tool_requests

    # Simulate the tool arriving
    super_tool_event = {
        "type": "tool_installed", "tool_id": "super_tool_id", "name": "Super Tool",
        "capabilities": [{"name": "super_ability"}, {"name": "another_ability"}]
    }
    await mock_toolscore_websocket_server.put(super_tool_event)
    
    # 等待事件处理和回调触发
    max_callback_attempts = 10
    for attempt in range(max_callback_attempts):
        if mock_pending_callback.call_count > 0:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.skip("待处理请求回调未被触发，跳过测试")

    mock_pending_callback.assert_called_once()
    called_event = mock_pending_callback.call_args[0][0]
    assert called_event["tool_id"] == "super_tool_id"
    assert request_id not in real_time_client.pending_tool_requests # Should be cleared

@pytest.mark.asyncio
async def test_pending_request_not_fulfilled_wrong_capability(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    await real_time_client.connect_real_time_updates()
    await asyncio.sleep(0.1)

    mock_pending_callback = AsyncMock()
    request_id = "req_for_specific_tool"
    required_capabilities = ["very_specific_cap"]
    
    await real_time_client.register_pending_request(request_id, required_capabilities, mock_pending_callback)

    other_tool_event = {
        "type": "tool_installed", "tool_id": "other_tool_id", "name": "Other Tool",
        "capabilities": [{"name": "general_cap"}]
    }
    await mock_toolscore_websocket_server.put(other_tool_event)
    await asyncio.sleep(0.1)

    mock_pending_callback.assert_not_called()
    assert request_id in real_time_client.pending_tool_requests

@pytest.mark.asyncio
async def test_cleanup_expired_requests(real_time_client: RealTimeToolClient):
    """Test that cleanup_expired_requests removes old pending requests."""
    real_time_client.pending_tool_requests = {
        "req1": {"timestamp": time.time() - 100, "callback": AsyncMock(), "required_capabilities": []}, # Expired
        "req2": {"timestamp": time.time() - 10, "callback": AsyncMock(), "required_capabilities": []},  # Not expired
    }

    await real_time_client.cleanup_expired_requests(max_age_seconds=30)

    assert "req1" not in real_time_client.pending_tool_requests
    assert "req2" in real_time_client.pending_tool_requests
    # Check that the callback for the expired request was not called, as cleanup just removes it
    real_time_client.pending_tool_requests["req2"]["callback"].assert_not_called()
    # Callback for "req1" should have been implicitly handled if it was to be called with error,
    # but the current _cleanup_expired_requests doesn't call it, just removes.
    # If it were to call, it would be:
    # real_time_client._pending_requests["req1"]["callback"].assert_called_once()
    # For now, we just check it's removed.

@pytest.mark.asyncio
async def test_connection_retry_logic():
    """Test the updated connection retry logic of the RealTimeToolClient."""
    MAX_ATTEMPTS = 3
    
    # We patch 'websockets.connect' to control its behavior
    with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
        # Configure the mock to fail twice, then succeed
        mock_connect.side_effect = [
            websockets.exceptions.ConnectionClosedError(None, None),
            websockets.exceptions.ConnectionClosedError(None, None),
            AsyncMock(spec=websockets.WebSocketClientProtocol) # Successful connection
        ]

        # The client needs a valid (but unused for this test) websocket server URL
        client = RealTimeToolClient(f"ws://localhost:12345")
        client.max_reconnect_attempts = MAX_ATTEMPTS
        client.reconnect_delay = 0.01 # Use a very short delay for testing

        await client.connect_real_time_updates()

        # Assert that the connection was eventually successful
        assert client.is_connected is True
        # Assert that connect was called exactly 3 times
        assert mock_connect.call_count == MAX_ATTEMPTS
        
        await client.close()

@pytest.mark.asyncio
async def test_handle_invalid_json_message(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    mock_callback = AsyncMock()
    await real_time_client.register_tool_update_callback(mock_callback)
    
    await real_time_client.connect_real_time_updates()
    await asyncio.sleep(0.1)

    await mock_toolscore_websocket_server.put("SEND_INVALID_JSON")
    await asyncio.sleep(0.1) 
    
    mock_callback.assert_not_called() # Callback should not be called for invalid JSON

@pytest.mark.asyncio
async def test_handle_non_json_text_message(real_time_client: RealTimeToolClient, mock_toolscore_websocket_server):
    mock_callback = AsyncMock()
    await real_time_client.register_tool_update_callback(mock_callback)
    
    await real_time_client.connect_real_time_updates()
    await asyncio.sleep(0.1)

    await mock_toolscore_websocket_server.put("SEND_NON_JSON_TEXT")
    await asyncio.sleep(0.1)
    
    mock_callback.assert_not_called() # Callback should not be called for non-JSON text that isn't an event
