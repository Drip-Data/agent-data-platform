# -*- coding: utf-8 -*-
"""
测试 task_manager.py 模块 - 任务管理器

覆盖功能:
1. TaskManager初始化和配置
2. 任务提交和状态管理
3. Redis持久化和内存回退
4. 任务生命周期管理
5. 轨迹保存和清理
6. 运行时配置
7. 错误处理和恢复
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.fixture
def task_manager_config():
    """TaskManager配置"""
    return {
        "redis_url": "redis://localhost:6379/0",
        "task_timeout": 300,
        "cleanup_interval": 60,
        "max_retries": 3
    }


@pytest.fixture
def sample_task():
    """示例任务数据"""
    return {
        "task_id": "test-task-001",
        "description": "测试任务描述",
        "task_type": "code_execution",
        "priority": "normal",
        "created_at": datetime.now().isoformat(),
        "timeout": 300,
        "metadata": {
            "user_id": "user123",
            "session_id": "session456"
        }
    }


@pytest_asyncio.fixture
async def task_manager_memory():
    """创建使用内存的TaskManager"""
    from core.task_manager import TaskManager
    
    config = {"task_timeout": 300}
    manager = TaskManager(config)
    
    return manager


@pytest.fixture
def sample_trajectory():
    """示例轨迹数据"""
    return {
        "task_id": "test-task-001",
        "steps": [
            {
                "step_id": 1,
                "action": "start",
                "timestamp": datetime.now().isoformat(),
                "result": "success"
            },
            {
                "step_id": 2,
                "action": "execute_code",
                "timestamp": datetime.now().isoformat(),
                "result": "completed",
                "output": "Hello, World!"
            }
        ],
        "final_status": "completed",
        "total_duration": 45.2
    }


class TestTaskManagerInit:
    """TaskManager初始化测试"""
    
    @patch("redis.asyncio.from_url")
    def test_init_with_redis_success(self, mock_redis, task_manager_config):
        """测试成功连接Redis初始化"""
        from core.task_manager import TaskManager
        
        # Mock Redis连接
        mock_redis_client = AsyncMock()
        mock_redis.return_value = mock_redis_client
        
        manager = TaskManager(task_manager_config)
        
        assert manager.config == task_manager_config
        assert manager.redis == mock_redis_client
        assert manager.fallback_mode == False
        assert manager.tasks == {}
        assert manager.task_history == []
        
        mock_redis.assert_called_once_with(task_manager_config["redis_url"])
    
    @patch("redis.asyncio.from_url")
    def test_init_redis_connection_error(self, mock_redis, task_manager_config):
        """测试Redis连接失败回退到内存模式"""
        from core.task_manager import TaskManager
        
        # Mock Redis连接失败
        mock_redis.side_effect = RedisConnectionError("连接失败")
        
        manager = TaskManager(task_manager_config)
        
        assert manager.redis_client is None
        assert manager.fallback_mode == True
        assert manager.tasks == {}
        assert manager.task_history == []
    
    def test_init_without_redis_url(self):
        """测试没有Redis URL时使用内存模式"""
        from core.task_manager import TaskManager
        
        config = {"task_timeout": 300}
        manager = TaskManager(config)
        
        assert manager.redis_client is None
        assert manager.fallback_mode == True
    
    def test_init_default_config(self):
        """测试默认配置"""
        from core.task_manager import TaskManager
        
        manager = TaskManager({})
        
        assert manager.config["task_timeout"] == 300  # 默认超时
        assert manager.config["cleanup_interval"] == 3600  # 默认清理间隔
        assert manager.fallback_mode == True


class TestTaskManagerSubmission:
    """TaskManager任务提交测试"""
    
    @pytest_asyncio.fixture
    async def task_manager_redis(self, task_manager_config):
        """创建使用Redis的TaskManager"""
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            from core.task_manager import TaskManager
            manager = TaskManager(task_manager_config)
            
            # 确保Redis客户端被正确设置
            manager.redis = mock_redis_client
            manager.redis_client = mock_redis_client
            manager.fallback_mode = False
            
            # Mock Redis操作
            mock_redis_client.hset = AsyncMock()
            mock_redis_client.expire = AsyncMock()
            mock_redis_client.hget = AsyncMock()
            mock_redis_client.hgetall = AsyncMock()
            mock_redis_client.hdel = AsyncMock()
            mock_redis_client.keys = AsyncMock()
            
            return manager
    

    
    @pytest.mark.asyncio
    async def test_submit_task_redis_mode(self, task_manager_redis, sample_task):
        """测试Redis模式下提交任务"""
        # Mock Redis返回值
        task_manager_redis.redis_client.hset.return_value = True
        task_manager_redis.redis_client.expire.return_value = True
        
        from core.interfaces import TaskSpec, TaskType
        
        task_spec = TaskSpec(
            task_id=sample_task["task_id"],
            description=sample_task["description"],
            task_type=TaskType.CODE,
            timeout=sample_task["timeout"]
        )
        
        task_id = await task_manager_redis.submit_task(task_spec)
        
        assert task_id is not None
        assert len(task_id) > 0
        
        # 验证Redis调用
        task_manager_redis.redis_client.hset.assert_called()
        task_manager_redis.redis_client.expire.assert_called()
    
    @pytest.mark.asyncio
    async def test_submit_task_memory_mode(self, task_manager_memory, sample_task):
        """测试内存模式下提交任务"""
        from core.interfaces import TaskSpec, TaskType
        
        # 创建TaskSpec对象
        task_spec = TaskSpec(
            task_id=sample_task["task_id"],
            description=sample_task["description"],
            task_type=TaskType.CODE,  # 使用枚举值
            timeout=sample_task["timeout"]
        )
        
        task_id = await task_manager_memory.submit_task(task_spec)
        
        assert task_id is not None
        assert task_id == sample_task["task_id"]
        
        # 验证任务数据存储在active_tasks中
        assert task_id in task_manager_memory.active_tasks
        task_data = task_manager_memory.active_tasks[task_id]
        assert task_data["status"] == "submitted"
    
    @pytest.mark.asyncio
    async def test_submit_task_with_priority(self, task_manager_memory):
        """测试提交带优先级的任务"""
        from core.interfaces import TaskSpec, TaskType
        
        # 创建TaskSpec对象
        task_spec = TaskSpec(
            task_id="priority-task-001",
            description="高优先级任务",
            task_type=TaskType.CODE,
            priority=5  # 高优先级
        )
        
        task_id = await task_manager_memory.submit_task(task_spec)
        
        assert task_id is not None
        task_data = task_manager_memory.active_tasks[task_id]
        assert task_data["task"]["priority"] == 5
    
    @pytest.mark.asyncio
    async def test_submit_task_redis_error_fallback(self, task_manager_redis, sample_task):
        """测试Redis错误时回退到内存模式"""
        # Mock Redis操作失败
        task_manager_redis.redis_client.hset.side_effect = RedisConnectionError("Redis错误")
        
        from core.interfaces import TaskSpec, TaskType
        
        task_spec = TaskSpec(
            task_id=sample_task["task_id"],
            description=sample_task["description"],
            task_type=TaskType.CODE
        )
        
        task_id = await task_manager_redis.submit_task(task_spec)
        
        # 验证任务仍然被创建（在内存中）
        assert task_id is not None
        assert task_id in task_manager_redis.tasks
        assert task_manager_redis.fallback_mode == True


class TestTaskManagerStatusManagement:
    """TaskManager状态管理测试"""
    
    @pytest_asyncio.fixture
    async def task_manager_with_task(self, task_manager_memory, sample_task):
        """创建包含任务的TaskManager"""
        from core.interfaces import TaskSpec, TaskType
        
        task_spec = TaskSpec(
            task_id=sample_task["task_id"],
            description=sample_task["description"],
            task_type=TaskType.CODE,
            timeout=sample_task["timeout"]
        )
        
        task_id = await task_manager_memory.submit_task(task_spec)
        return task_manager_memory, task_id
    
    @pytest.mark.asyncio
    async def test_update_task_status_memory_mode(self, task_manager_with_task):
        """测试内存模式下更新任务状态"""
        manager, task_id = task_manager_with_task
        
        # 更新状态为运行中
        success = await manager.update_task_status(task_id, "running", "任务开始执行")
        
        assert success == True
        
        task_data = manager.tasks[task_id]
        assert task_data["status"] == "running"
        assert task_data["status_message"] == "任务开始执行"
        assert "updated_at" in task_data
    
    @pytest.mark.asyncio
    async def test_update_task_status_nonexistent_task(self, task_manager_memory):
        """测试更新不存在任务的状态"""
        success = await task_manager_memory.update_task_status(
            "nonexistent-task", "running"
        )
        
        assert success == False
    
    @pytest.mark.asyncio
    async def test_get_task_status_memory_mode(self, task_manager_with_task):
        """测试内存模式下获取任务状态"""
        manager, task_id = task_manager_with_task
        
        # 更新状态
        await manager.update_task_status(task_id, "completed", "任务完成")
        
        # 获取状态
        status = await manager.get_task_status(task_id)
        
        assert status is not None
        assert status["status"] == "completed"
        assert status["status_message"] == "任务完成"
        assert status["task_id"] == task_id
    
    @pytest.mark.asyncio
    async def test_get_task_status_nonexistent_task(self, task_manager_memory):
        """测试获取不存在任务的状态"""
        status = await task_manager_memory.get_task_status("nonexistent-task")
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_complete_task_success(self, task_manager_with_task, sample_trajectory):
        """测试成功完成任务"""
        manager, task_id = task_manager_with_task
        
        # 完成任务
        from core.interfaces import TrajectoryResult
        
        trajectory_result = TrajectoryResult(
            task_name="test-task-001",
            task_id=task_id,
            task_description="测试任务描述",
            runtime_id="test-runtime",
            success=True,
            steps=sample_trajectory["steps"],
            final_result="任务成功完成"
        )
        
        await manager.complete_task(task_id, trajectory_result)
        
        # 验证任务已从内存中移除（因为complete_task会清理内存中的任务）
        assert task_id not in manager.active_tasks
    
    @pytest.mark.asyncio
    async def test_complete_task_with_error(self, task_manager_with_task):
        """测试任务完成时出现错误"""
        manager, task_id = task_manager_with_task
        
        # 完成任务（失败）
        from core.interfaces import TrajectoryResult, ErrorType
        
        trajectory_result = TrajectoryResult(
            task_name="test-task-001",
            task_id=task_id,
            task_description="测试任务描述",
            runtime_id="test-runtime",
            success=False,
            steps=[],
            final_result="任务执行失败",
            error_type=ErrorType.EXECUTION_ERROR,
            error_message="代码执行错误"
        )
        
        await manager.complete_task(task_id, trajectory_result)
        
        # 验证任务已从内存中移除（因为complete_task会清理内存中的任务）
        assert task_id not in manager.active_tasks


class TestTaskManagerTrajectoryManagement:
    """TaskManager轨迹管理测试"""
    
    @pytest_asyncio.fixture
    async def task_manager_with_completed_task(self, task_manager_memory, sample_task, sample_trajectory):
        """创建包含已完成任务的TaskManager"""
        from core.interfaces import TaskSpec, TaskType
        
        task_spec = TaskSpec(
            task_id=sample_task["task_id"],
            description=sample_task["description"],
            task_type=TaskType.CODE
        )
        task_id = await task_manager_memory.submit_task(task_spec)
        
        from core.interfaces import TrajectoryResult
        
        trajectory_result = TrajectoryResult(
            task_name=sample_task["task_id"],
            task_id=task_id,
            task_description=sample_task["description"],
            runtime_id="test-runtime",
            success=True,
            steps=sample_trajectory["steps"],
            final_result="任务完成"
        )
        
        await task_manager_memory.complete_task(task_id, trajectory_result)
        
        return task_manager_memory, task_id
    
    @pytest.mark.asyncio
    async def test_save_trajectory_memory_mode(self, task_manager_with_completed_task, sample_trajectory):
        """测试内存模式下保存轨迹"""
        manager, task_id = task_manager_with_completed_task
        
        # 保存轨迹
        success = await manager.save_trajectory(task_id, sample_trajectory)
        
        assert success == True
        
        # 验证轨迹被添加到历史记录
        assert len(manager.task_history) > 0
        
        # 查找保存的轨迹
        saved_trajectory = None
        for trajectory in manager.task_history:
            if trajectory["task_id"] == task_id:
                saved_trajectory = trajectory
                break
        
        assert saved_trajectory is not None
        assert saved_trajectory["steps"] == sample_trajectory["steps"]
        assert saved_trajectory["final_status"] == sample_trajectory["final_status"]
    
    @pytest.mark.asyncio
    async def test_save_trajectory_nonexistent_task(self, task_manager_memory, sample_trajectory):
        """测试保存不存在任务的轨迹"""
        success = await task_manager_memory.save_trajectory(
            "nonexistent-task", sample_trajectory
        )
        
        assert success == False
    
    @pytest.mark.asyncio
    async def test_get_task_trajectory_memory_mode(self, task_manager_with_completed_task, sample_trajectory):
        """测试内存模式下获取任务轨迹"""
        manager, task_id = task_manager_with_completed_task
        
        # 保存轨迹
        await manager.save_trajectory(task_id, sample_trajectory)
        
        # 获取轨迹
        trajectory = await manager.get_task_trajectory(task_id)
        
        assert trajectory is not None
        assert trajectory["task_id"] == task_id
        assert trajectory["steps"] == sample_trajectory["steps"]
    
    @pytest.mark.asyncio
    async def test_get_task_trajectory_nonexistent(self, task_manager_memory):
        """测试获取不存在任务的轨迹"""
        trajectory = await task_manager_memory.get_task_trajectory("nonexistent-task")
        
        assert trajectory is None


class TestTaskManagerListAndCleanup:
    """TaskManager列表和清理测试"""
    
    @pytest_asyncio.fixture
    async def task_manager_with_multiple_tasks(self, task_manager_memory):
        """创建包含多个任务的TaskManager"""
        # 创建不同状态的任务
        task_ids = []
        
        from core.interfaces import TaskSpec, TaskType
        
        # 待处理任务
        task_spec1 = TaskSpec(task_id="task-1", description="任务1", task_type=TaskType.CODE)
        task_id1 = await task_manager_memory.submit_task(task_spec1)
        task_ids.append(task_id1)
        
        # 运行中任务
        task_spec2 = TaskSpec(task_id="task-2", description="任务2", task_type=TaskType.CODE)
        task_id2 = await task_manager_memory.submit_task(task_spec2)
        await task_manager_memory.update_task_status(task_id2, "running")
        task_ids.append(task_id2)
        
        # 已完成任务
        task_spec3 = TaskSpec(task_id="task-3", description="任务3", task_type=TaskType.CODE)
        task_id3 = await task_manager_memory.submit_task(task_spec3)
        from core.interfaces import TrajectoryResult
        
        trajectory_result3 = TrajectoryResult(
            task_name="task-3",
            task_id=task_id3,
            task_description="任务3",
            runtime_id="test-runtime",
            success=True,
            steps=[],
            final_result="完成"
        )
        
        await task_manager_memory.complete_task(task_id3, trajectory_result3)
        task_ids.append(task_id3)
        
        return task_manager_memory, task_ids
    
    @pytest.mark.asyncio
    async def test_list_active_tasks(self, task_manager_with_multiple_tasks):
        """测试列出活跃任务"""
        manager, task_ids = task_manager_with_multiple_tasks
        
        active_tasks = await manager.list_active_tasks()
        
        # 应该有2个活跃任务（pending和running）
        assert len(active_tasks) == 2
        
        # 验证任务状态
        statuses = [task["status"] for task in active_tasks]
        assert "submitted" in statuses
        assert "running" in statuses
        assert "completed" not in statuses
    
    @pytest.mark.asyncio
    async def test_list_active_tasks_empty(self, task_manager_memory):
        """测试列出空的活跃任务列表"""
        active_tasks = await task_manager_memory.list_active_tasks()
        
        assert active_tasks == []
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tasks(self, task_manager_memory):
        """测试清理过期任务"""
        # 创建一个任务并手动设置为过期
        from core.interfaces import TaskSpec, TaskType
        
        task_spec = TaskSpec(task_id="expired-task", description="过期任务", task_type=TaskType.CODE)
        task_id = await task_manager_memory.submit_task(task_spec)
        
        # 手动设置更新时间为过去（cleanup_expired_tasks 检查的是 updated_at）
        task_data = task_manager_memory.active_tasks[task_id]
        expired_time = time.time() - 7200  # 2小时前的时间戳
        task_data["updated_at"] = expired_time
        
        # 执行清理（设置较短的超时时间）
        cleaned_count = await task_manager_memory.cleanup_expired_tasks(timeout_seconds=3600)
        
        assert cleaned_count == 1
        assert task_id not in task_manager_memory.active_tasks
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tasks_no_expired(self, task_manager_with_multiple_tasks):
        """测试清理没有过期任务的情况"""
        manager, task_ids = task_manager_with_multiple_tasks
        
        # 执行清理（使用默认超时时间）
        cleaned_count = await manager.cleanup_expired_tasks()
        
        assert cleaned_count == 0
        
        # 验证活跃任务仍然存在（已完成的任务会从 active_tasks 中移除）
        active_task_ids = [task_ids[0], task_ids[1]]  # task-1 和 task-2 仍然活跃
        for task_id in active_task_ids:
            assert task_id in manager.active_tasks
        
        # 验证已完成的任务在历史记录中
        completed_task_id = task_ids[2]  # task-3 已完成
        assert completed_task_id not in manager.active_tasks
        assert any(task['task_id'] == completed_task_id for task in manager.task_history)


class TestTaskManagerUtilityFunctions:
    """TaskManager工具函数测试"""
    
    def test_get_runtime_code_execution(self):
        """测试获取代码执行任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("code_execution")
        assert runtime == 300  # 5分钟
    
    def test_get_runtime_web_automation(self):
        """测试获取Web自动化任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("web_automation")
        assert runtime == 600  # 10分钟
    
    def test_get_runtime_data_analysis(self):
        """测试获取数据分析任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("data_analysis")
        assert runtime == 900  # 15分钟
    
    def test_get_runtime_file_processing(self):
        """测试获取文件处理任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("file_processing")
        assert runtime == 180  # 3分钟
    
    def test_get_runtime_unknown_type(self):
        """测试获取未知类型任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("unknown_task_type")
        assert runtime == 300  # 默认5分钟
    
    def test_get_runtime_none_type(self):
        """测试获取None类型任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime(None)
        assert runtime == 300  # 默认5分钟
    
    def test_get_runtime_empty_string(self):
        """测试获取空字符串类型任务的运行时间"""
        from core.task_manager import get_runtime
        
        runtime = get_runtime("")
        assert runtime == 300  # 默认5分钟


class TestTaskManagerRedisOperations:
    """TaskManager Redis操作测试"""
    
    @pytest_asyncio.fixture
    async def task_manager_redis_mock(self, task_manager_config):
        """创建Mock Redis的TaskManager"""
        mock_redis_client = AsyncMock()
        
        from core.task_manager import TaskManager
        manager = TaskManager(task_manager_config)
        
        # 设置mock Redis客户端
        manager.set_redis_client(mock_redis_client)
        
        return manager, mock_redis_client
    
    @pytest.mark.asyncio
    async def test_redis_get_task_status(self, task_manager_redis_mock, sample_task):
        """测试Redis模式下获取任务状态"""
        manager, mock_redis = task_manager_redis_mock
        
        # Mock Redis返回值
        task_data = {
            "task_id": sample_task["task_id"],
            "status": "running",
            "description": sample_task["description"],
            "created_at": sample_task["created_at"]
        }
        
        # 将字典转换为字节字符串（模拟Redis返回）
        redis_data = {k.encode(): json.dumps(v).encode() if isinstance(v, (dict, list)) else str(v).encode() 
                     for k, v in task_data.items()}
        
        mock_redis.hgetall.return_value = redis_data
        
        # 获取任务状态
        status = await manager.get_task_status(sample_task["task_id"])
        
        assert status is not None
        assert status["task_id"] == sample_task["task_id"]
        assert status["status"] == "running"
        
        # 验证Redis调用
        mock_redis.hgetall.assert_called_once_with(f"task:{sample_task['task_id']}")
    
    @pytest.mark.asyncio
    async def test_redis_update_task_status(self, task_manager_redis_mock, sample_task):
        """测试Redis模式下更新任务状态"""
        manager, mock_redis = task_manager_redis_mock
        
        # Mock Redis操作成功
        mock_redis.hset.return_value = True
        mock_redis.hget.return_value = b"pending"  # 模拟任务存在
        
        # 更新任务状态
        success = await manager.update_task_status(
            sample_task["task_id"], "running", "任务开始执行"
        )
        
        assert success == True
        
        # 验证Redis调用
        mock_redis.hget.assert_called_once_with(f"task:{sample_task['task_id']}", "status")
        mock_redis.hset.assert_called()
    
    @pytest.mark.asyncio
    async def test_redis_connection_error_fallback(self, task_manager_redis_mock, sample_task):
        """测试Redis连接错误时的回退处理"""
        manager, mock_redis = task_manager_redis_mock
        
        # Mock Redis操作失败
        mock_redis.hgetall.side_effect = RedisConnectionError("连接失败")
        
        # 尝试获取任务状态
        status = await manager.get_task_status(sample_task["task_id"])
        
        # 应该回退到内存模式并返回None（因为内存中没有数据）
        assert status is None
        assert manager.fallback_mode == True
    
    @pytest.mark.asyncio
    async def test_redis_list_active_tasks(self, task_manager_redis_mock):
        """测试Redis模式下列出活跃任务"""
        manager, mock_redis = task_manager_redis_mock
        
        # Mock Redis返回任务键列表
        mock_redis.keys.return_value = [b"task:task1", b"task:task2"]
        
        # Mock每个任务的数据
        task1_data = {b"status": b"pending", b"task_id": b"task1", b"description": b"task1"}
        task2_data = {b"status": b"running", b"task_id": b"task2", b"description": b"task2"}
        
        mock_redis.hgetall.side_effect = [task1_data, task2_data]
        
        # 获取活跃任务
        active_tasks = await manager.list_active_tasks()
        
        assert len(active_tasks) == 2
        assert active_tasks[0]["status"] == "pending"
        assert active_tasks[1]["status"] == "running"
        
        # 验证Redis调用
        mock_redis.keys.assert_called_once_with("task:*")
        assert mock_redis.hgetall.call_count == 2


if __name__ == "__main__":
    pytest.main(["-v", __file__])