"""
Pytest configuration and shared fixtures for Agent Data Platform tests
"""

import pytest
import pytest_asyncio
import asyncio
import logging
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

# Import modules for testing
from core.config_manager import ConfigManager
from core.interfaces import TaskSpec, TaskType, ErrorType

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)

@pytest.fixture
def test_config():
    """Basic test configuration"""
    return {
        'runtime': {
            'max_workers': 2,
            'timeout': 30,
            'retry_attempts': 3
        },
        'redis': {
            'host': 'localhost',
            'port': 6379,
            'db': 15  # Use test database
        },
        'mcp_servers': {
            'toolscore_http': {'port': 9091},
            'toolscore_mcp': {'port': 9090, 'endpoint': '/websocket'},
            'python_executor': {'port': 9083},
            'browser_navigator': {'port': 9084},
            'search_tool': {'port': 9003}
        }
    }

@pytest.fixture
def mock_config_manager(test_config):
    """Mock ConfigManager for testing"""
    mock = MagicMock()
    mock.get_redis_url.return_value = "redis://localhost:6379"
    mock.get_ports_config.return_value = test_config['mcp_servers']
    mock.get_llm_config.return_value = {
        'provider': 'openai',
        'model': 'gpt-4',
        'api_key': 'test_key',
        'max_tokens': 4000,
        'temperature': 0.7
    }
    mock.load_routing_config.return_value = MagicMock()
    return mock

@pytest.fixture
def sample_task():
    """Sample TaskSpec for testing"""
    return TaskSpec(
        task_id="test-task-001",
        task_type=TaskType.CODE,
        description="Test task for unit testing",
        context="This is a test context",
        expected_tools=["python_executor"],
        constraints={"language": "python"},
        max_steps=5,
        timeout=60,
        priority=1
    )

@pytest.fixture
def sample_web_task():
    """Sample web TaskSpec for testing"""
    return TaskSpec(
        task_id="test-web-task-001",
        task_type=TaskType.WEB,
        description="Test web task for unit testing",
        context="Navigate to a webpage and extract information",
        expected_tools=["browser_navigator"],
        constraints={"url": "https://example.com"},
        max_steps=10,
        timeout=120,
        priority=2
    )

@pytest.fixture
def sample_reasoning_task():
    """Sample reasoning TaskSpec for testing"""
    return TaskSpec(
        task_id="test-reasoning-task-001",
        task_type=TaskType.REASONING,
        description="Test reasoning task for unit testing",
        context="Analyze and reason about a complex problem",
        expected_tools=["llm_client"],
        constraints={"model": "gpt-4"},
        max_steps=15,
        timeout=300,
        priority=3
    )

@pytest_asyncio.fixture
async def mock_redis():
    """Mock Redis client for testing"""
    mock = AsyncMock()
    mock.ping.return_value = True
    mock.set.return_value = True
    mock.get.return_value = None
    mock.exists.return_value = False
    mock.delete.return_value = 1
    mock.keys.return_value = []
    return mock

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session scope"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing"""
    mock = AsyncMock()
    mock.generate_response.return_value = {
        "content": "Test response from LLM",
        "finish_reason": "stop",
        "usage": {"total_tokens": 100}
    }
    return mock

@pytest.fixture
def test_ports():
    """Generate unique test ports to avoid conflicts"""
    import time
    base_port = 9500 + int(time.time() % 100)
    return {
        'toolscore_mcp': base_port,
        'toolscore_http': base_port + 1,
        'python_executor': base_port + 2,
        'browser_navigator': base_port + 3,
        'search_tool': base_port + 4
    }

# Auto-use fixtures for all tests
pytest_plugins = []