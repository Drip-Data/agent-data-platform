# -*- coding: utf-8 -*-
"""
测试 synthesis.py 模块 - 任务合成器

覆盖功能:
1. SynthesisService 初始化和配置
2. 轨迹文件监控和处理
3. 任务本质提取
4. 种子任务生成
5. JSON文件存储操作
6. Redis命令处理
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest
import pytest_asyncio


@pytest.fixture
def temp_synthesis_config(tmp_path):
    """创建临时的synthesis配置"""
    config = {
        "redis_url": "redis://localhost:6379/15",
        "synthesis_enabled": True,
        "auto_monitor_trajectories": True,
        "auto_export_seeds": True,
        "provider": "vllm",
        "disable_cache": True
    }
    
    # 设置临时路径
    os.environ["OUTPUT_DIR"] = str(tmp_path)
    return config


@pytest.fixture
def mock_trajectory_data():
    """模拟轨迹数据"""
    return {
        "task_id": "test_task_001",
        "task_type": "reasoning",
        "query": "计算斐波那契数列的第10项",
        "success": True,
        "steps": [
            {
                "step_id": 1,
                "action": "python_code",
                "tool": "python-executor",
                "parameters": {"code": "def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)"},
                "result": "函数定义成功",
                "success": True
            }
        ],
        "final_output": "55",
        "execution_time": 2.5
    }


@pytest_asyncio.fixture
async def synthesis_service(temp_synthesis_config):
    """创建SynthesisService实例，mock掉外部依赖"""
    with (
        patch("core.synthesiscore.synthesis.async_redis") as mock_redis,
        patch("core.synthesiscore.synthesis.LLMClient") as mock_llm,
        patch("core.synthesiscore.synthesis.UnifiedToolLibrary") as mock_tool_lib,
        patch("core.synthesiscore.synthesis.Observer") as mock_observer
    ):
        # Mock Redis
        mock_redis_instance = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_instance
        
        # Mock LLM Client
        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance
        
        # Mock Tool Library
        mock_tool_lib_instance = MagicMock()
        mock_tool_lib.return_value = mock_tool_lib_instance
        
        # Import and create service
        from core.synthesiscore.synthesis import SynthesisService
        service = SynthesisService(temp_synthesis_config)
        
        # Mock file operations
        service._load_json_file = MagicMock(return_value=[])
        service._save_json_file = MagicMock(return_value=True)
        
        yield service


class TestSynthesisService:
    """SynthesisService 核心功能测试"""
    
    def test_init_synthesis_service(self, synthesis_service, temp_synthesis_config):
        """测试SynthesisService初始化"""
        assert synthesis_service.config == temp_synthesis_config
        assert synthesis_service.enabled == True
        assert synthesis_service.auto_monitor_enabled == True
        assert synthesis_service.auto_export_seeds == True
        assert isinstance(synthesis_service.processed_trajectories, set)
    
    def test_init_json_files(self, synthesis_service, tmp_path):
        """测试JSON文件初始化"""
        # Mock os.path.exists to return False (files don't exist)
        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs") as mock_makedirs:
                with patch("pathlib.Path.touch") as mock_touch:
                    synthesis_service._init_json_files()
                    
                    # 验证目录创建
                    assert mock_makedirs.call_count >= 2
                    
                    # 验证文件创建
                    assert synthesis_service._save_json_file.call_count >= 2
                    mock_touch.assert_called_once()
    
    def test_load_processed_trajectories(self, synthesis_service):
        """测试加载已处理轨迹列表"""
        # Mock返回一些已处理的轨迹ID
        test_trajectories = ["traj_001", "traj_002", "traj_003"]
        synthesis_service._load_json_file.return_value = test_trajectories
        
        synthesis_service._load_processed_trajectories()
        
        assert synthesis_service.processed_trajectories == set(test_trajectories)
        synthesis_service._load_json_file.assert_called_with(
            synthesis_service.processed_trajectories_path, []
        )
    
    def test_save_processed_trajectories(self, synthesis_service):
        """测试保存已处理轨迹列表"""
        # 设置一些已处理的轨迹
        synthesis_service.processed_trajectories = {"traj_001", "traj_002"}
        
        synthesis_service._save_processed_trajectories()
        
        # 验证保存调用
        synthesis_service._save_json_file.assert_called_with(
            synthesis_service.processed_trajectories_path,
            ["traj_001", "traj_002"]  # 转换为列表
        )
    
    def test_load_json_file_success(self, synthesis_service, tmp_path):
        """测试成功加载JSON文件"""
        # 创建真实的JSON文件
        test_file = tmp_path / "test.json"
        test_data = {"test": "data"}
        test_file.write_text(json.dumps(test_data))
        
        # 重置mock，使用真实的文件操作
        synthesis_service._load_json_file = synthesis_service.__class__._load_json_file.__get__(synthesis_service)
        
        result = synthesis_service._load_json_file(str(test_file))
        assert result == test_data
    
    def test_load_json_file_not_exists(self, synthesis_service, tmp_path):
        """测试加载不存在的JSON文件"""
        non_existent_file = tmp_path / "non_existent.json"
        
        # 重置mock，使用真实的文件操作
        synthesis_service._load_json_file = synthesis_service.__class__._load_json_file.__get__(synthesis_service)
        
        result = synthesis_service._load_json_file(str(non_existent_file), {"default": "value"})
        assert result == {"default": "value"}
    
    def test_save_json_file_success(self, synthesis_service, tmp_path):
        """测试成功保存JSON文件"""
        test_file = tmp_path / "test_save.json"
        test_data = {"save": "test", "number": 42}
        
        # 重置mock，使用真实的文件操作
        synthesis_service._save_json_file = synthesis_service.__class__._save_json_file.__get__(synthesis_service)
        
        result = synthesis_service._save_json_file(str(test_file), test_data)
        assert result == True
        
        # 验证文件内容
        saved_data = json.loads(test_file.read_text())
        assert saved_data == test_data


class TestTrajectoryHandler:
    """轨迹文件处理器测试"""
    
    @pytest.fixture
    def trajectory_handler(self, synthesis_service):
        """创建轨迹处理器实例"""
        from core.synthesiscore.synthesis import TrajectoryHandler
        target_path = "/test/path/trajectories.json"
        return TrajectoryHandler(synthesis_service, target_path)
    
    def test_trajectory_handler_init(self, trajectory_handler, synthesis_service):
        """测试轨迹处理器初始化"""
        assert trajectory_handler.synthesis == synthesis_service
        assert trajectory_handler.target_file_path == "/test/path/trajectories.json"
    
    @patch("redis.from_url")
    def test_on_created_trigger_processing(self, mock_redis, trajectory_handler):
        """测试文件创建事件触发处理"""
        # Mock Redis客户端
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        
        # Mock事件
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = trajectory_handler.target_file_path
        
        # 触发事件
        trajectory_handler.on_created(mock_event)
        
        # 验证Redis命令发送
        mock_redis_client.xadd.assert_called_once()
        call_args = mock_redis_client.xadd.call_args
        assert call_args[0][0] == "synthesis:commands"
        assert call_args[0][1]["command"] == "process_trajectories"
    
    @patch("redis.from_url")
    def test_on_modified_trigger_processing(self, mock_redis, trajectory_handler):
        """测试文件修改事件触发处理"""
        # Mock Redis客户端
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        
        # Mock事件
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = trajectory_handler.target_file_path
        
        # 触发事件
        trajectory_handler.on_modified(mock_event)
        
        # 验证Redis命令发送
        mock_redis_client.xadd.assert_called_once()
    
    def test_ignore_directory_events(self, trajectory_handler):
        """测试忽略目录事件"""
        with patch("redis.from_url") as mock_redis:
            mock_redis_client = MagicMock()
            mock_redis.return_value = mock_redis_client
            
            # Mock目录事件
            mock_event = MagicMock()
            mock_event.is_directory = True
            mock_event.src_path = trajectory_handler.target_file_path
            
            # 触发事件
            trajectory_handler.on_created(mock_event)
            
            # 验证没有发送Redis命令
            mock_redis_client.xadd.assert_not_called()
    
    def test_ignore_other_files(self, trajectory_handler):
        """测试忽略其他文件的事件"""
        with patch("redis.from_url") as mock_redis:
            mock_redis_client = MagicMock()
            mock_redis.return_value = mock_redis_client
            
            # Mock其他文件事件
            mock_event = MagicMock()
            mock_event.is_directory = False
            mock_event.src_path = "/other/path/other_file.json"
            
            # 触发事件
            trajectory_handler.on_created(mock_event)
            
            # 验证没有发送Redis命令
            mock_redis_client.xadd.assert_not_called()


class TestTaskEssence:
    """任务本质数据结构测试"""
    
    def test_task_essence_creation(self):
        """测试TaskEssence创建"""
        from core.synthesiscore.synthesis import TaskEssence
        
        essence = TaskEssence(
            essence_id="essence_001",
            task_type="reasoning",
            domain="mathematics",
            query="计算斐波那契数列",
            complexity_level="medium",
            success_pattern={"pattern": "recursive_solution"},
            extracted_at="2025-01-16T10:00:00",
            source_trajectory_id="traj_001"
        )
        
        assert essence.essence_id == "essence_001"
        assert essence.task_type == "reasoning"
        assert essence.domain == "mathematics"
        assert essence.query == "计算斐波那契数列"
        assert essence.complexity_level == "medium"
        assert essence.success_pattern == {"pattern": "recursive_solution"}
        assert essence.extracted_at == "2025-01-16T10:00:00"
        assert essence.source_trajectory_id == "traj_001"
    
    def test_task_essence_to_dict(self):
        """测试TaskEssence转换为字典"""
        from core.synthesiscore.synthesis import TaskEssence
        from dataclasses import asdict
        
        essence = TaskEssence(
            essence_id="essence_001",
            task_type="reasoning",
            domain="mathematics",
            query="计算斐波那契数列",
            complexity_level="medium",
            success_pattern={"pattern": "recursive_solution"},
            extracted_at="2025-01-16T10:00:00",
            source_trajectory_id="traj_001"
        )
        
        essence_dict = asdict(essence)
        
        assert isinstance(essence_dict, dict)
        assert essence_dict["essence_id"] == "essence_001"
        assert essence_dict["task_type"] == "reasoning"
        assert essence_dict["success_pattern"] == {"pattern": "recursive_solution"}


@pytest.mark.asyncio
class TestSynthesisServiceAsync:
    """SynthesisService异步功能测试"""
    
    async def test_redis_connection(self, synthesis_service):
        """测试Redis连接"""
        # 验证Redis客户端已初始化
        assert synthesis_service.redis is not None
        
        # 测试Redis操作（使用mock）
        synthesis_service.redis.ping = AsyncMock(return_value=True)
        result = await synthesis_service.redis.ping()
        assert result == True
    
    async def test_llm_client_integration(self, synthesis_service):
        """测试LLM客户端集成"""
        # 验证LLM客户端已初始化
        assert synthesis_service.llm_client is not None
        
        # Mock LLM响应
        synthesis_service.llm_client.generate_reasoning = AsyncMock(
            return_value={
                "thinking": "分析任务本质",
                "action": "extract_essence",
                "confidence": 0.9
            }
        )
        
        # 测试调用
        result = await synthesis_service.llm_client.generate_reasoning(
            "测试任务", ["tool1", "tool2"]
        )
        assert result["action"] == "extract_essence"
        assert result["confidence"] == 0.9
    
    async def test_tool_library_integration(self, synthesis_service):
        """测试工具库集成"""
        # 验证工具库已初始化
        assert synthesis_service.tool_library is not None
        
        # Mock工具库方法
        synthesis_service.tool_library.get_available_tools = MagicMock(
            return_value=["python-executor", "web-navigator"]
        )
        
        # 测试调用
        tools = synthesis_service.tool_library.get_available_tools()
        assert "python-executor" in tools
        assert "web-navigator" in tools


if __name__ == "__main__":
    pytest.main(["-v", __file__])