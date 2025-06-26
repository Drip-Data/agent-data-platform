"""
Pytest configuration and shared fixtures for Agent Data Platform
提供所有测试文件共享的配置和夹具
"""

import asyncio
import logging
import os
import sys
import tempfile
import redis.asyncio as redis
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Disable some noisy loggers during tests
logging.getLogger('playwright').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config_manager():
    """Mock configuration manager for testing"""
    from core.config_manager import ConfigManager
    
    mock_config = MagicMock(spec=ConfigManager)
    
    # Mock LLM config
    mock_config.get_llm_config.return_value = {
        "provider": "openai",
        "model": "gpt-4",
        "api_key": "test_key",
        "base_url": None,
        "temperature": 0.7
    }
    
    # Mock ports config
    mock_config.get_ports_config.return_value = {
        "mcp_servers": {
            "browser_use": {"port": 8003},
            "microsandbox_server": {"port": 8001},
            "microsandbox_mcp": {"port": 8001},  # 添加这个配置以兼容MicroSandboxMCPServer
            "toolscore_mcp": {"port": 8000},
            "toolscore_http": {"port": 8091}
        }
    }
    
    # Mock Redis URL
    mock_config.get_redis_url.return_value = "redis://localhost:6379"
    
    # Mock routing config
    mock_config.load_routing_config.return_value = MagicMock(
        task_type_mapping={
            "WEB": "web_queue",
            "CODE": "code_queue",
            "REASONING": "reasoning_queue"
        }
    )
    
    return mock_config


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables"""
    # Set headless mode for browser tests
    os.environ["BROWSER_HEADLESS"] = "true"
    os.environ["BROWSER_USE_SERVER_PORT"] = "8003"
    
    yield
    
    # Clean up environment
    for key in ["BROWSER_HEADLESS", "BROWSER_USE_SERVER_PORT"]:
        if key in os.environ:
            del os.environ[key]


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing"""
    mock_redis = AsyncMock(spec=redis.Redis)
    
    # Mock basic Redis operations
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.hget.return_value = None
    mock_redis.hset.return_value = True
    mock_redis.publish.return_value = 1
    mock_redis.close.return_value = None
    
    return mock_redis


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory for tests"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create subdirectories
        (temp_path / "trajectories").mkdir()
        (temp_path / "screenshots").mkdir()
        (temp_path / "python_execution").mkdir()
        (temp_path / "logs").mkdir()
        
        yield temp_path


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing"""
    mock_llm = AsyncMock()
    
    # Mock common LLM responses
    mock_llm.generate_response.return_value = {
        "content": "Test response",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    }
    
    mock_llm.analyze_task.return_value = {
        "task_type": "CODE",
        "complexity": "medium",
        "estimated_steps": 3
    }
    
    return mock_llm


@pytest.fixture
def mock_service_manager():
    """Mock service manager for testing"""
    from services.service_manager import ServiceManager
    
    mock_manager = AsyncMock(spec=ServiceManager)
    mock_manager.is_running = False
    mock_manager.services = {}
    
    # Mock service operations
    mock_manager.start_all.return_value = None
    mock_manager.stop_all.return_value = None
    mock_manager.health_check.return_value = {"status": "healthy"}
    
    return mock_manager


@pytest.fixture
def sample_task():
    """Sample task for testing"""
    return {
        "task_id": "test_task_001",
        "description": "This is a test task for validation",
        "task_type": "CODE",
        "priority": "medium",
        "expected_output": "Test completion",
        "metadata": {
            "created_at": "2025-06-18T10:00:00Z",
            "timeout": 300
        }
    }