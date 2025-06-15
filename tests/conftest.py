"""pytest 配置文件
提供全局 fixtures 和测试配置
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置测试环境变量
os.environ["TESTING"] = "1"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use test database


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test"""
    original_env = os.environ.copy()
    yield
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace directory for tests"""
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    
    # Create standard directories
    (workspace / "output").mkdir()
    (workspace / "output" / "trajectories").mkdir()
    (workspace / "logs").mkdir()
    (workspace / "config").mkdir()
    (workspace / "data").mkdir()
    
    return workspace


@pytest_asyncio.fixture
async def mock_redis():
    """Provide a mock Redis client for tests"""
    from unittest.mock import AsyncMock
    
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.rpop = AsyncMock(return_value=None)
    redis_mock.xadd = AsyncMock(return_value="1234567890")
    redis_mock.xread = AsyncMock(return_value=[])
    redis_mock.xlen = AsyncMock(return_value=0)
    redis_mock.publish = AsyncMock(return_value=1)
    redis_mock.aclose = AsyncMock()
    
    yield redis_mock


@pytest.fixture
def mock_llm_response():
    """Provide mock LLM responses for different scenarios"""
    return {
        "code_generation": {
            "thinking": "I need to write a function to calculate the sum",
            "code": "def calculate_sum(n):\n    return sum(range(1, n+1))"
        },
        "tool_selection": {
            "thinking": "I should use the python_executor tool",
            "action": "execute_code",
            "tool_id": "python-executor-server",
            "parameters": {"code": "print(sum(range(1, 101)))"}
        },
        "task_completion": {
            "completed": True,
            "reason": "Successfully calculated the sum",
            "summary": "The sum of 1 to 100 is 5050"
        },
        "error_response": {
            "thinking": "Something went wrong",
            "error": "Failed to process request"
        }
    }


@pytest.fixture
def sample_task_spec():
    """Provide a sample TaskSpec for testing"""
    from core.interfaces import TaskSpec
    
    return TaskSpec(
        task_id="test-task-001",
        task_type="reasoning",
        description="Calculate the sum of numbers from 1 to 100",
        user_id="test-user",
        constraints={"max_steps": 5}
    )


@pytest.fixture
def sample_tool_spec():
    """Provide a sample tool specification"""
    from core.toolscore.interfaces import MCPServerSpec, ToolCapability, ToolType
    
    return MCPServerSpec(
        tool_id="test-tool",
        name="Test Tool",
        description="A tool for testing",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[
            ToolCapability(
                name="test_action",
                description="Perform a test action",
                parameters={
                    "input": {"type": "string", "required": True}
                }
            )
        ],
        tags=["test", "sample"],
        enabled=True,
        endpoint="ws://localhost:9999/mcp"
    )


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security-related"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names"""
    for item in items:
        # Add markers based on test file names
        if "security" in item.nodeid:
            item.add_marker(pytest.mark.security)
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        if "test_enhanced_runtime" in item.nodeid:
            item.add_marker(pytest.mark.slow)


# Test utilities
class AsyncContextManager:
    """Helper for creating async context managers in tests"""
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def assert_called_with_subset(mock, **expected_kwargs):
    """Assert that a mock was called with at least the expected kwargs"""
    actual_kwargs = mock.call_args.kwargs
    for key, expected_value in expected_kwargs.items():
        assert key in actual_kwargs
        assert actual_kwargs[key] == expected_value