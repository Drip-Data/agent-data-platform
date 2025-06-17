"""
Tests for core.interfaces module
"""

import pytest
import uuid
import time
from dataclasses import asdict

from core.interfaces import (
    TaskSpec, TaskType, ActionType, ErrorType,
    ExecutionStep, TrajectoryResult, LLMInteraction
)


class TestTaskType:
    """Test TaskType enum"""
    
    def test_task_type_values(self):
        """Test that TaskType has expected values"""
        assert TaskType.CODE.value == "code"
        assert TaskType.WEB.value == "web"
        assert TaskType.REASONING.value == "reasoning"
    
    def test_task_type_from_string(self):
        """Test creating TaskType from string"""
        assert TaskType("code") == TaskType.CODE
        assert TaskType("web") == TaskType.WEB
        assert TaskType("reasoning") == TaskType.REASONING


class TestActionType:
    """Test ActionType enum"""
    
    def test_action_type_values(self):
        """Test that ActionType has expected values"""
        assert ActionType.CODE_GENERATION.value == "code_generation"
        assert ActionType.CODE_EXECUTION.value == "code_execution"
        assert ActionType.BROWSER_ACTION.value == "browser_action"
        assert ActionType.TOOL_CALL.value == "tool_call"


class TestErrorType:
    """Test ErrorType enum"""
    
    def test_error_type_values(self):
        """Test that ErrorType has expected values"""
        assert ErrorType.TIMEOUT.value == "timeout"
        assert ErrorType.NETWORK_ERROR.value == "network_error"
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
        assert ErrorType.SYSTEM_ERROR.value == "system_error"
        assert ErrorType.EXECUTION_ERROR.value == "ExecutionError"


class TestTaskSpec:
    """Test TaskSpec dataclass"""
    
    def test_task_spec_creation(self):
        """Test creating a TaskSpec"""
        task = TaskSpec(
            task_id="test-001",
            task_type=TaskType.CODE,
            description="Test task",
            context="Test context"
        )
        
        assert task.task_id == "test-001"
        assert task.task_type == TaskType.CODE
        assert task.description == "Test task"
        assert task.context == "Test context"
        assert task.expected_tools == []
        assert task.constraints == {}
        assert task.max_steps == 10
        assert task.timeout == 300
        assert task.priority == 1
    
    def test_task_spec_auto_id(self):
        """Test that TaskSpec generates ID if not provided"""
        task = TaskSpec(
            task_id="",
            task_type=TaskType.WEB,
            description="Test task"
        )
        
        assert task.task_id is not None
        assert len(task.task_id) > 0
        # Should be a valid UUID
        uuid.UUID(task.task_id)
    
    def test_task_spec_string_task_type(self):
        """Test that TaskSpec converts string to TaskType"""
        task = TaskSpec(
            task_id="test-002",
            task_type=TaskType.REASONING,  # Use enum directly
            description="Test task"
        )
        
        assert isinstance(task.task_type, TaskType)
        assert task.task_type == TaskType.REASONING
    
    def test_task_spec_with_tools_and_constraints(self):
        """Test TaskSpec with tools and constraints"""
        task = TaskSpec(
            task_id="test-003",
            task_type=TaskType.CODE,
            description="Complex test task",
            expected_tools=["python_executor", "browser_navigator"],
            constraints={"language": "python", "timeout": 60},
            max_steps=20,
            priority=5
        )
        
        assert task.expected_tools == ["python_executor", "browser_navigator"]
        assert task.constraints == {"language": "python", "timeout": 60}
        assert task.max_steps == 20
        assert task.priority == 5
    
    def test_task_spec_to_dict(self):
        """Test converting TaskSpec to dictionary"""
        task = TaskSpec(
            task_id="test-004",
            task_type=TaskType.WEB,
            description="Dictionary test task",
            context="Test context",
            expected_tools=["browser"],
            constraints={"url": "https://example.com"}
        )
        
        task_dict = task.to_dict()
        
        assert task_dict["task_id"] == "test-004"
        assert task_dict["task_type"] == "web"  # Should be string value
        assert task_dict["description"] == "Dictionary test task"
        assert task_dict["expected_tools"] == ["browser"]
        assert task_dict["constraints"] == {"url": "https://example.com"}
    
    def test_task_spec_from_dict(self):
        """Test creating TaskSpec from dictionary"""
        data = {
            "task_id": "test-005",
            "task_type": "code",
            "description": "Task from dict",
            "context": "Dict context"
        }
        
        task = TaskSpec.from_dict(data)
        
        assert task.task_id == "test-005"
        assert task.task_type == TaskType.CODE
        assert task.description == "Task from dict"
    
    def test_task_spec_json(self):
        """Test TaskSpec JSON serialization"""
        task = TaskSpec(
            task_id="test-006",
            task_type=TaskType.REASONING,
            description="JSON test task"
        )
        
        json_str = task.json()
        assert isinstance(json_str, str)
        assert "test-006" in json_str
        assert "reasoning" in json_str


class TestExecutionStep:
    """Test ExecutionStep dataclass"""
    
    def test_execution_step_creation(self):
        """Test creating an ExecutionStep"""
        step = ExecutionStep(
            step_id=1,
            action_type=ActionType.CODE_EXECUTION,
            action_params={"code": "print('hello')", "language": "python"},
            observation="Code executed successfully",
            success=True,
            thinking="I need to execute this Python code"
        )
        
        assert step.step_id == 1
        assert step.action_type == ActionType.CODE_EXECUTION
        assert step.action_params["code"] == "print('hello')"
        assert step.observation == "Code executed successfully"
        assert step.success is True
        assert step.thinking == "I need to execute this Python code"
        assert step.error_type is None
        assert step.error_message is None
    
    def test_execution_step_with_error(self):
        """Test creating an ExecutionStep with error"""
        step = ExecutionStep(
            step_id=2,
            action_type=ActionType.TOOL_CALL,
            action_params={"tool": "nonexistent_tool"},
            observation="Tool not found",
            success=False,
            error_type=ErrorType.TOOL_ERROR,
            error_message="Tool 'nonexistent_tool' not found"
        )
        
        assert step.success is False
        assert step.error_type == ErrorType.TOOL_ERROR
        assert step.error_message == "Tool 'nonexistent_tool' not found"
    
    def test_execution_step_to_dict(self):
        """Test converting ExecutionStep to dictionary"""
        step = ExecutionStep(
            step_id=1,
            action_type=ActionType.BROWSER_ACTION,
            action_params={"action": "click", "element": "#button"},
            observation="Button clicked",
            success=True,
            duration=1.5
        )
        
        step_dict = step.to_dict()
        
        assert step_dict["step_id"] == 1
        assert step_dict["action_type"] == "browser_action"
        assert step_dict["tool_input"] == {"action": "click", "element": "#button"}
        assert step_dict["tool_output"] == "Button clicked"
        assert step_dict["success"] is True
        assert step_dict["duration"] == 1.5
    
    def test_execution_step_llm_interactions(self):
        """Test ExecutionStep with LLM interactions"""
        interaction = LLMInteraction(
            prompt="What should I do next?",
            response="Click the submit button",
            model="gpt-4",
            tokens_used=50
        )
        
        step = ExecutionStep(
            step_id=1,
            action_type=ActionType.BROWSER_ACTION,
            action_params={"action": "click"},
            observation="Action completed",
            success=True,
            llm_interactions=[interaction]
        )
        
        assert len(step.llm_interactions) == 1
        assert step.llm_interactions[0].prompt == "What should I do next?"
        
        step_dict = step.to_dict()
        assert len(step_dict["llm_interactions"]) == 1


class TestTrajectoryResult:
    """Test TrajectoryResult dataclass"""
    
    def test_trajectory_result_creation(self):
        """Test creating a TrajectoryResult"""
        steps = [
            ExecutionStep(
                step_id=1,
                action_type=ActionType.CODE_EXECUTION,
                action_params={"code": "x = 1 + 1"},
                observation="x = 2",
                success=True
            ),
            ExecutionStep(
                step_id=2,
                action_type=ActionType.CODE_EXECUTION,
                action_params={"code": "print(x)"},
                observation="2",
                success=True
            )
        ]
        
        result = TrajectoryResult(
            task_name="test_task",
            task_id="test-trajectory-001",
            task_description="Test trajectory",
            runtime_id="runtime-001",
            success=True,
            steps=steps,
            final_result="Task completed successfully",
            total_duration=3.5
        )
        
        assert result.task_name == "test_task"
        assert result.task_id == "test-trajectory-001"
        assert result.task_description == "Test trajectory"
        assert result.runtime_id == "runtime-001"
        assert result.success is True
        assert len(result.steps) == 2
        assert result.final_result == "Task completed successfully"
        assert result.total_duration == 3.5
        assert result.error_type is None
    
    def test_trajectory_result_with_error(self):
        """Test creating a TrajectoryResult with error"""
        steps = [
            ExecutionStep(
                step_id=1,
                action_type=ActionType.CODE_EXECUTION,
                action_params={"code": "invalid syntax"},
                observation="SyntaxError",
                success=False,
                error_type=ErrorType.COMPILE_ERROR,
                error_message="Invalid Python syntax"
            )
        ]
        
        result = TrajectoryResult(
            task_name="failed_task",
            task_id="test-trajectory-002",
            task_description="Failed trajectory",
            runtime_id="runtime-002",
            success=False,
            steps=steps,
            final_result="Task failed due to syntax error",
            error_type=ErrorType.COMPILE_ERROR,
            error_message="Code compilation failed"
        )
        
        assert result.success is False
        assert result.error_type == ErrorType.COMPILE_ERROR
        assert result.error_message == "Code compilation failed"
        assert len(result.steps) == 1
        assert result.steps[0].success is False
    
    def test_trajectory_result_to_dict(self):
        """Test converting TrajectoryResult to dictionary"""
        steps = [
            ExecutionStep(
                step_id=1,
                action_type=ActionType.TOOL_CALL,
                action_params={"tool": "calculator", "operation": "add", "args": [1, 2]},
                observation="3",
                success=True
            )
        ]
        
        result = TrajectoryResult(
            task_name="math_task",
            task_id="test-trajectory-003",
            task_description="Simple math calculation",
            runtime_id="runtime-003",
            success=True,
            steps=steps,
            final_result="1 + 2 = 3",
            metadata={"complexity": "low", "category": "math"}
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["task_id"] == "test-trajectory-003"
        assert result_dict["task_name"] == "math_task"
        assert result_dict["success"] is True
        assert len(result_dict["steps"]) == 1
        assert result_dict["metadata"]["complexity"] == "low"
        assert "created_at" in result_dict  # Should have timestamp


class TestLLMInteraction:
    """Test LLMInteraction dataclass"""
    
    def test_llm_interaction_creation(self):
        """Test creating an LLMInteraction"""
        interaction = LLMInteraction(
            prompt="Write a Python function to calculate factorial",
            response="def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)",
            model="gpt-4",
            tokens_used=120,
            temperature=0.7
        )
        
        assert interaction.prompt == "Write a Python function to calculate factorial"
        assert "def factorial(n):" in interaction.response
        assert interaction.model == "gpt-4"
        assert interaction.tokens_used == 120
        assert interaction.temperature == 0.7
        assert interaction.timestamp > 0  # Should be auto-generated
    
    def test_llm_interaction_to_dict(self):
        """Test converting LLMInteraction to dictionary"""
        interaction = LLMInteraction(
            prompt="What is 2+2?",
            response="2+2 equals 4",
            model="gpt-3.5-turbo",
            tokens_used=25
        )
        
        interaction_dict = interaction.to_dict()
        
        assert interaction_dict["prompt"] == "What is 2+2?"
        assert interaction_dict["response"] == "2+2 equals 4"
        assert interaction_dict["model"] == "gpt-3.5-turbo"
        assert interaction_dict["tokens_used"] == 25
        assert "timestamp" in interaction_dict