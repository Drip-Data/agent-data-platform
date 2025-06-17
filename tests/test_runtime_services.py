"""
Tests for runtime services and enhanced runtime
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime

from runtimes.reasoning.enhanced_runtime import EnhancedRuntime
from runtimes.reasoning.real_time_tool_client import RealTimeToolClient
from core.interfaces import TaskSpec, TaskType, ExecutionStep, ActionType
from services.runtime_service import RuntimeService


class TestEnhancedRuntime:
    """Test EnhancedRuntime class"""
    
    @pytest.fixture
    def enhanced_runtime(self, mock_config_manager):
        """Create EnhancedRuntime instance for testing"""
        with patch('runtimes.reasoning.enhanced_runtime.RealTimeToolClient'):
            return EnhancedRuntime(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, enhanced_runtime):
        """Test EnhancedRuntime initialization"""
        assert enhanced_runtime is not None
        assert hasattr(enhanced_runtime, 'config_manager')
        assert hasattr(enhanced_runtime, 'tool_client')
        assert hasattr(enhanced_runtime, 'llm_client')
    
    @pytest.mark.asyncio
    async def test_start_runtime(self, enhanced_runtime):
        """Test starting the runtime"""
        with patch.object(enhanced_runtime.tool_client, 'connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            
            result = await enhanced_runtime.start()
            
            assert result is True
            mock_connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_runtime(self, enhanced_runtime):
        """Test stopping the runtime"""
        with patch.object(enhanced_runtime.tool_client, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
            mock_disconnect.return_value = True
            
            result = await enhanced_runtime.stop()
            
            assert result is True
            mock_disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_task_success(self, enhanced_runtime, sample_task):
        """Test successful task execution"""
        with patch.object(enhanced_runtime, '_plan_execution', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = [
                {"action": "code_execution", "params": {"code": "print('hello')"}}
            ]
            
            with patch.object(enhanced_runtime, '_execute_step', new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = ExecutionStep(
                    step_id=1,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "print('hello')"},
                    observation="hello",
                    success=True
                )
                
                result = await enhanced_runtime.execute_task(sample_task)
                
                assert result.success is True
                assert len(result.steps) == 1
                assert result.steps[0].observation == "hello"
                mock_plan.assert_called_once()
                mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_task_failure(self, enhanced_runtime, sample_task):
        """Test task execution with failure"""
        with patch.object(enhanced_runtime, '_plan_execution', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = [
                {"action": "code_execution", "params": {"code": "invalid_code"}}
            ]
            
            with patch.object(enhanced_runtime, '_execute_step', new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = ExecutionStep(
                    step_id=1,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "invalid_code"},
                    observation="SyntaxError: invalid syntax",
                    success=False,
                    error_message="Syntax error in code"
                )
                
                result = await enhanced_runtime.execute_task(sample_task)
                
                assert result.success is False
                assert len(result.steps) == 1
                assert "SyntaxError" in result.steps[0].observation
    
    @pytest.mark.asyncio
    async def test_plan_execution(self, enhanced_runtime, sample_task):
        """Test execution planning"""
        with patch.object(enhanced_runtime.llm_client, 'analyze_task', new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {
                "analysis": "This is a code generation task",
                "required_tools": ["python_executor"],
                "estimated_steps": 2,
                "approach": "Generate and execute Python code"
            }
            
            with patch.object(enhanced_runtime.llm_client, 'extract_actions', new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = [
                    {
                        "action_type": "code_generation",
                        "description": "Generate Python code",
                        "parameters": {"language": "python", "task": "fibonacci"}
                    },
                    {
                        "action_type": "code_execution", 
                        "description": "Execute the generated code",
                        "parameters": {"code": "def fibonacci(n): ..."}
                    }
                ]
                
                plan = await enhanced_runtime._plan_execution(sample_task)
                
                assert len(plan) == 2
                assert plan[0]["action_type"] == "code_generation"
                assert plan[1]["action_type"] == "code_execution"
                mock_analyze.assert_called_once()
                mock_extract.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_step_code_execution(self, enhanced_runtime):
        """Test executing a code execution step"""
        step_plan = {
            "action_type": "code_execution",
            "parameters": {"code": "print('test')", "language": "python"}
        }
        
        with patch.object(enhanced_runtime.tool_client, 'execute_tool', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "result": "test\n",
                "error": None
            }
            
            step = await enhanced_runtime._execute_step(step_plan, 1)
            
            assert step.step_id == 1
            assert step.action_type == ActionType.CODE_EXECUTION
            assert step.success is True
            assert step.observation == "test\n"
            mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_step_browser_action(self, enhanced_runtime):
        """Test executing a browser action step"""
        step_plan = {
            "action_type": "browser_action",
            "parameters": {"action": "navigate", "url": "https://example.com"}
        }
        
        with patch.object(enhanced_runtime.tool_client, 'execute_tool', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "result": "Navigation successful",
                "error": None
            }
            
            step = await enhanced_runtime._execute_step(step_plan, 1)
            
            assert step.action_type == ActionType.BROWSER_ACTION
            assert step.success is True
            assert step.observation == "Navigation successful"
    
    @pytest.mark.asyncio
    async def test_execute_step_with_error(self, enhanced_runtime):
        """Test executing a step that fails"""
        step_plan = {
            "action_type": "tool_call",
            "parameters": {"tool": "nonexistent_tool"}
        }
        
        with patch.object(enhanced_runtime.tool_client, 'execute_tool', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": False,
                "result": None,
                "error": "Tool not found"
            }
            
            step = await enhanced_runtime._execute_step(step_plan, 1)
            
            assert step.success is False
            assert step.error_message == "Tool not found"
    
    @pytest.mark.asyncio
    async def test_adaptive_execution(self, enhanced_runtime, sample_task):
        """Test adaptive execution with step modification"""
        initial_plan = [
            {"action_type": "code_execution", "parameters": {"code": "failing_code"}}
        ]
        
        with patch.object(enhanced_runtime, '_plan_execution', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = initial_plan
            
            with patch.object(enhanced_runtime, '_execute_step', new_callable=AsyncMock) as mock_execute:
                # First execution fails
                mock_execute.side_effect = [
                    ExecutionStep(
                        step_id=1,
                        action_type=ActionType.CODE_EXECUTION,
                        action_params={"code": "failing_code"},
                        observation="Error occurred",
                        success=False,
                        error_message="Execution failed"
                    ),
                    # Second execution succeeds after adaptation
                    ExecutionStep(
                        step_id=2,
                        action_type=ActionType.CODE_EXECUTION,
                        action_params={"code": "fixed_code"},
                        observation="Success",
                        success=True
                    )
                ]
                
                with patch.object(enhanced_runtime, '_adapt_plan', new_callable=AsyncMock) as mock_adapt:
                    mock_adapt.return_value = [
                        {"action_type": "code_execution", "parameters": {"code": "fixed_code"}}
                    ]
                    
                    result = await enhanced_runtime.execute_task(sample_task)
                    
                    assert len(result.steps) == 2
                    assert result.steps[0].success is False
                    assert result.steps[1].success is True
                    mock_adapt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, enhanced_runtime):
        """Test handling of task timeouts"""
        timeout_task = TaskSpec(
            task_id="timeout-test",
            task_type=TaskType.CODE,
            description="Task that will timeout",
            timeout=1  # 1 second timeout
        )
        
        with patch.object(enhanced_runtime, '_plan_execution', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = [{"action": "long_running_task"}]
            
            with patch.object(enhanced_runtime, '_execute_step', new_callable=AsyncMock) as mock_execute:
                # Simulate long-running step
                async def long_running_step(*args, **kwargs):
                    await asyncio.sleep(2)  # Longer than timeout
                    return ExecutionStep(step_id=1, action_type=ActionType.TOOL_CALL, 
                                       action_params={}, observation="", success=True)
                
                mock_execute.side_effect = long_running_step
                
                result = await enhanced_runtime.execute_task(timeout_task)
                
                assert result.success is False
                assert "timeout" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_health_check(self, enhanced_runtime):
        """Test runtime health check"""
        with patch.object(enhanced_runtime.tool_client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {"status": "healthy", "connected_tools": 3}
            
            health = await enhanced_runtime.health_check()
            
            assert health["status"] == "healthy"
            assert "connected_tools" in health
            assert "runtime_id" in health
            mock_health.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, enhanced_runtime):
        """Test getting runtime metrics"""
        metrics = await enhanced_runtime.get_metrics()
        
        assert "tasks_executed" in metrics
        assert "success_rate" in metrics
        assert "average_execution_time" in metrics
        assert "active_connections" in metrics


class TestRealTimeToolClient:
    """Test RealTimeToolClient class"""
    
    @pytest.fixture
    def tool_client(self, mock_config_manager):
        """Create RealTimeToolClient instance for testing"""
        return RealTimeToolClient(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, tool_client):
        """Test RealTimeToolClient initialization"""
        assert tool_client is not None
        assert hasattr(tool_client, 'config_manager')
        assert hasattr(tool_client, 'connected_tools')
    
    @pytest.mark.asyncio
    async def test_connect_to_tools(self, tool_client):
        """Test connecting to tools"""
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            result = await tool_client.connect()
            
            assert result is True
            assert len(tool_client.connected_tools) >= 0
    
    @pytest.mark.asyncio
    async def test_execute_tool_success(self, tool_client):
        """Test successful tool execution"""
        mock_ws = AsyncMock()
        tool_client.connected_tools = {"python_executor": mock_ws}
        
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value='{"success": true, "result": "executed successfully"}')
        
        result = await tool_client.execute_tool("python_executor", "execute", {"code": "print('hello')"})
        
        assert result["success"] is True
        assert result["result"] == "executed successfully"
        mock_ws.send.assert_called_once()
        mock_ws.recv.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_tool_not_connected(self, tool_client):
        """Test executing tool when not connected"""
        result = await tool_client.execute_tool("nonexistent_tool", "execute", {})
        
        assert result["success"] is False
        assert "not connected" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_execute_tool_error(self, tool_client):
        """Test tool execution with error"""
        mock_ws = AsyncMock()
        tool_client.connected_tools = {"python_executor": mock_ws}
        
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value='{"success": false, "error": "Execution failed"}')
        
        result = await tool_client.execute_tool("python_executor", "execute", {"code": "invalid_code"})
        
        assert result["success"] is False
        assert result["error"] == "Execution failed"
    
    @pytest.mark.asyncio
    async def test_get_available_tools(self, tool_client):
        """Test getting available tools"""
        mock_ws = AsyncMock()
        tool_client.connected_tools = {"python_executor": mock_ws, "browser_navigator": mock_ws}
        
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value='{"tools": ["execute", "analyze"]}')
        
        tools = await tool_client.get_available_tools()
        
        assert len(tools) >= 2
        assert "python_executor" in tools
        assert "browser_navigator" in tools
    
    @pytest.mark.asyncio
    async def test_disconnect(self, tool_client):
        """Test disconnecting from tools"""
        mock_ws = AsyncMock()
        tool_client.connected_tools = {"tool1": mock_ws, "tool2": mock_ws}
        
        mock_ws.close = AsyncMock()
        
        result = await tool_client.disconnect()
        
        assert result is True
        assert len(tool_client.connected_tools) == 0
        assert mock_ws.close.call_count == 2
    
    @pytest.mark.asyncio
    async def test_health_check(self, tool_client):
        """Test tool client health check"""
        mock_ws = AsyncMock()
        tool_client.connected_tools = {"tool1": mock_ws}
        
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value='{"status": "healthy"}')
        
        health = await tool_client.health_check()
        
        assert health["connected_tools"] == 1
        assert "tool_statuses" in health


class TestRuntimeService:
    """Test RuntimeService class"""
    
    @pytest.fixture
    def runtime_service(self, mock_config_manager):
        """Create RuntimeService instance for testing"""
        with patch('services.runtime_service.EnhancedRuntime'):
            return RuntimeService(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, runtime_service):
        """Test RuntimeService initialization"""
        assert runtime_service is not None
        assert hasattr(runtime_service, 'config_manager')
        assert hasattr(runtime_service, 'runtimes')
    
    @pytest.mark.asyncio
    async def test_start_service(self, runtime_service):
        """Test starting the runtime service"""
        with patch.object(runtime_service, '_initialize_runtimes', new_callable=AsyncMock) as mock_init:
            mock_init.return_value = True
            
            result = await runtime_service.start()
            
            assert result is True
            mock_init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_service(self, runtime_service):
        """Test stopping the runtime service"""
        with patch.object(runtime_service, '_shutdown_runtimes', new_callable=AsyncMock) as mock_shutdown:
            mock_shutdown.return_value = True
            
            result = await runtime_service.stop()
            
            assert result is True
            mock_shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_task(self, runtime_service, sample_task):
        """Test submitting a task to runtime"""
        mock_runtime = AsyncMock()
        runtime_service.runtimes = {"code_runtime": mock_runtime}
        
        mock_runtime.execute_task.return_value = MagicMock(success=True, task_id=sample_task.task_id)
        
        result = await runtime_service.submit_task(sample_task)
        
        assert result.success is True
        assert result.task_id == sample_task.task_id
        mock_runtime.execute_task.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_task_no_runtime(self, runtime_service, sample_task):
        """Test submitting task when no runtime available"""
        runtime_service.runtimes = {}
        
        result = await runtime_service.submit_task(sample_task)
        
        assert result.success is False
        assert "no runtime available" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_get_runtime_status(self, runtime_service):
        """Test getting runtime status"""
        mock_runtime = AsyncMock()
        runtime_service.runtimes = {"test_runtime": mock_runtime}
        
        mock_runtime.health_check.return_value = {"status": "healthy", "tasks_running": 2}
        
        status = await runtime_service.get_runtime_status("test_runtime")
        
        assert status["status"] == "healthy"
        assert status["tasks_running"] == 2
        mock_runtime.health_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_all_runtimes_status(self, runtime_service):
        """Test getting status of all runtimes"""
        mock_runtime1 = AsyncMock()
        mock_runtime2 = AsyncMock()
        runtime_service.runtimes = {"runtime1": mock_runtime1, "runtime2": mock_runtime2}
        
        mock_runtime1.health_check.return_value = {"status": "healthy"}
        mock_runtime2.health_check.return_value = {"status": "healthy"}
        
        statuses = await runtime_service.get_all_runtimes_status()
        
        assert len(statuses) == 2
        assert "runtime1" in statuses
        assert "runtime2" in statuses
        assert statuses["runtime1"]["status"] == "healthy"
        assert statuses["runtime2"]["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_scale_runtime(self, runtime_service):
        """Test scaling runtime instances"""
        with patch.object(runtime_service, '_create_runtime_instance', new_callable=AsyncMock) as mock_create:
            mock_runtime = AsyncMock()
            mock_create.return_value = mock_runtime
            
            result = await runtime_service.scale_runtime("code_runtime", 2)
            
            assert result is True
            assert mock_create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_get_service_metrics(self, runtime_service):
        """Test getting service metrics"""
        mock_runtime = AsyncMock()
        runtime_service.runtimes = {"test_runtime": mock_runtime}
        
        mock_runtime.get_metrics.return_value = {
            "tasks_executed": 10,
            "success_rate": 0.9,
            "average_execution_time": 2.5
        }
        
        metrics = await runtime_service.get_service_metrics()
        
        assert "total_runtimes" in metrics
        assert "total_tasks_executed" in metrics
        assert "overall_success_rate" in metrics
        assert metrics["total_runtimes"] == 1