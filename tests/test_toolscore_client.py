import pytest
import pytest_asyncio
import json
from aiohttp import web

from runtimes.reasoning.toolscore_client import ToolScoreClient

MOCK_SERVER_PORT = 12345 # Choose an unlikely port for tests

@pytest_asyncio.fixture
async def mock_toolscore_server(aiohttp_server):
    """Fixture to create a mock aiohttp server for ToolScore APIs."""
    app = web.Application()
    
    # --- Mock Handlers ---
    async def health_handler(request):
        if request.app.get("simulate_health_error", False):
            return web.Response(text="Service Unavailable", status=503)
        return web.Response(text="OK", status=200)

    async def available_tools_handler(request):
        if request.app.get("simulate_tools_error", False):
            return web.Response(text="Internal Server Error", status=500)
        if request.app.get("simulate_tools_malformed_json", False):
            return web.Response(text="{not_json", status=200, content_type="application/json")
            
        return web.json_response({
            "formatted_tools_description": "- tool1: Does thing1\n- tool2: Does thing2",
            "tools": [
                {"tool_id": "tool1", "name": "Tool One", "description": "Does thing1"},
                {"tool_id": "tool2", "name": "Tool Two", "description": "Does thing2"}
            ],
            "available_tools": [ # Used by get_available_tools()
                {"tool_id": "tool1", "name": "Tool One", "description": "Does thing1", "capabilities": ["cap1"]},
                {"tool_id": "tool2", "name": "Tool Two", "description": "Does thing2", "capabilities": ["cap2"]}
            ]
        })

    async def request_capability_handler(request):
        if request.app.get("simulate_request_cap_error", False):
            return web.json_response({"success": False, "message": "Failed to process capability request"}, status=400)
        
        data = await request.json()
        request.app["last_request_cap_payload"] = data # Store for assertion
        
        if data.get("task_description") == "install_specific_tool":
            return web.json_response({
                "success": True,
                "installed_tools": [{"tool_id": "newly_installed_tool", "name": "Newly Installed Tool"}],
                "message": "Tool installed successfully"
            })
        return web.json_response({"success": False, "message": "No suitable tool found or action taken"})

    async def analyze_gap_handler(request):
        if request.app.get("simulate_analyze_gap_error", False):
            return web.json_response({"error": "Analysis failed"}, status=500)
        
        data = await request.json()
        request.app["last_analyze_gap_payload"] = data
        
        if data.get("task_description") == "needs_tool_x":
            return web.json_response({
                "has_sufficient_tools": False,
                "gap_analysis": {"missing_capabilities": ["tool_x_cap"], "reasoning": "Tool X is missing"}
            })
        return web.json_response({"has_sufficient_tools": True, "gap_analysis": {}})

    async def tool_detail_handler(request):
        tool_id = request.match_info.get('tool_id')
        if tool_id == "existing_tool":
            return web.json_response({"tool_id": "existing_tool", "name": "Existing Tool", "mcp_endpoint": "ws://localhost:9000/mcp"})
        elif tool_id == "error_tool":
            return web.Response(text="Tool detail error", status=500)
        return web.Response(text="Not Found", status=404)

    async def execute_tool_handler(request):
        if request.app.get("simulate_execute_error_status", None):
            status = request.app["simulate_execute_error_status"]
            return web.json_response({"success": False, "message": f"Execution failed with status {status}"}, status=status)

        data = await request.json()
        request.app["last_execute_payload"] = data
        
        if data.get("tool_id") == "success_tool" and data.get("action") == "do_work":
            return web.json_response({"success": True, "result": {"output": "Tool executed successfully"}})
        return web.json_response({"success": False, "message": "Tool or action not recognized"})
        
    async def register_mcp_handler(request):
        if request.app.get("simulate_register_mcp_error", False):
            return web.json_response({"success": False, "message": "Registration failed"}, status=400)
        
        data = await request.json()
        request.app["last_register_mcp_payload"] = data
        return web.json_response({"success": True, "message": "MCP server registered", "tool_id": data.get("server_spec", {}).get("tool_id")})


    app.router.add_get("/health", health_handler)
    app.router.add_get("/api/v1/tools/available", available_tools_handler)
    app.router.add_post("/api/v1/tools/request-capability", request_capability_handler)
    app.router.add_post("/api/v1/tools/analyze-gap", analyze_gap_handler)
    app.router.add_get("/api/v1/tools/{tool_id}", tool_detail_handler)
    app.router.add_post("/api/v1/tools/execute", execute_tool_handler)
    app.router.add_post("/admin/mcp/register", register_mcp_handler)
    
    return await aiohttp_server(app, port=MOCK_SERVER_PORT)

@pytest_asyncio.fixture
async def toolscore_client(mock_toolscore_server):
    """Fixture to create a ToolScoreClient instance pointing to the mock server."""
    client = ToolScoreClient(f"http://localhost:{MOCK_SERVER_PORT}")
    await client._ensure_session() # Initialize session
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_health_check_healthy(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_health_error"] = False
    assert await toolscore_client.health_check() is True

@pytest.mark.asyncio
async def test_health_check_unhealthy(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_health_error"] = True
    assert await toolscore_client.health_check() is False

@pytest.mark.asyncio
async def test_health_check_connection_error(toolscore_client: ToolScoreClient):
    # Test with a non-existent server
    bad_client = ToolScoreClient("http://localhost:1") 
    await bad_client._ensure_session()
    assert await bad_client.health_check() is False
    await bad_client.close()

@pytest.mark.asyncio
async def test_wait_for_ready_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_health_error"] = False
    assert await toolscore_client.wait_for_ready(max_wait_seconds=1) is True

@pytest.mark.asyncio
async def test_wait_for_ready_timeout(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_health_error"] = True
    assert await toolscore_client.wait_for_ready(max_wait_seconds=1) is False

@pytest.mark.asyncio
async def test_get_available_tools_for_llm_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = False
    description = await toolscore_client.get_available_tools_for_llm()
    assert description == "- tool1: Does thing1\n- tool2: Does thing2"

@pytest.mark.asyncio
async def test_get_available_tools_for_llm_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = True
    description = await toolscore_client.get_available_tools_for_llm()
    assert description == ""

@pytest.mark.asyncio
async def test_get_available_tools_raw_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = False
    tools = await toolscore_client.get_available_tools_raw()
    assert len(tools) == 2
    assert tools[0]["tool_id"] == "tool1"

@pytest.mark.asyncio
async def test_get_available_tools_raw_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = True
    tools = await toolscore_client.get_available_tools_raw()
    assert tools == []
    
@pytest.mark.asyncio
async def test_get_available_tools_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = False
    response = await toolscore_client.get_available_tools()
    assert "available_tools" in response
    assert len(response["available_tools"]) == 2
    assert response["available_tools"][0]["tool_id"] == "tool1"

@pytest.mark.asyncio
async def test_get_available_tools_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_error"] = True
    response = await toolscore_client.get_available_tools()
    assert response == {"available_tools": []}


@pytest.mark.asyncio
async def test_request_tool_capability_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_request_cap_error"] = False
    payload = {"task_description": "install_specific_tool", "required_capabilities": ["new_cap"], "auto_install": True}
    response = await toolscore_client.request_tool_capability(**payload)
    
    assert response["success"] is True
    assert response["installed_tools"][0]["tool_id"] == "newly_installed_tool"
    assert mock_toolscore_server.app["last_request_cap_payload"] == payload

@pytest.mark.asyncio
async def test_request_tool_capability_failure_no_tool(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_request_cap_error"] = False
    payload = {"task_description": "unknown_task", "auto_install": False}
    response = await toolscore_client.request_tool_capability(**payload)
    assert response["success"] is False
    assert "No suitable tool found" in response["message"]

@pytest.mark.asyncio
async def test_request_tool_capability_server_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_request_cap_error"] = True
    payload = {"task_description": "any_task"}
    response = await toolscore_client.request_tool_capability(**payload)
    assert response["success"] is False
    assert "Failed to process capability request" in response["message"]
    assert "HTTP 400" in response["message"] # Check if status code is in message

@pytest.mark.asyncio
async def test_analyze_tool_gap_sufficient(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_analyze_gap_error"] = False
    payload = {"task_description": "simple_task", "current_tools": [{"name": "toolA"}]}
    response = await toolscore_client.analyze_tool_gap(**payload)
    assert response["has_sufficient_tools"] is True
    assert mock_toolscore_server.app["last_analyze_gap_payload"] == payload

@pytest.mark.asyncio
async def test_analyze_tool_gap_insufficient(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_analyze_gap_error"] = False
    payload = {"task_description": "needs_tool_x"}
    response = await toolscore_client.analyze_tool_gap(**payload)
    assert response["has_sufficient_tools"] is False
    assert response["gap_analysis"]["missing_capabilities"] == ["tool_x_cap"]

@pytest.mark.asyncio
async def test_analyze_tool_gap_server_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_analyze_gap_error"] = True
    response = await toolscore_client.analyze_tool_gap(task_description="any")
    assert response["has_sufficient_tools"] is True # Default on error
    assert "Analysis failed" in response["gap_analysis"]["reasoning"]

@pytest.mark.asyncio
async def test_get_tool_detail_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    tool_info = await toolscore_client.get_tool_detail("existing_tool")
    assert tool_info is not None
    assert tool_info["tool_id"] == "existing_tool"
    assert tool_info["mcp_endpoint"] == "ws://localhost:9000/mcp"

@pytest.mark.asyncio
async def test_get_tool_detail_not_found(toolscore_client: ToolScoreClient, mock_toolscore_server):
    tool_info = await toolscore_client.get_tool_detail("non_existing_tool")
    assert tool_info is None

@pytest.mark.asyncio
async def test_get_tool_detail_server_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    tool_info = await toolscore_client.get_tool_detail("error_tool")
    assert tool_info is None

@pytest.mark.asyncio
async def test_execute_tool_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_execute_error_status"] = None
    payload = {"tool_id": "success_tool", "action": "do_work", "parameters": {"input": "data"}}
    response = await toolscore_client.execute_tool(**payload)
    
    assert response["success"] is True
    assert response["result"]["output"] == "Tool executed successfully"
    assert mock_toolscore_server.app["last_execute_payload"] == payload

@pytest.mark.asyncio
async def test_execute_tool_failure_tool_not_recognized(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_execute_error_status"] = None
    payload = {"tool_id": "unknown_tool", "action": "any_action", "parameters": {}}
    response = await toolscore_client.execute_tool(**payload)
    assert response["success"] is False
    assert "Tool or action not recognized" in response["message"]

@pytest.mark.asyncio
@pytest.mark.parametrize("error_status", [400, 404, 500, 503])
async def test_execute_tool_server_errors(toolscore_client: ToolScoreClient, mock_toolscore_server, error_status):
    mock_toolscore_server.app["simulate_execute_error_status"] = error_status
    payload = {"tool_id": "any_tool", "action": "any_action", "parameters": {}}
    response = await toolscore_client.execute_tool(**payload)
    assert response["success"] is False
    assert f"Execution failed with status {error_status}" in response["message"]
    assert f"HTTP {error_status}" in response["message"]
    assert response["status"] == error_status

@pytest.mark.asyncio
async def test_register_external_mcp_server_success(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_register_mcp_error"] = False
    server_spec = {
        "tool_id": "my-custom-server", "name": "My Custom Server", "endpoint": "ws://custom:1234/mcp",
        "capabilities": [{"name": "custom_op"}], "description": "A custom server."
    }
    response = await toolscore_client.register_external_mcp_server(server_spec)
    assert response["success"] is True
    assert response["tool_id"] == "my-custom-server"
    assert mock_toolscore_server.app["last_register_mcp_payload"]["server_spec"] == server_spec

@pytest.mark.asyncio
async def test_register_external_mcp_server_error(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_register_mcp_error"] = True
    server_spec = {"tool_id": "error-server"}
    response = await toolscore_client.register_external_mcp_server(server_spec)
    assert response["success"] is False
    assert "Registration failed" in response["message"]
    assert response["status"] == 400

@pytest.mark.asyncio
async def test_malformed_json_response_tools_available(toolscore_client: ToolScoreClient, mock_toolscore_server):
    mock_toolscore_server.app["simulate_tools_malformed_json"] = True
    # get_available_tools_for_llm should return empty string on JSON error
    description = await toolscore_client.get_available_tools_for_llm()
    assert description == ""
    # get_available_tools_raw should return empty list on JSON error
    tools_raw = await toolscore_client.get_available_tools_raw()
    assert tools_raw == []
    # get_available_tools should return default on JSON error
    tools_available = await toolscore_client.get_available_tools()
    assert tools_available == {"available_tools": []}
    mock_toolscore_server.app["simulate_tools_malformed_json"] = False # Reset for other tests
