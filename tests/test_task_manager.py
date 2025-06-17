"""
Tests for core.task_manager module
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.task_manager import TaskManager
from core.interfaces import TaskSpec, TaskType, TrajectoryResult, ErrorType


class TestTaskManager:
    """Test TaskManager class"""
    
    @pytest.fixture
    def task_manager(self, mock_config_manager, mock_redis):
        """Create TaskManager instance for testing"""
        with patch('core.task_manager.redis.Redis', return_value=mock_redis):
            return TaskManager(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, task_manager):
        """Test TaskManager initialization"""
        assert task_manager is not None
        assert hasattr(task_manager, 'config_manager')
        assert hasattr(task_manager, 'redis_client')
    
    @pytest.mark.asyncio
    async def test_submit_task(self, task_manager, sample_task):
        """Test submitting a task"""
        # Mock the queue submission
        task_manager.redis_client.lpush = AsyncMock(return_value=1)
        task_manager.redis_client.set = AsyncMock(return_value=True)
        
        result = await task_manager.submit_task(sample_task)
        
        assert result is True
        task_manager.redis_client.lpush.assert_called_once()
        task_manager.redis_client.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_submit_task_redis_error(self, task_manager, sample_task):
        """Test submitting a task with Redis error"""
        task_manager.redis_client.lpush = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await task_manager.submit_task(sample_task)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_task(self, task_manager):
        """Test getting a task from queue"""
        # Mock Redis response
        mock_task_data = {
            'task_id': 'test-001',
            'task_type': 'code',
            'description': 'Test task',
            'context': 'Test context'
        }
        
        task_manager.redis_client.brpop = AsyncMock(
            return_value=('code_queue', str(mock_task_data).encode())
        )
        
        with patch('json.loads', return_value=mock_task_data):
            task = await task_manager.get_task('code_queue')
        
        assert task is not None
        assert task.task_id == 'test-001'
        assert task.task_type == TaskType.CODE
        assert task.description == 'Test task'
    
    @pytest.mark.asyncio
    async def test_get_task_timeout(self, task_manager):
        """Test getting task with timeout"""
        task_manager.redis_client.brpop = AsyncMock(return_value=None)
        
        task = await task_manager.get_task('code_queue', timeout=1)
        
        assert task is None
    
    @pytest.mark.asyncio
    async def test_get_task_invalid_data(self, task_manager):
        """Test getting task with invalid data"""
        task_manager.redis_client.brpop = AsyncMock(
            return_value=('code_queue', b'invalid json data')
        )
        
        task = await task_manager.get_task('code_queue')
        
        assert task is None
    
    @pytest.mark.asyncio
    async def test_update_task_status(self, task_manager, sample_task):
        """Test updating task status"""
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        
        result = await task_manager.update_task_status(
            sample_task.task_id, 
            'running',
            progress=50
        )
        
        assert result is True
        task_manager.redis_client.hset.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_task_status(self, task_manager, sample_task):
        """Test getting task status"""
        mock_status = {
            'status': 'completed',
            'progress': 100,
            'updated_at': datetime.now().isoformat()
        }
        
        task_manager.redis_client.hgetall = AsyncMock(return_value=mock_status)
        
        status = await task_manager.get_task_status(sample_task.task_id)
        
        assert status == mock_status
        task_manager.redis_client.hgetall.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_complete_task(self, task_manager, sample_task):
        """Test completing a task"""
        task_result = TrajectoryResult(
            task_name=sample_task.description,
            task_id=sample_task.task_id,
            task_description=sample_task.description,
            runtime_id="test-runtime",
            success=True,
            steps=[],
            final_result='Task completed',
            total_duration=2.5
        )
        
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        task_manager.redis_client.set = AsyncMock(return_value=True)
        
        result = await task_manager.complete_task(task_result)
        
        assert result is True
        task_manager.redis_client.hset.assert_called()
        task_manager.redis_client.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_complete_task_with_error(self, task_manager, sample_task):
        """Test completing a task with error"""
        task_result = TrajectoryResult(
            task_name=sample_task.description,
            task_id=sample_task.task_id,
            task_description=sample_task.description,
            runtime_id="test-runtime",
            success=False,
            steps=[],
            final_result='Task execution failed',
            error_message='Task execution failed',
            error_type=ErrorType.EXECUTION_ERROR,
            total_duration=1.0
        )
        
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        task_manager.redis_client.set = AsyncMock(return_value=True)
        
        result = await task_manager.complete_task(task_result)
        
        assert result is True
        # Verify error information is stored
        task_manager.redis_client.hset.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_task_result(self, task_manager, sample_task):
        """Test getting task result"""
        mock_result_data = {
            'task_id': sample_task.task_id,
            'success': True,
            'result_data': {'output': 'Success'},
            'total_duration': 3.2,
            'steps_taken': 4
        }
        
        task_manager.redis_client.get = AsyncMock(
            return_value=str(mock_result_data).encode()
        )
        
        with patch('json.loads', return_value=mock_result_data):
            result = await task_manager.get_task_result(sample_task.task_id)
        
        assert result is not None
        assert result.task_id == sample_task.task_id
        assert result.success is True
        assert result.total_duration == 3.2
    
    @pytest.mark.asyncio
    async def test_get_task_result_not_found(self, task_manager, sample_task):
        """Test getting non-existent task result"""
        task_manager.redis_client.get = AsyncMock(return_value=None)
        
        result = await task_manager.get_task_result(sample_task.task_id)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, task_manager, sample_task):
        """Test canceling a task"""
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        task_manager.redis_client.delete = AsyncMock(return_value=1)
        
        result = await task_manager.cancel_task(sample_task.task_id)
        
        assert result is True
        task_manager.redis_client.hset.assert_called()
    
    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, task_manager):
        """Test listing tasks by status"""
        mock_task_keys = [
            f'task:status:test-001',
            f'task:status:test-002',
            f'task:status:test-003'
        ]
        
        task_manager.redis_client.keys = AsyncMock(return_value=mock_task_keys)
        task_manager.redis_client.hgetall = AsyncMock(return_value={'status': 'running'})
        
        tasks = await task_manager.list_tasks_by_status('running')
        
        assert len(tasks) == 3
        assert all(task['status'] == 'running' for task in tasks)
    
    @pytest.mark.asyncio
    async def test_get_queue_info(self, task_manager):
        """Test getting queue information"""
        task_manager.redis_client.llen = AsyncMock(return_value=5)
        task_manager.redis_client.keys = AsyncMock(return_value=[
            'task:status:1', 'task:status:2', 'task:status:3'
        ])
        task_manager.redis_client.hget = AsyncMock(return_value='running')
        
        queue_info = await task_manager.get_queue_info('code_queue')
        
        assert queue_info['queue_name'] == 'code_queue'
        assert queue_info['pending_tasks'] == 5
        assert 'active_tasks' in queue_info
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_tasks(self, task_manager):
        """Test cleaning up completed tasks"""
        # Mock completed task keys
        mock_task_keys = [
            'task:status:test-001',
            'task:status:test-002'
        ]
        
        task_manager.redis_client.keys = AsyncMock(return_value=mock_task_keys)
        task_manager.redis_client.hget = AsyncMock(return_value='completed')
        task_manager.redis_client.delete = AsyncMock(return_value=1)
        
        cleaned_count = await task_manager.cleanup_completed_tasks(max_age_hours=24)
        
        assert cleaned_count >= 0
        task_manager.redis_client.delete.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_task_metrics(self, task_manager):
        """Test getting task metrics"""
        mock_metrics_data = {
            'total_tasks': 100,
            'completed_tasks': 85,
            'failed_tasks': 10,
            'pending_tasks': 5,
            'average_execution_time': 2.5
        }
        
        task_manager.redis_client.keys = AsyncMock(return_value=['key1', 'key2'])
        task_manager.redis_client.hgetall = AsyncMock(return_value={'status': 'completed'})
        
        with patch.object(task_manager, '_calculate_metrics', return_value=mock_metrics_data):
            metrics = await task_manager.get_task_metrics()
        
        assert metrics['total_tasks'] == 100
        assert metrics['completed_tasks'] == 85
        assert metrics['average_execution_time'] == 2.5
    
    @pytest.mark.asyncio
    async def test_retry_failed_task(self, task_manager, sample_task):
        """Test retrying a failed task"""
        task_manager.redis_client.hget = AsyncMock(return_value='failed')
        task_manager.redis_client.lpush = AsyncMock(return_value=1)
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        
        result = await task_manager.retry_failed_task(sample_task.task_id)
        
        assert result is True
        task_manager.redis_client.lpush.assert_called_once()
        task_manager.redis_client.hset.assert_called()
    
    @pytest.mark.asyncio
    async def test_retry_non_failed_task(self, task_manager, sample_task):
        """Test retrying a non-failed task"""
        task_manager.redis_client.hget = AsyncMock(return_value='completed')
        
        result = await task_manager.retry_failed_task(sample_task.task_id)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_task_timeout_handling(self, task_manager, sample_task):
        """Test handling task timeout"""
        # Create a task with short timeout
        short_timeout_task = TaskSpec(
            task_id="timeout-test",
            task_type=TaskType.CODE,
            description="Task that will timeout",
            timeout=1  # 1 second timeout
        )
        
        task_manager.redis_client.hset = AsyncMock(return_value=True)
        
        # Simulate task timeout
        result = await task_manager.handle_task_timeout(short_timeout_task.task_id)
        
        assert result is True
        task_manager.redis_client.hset.assert_called()
    
    @pytest.mark.asyncio
    async def test_bulk_task_submission(self, task_manager, sample_task, sample_web_task):
        """Test submitting multiple tasks at once"""
        tasks = [sample_task, sample_web_task]
        
        task_manager.redis_client.lpush = AsyncMock(return_value=1)
        task_manager.redis_client.set = AsyncMock(return_value=True)
        
        results = await task_manager.submit_tasks(tasks)
        
        assert len(results) == 2
        assert all(result is True for result in results)
        assert task_manager.redis_client.lpush.call_count == 2
    
    @pytest.mark.asyncio
    async def test_task_priority_handling(self, task_manager):
        """Test handling task priorities"""
        high_priority_task = TaskSpec(
            task_id="high-priority",
            task_type=TaskType.CODE,
            description="High priority task",
            priority=5
        )
        
        low_priority_task = TaskSpec(
            task_id="low-priority",
            task_type=TaskType.CODE,
            description="Low priority task",
            priority=1
        )
        
        task_manager.redis_client.lpush = AsyncMock(return_value=1)
        task_manager.redis_client.set = AsyncMock(return_value=True)
        
        # Submit both tasks
        await task_manager.submit_task(high_priority_task)
        await task_manager.submit_task(low_priority_task)
        
        # High priority task should be processed first
        # This would typically involve priority queue implementation
        assert task_manager.redis_client.lpush.call_count == 2