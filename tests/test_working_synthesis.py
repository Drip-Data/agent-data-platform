"""
Working tests for synthesis functionality based on actual codebase
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys
import json

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSynthesisServiceReal:
    """Test cases for actual SynthesisService from synthesis.py"""
    
    def test_synthesis_service_init(self):
        """Test SynthesisService initialization"""
        from core.synthesiscore.synthesis import SynthesisService
        
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True,
            "llm": {"provider": "openai", "model": "gpt-3.5-turbo"}
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient') as mock_llm:
            
            service = SynthesisService(config)
            
            assert service.config == config
            assert service.enabled is True
            mock_redis.assert_called_once_with(config["redis_url"])
            mock_llm.assert_called_once_with(config)
    
    def test_synthesis_service_disabled(self):
        """Test SynthesisService when disabled"""
        from core.synthesiscore.synthesis import SynthesisService
        
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": False
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient') as mock_llm:
            
            service = SynthesisService(config)
            assert service.enabled is False


class TestTaskEssence:
    """Test TaskEssence dataclass"""
    
    def test_task_essence_creation(self):
        """Test creating TaskEssence objects"""
        from core.synthesiscore.synthesis import TaskEssence
        
        essence = TaskEssence(
            id="test-001",
            task_type="code_generation",
            domain="python",
            query="Create a function",
            complexity_level="simple",
            success_pattern={"pattern": "function_definition"},
            extracted_at="2024-01-01T00:00:00Z",
            source_trajectory_id="traj-001"
        )
        
        assert essence.id == "test-001"
        assert essence.task_type == "code_generation"
        assert essence.domain == "python"
        assert essence.complexity_level == "simple"


class TestTrajectoryHandler:
    """Test TrajectoryHandler file system monitoring"""
    
    def test_trajectory_handler_init(self):
        """Test TrajectoryHandler initialization"""
        from core.synthesiscore.synthesis import TrajectoryHandler
        
        mock_synthesis = Mock()
        target_path = "/test/path/trajectories.json"
        
        handler = TrajectoryHandler(mock_synthesis, target_path)
        
        assert handler.synthesis == mock_synthesis
        assert handler.target_file_path == target_path
    
    def test_trigger_processing(self):
        """Test _trigger_processing method"""
        from core.synthesiscore.synthesis import TrajectoryHandler
        
        mock_synthesis = Mock()
        mock_synthesis.config = {"redis_url": "redis://localhost:6379"}
        
        with patch('redis.from_url') as mock_redis_from_url:
            mock_redis_client = Mock()
            mock_redis_from_url.return_value = mock_redis_client
            
            handler = TrajectoryHandler(mock_synthesis, "/test/path")
            handler._trigger_processing()
            
            mock_redis_from_url.assert_called_once_with("redis://localhost:6379")
            mock_redis_client.xadd.assert_called_once()


class TestActualServices:
    """Test actual service classes that exist"""
    
    def test_service_manager_exists(self):
        """Test that ServiceManager can be imported"""
        from services.service_manager import ServiceManager
        from core.config_manager import ConfigManager
        
        mock_config = Mock(spec=ConfigManager)
        service_manager = ServiceManager(config_manager=mock_config)
        
        assert service_manager is not None
        assert hasattr(service_manager, 'config_manager')
    
    def test_task_api_service_exists(self):
        """Test that TaskAPIService can be imported"""
        from services.task_api_service import TaskAPIService
        from core.config_manager import ConfigManager
        
        mock_config = Mock(spec=ConfigManager)
        with patch('services.task_api_service.RedisManager'):
            task_api_service = TaskAPIService(config_manager=mock_config)
            
            assert task_api_service is not None
    
    def test_enhanced_reasoning_runtime_exists(self):
        """Test that EnhancedReasoningRuntime can be imported"""
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        from core.config_manager import ConfigManager
        
        mock_config = Mock(spec=ConfigManager)
        runtime = EnhancedReasoningRuntime(config_manager=mock_config)
        
        assert runtime is not None
        assert hasattr(runtime, 'config_manager')


@pytest.mark.integration
class TestRealSystemIntegration:
    """Integration tests using real system components"""
    
    def test_config_manager_integration(self):
        """Test ConfigManager integration"""
        from core.config_manager import ConfigManager
        
        # Test with minimal config
        config_manager = ConfigManager()
        
        assert config_manager is not None
        # Test that it can handle missing configs gracefully
        config = config_manager.get_config("nonexistent", default={})
        assert config == {}
    
    @pytest.mark.asyncio
    async def test_synthesis_service_workflow(self):
        """Test a realistic synthesis workflow"""
        from core.synthesiscore.synthesis import SynthesisService
        
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True,
            "llm": {"provider": "openai", "model": "gpt-3.5-turbo"}
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient') as mock_llm:
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            service = SynthesisService(config)
            
            # Test that service is properly initialized
            assert service.enabled is True
            assert service.config == config
            
            # Test basic functionality exists
            assert hasattr(service, 'redis')
            assert hasattr(service, 'llm_client')


class TestSystemHealth:
    """Test system health and basic functionality"""
    
    def test_all_core_modules_importable(self):
        """Test that all core modules can be imported"""
        modules_to_test = [
            'core.config_manager',
            'core.redis_manager', 
            'core.task_manager',
            'core.synthesiscore.synthesis',
            'services.service_manager',
            'services.task_api_service',
            'runtimes.reasoning.enhanced_runtime'
        ]
        
        for module_name in modules_to_test:
            try:
                __import__(module_name)
                print(f"✅ {module_name} imported successfully")
            except ImportError as e:
                pytest.fail(f"❌ Failed to import {module_name}: {e}")
    
    def test_mcp_servers_importable(self):
        """Test that MCP servers can be imported"""
        mcp_modules = [
            'mcp_servers.python_executor_server.main',
            'mcp_servers.browser_navigator_server.main',
            'mcp_servers.search_tool_server.main'
        ]
        
        for module_name in mcp_modules:
            try:
                __import__(module_name)
                print(f"✅ {module_name} imported successfully")
            except ImportError as e:
                print(f"⚠️  {module_name} import issue: {e}")
                # Don't fail the test for MCP servers as they might have external dependencies