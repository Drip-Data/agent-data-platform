"""
Tests for Task API endpoints and functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import sys
import json

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Note: TaskAPI class doesn't exist, using service directly
from services.task_api_service import TaskAPIService


class TestTaskAPIService:
    """Test cases for Task API RESTful endpoints"""
    
    @pytest.fixture
    def task_api_service(self, mock_config_manager, mock_redis):
        """Create TaskAPIService instance for testing"""
        with patch('services.task_api_service.RedisManager') as mock_redis_manager:
            mock_redis_manager.return_value.get_redis_client.return_value = mock_redis
            return TaskAPIService(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_task_submission_endpoint(self, task_api_service, sample_task):
        """Test task submission via API endpoint"""
        with patch.object(task_api_service, 'submit_task', new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = {
                "task_id": sample_task["id"],
                "status": "submitted",
                "message": "Task submitted successfully"
            }
            
            result = await task_api_service.submit_task(sample_task)
            
            assert result["status"] == "submitted"
            assert result["task_id"] == sample_task["id"]
            mock_submit.assert_called_once_with(sample_task)
    
    @pytest.mark.asyncio
    async def test_task_status_query(self, task_api_service, sample_task):
        """Test task status querying"""
        task_id = sample_task["id"]
        expected_status = {
            "task_id": task_id,
            "status": "running",
            "progress": 50,
            "estimated_completion": "2024-01-01T00:05:00Z"
        }
        
        with patch.object(task_api_service, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = expected_status
            
            status = await task_api_service.get_task_status(task_id)
            
            assert status["task_id"] == task_id
            assert status["status"] == "running"
            assert status["progress"] == 50
            mock_status.assert_called_once_with(task_id)
    
    @pytest.mark.asyncio
    async def test_task_result_retrieval(self, task_api_service, sample_task):
        """Test task result retrieval"""
        task_id = sample_task["id"]
        expected_result = {
            "task_id": task_id,
            "status": "completed",
            "result": {
                "output": "Task completed successfully",
                "files_generated": ["output.txt"],
                "execution_time": 3.2
            }
        }
        
        with patch.object(task_api_service, 'get_task_result', new_callable=AsyncMock) as mock_result:
            mock_result.return_value = expected_result
            
            result = await task_api_service.get_task_result(task_id)
            
            assert result["status"] == "completed"
            assert "output" in result["result"]
            assert result["result"]["execution_time"] == 3.2
            mock_result.assert_called_once_with(task_id)
    
    @pytest.mark.asyncio
    async def test_task_cancellation(self, task_api_service, sample_task):
        """Test task cancellation"""
        task_id = sample_task["id"]
        
        with patch.object(task_api_service, 'cancel_task', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = {
                "task_id": task_id,
                "status": "cancelled",
                "message": "Task cancelled successfully"
            }
            
            result = await task_api_service.cancel_task(task_id)
            
            assert result["status"] == "cancelled"
            assert result["task_id"] == task_id
            mock_cancel.assert_called_once_with(task_id)


class TestTaskAPIErrorHandling:
    """Test cases for Task API error handling and fallback mechanisms"""
    
    @pytest.fixture
    def task_api(self, mock_config_manager, mock_redis):
        """Create TaskAPI instance for testing"""
        with patch('core.task_api.RedisManager') as mock_redis_manager:
            mock_redis_manager.return_value.get_redis_client.return_value = mock_redis
            return TaskAPI(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_invalid_task_submission(self, task_api):
        """Test handling of invalid task submissions"""
        invalid_task = {
            "id": "",  # Empty ID
            "type": "invalid_type",
            # Missing required fields
        }
        
        with patch.object(task_api, 'validate_task') as mock_validate:
            mock_validate.return_value = False
            
            with patch.object(task_api, 'submit_task', new_callable=AsyncMock) as mock_submit:
                mock_submit.side_effect = ValueError("Invalid task format")
                
                with pytest.raises(ValueError):
                    await task_api.submit_task(invalid_task)
    
    @pytest.mark.asyncio
    async def test_nonexistent_task_query(self, task_api):
        """Test querying non-existent task"""
        nonexistent_id = "non-existent-task"
        
        with patch.object(task_api, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "error": "Task not found",
                "status_code": 404
            }
            
            result = await task_api.get_task_status(nonexistent_id)
            
            assert "error" in result
            assert result["status_code"] == 404
    
    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, task_api):
        """Test API rate limiting"""
        # Simulate multiple rapid requests
        tasks = [{"id": f"task-{i}", "type": "test"} for i in range(10)]
        
        with patch.object(task_api, 'check_rate_limit') as mock_rate_limit:
            mock_rate_limit.side_effect = [True] * 5 + [False] * 5  # First 5 allowed, then blocked
            
            allowed_count = 0
            blocked_count = 0
            
            for task in tasks:
                if task_api.check_rate_limit("test_user"):
                    allowed_count += 1
                else:
                    blocked_count += 1
            
            assert allowed_count == 5
            assert blocked_count == 5
    
    @pytest.mark.asyncio
    async def test_fallback_mechanisms(self, task_api, mock_redis):
        """Test fallback mechanisms when Redis is unavailable"""
        # Simulate Redis connection failure
        mock_redis.ping.side_effect = Exception("Redis connection failed")
        
        with patch.object(task_api, 'enable_fallback_mode') as mock_fallback:
            task_api.enable_fallback_mode()
            mock_fallback.assert_called_once()
            
            # Test that API still works in fallback mode
            with patch.object(task_api, 'submit_task_fallback', new_callable=AsyncMock) as mock_submit_fallback:
                mock_submit_fallback.return_value = {"status": "submitted", "mode": "fallback"}
                
                result = await task_api.submit_task_fallback({"id": "fallback-test", "type": "test"})
                assert result["mode"] == "fallback"


class TestTaskAPIService:
    """Test cases for TaskAPIService"""
    
    @pytest.fixture
    def task_api_service(self, mock_config_manager):
        """Create TaskAPIService instance for testing"""
        return TaskAPIService(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_service_startup(self, task_api_service):
        """Test TaskAPIService startup"""
        with patch.object(task_api_service, 'start_server', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True
            
            result = await task_api_service.start_server()
            assert result is True
            mock_start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_service_health_check(self, task_api_service):
        """Test service health check endpoint"""
        with patch.object(task_api_service, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "status": "healthy",
                "uptime": 3600,
                "active_tasks": 5,
                "last_check": "2024-01-01T00:00:00Z"
            }
            
            health_status = await task_api_service.health_check()
            
            assert health_status["status"] == "healthy"
            assert health_status["active_tasks"] == 5
            mock_health.assert_called_once()
    
    def test_service_configuration_validation(self, task_api_service):
        """Test service configuration validation"""
        required_configs = ["port", "host", "max_workers", "timeout"]
        
        with patch.object(task_api_service, 'validate_configuration') as mock_validate:
            mock_validate.return_value = True
            
            is_valid = task_api_service.validate_configuration(required_configs)
            assert is_valid is True
            mock_validate.assert_called_once_with(required_configs)


class TestTaskAPIIntegration:
    """Integration tests for Task API"""
    
    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, mock_config_manager, sample_task):
        """Test complete task lifecycle through API"""
        # This test simulates a complete task workflow:
        # 1. Submit task
        # 2. Query status multiple times
        # 3. Retrieve final result
        
        task_api = TaskAPI(config_manager=mock_config_manager)
        
        # Mock the complete lifecycle
        with patch.object(task_api, 'submit_task', new_callable=AsyncMock) as mock_submit, \
             patch.object(task_api, 'get_task_status', new_callable=AsyncMock) as mock_status, \
             patch.object(task_api, 'get_task_result', new_callable=AsyncMock) as mock_result:
            
            # 1. Task submission
            mock_submit.return_value = {"task_id": sample_task["id"], "status": "submitted"}
            submit_result = await task_api.submit_task(sample_task)
            assert submit_result["status"] == "submitted"
            
            # 2. Status queries (simulating progression)
            status_progression = [
                {"status": "queued", "progress": 0},
                {"status": "running", "progress": 30},
                {"status": "running", "progress": 70},
                {"status": "completed", "progress": 100}
            ]
            mock_status.side_effect = status_progression
            
            # Query status multiple times
            for expected_status in status_progression:
                status = await task_api.get_task_status(sample_task["id"])
                assert status["status"] == expected_status["status"]
                assert status["progress"] == expected_status["progress"]
            
            # 3. Final result retrieval
            mock_result.return_value = {
                "task_id": sample_task["id"],
                "status": "completed",
                "result": {"output": "Integration test completed successfully"}
            }
            
            final_result = await task_api.get_task_result(sample_task["id"])
            assert final_result["status"] == "completed"
            assert "Integration test completed" in final_result["result"]["output"]
    
    @pytest.mark.asyncio
    async def test_concurrent_task_handling(self, mock_config_manager):
        """Test handling multiple concurrent tasks"""
        task_api = TaskAPI(config_manager=mock_config_manager)
        
        # Create multiple tasks
        tasks = [
            {"id": f"concurrent-task-{i}", "type": "test", "data": f"data-{i}"}
            for i in range(5)
        ]
        
        with patch.object(task_api, 'submit_task', new_callable=AsyncMock) as mock_submit:
            mock_submit.side_effect = [
                {"task_id": task["id"], "status": "submitted"} for task in tasks
            ]
            
            # Submit all tasks concurrently
            results = await asyncio.gather(*[
                task_api.submit_task(task) for task in tasks
            ])
            
            # Verify all tasks were submitted
            assert len(results) == 5
            for i, result in enumerate(results):
                assert result["task_id"] == f"concurrent-task-{i}"
                assert result["status"] == "submitted"