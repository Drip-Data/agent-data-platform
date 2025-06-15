"""Task API 单元测试
测试 FastAPI 端点的完整功能，包括任务提交、状态查询等
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from core.task_api import app, redis_client


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.xadd = AsyncMock(return_value="1234567890")
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock()
    redis_mock.xlen = AsyncMock(return_value=5)
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.aclose = AsyncMock()
    return redis_mock


@pytest.fixture
def test_client(mock_redis):
    """Create test client with mocked Redis"""
    # Patch the global redis_client
    with patch("core.task_api.redis_client", mock_redis):
        # Also patch the startup event to use our mock
        app.dependency_overrides = {}
        yield TestClient(app)


def test_root_endpoint(test_client):
    """Test root endpoint returns API info"""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Agent Data Platform - Task API"
    assert "endpoints" in data
    assert "components" in data


def test_health_check_healthy(test_client, mock_redis):
    """Test health check when Redis is connected"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis"] == "connected"
    mock_redis.ping.assert_called()


def test_health_check_degraded(test_client, mock_redis):
    """Test health check when Redis fails"""
    mock_redis.ping.side_effect = Exception("Connection failed")
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["redis"] == "disconnected"
    assert "error" in data


def test_system_status(test_client, mock_redis):
    """Test system status endpoint"""
    response = test_client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "components" in data
    assert data["components"]["redis"] == "connected"
    assert data["components"]["task_queue_length"] == 5
    mock_redis.xlen.assert_called_with("tasks:reasoning")


def test_submit_task_success(test_client, mock_redis):
    """Test successful task submission"""
    task_request = {
        "task_type": "reasoning",
        "input": "Calculate the sum of 1 to 100",
        "priority": "high",
        "context": {"max_steps": 5}
    }
    
    response = test_client.post("/api/v1/tasks", json=task_request)
    assert response.status_code == 200
    data = response.json()
    
    assert "task_id" in data
    assert data["status"] == "queued"
    assert data["message"] == "Task submitted successfully"
    assert "timestamp" in data
    
    # Verify Redis calls
    mock_redis.xadd.assert_called_once()
    mock_redis.setex.assert_called_once()
    
    # Check the task data sent to Redis
    xadd_call = mock_redis.xadd.call_args
    assert xadd_call[0][0] == "tasks:reasoning"
    task_data = json.loads(xadd_call[0][1]["task"])
    assert task_data["task_type"] == "reasoning"
    assert task_data["description"] == "Calculate the sum of 1 to 100"
    assert task_data["priority"] == "high"


def test_submit_task_default_values(test_client, mock_redis):
    """Test task submission with default values"""
    task_request = {
        "input": "Simple task"
    }
    
    response = test_client.post("/api/v1/tasks", json=task_request)
    assert response.status_code == 200
    data = response.json()
    
    # Check defaults were applied
    xadd_call = mock_redis.xadd.call_args
    task_data = json.loads(xadd_call[0][1]["task"])
    assert task_data["task_type"] == "reasoning"  # default
    assert task_data["priority"] == "medium"  # default


def test_submit_task_error(test_client, mock_redis):
    """Test task submission when Redis fails"""
    mock_redis.xadd.side_effect = Exception("Redis error")
    
    task_request = {
        "input": "Test task"
    }
    
    response = test_client.post("/api/v1/tasks", json=task_request)
    assert response.status_code == 500
    assert "Failed to submit task" in response.json()["detail"]


def test_get_task_status_found(test_client, mock_redis):
    """Test getting status of existing task"""
    task_id = "test-task-123"
    status_data = {
        "task_id": task_id,
        "status": "processing",
        "message": "Task is being processed",
        "timestamp": datetime.now().isoformat()
    }
    result_data = {
        "output": "Task completed successfully",
        "steps": 3
    }
    
    mock_redis.get.side_effect = [
        json.dumps(status_data),  # task_status:task_id
        json.dumps(result_data)   # task_result:task_id
    ]
    
    response = test_client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    
    assert data["task_id"] == task_id
    assert data["status"] == "processing"
    assert data["message"] == "Task is being processed"
    assert data["result"] == result_data


def test_get_task_status_not_found(test_client, mock_redis):
    """Test getting status of non-existent task"""
    mock_redis.get.return_value = None
    
    response = test_client.get("/api/v1/tasks/non-existent-task")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_task_status_no_result(test_client, mock_redis):
    """Test getting status when task has no result yet"""
    task_id = "test-task-456"
    status_data = {
        "task_id": task_id,
        "status": "queued",
        "timestamp": datetime.now().isoformat()
    }
    
    mock_redis.get.side_effect = [
        json.dumps(status_data),  # task_status:task_id
        None                      # task_result:task_id (no result yet)
    ]
    
    response = test_client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    
    assert data["task_id"] == task_id
    assert data["status"] == "queued"
    assert data["result"] is None


def test_list_tools(test_client, mock_redis):
    """Test listing available tools"""
    response = test_client.post("/api/v1/tools/list")
    assert response.status_code == 200
    data = response.json()
    
    assert data["message"] == "Tool list request sent to ToolScore"
    assert data["message"] == "Tool list request sent to ToolScore"
    
    # Verify Redis command was sent
    mock_redis.lpush.assert_called_once()
    lpush_call = mock_redis.lpush.call_args
    assert lpush_call[0][0] == "toolscore:commands"
    command_data = json.loads(lpush_call[0][1])
    assert command_data["command"] == "list_tools"


@pytest.mark.asyncio
async def test_startup_event():
    """Test startup event Redis connection"""
    with patch("core.task_api.redis.from_url") as mock_from_url:
        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_from_url.return_value = mock_redis_instance
        
        # Import and call startup directly
        from core.task_api import startup_event
        await startup_event()
        
        mock_from_url.assert_called_once()
        mock_redis_instance.ping.assert_called_once()


@pytest.mark.asyncio
async def test_startup_event_redis_failure():
    """Test startup event when Redis connection fails"""
    with patch("core.task_api.redis.from_url") as mock_from_url:
        mock_from_url.side_effect = Exception("Connection refused")
        
        # Import and call startup directly
        from core.task_api import startup_event
        await startup_event()
        
        # Should not raise exception, just log warning
        mock_from_url.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_event():
    """Test shutdown event closes Redis connection"""
    mock_redis_instance = AsyncMock()
    mock_redis_instance.aclose = AsyncMock()
    
    with patch("core.task_api.redis_client", mock_redis_instance):
        from core.task_api import shutdown_event
        await shutdown_event()
        
        mock_redis_instance.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_event_no_redis():
    """Test shutdown event when Redis is not connected"""
    with patch("core.task_api.redis_client", None):
        from core.task_api import shutdown_event
        # Should not raise exception
        await shutdown_event()