"""
Tests for synthesis services (core.synthesiscore)
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from core.synthesiscore.synthesis import SynthesisService
from core.interfaces import TaskSpec, TaskType, TrajectoryResult, ExecutionStep, ActionType


class TestSynthesisService:
    """Test SynthesisService class"""
    
    @pytest.fixture
    def synthesis_service(self, mock_config_manager):
        """Create SynthesisService instance for testing"""
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True,
            "auto_monitor_trajectories": True,
            "auto_export_seeds": True
        }
        with patch('core.synthesiscore.synthesis.async_redis'), \
             patch('core.synthesiscore.synthesis.LLMClient'), \
             patch('core.synthesiscore.synthesis.UnifiedToolLibrary'):
            return SynthesisService(config)
    
    @pytest.mark.asyncio
    async def test_initialization(self, synthesis_service):
        """Test SynthesisService initialization"""
        assert synthesis_service is not None
        assert hasattr(synthesis_service, 'config')
        assert hasattr(synthesis_service, 'llm_client')
        assert hasattr(synthesis_service, 'enabled')
    
    @pytest.mark.asyncio
    async def test_should_process_trajectory_success(self, synthesis_service):
        """Test processing successful trajectories"""
        trajectory = TrajectoryResult(
            task_name="test_task",
            task_id="test-001",
            task_description="Test successful task",
            runtime_id="runtime-001",
            success=True,
            steps=[
                ExecutionStep(
                    step_id=1,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "print('hello')"},
                    observation="hello",
                    success=True
                )
            ],
            final_result="Task completed successfully"
        )
        
        should_process = synthesis_service._should_process_trajectory(trajectory)
        assert should_process is True
    
    @pytest.mark.asyncio
    async def test_should_process_trajectory_reasoning(self, synthesis_service):
        """Test processing reasoning trajectories"""
        trajectory = TrajectoryResult(
            task_name="reasoning_task",
            task_id="reasoning-001",
            task_description="Complex reasoning task",
            runtime_id="reasoning-runtime-001",
            success=False,  # Even failed reasoning tasks are valuable
            steps=[
                ExecutionStep(
                    step_id=1,
                    action_type=ActionType.BROWSER_ACTION,
                    action_params={"action": "navigate", "url": "https://example.com"},
                    observation="Page loaded",
                    success=True
                ),
                ExecutionStep(
                    step_id=2,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "analyze_data()"},
                    observation="Analysis failed",
                    success=False
                )
            ],
            final_result="Task failed but has valuable patterns"
        )
        
        should_process = synthesis_service._should_process_trajectory(trajectory)
        assert should_process is True
    
    @pytest.mark.asyncio
    async def test_convert_trajectory_format(self, synthesis_service):
        """Test trajectory format conversion"""
        trajectory_data = {
            "task_id": "test-001",
            "task_name": "test_task",
            "task_description": "Test task description",
            "runtime_id": "runtime-001",
            "success": True,
            "final_result": "Success",
            "total_duration": 2.5,
            "steps": [
                {
                    "step_id": 1,
                    "action_type": "code_execution",
                    "action_params": {"code": "print('hello')"},
                    "observation": "hello",
                    "success": True,
                    "duration": 1.0
                }
            ]
        }
        
        converted = synthesis_service._convert_trajectory_format(trajectory_data)
        
        assert converted is not None
        assert converted.task_id == "test-001"
        assert converted.success is True
        assert len(converted.steps) == 1
        assert converted.steps[0].observation == "hello"
    
    @pytest.mark.asyncio
    async def test_extract_tools_from_trajectory(self, synthesis_service):
        """Test tool extraction from trajectory"""
        trajectory = TrajectoryResult(
            task_name="multi_tool_task",
            task_id="multi-001",
            task_description="Task using multiple tools",
            runtime_id="runtime-001",
            success=True,
            steps=[
                ExecutionStep(
                    step_id=1,
                    action_type=ActionType.BROWSER_ACTION,
                    action_params={"action": "navigate", "url": "https://example.com"},
                    observation="Page loaded",
                    success=True
                ),
                ExecutionStep(
                    step_id=2,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "process_data()"},
                    observation="Data processed",
                    success=True
                )
            ],
            final_result="Task completed"
        )
        
        tools = synthesis_service._extract_tools_from_trajectory(trajectory)
        
        assert "browser_navigator" in tools
        assert "python_executor" in tools
    
    @pytest.mark.asyncio
    async def test_infer_task_type_from_runtime(self, synthesis_service):
        """Test task type inference from runtime ID"""
        # Test reasoning runtime
        trajectory = TrajectoryResult(
            task_name="test",
            task_id="test-001", 
            task_description="Test task",
            runtime_id="reasoning-runtime-001",
            success=True,
            steps=[],
            final_result=""
        )
        
        task_type = synthesis_service._infer_task_type(trajectory, "")
        assert task_type == "reasoning"
        
        # Test web runtime
        trajectory.runtime_id = "web-runtime-001"
        task_type = synthesis_service._infer_task_type(trajectory, "")
        assert task_type == "web"
        
        # Test code runtime
        trajectory.runtime_id = "sandbox-runtime-001"
        task_type = synthesis_service._infer_task_type(trajectory, "")
        assert task_type == "code"
    
    @pytest.mark.asyncio
    async def test_infer_task_type_from_description(self, synthesis_service):
        """Test task type inference from description"""
        trajectory = TrajectoryResult(
            task_name="test",
            task_id="test-001",
            task_description="Compare and analyze the performance differences between algorithms",
            runtime_id="unknown-runtime",
            success=True,
            steps=[],
            final_result=""
        )
        
        task_type = synthesis_service._infer_task_type(trajectory, "")
        assert task_type == "reasoning"
    
    @pytest.mark.asyncio
    async def test_infer_domain(self, synthesis_service):
        """Test domain inference"""
        trajectory = TrajectoryResult(
            task_name="test",
            task_id="test-001",
            task_description="Implement a sorting algorithm with performance analysis",
            runtime_id="runtime-001",
            success=True,
            steps=[],
            final_result=""
        )
        
        domain = synthesis_service._infer_domain(trajectory, "general", "code")
        assert domain == "algorithm"
    
    @pytest.mark.asyncio
    async def test_mark_and_check_processed_trajectory(self, synthesis_service):
        """Test trajectory processing tracking"""
        trajectory_id = "test-trajectory-001"
        
        # Initially not processed
        assert synthesis_service._is_trajectory_processed(trajectory_id) is False
        
        # Mark as processed
        synthesis_service._mark_trajectory_processed(trajectory_id)
        
        # Should now be processed
        assert synthesis_service._is_trajectory_processed(trajectory_id) is True
    
    @pytest.mark.asyncio
    async def test_file_operations(self, synthesis_service):
        """Test JSON file operations"""
        test_data = {"test": "data", "number": 123}
        test_file = "/tmp/test_synthesis.json"
        
        # Test save
        result = synthesis_service._save_json_file(test_file, test_data)
        assert result is True
        
        # Test load
        loaded_data = synthesis_service._load_json_file(test_file)
        assert loaded_data == test_data
        
        # Clean up
        import os
        if os.path.exists(test_file):
            os.remove(test_file)
    
    @pytest.mark.asyncio
    async def test_infer_expected_tools_async(self, synthesis_service):
        """Test expected tools inference"""
        with patch.object(synthesis_service.tool_library, 'get_all_tools', new_callable=AsyncMock) as mock_get_tools:
            mock_tool1 = MagicMock()
            mock_tool1.tool_id = "python_executor"
            mock_tool1.description = "Execute Python code"
            mock_tool1.name = "Python Executor"
            mock_tool1.tags = ["python", "code"]
            
            mock_tool2 = MagicMock()
            mock_tool2.tool_id = "browser_navigator"
            mock_tool2.description = "Navigate web pages"
            mock_tool2.name = "Browser Navigator"
            mock_tool2.tags = ["web", "browser"]
            
            mock_get_tools.return_value = [mock_tool1, mock_tool2]
            
            # Test code task
            tools = await synthesis_service._infer_expected_tools("code", "algorithm")
            assert "python_executor" in tools
            
            # Test web task
            tools = await synthesis_service._infer_expected_tools("web", "web_automation")
            assert "browser_navigator" in tools
    
    @pytest.mark.asyncio
    async def test_infer_max_steps(self, synthesis_service):
        """Test max steps inference"""
        # Simple task
        steps = synthesis_service._infer_max_steps("simple", "code")
        assert steps == 5
        
        # Complex reasoning task
        steps = synthesis_service._infer_max_steps("complex", "reasoning")
        assert steps == 20  # 15 + 5 for reasoning, capped at 20
        
        # Medium web task
        steps = synthesis_service._infer_max_steps("medium", "web")
        assert steps == 10
    
    @pytest.mark.asyncio
    async def test_create_fallback_essence(self, synthesis_service):
        """Test fallback essence creation"""
        trajectory = TrajectoryResult(
            task_name="fallback_test",
            task_id="fallback-001",
            task_description="Test fallback essence creation",
            runtime_id="code-runtime-001",
            success=True,
            steps=[],
            final_result="Success",
            total_duration=1.5
        )
        
        essence = synthesis_service._create_fallback_essence(trajectory)
        
        assert essence is not None
        assert essence.task_type == "code"
        assert essence.query == "Test fallback essence"  # First 20 chars
        assert essence.complexity_level == "medium"
        assert essence.source_trajectory_id == "fallback-001"
    
    @pytest.mark.asyncio
    async def test_build_extraction_prompt(self, synthesis_service):
        """Test extraction prompt building"""
        trajectory = TrajectoryResult(
            task_name="prompt_test",
            task_id="prompt-001",
            task_description="Test prompt building",
            runtime_id="reasoning-runtime-001",
            success=True,
            steps=[
                ExecutionStep(
                    step_id=1,
                    action_type=ActionType.CODE_EXECUTION,
                    action_params={"code": "test_code()"},
                    observation="Code executed",
                    success=True,
                    thinking="I need to run this code",
                    duration=1.0
                )
            ],
            final_result="Success",
            total_duration=2.0
        )
        
        prompt = synthesis_service._build_extraction_prompt(trajectory)
        
        assert "reasoning" in prompt.lower()
        assert "prompt-001" in prompt
        assert "test_code()" in prompt
        assert "Code executed" in prompt
        assert "JSON" in prompt
    
    @pytest.mark.asyncio
    async def test_safe_parse_error_type(self, synthesis_service):
        """Test safe error type parsing"""
        from core.interfaces import ErrorType
        
        # Test with None
        result = synthesis_service._safe_parse_error_type(None)
        assert result is None
        
        # Test with ErrorType instance
        result = synthesis_service._safe_parse_error_type(ErrorType.SYSTEM_ERROR)
        assert result == ErrorType.SYSTEM_ERROR
        
        # Test with string
        result = synthesis_service._safe_parse_error_type("timeout")
        assert result == ErrorType.TIMEOUT
        
        # Test with invalid string
        result = synthesis_service._safe_parse_error_type("invalid_error_type")
        assert result is None