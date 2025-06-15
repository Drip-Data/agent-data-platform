# agent-data-platform/tests/test_enhanced_runtime.py
import asyncio
import pytest
import pytest_asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

from core.interfaces import TaskSpec, TrajectoryResult, ExecutionStep, ActionType, ErrorType, LLMInteraction
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
from core.llm_client import LLMClient
from runtimes.reasoning.toolscore_client import ToolScoreClient
from runtimes.reasoning.real_time_tool_client import RealTimeToolClient
from core.toolscore.mcp_client import MCPToolClient
from core.toolscore.interfaces import ExecutionResult

# Mock get_ports_config to avoid dependency on actual config files during tests
@pytest.fixture(scope="module", autouse=True)
def mock_ports_config_module_scope():
    with patch('runtimes.reasoning.enhanced_runtime.get_ports_config') as mock_config_func:
        mock_config_func.return_value = {
            'mcp_servers': {
                'toolscore_http': {'port': 8082},
                'toolscore_mcp': {'port': 8081}
            }
        }
        yield mock_config_func


@pytest_asyncio.fixture
async def mock_llm_client():
    client = AsyncMock(spec=LLMClient)
    client.provider = MagicMock()
    client.provider.value = "mock_provider"
    client.model = "mock_model"
    client.analyze_task_requirements = AsyncMock(return_value={
        'task_type': 'general',
        'required_capabilities': ['mock_capability'],
        'tools_needed': ['mock_tool_type'],
        'confidence': 0.9
    })
    client.generate_enhanced_reasoning = AsyncMock() # Will be configured per test
    client.check_task_completion = AsyncMock(return_value={'completed': False, 'reason': 'Default: Not completed'}) # Default to not completed
    client.generate_task_summary = AsyncMock(return_value="Mocked task summary.")
    client._call_api = AsyncMock(side_effect=lambda prompt: f"mock_response_for_{prompt[:20]}")
    return client

@pytest_asyncio.fixture
async def mock_toolscore_http_client():
    client = AsyncMock(spec=ToolScoreClient)
    client.wait_for_ready = AsyncMock(return_value=True)
    client.health_check = AsyncMock(return_value=True)
    client.get_available_tools = AsyncMock(return_value={"available_tools": []})
    client.analyze_tool_gap = AsyncMock(return_value={"has_sufficient_tools": True})
    client.request_tool_capability = AsyncMock()
    client.execute_tool = AsyncMock()
    client.search_and_install_tools = AsyncMock()
    client.analyze_tool_needs = AsyncMock()
    client.close = AsyncMock()
    return client

@pytest_asyncio.fixture
async def mock_real_time_tool_client():
    client = AsyncMock(spec=RealTimeToolClient)
    client.connect_real_time_updates = AsyncMock()
    client.register_tool_update_callback = AsyncMock()
    client.get_fresh_tools_for_llm = AsyncMock(return_value="No tools available.")
    client.register_pending_request = AsyncMock()
    client.cleanup_expired_requests = AsyncMock()
    client.close = AsyncMock()
    client._tool_update_callbacks = []
    
    async def mock_register_callback(callback):
        client._tool_update_callbacks.append(callback)
    client.register_tool_update_callback = mock_register_callback
    return client

@pytest_asyncio.fixture
async def mock_mcp_tool_client():
    client = AsyncMock(spec=MCPToolClient)
    client.execute_tool = AsyncMock()
    client.cleanup = AsyncMock()
    return client

@pytest_asyncio.fixture
async def runtime(mock_llm_client, mock_toolscore_http_client, mock_real_time_tool_client, mock_mcp_tool_client):
    with patch('runtimes.reasoning.enhanced_runtime.LLMClient', return_value=mock_llm_client), \
         patch('runtimes.reasoning.enhanced_runtime.ToolScoreClient', return_value=mock_toolscore_http_client), \
         patch('runtimes.reasoning.enhanced_runtime.RealTimeToolClient', return_value=mock_real_time_tool_client), \
         patch('runtimes.reasoning.enhanced_runtime.MCPToolClient', return_value=mock_mcp_tool_client), \
         patch('runtimes.reasoning.enhanced_runtime.EnhancedMetrics') as MockMetrics: # Mock metrics
        
        runtime_instance = EnhancedReasoningRuntime()
        runtime_instance.metrics = MockMetrics() # Assign mocked metrics
        await runtime_instance.initialize()
        runtime_instance._mock_llm_client = mock_llm_client
        runtime_instance._mock_toolscore_http_client = mock_toolscore_http_client
        runtime_instance._mock_real_time_tool_client = mock_real_time_tool_client
        runtime_instance._mock_mcp_tool_client = mock_mcp_tool_client
        yield runtime_instance
        await runtime_instance.cleanup()

@pytest.mark.asyncio
async def test_runtime_initialization(runtime: EnhancedReasoningRuntime):
    assert runtime.runtime_id.startswith("enhanced-reasoning-")
    runtime._mock_toolscore_http_client.wait_for_ready.assert_called_once()
    runtime._mock_real_time_tool_client.connect_real_time_updates.assert_called_once()
    assert len(runtime._mock_real_time_tool_client._tool_update_callbacks) > 0

@pytest.mark.asyncio
async def test_execute_simple_task_tool_available(runtime: EnhancedReasoningRuntime):
    task_desc = "Test task: use mock_tool to do something."
    task_spec = TaskSpec(task_id="test-task-1", description=task_desc, task_type="reasoning")

    mock_tool_description = """
    # 已注册的工具
    - mock_tool_id (Mock Tool): A tool for mocking. (能力: mock_capability) [function类型]
    """
    runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = mock_tool_description
    runtime._mock_toolscore_http_client.get_available_tools.return_value = {
        "available_tools": [{
            "tool_id": "mock_tool_id", "name": "Mock Tool", "description": "A tool for mocking.",
            "capabilities": [{"name": "mock_capability"}], "tool_type": "function"
        }]
    }
    runtime._mock_toolscore_http_client.analyze_tool_gap.return_value = {"has_sufficient_tools": True}

    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "I should use mock_tool.",
        "action": "mock_action",
        "tool_id": "mock_tool_id",
        "parameters": {"param1": "value1"}
    }
    runtime._mock_toolscore_http_client.execute_tool.return_value = {
        "success": True,
        "result": {"stdout": "Mock tool executed successfully."}
    }
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': True, 'reason': 'Tool executed'}

    trajectory = await runtime.execute(task_spec)

    assert trajectory.success is True
    assert "Mock tool executed successfully." in trajectory.steps[-1].observation
    runtime._mock_llm_client.analyze_task_requirements.assert_called_once_with(task_desc)
    runtime._mock_toolscore_http_client.analyze_tool_gap.assert_called_once()
    runtime._mock_llm_client.generate_enhanced_reasoning.assert_called_once()
    runtime._mock_toolscore_http_client.execute_tool.assert_called_once_with(
        tool_id="mock_tool_id", action="mock_action", parameters={"param1": "value1"}
    )
    runtime._mock_llm_client.check_task_completion.assert_called_once()
    assert "mock_tool_id" in trajectory.steps[0].action_params.get("tools_snapshot", "")

@pytest.mark.asyncio
async def test_execute_task_request_and_use_new_tool(runtime: EnhancedReasoningRuntime):
    task_desc = "Test task: need a new_tool for a new_capability."
    task_spec = TaskSpec(task_id="test-task-2", description=task_desc, task_type="reasoning")

    runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = "No tools available initially."
    runtime._mock_toolscore_http_client.get_available_tools.return_value = {"available_tools": []}
    
    runtime._mock_llm_client.analyze_task_requirements.return_value = {
        'task_type': 'special_ops', 'required_capabilities': ['new_capability'],
        'tools_needed': ['new_tool_type'], 'confidence': 0.95
    }
    runtime._mock_toolscore_http_client.analyze_tool_gap.return_value = {
        "has_sufficient_tools": False,
        "gap_analysis": {"missing_capabilities": ["new_capability"], "reasoning": "Capability not found"}
    }
    runtime._mock_toolscore_http_client.request_tool_capability.return_value = {
        "success": True,
        "installed_tools": [{"tool_id": "new_tool_id", "name": "New Tool", "capabilities": [{"name":"new_capability"}]}],
        "message": "New tool installed."
    }
    
    reasoning_call_count = 0
    async def mock_generate_reasoning_sequence(*args, **kwargs):
        nonlocal reasoning_call_count
        reasoning_call_count += 1
        tool_descriptions_arg = kwargs.get('tool_descriptions', "")
        if "new_tool_id" in tool_descriptions_arg: # Tool is now available
            return {
                "thinking": "New tool is available, I should use new_tool_id.", "action": "new_action",
                "tool_id": "new_tool_id", "parameters": {"p_new": "v_new"}
            }
        # This case should ideally not be hit if the tool arrival simulation is correct
        # and the LLM is called after the tool is "available" in the descriptions.
        # However, if the first call to reasoning happens *before* the tool description is updated,
        # it might return a "wait" or "search" action.
        # For this test, we assume the flow ensures the LLM sees the new tool.
        # If the test needs to model the LLM *itself* deciding to wait for a tool,
        # the logic here would need to be more complex, possibly returning a 'request_tool_capability'
        # or 'wait' action on the first call if the gap analysis didn't trigger the install.
        return {
            "thinking": "Initial reasoning, tool not yet in description.", "action": "analyze_tool_needs",
            "tool_id": "mcp-search-tool", "parameters": {"task_description": task_desc}
        }

    runtime._mock_llm_client.generate_enhanced_reasoning.side_effect = mock_generate_reasoning_sequence
    
    runtime._mock_toolscore_http_client.execute_tool.return_value = {
        "success": True, "result": {"stdout": "New tool executed successfully."}
    }
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': True, 'reason': 'New tool used'}

    async def execute_and_simulate_tool_arrival():
        execute_task = asyncio.create_task(runtime.execute(task_spec))
        await asyncio.sleep(0.1) # Time for gap analysis and request_tool_capability
        
        runtime._mock_toolscore_http_client.get_available_tools.return_value = {
             "available_tools": [{"tool_id": "new_tool_id", "name": "New Tool", "capabilities": [{"name":"new_capability"}]}]
        }
        new_tool_event_data = {
            "tool_id": "new_tool_id", "name": "New Tool", "description": "A newly installed tool.",
            "capabilities": [{"name": "new_capability"}], "tool_type": "function"
        }
        for callback in runtime._mock_real_time_tool_client._tool_update_callbacks:
            await callback(new_tool_event_data)

        # Crucially, update what get_fresh_tools_for_llm returns for the *next* LLM call
        runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = """
        # 已注册的工具
        # 实时安装的工具
        - new_tool_id (New Tool): A newly installed tool. (能力: new_capability) [function类型]
        """        
        trajectory = await execute_task
        return trajectory

    trajectory = await execute_and_simulate_tool_arrival()
    assert trajectory.success is True
    # 检查工具执行成功的消息 - 可能是中文或英文
    final_observation = trajectory.steps[-1].observation
    success_indicators = ["New tool executed successfully", "成功", "available during execution", "New Tool"]
    assert any(indicator in final_observation for indicator in success_indicators), f"最终观察: {final_observation}"
    
    runtime._mock_toolscore_http_client.request_tool_capability.assert_called_once_with(
        task_description=task_desc, required_capabilities=['new_capability'], auto_install=True
    )
    
    # Check that execute_tool was called for the new_tool_id
    execute_tool_called_for_new_tool = any(
        call_args[1].get('tool_id') == 'new_tool_id' 
        for call_args in runtime._mock_toolscore_http_client.execute_tool.call_args_list
    )
    assert execute_tool_called_for_new_tool, "execute_tool was not called with new_tool_id"
    assert reasoning_call_count > 0 # Ensure LLM reasoning was invoked

@pytest.mark.asyncio
async def test_tool_matches_requirement(runtime: EnhancedReasoningRuntime):
    tool_event_exact = {"capabilities": [{"name": "image_generation"}, {"name": "format_conversion"}]}
    tool_event_partial = {"capabilities": ["generate images", "convert formats"]}
    tool_event_case_insensitive = {"capabilities": [{"name": "Image_Generation"}]}
    tool_event_no_caps = {"capabilities": []}
    tool_event_str_caps = {"capabilities": ["image_generation", "file_processing"]}

    assert runtime._tool_matches_requirement(tool_event_exact, ["image_generation"]) is True
    assert runtime._tool_matches_requirement(tool_event_exact, ["Image_Generation"]) is True
    assert runtime._tool_matches_requirement(tool_event_exact, ["format_conversion"]) is True
    assert runtime._tool_matches_requirement(tool_event_exact, ["text_analysis"]) is False
    assert runtime._tool_matches_requirement(tool_event_partial, ["image"]) is True
    assert runtime._tool_matches_requirement(tool_event_partial, ["generate"]) is True
    assert runtime._tool_matches_requirement(tool_event_partial, ["convert"]) is True
    assert runtime._tool_matches_requirement(tool_event_case_insensitive, ["image_generation"]) is True
    assert runtime._tool_matches_requirement(tool_event_no_caps, ["any_capability"]) is False
    assert runtime._tool_matches_requirement(tool_event_no_caps, []) is True
    assert runtime._tool_matches_requirement(tool_event_str_caps, ["file_processing"]) is True
    assert runtime._tool_matches_requirement(tool_event_str_caps, ["File_Processing"]) is True

@pytest.mark.asyncio
async def test_execute_tool_fails_fallback_to_mcp_client_success(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-fallback", description="Test fallback", task_type="reasoning")
    runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = "- fallback_tool (Fallback Tool): For testing fallback."
    runtime._mock_toolscore_http_client.get_available_tools.return_value = {
        "available_tools": [{"tool_id": "fallback_tool", "name": "Fallback Tool"}]
    }
    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "Use fallback_tool.", "action": "do_fallback",
        "tool_id": "fallback_tool", "parameters": {}
    }
    # ToolScore API execution fails
    runtime._mock_toolscore_http_client.execute_tool.return_value = {"success": False, "message": "ToolScore API failed"}
    # MCP Client execution succeeds
    runtime._mock_mcp_tool_client.execute_tool.return_value = ExecutionResult(
        success=True, data={"result": "MCP fallback success"}, error_message=None
    )
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': True}

    trajectory = await runtime.execute(task_spec)
    assert trajectory.success is True
    assert "MCP fallback success" in trajectory.steps[-1].observation
    runtime._mock_toolscore_http_client.execute_tool.assert_called_once()
    runtime._mock_mcp_tool_client.execute_tool.assert_called_once_with(
        "fallback_tool", # Assuming _map_tool_id_to_server returns the same if not mapped
        "do_fallback",
        {}
    )

@pytest.mark.asyncio
async def test_llm_requests_tool_capability_directly(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-llm-req-cap", description="LLM requests capability", task_type="reasoning")
    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "I need a tool for 'super_ability'.",
        "action": "request_tool_capability", # LLM directly asks for this
        "tool_id": None, # or could be a generic tool_id like 'toolscore_manager'
        "parameters": {"task_description": "Need super_ability for my task", "required_capabilities": ["super_ability"]}
    }
    runtime._mock_toolscore_http_client.request_tool_capability.return_value = {
        "success": True, "installed_tools": [{"tool_id": "super_tool", "name": "SuperTool"}], "message": "SuperTool installed"
    }
    # Simulate that after this, LLM decides task is done or next step is different
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': True}


    # To make the test pass, we need to ensure the LLM doesn't loop indefinitely trying to request.
    # We'll mock generate_enhanced_reasoning to return a complete_task action after the first call.
    llm_call_count = 0
    async def mock_reasoning_for_cap_request(*args, **kwargs):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return {
                "thinking": "I need a tool for 'super_ability'.", "action": "request_tool_capability",
                "parameters": {"task_description": "Need super_ability for my task", "required_capabilities": ["super_ability"]}
            }
        # After requesting, assume LLM gets what it needs or moves on
        # For this test, let's say it completes.
        # We also need to simulate the tool appearing in the list for the next step if it were to use it.
        runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = "- super_tool (SuperTool): Does super things."
        return {
            "thinking": "Capability requested, now completing.", "action": "complete_task",
            "parameters": {"summary": "Task completed after capability request."}
        }
    runtime._mock_llm_client.generate_enhanced_reasoning.side_effect = mock_reasoning_for_cap_request


    trajectory = await runtime.execute(task_spec)
    assert trajectory.success is True
    runtime._mock_toolscore_http_client.request_tool_capability.assert_called_once_with(
        task_description="Need super_ability for my task",
        required_capabilities=["super_ability"],        auto_install=True
    )
    # 检查中文或英文的成功安装消息
    observation = trajectory.steps[1].observation
    assert ("SuperTool installed" in observation or 
            "SuperTool" in observation and "安装" in observation), f"实际输出: {observation}"
    # 检查任务成功完成
    assert trajectory.success is True
    # 由于final_result被mock为"Mocked task summary."，我们检查步骤而不是final_result
    assert len(trajectory.steps) >= 2  # 至少有工具暴露和工具请求两个步骤

@pytest.mark.asyncio
async def test_llm_uses_mcp_search_tool(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-mcp-search", description="LLM uses mcp-search-tool", task_type="reasoning")
    
    llm_call_count = 0
    async def mock_reasoning_for_search(*args, **kwargs):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return {
                "thinking": "I need to find a tool for 'image_editing'.",
                "action": "search_and_install_tools",
                "tool_id": "mcp-search-tool",  # 确保tool_id正确设置
                "parameters": {"task_description": "Edit an image", "reason": "Need to crop and resize"}
            }
        # After search, assume LLM gets what it needs or moves on
        runtime._mock_real_time_tool_client.get_fresh_tools_for_llm.return_value = "- image_editor_tool (ImageEditor): Edits images."
        return {
            "thinking": "Found image_editor_tool, now completing.", "action": "complete_task",
            "parameters": {"summary": "Task completed after mcp-search-tool."}
        }
    runtime._mock_llm_client.generate_enhanced_reasoning.side_effect = mock_reasoning_for_search

    runtime._mock_toolscore_http_client.search_and_install_tools.return_value = {
        "success": True, "installed_tools": [{"tool_id": "image_editor_tool", "name": "ImageEditor"}],
        "message": "ImageEditor tool installed via search."    }
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': True} # To ensure loop terminates
    
    trajectory = await runtime.execute(task_spec)
    
    assert trajectory.success is True
    runtime._mock_toolscore_http_client.search_and_install_tools.assert_called_once_with(
        task_description="Edit an image",
        reason="Need to crop and resize"
    )
    # 检查中文安装消息或英文消息
    step1_observation = trajectory.steps[1].observation
    assert ("ImageEditor tool installed via search." in step1_observation or 
            "ImageEditor" in step1_observation or "image_editor_tool" in step1_observation), f"实际输出: {step1_observation}"
    # 由于final_result被mock，我们只检查任务成功完成
    assert trajectory.success is True

@pytest.mark.asyncio
async def test_max_steps_reached(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-max-steps", description="Test max steps", task_type="reasoning")
    runtime.max_steps = 2 # Override for test

    # LLM keeps generating non-completing actions
    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "Still working...", "action": "some_action", "tool_id": "some_tool", "parameters": {}
    }
    runtime._mock_toolscore_http_client.execute_tool.return_value = {"success": True, "result": {"stdout": "Step executed"}}
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': False} # Never completes

    trajectory = await runtime.execute(task_spec)
    assert trajectory.success is False
    assert len(trajectory.steps) <= runtime.max_steps + 1 # +1 for initial tool exposure step
    assert trajectory.error_type == ErrorType.EXECUTION_FAILED
    assert "Task failed after 2 steps" in trajectory.error_message # or similar, depending on exact step count logic

@pytest.mark.asyncio
async def test_llm_completes_task_directly(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-direct-complete", description="LLM completes directly", task_type="reasoning")
    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "I have all the info.",
        "action": "complete_task",
        "tool_id": None,
        "parameters": {"summary": "All information gathered and processed."}
    }
    # check_task_completion might not even be called if complete_task action is taken first.
    # However, the current logic in execute() calls check_task_completion after each step *unless*
    # the action was 'complete_task' and it was successful.
    # The summary for complete_task action is generated by a separate LLM call.
    runtime._mock_llm_client.generate_task_summary.return_value = "Final summary from LLM for complete_task action."


    trajectory = await runtime.execute(task_spec)
    assert trajectory.success is True
    assert "Final summary from LLM for complete_task action." in trajectory.final_result
    assert trajectory.steps[-1].action_params.get("action") == "complete_task"
    runtime._mock_llm_client.generate_task_summary.assert_called()


@pytest.mark.asyncio
async def test_tool_execution_throws_exception(runtime: EnhancedReasoningRuntime):
    task_spec = TaskSpec(task_id="test-tool-exception", description="Tool throws exception", task_type="reasoning")
    runtime._mock_llm_client.generate_enhanced_reasoning.return_value = {
        "thinking": "Using risky_tool.", "action": "risky_op", "tool_id": "risky_tool", "parameters": {}
    }
    runtime._mock_toolscore_http_client.execute_tool.side_effect = Exception("Network Error during tool call")
    runtime._mock_llm_client.check_task_completion.return_value = {'completed': False} # Task doesn't complete due to error

    trajectory = await runtime.execute(task_spec)
    assert trajectory.success is False
    assert trajectory.steps[-1].success is False
    assert trajectory.steps[-1].error_type == ErrorType.TOOL_ERROR
    assert "Network Error during tool call" in trajectory.steps[-1].error_message
    assert "Network Error during tool call" in trajectory.error_message # or similar

@pytest.mark.asyncio
async def test_health_check_healthy(runtime: EnhancedReasoningRuntime):
    runtime._mock_llm_client.generate_reasoning = AsyncMock() # Used in health_check
    runtime._mock_toolscore_http_client.health_check.return_value = True
    
    is_healthy = await runtime.health_check()
    assert is_healthy is True
    runtime._mock_llm_client.generate_reasoning.assert_called_once_with("health check", [], [])
    runtime._mock_toolscore_http_client.health_check.assert_called_once()

@pytest.mark.asyncio
async def test_health_check_toolscore_unhealthy(runtime: EnhancedReasoningRuntime):
    runtime._mock_llm_client.generate_reasoning = AsyncMock()
    runtime._mock_toolscore_http_client.health_check.return_value = False
    
    is_healthy = await runtime.health_check()
    assert is_healthy is False

@pytest.mark.asyncio
async def test_health_check_llm_fails(runtime: EnhancedReasoningRuntime):
    runtime._mock_llm_client.generate_reasoning = AsyncMock(side_effect=Exception("LLM unavailable"))
    runtime._mock_toolscore_http_client.health_check.return_value = True # Toolscore is fine
    
    is_healthy = await runtime.health_check()
    assert is_healthy is False
