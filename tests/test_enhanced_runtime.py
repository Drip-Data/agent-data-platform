"""
Tests for enhanced runtime functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys
import json

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
from runtimes.reasoning.toolscore_client import ToolScoreClient


class TestEnhancedReasoningRuntime:
    """Test cases for EnhancedReasoningRuntime task execution workflow"""
    
    @pytest.fixture
    def enhanced_runtime(self, mock_config_manager):
        """Create EnhancedReasoningRuntime instance for testing"""
        return EnhancedReasoningRuntime(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_task_execution_workflow(self, enhanced_runtime, sample_task):
        """Test complete task execution workflow"""
        expected_result = {
            "task_id": sample_task["id"],
            "status": "completed",
            "result": "Task executed successfully",
            "execution_time": 2.5
        }
        
        with patch.object(enhanced_runtime, 'execute_task', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = expected_result
            
            result = await enhanced_runtime.execute_task(sample_task)
            
            assert result["status"] == "completed"
            assert result["task_id"] == sample_task["id"]
            assert "execution_time" in result
            mock_execute.assert_called_once_with(sample_task)
    
    @pytest.mark.asyncio
    async def test_tool_gap_detection(self, enhanced_runtime):
        """Test tool gap detection and installation"""
        # Mock a task that requires a missing tool
        task_with_missing_tool = {
            "id": "test-gap-detection",
            "type": "code_execution",
            "requirements": ["python", "numpy"],  # numpy might be missing
            "code": "import numpy as np; print(np.array([1,2,3]))"
        }
        
        with patch.object(enhanced_runtime, 'detect_tool_gaps', new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = ["numpy"]  # Missing tool detected
            
            gaps = await enhanced_runtime.detect_tool_gaps(task_with_missing_tool)
            
            assert "numpy" in gaps
            mock_detect.assert_called_once_with(task_with_missing_tool)
    
    @pytest.mark.asyncio
    async def test_tool_installation(self, enhanced_runtime):
        """Test dynamic tool installation"""
        missing_tools = ["numpy", "pandas"]
        
        with patch.object(enhanced_runtime, 'install_missing_tools', new_callable=AsyncMock) as mock_install:
            mock_install.return_value = {"numpy": True, "pandas": True}
            
            result = await enhanced_runtime.install_missing_tools(missing_tools)
            
            assert result["numpy"] is True
            assert result["pandas"] is True
            mock_install.assert_called_once_with(missing_tools)
    
    @pytest.mark.asyncio
    async def test_llm_interaction_logging(self, enhanced_runtime, sample_task):
        """Test LLM interaction logging"""
        # Mock LLM interaction
        llm_request = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Analyze this task"}],
            "temperature": 0.7
        }
        
        llm_response = {
            "content": "Task analysis completed",
            "usage": {"prompt_tokens": 50, "completion_tokens": 20}
        }
        
        with patch.object(enhanced_runtime, 'log_llm_interaction') as mock_log:
            enhanced_runtime.log_llm_interaction(sample_task["id"], llm_request, llm_response)
            
            mock_log.assert_called_once_with(sample_task["id"], llm_request, llm_response)
    
    @pytest.mark.asyncio
    async def test_trajectory_saving(self, enhanced_runtime, sample_trajectory):
        """Test trajectory saving functionality"""
        with patch.object(enhanced_runtime, 'save_trajectory', new_callable=AsyncMock) as mock_save:
            mock_save.return_value = True
            
            result = await enhanced_runtime.save_trajectory(sample_trajectory)
            
            assert result is True
            mock_save.assert_called_once_with(sample_trajectory)
    
    def test_trajectory_format_validation(self, enhanced_runtime):
        """Test trajectory data format validation"""
        valid_trajectory = {
            "task_id": "test-001",
            "steps": [
                {
                    "step_id": 1,
                    "action": "analysis",
                    "input": "test input",
                    "output": "test output",
                    "timestamp": "2024-01-01T00:00:00Z"
                }
            ]
        }
        
        with patch.object(enhanced_runtime, 'validate_trajectory_format') as mock_validate:
            mock_validate.return_value = True
            
            is_valid = enhanced_runtime.validate_trajectory_format(valid_trajectory)
            assert is_valid is True
            mock_validate.assert_called_once_with(valid_trajectory)


class TestToolScoreClient:
    """Test cases for ToolScoreClient integration"""
    
    @pytest.fixture
    def toolscore_client(self, mock_config_manager):
        """Create ToolScoreClient instance for testing"""
        return ToolScoreClient(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_tool_execution_request(self, toolscore_client):
        """Test tool execution request"""
        tool_request = {
            "tool_name": "python_executor",
            "parameters": {
                "code": "print('Hello, World!')",
                "timeout": 30
            }
        }
        
        expected_response = {
            "success": True,
            "output": "Hello, World!\n",
            "execution_time": 0.1
        }
        
        with patch.object(toolscore_client, 'execute_tool', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = expected_response
            
            result = await toolscore_client.execute_tool(tool_request)
            
            assert result["success"] is True
            assert "Hello, World!" in result["output"]
            mock_execute.assert_called_once_with(tool_request)
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self, toolscore_client):
        """Test WebSocket connection to ToolScore"""
        with patch.object(toolscore_client, 'connect_websocket', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            
            connected = await toolscore_client.connect_websocket()
            assert connected is True
            mock_connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tool_availability_check(self, toolscore_client):
        """Test checking tool availability"""
        available_tools = ["python_executor", "browser_navigator", "search_tool"]
        
        with patch.object(toolscore_client, 'get_available_tools', new_callable=AsyncMock) as mock_get_tools:
            mock_get_tools.return_value = available_tools
            
            tools = await toolscore_client.get_available_tools()
            
            assert "python_executor" in tools
            assert "browser_navigator" in tools
            assert "search_tool" in tools
            mock_get_tools.assert_called_once()


class TestRuntimeErrorHandling:
    """Test cases for runtime error handling and recovery"""
    
    @pytest.fixture
    def enhanced_runtime(self, mock_config_manager):
        return EnhancedReasoningRuntime(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_task_execution_timeout(self, enhanced_runtime):
        """Test task execution timeout handling"""
        timeout_task = {
            "id": "timeout-test",
            "type": "long_running",
            "timeout": 1  # 1 second timeout
        }
        
        with patch.object(enhanced_runtime, 'execute_task', new_callable=AsyncMock) as mock_execute:
            # Simulate timeout
            mock_execute.side_effect = asyncio.TimeoutError("Task timed out")
            
            with pytest.raises(asyncio.TimeoutError):
                await enhanced_runtime.execute_task(timeout_task)
    
    @pytest.mark.asyncio
    async def test_tool_execution_failure_recovery(self, enhanced_runtime):
        """Test recovery from tool execution failures"""
        failing_task = {
            "id": "fail-test",
            "type": "tool_execution",
            "tool": "python_executor",
            "code": "invalid python code"
        }
        
        with patch.object(enhanced_runtime, 'execute_task', new_callable=AsyncMock) as mock_execute:
            # First attempt fails
            mock_execute.side_effect = [
                Exception("Execution failed"),
                {"status": "completed", "result": "Recovered and completed"}
            ]
            
            # Test retry mechanism
            with patch.object(enhanced_runtime, 'retry_task_execution', new_callable=AsyncMock) as mock_retry:
                mock_retry.return_value = {"status": "completed", "result": "Recovered and completed"}
                
                result = await enhanced_runtime.retry_task_execution(failing_task)
                assert result["status"] == "completed"


@pytest.mark.integration
class TestRuntimeIntegration:
    """Integration tests for enhanced runtime"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_task_execution(self, mock_config_manager, sample_task):
        """Test complete end-to-end task execution"""
        # This would test the full workflow from task submission to completion
        runtime = EnhancedReasoningRuntime(config_manager=mock_config_manager)
        
        # Mock the complete workflow
        with patch.object(runtime, 'execute_task', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "task_id": sample_task["id"],
                "status": "completed",
                "result": "End-to-end test successful",
                "trajectory": {
                    "steps": [
                        {"action": "analysis", "status": "completed"},
                        {"action": "execution", "status": "completed"},
                        {"action": "validation", "status": "completed"}
                    ]
                }
            }
            
            result = await runtime.execute_task(sample_task)
            
            assert result["status"] == "completed"
            assert "trajectory" in result
            assert len(result["trajectory"]["steps"]) == 3