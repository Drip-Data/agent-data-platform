"""
Pytest configuration and fixtures for agent-data-platform tests
"""
import asyncio
import pytest
import tempfile
import os
from unittest.mock import Mock, AsyncMock
from pathlib import Path

# Add the project root to the path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modules as needed in tests


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configurations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)
    mock_redis.set = Mock(return_value=True)
    mock_redis.get = Mock(return_value=None)
    mock_redis.delete = Mock(return_value=1)
    mock_redis.exists = Mock(return_value=False)
    return mock_redis


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    from core.config_manager import ConfigManager
    config_manager = Mock(spec=ConfigManager)
    config_manager.get_config = Mock(return_value={
        "redis": {"host": "localhost", "port": 6379},
        "llm": {"provider": "openai", "model": "gpt-3.5-turbo"},
        "ports": {"base_port": 8000}
    })
    return config_manager


@pytest.fixture
def mock_service_manager():
    """Mock ServiceManager for testing."""
    from services.service_manager import ServiceManager
    service_manager = Mock(spec=ServiceManager)
    service_manager.start_service = AsyncMock(return_value=True)
    service_manager.stop_service = AsyncMock(return_value=True)
    service_manager.get_service_status = Mock(return_value="running")
    return service_manager


@pytest.fixture
def sample_task():
    """Sample task data for testing."""
    return {
        "id": "test-task-001",
        "type": "code_generation",
        "description": "Generate a simple Python function",
        "requirements": ["Create a function that adds two numbers"],
        "priority": "medium",
        "status": "pending"
    }


@pytest.fixture
def sample_trajectory():
    """Sample trajectory data for testing."""
    return {
        "task_id": "test-task-001",
        "steps": [
            {
                "step_id": 1,
                "action": "analysis",
                "input": "Analyze task requirements",
                "output": "Task requires creating an addition function",
                "timestamp": "2024-01-01T00:00:00Z"
            },
            {
                "step_id": 2,
                "action": "code_generation",
                "input": "Generate Python function",
                "output": "def add(a, b): return a + b",
                "timestamp": "2024-01-01T00:01:00Z"
            }
        ]
    }