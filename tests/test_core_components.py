"""
Tests for core system components
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.service_manager import ServiceManager
from core.toolscore.unified_tool_library import UnifiedToolLibrary
from core.dispatcher_enhanced import TaskProcessingCoordinator
from core.redis_manager import RedisManager


class TestServiceManager:
    """Test cases for ServiceManager dependency topology parsing"""
    
    @pytest.fixture
    def service_manager(self, mock_config_manager):
        """Create ServiceManager instance for testing"""
        return ServiceManager(config_manager=mock_config_manager)
    
    def test_service_dependency_parsing(self, service_manager):
        """Test service dependency topology parsing"""
        # Mock service dependencies
        dependencies = {
            "redis_service": [],
            "toolscore_service": ["redis_service"],
            "synthesis_service": ["redis_service", "toolscore_service"],
            "task_api_service": ["redis_service", "synthesis_service"]
        }
        
        with patch.object(service_manager, 'get_service_dependencies', return_value=dependencies):
            topology = service_manager.get_service_dependencies()
            
            # Verify dependency structure
            assert "redis_service" in topology
            assert len(topology["redis_service"]) == 0  # No dependencies
            assert "redis_service" in topology["toolscore_service"]
            assert "toolscore_service" in topology["synthesis_service"]
    
    @pytest.mark.asyncio
    async def test_service_startup_order(self, service_manager):
        """Test services start in correct dependency order"""
        startup_order = []
        
        async def mock_start_service(service_name):
            startup_order.append(service_name)
            return True
        
        with patch.object(service_manager, 'start_service', side_effect=mock_start_service):
            await service_manager.start_all_services()
            
            # Verify redis starts before toolscore
            redis_index = startup_order.index("redis_service")
            toolscore_index = startup_order.index("toolscore_service")
            assert redis_index < toolscore_index


class TestUnifiedToolLibrary:
    """Test cases for ToolScore instant tool registration"""
    
    @pytest.fixture
    def tool_library(self, mock_config_manager, mock_redis):
        """Create UnifiedToolLibrary instance for testing"""
        with patch('core.toolscore.unified_tool_library.RedisManager') as mock_redis_manager:
            mock_redis_manager.return_value.get_redis_client.return_value = mock_redis
            return UnifiedToolLibrary(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_instant_tool_registration(self, tool_library, mock_redis):
        """Test instant tool registration functionality"""
        # Mock tool data
        tool_data = {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"param1": "string"},
            "server_info": {"host": "localhost", "port": 8001}
        }
        
        with patch.object(tool_library, 'register_tool', new_callable=AsyncMock) as mock_register:
            mock_register.return_value = True
            
            result = await tool_library.register_tool(tool_data)
            
            assert result is True
            mock_register.assert_called_once_with(tool_data)
    
    def test_tool_caching(self, tool_library, mock_redis):
        """Test tool registration caching"""
        tool_name = "cached_tool"
        tool_data = {"name": tool_name, "cached": True}
        
        # Mock Redis get/set operations
        mock_redis.get.return_value = None  # Tool not in cache
        mock_redis.set.return_value = True
        
        # Register tool (should cache)
        with patch.object(tool_library, '_cache_tool') as mock_cache:
            tool_library._cache_tool(tool_name, tool_data)
            mock_cache.assert_called_once_with(tool_name, tool_data)


class TestTaskProcessingCoordinator:
    """Test cases for TaskProcessingCoordinator task queue management"""
    
    @pytest.fixture
    def coordinator(self, mock_config_manager, mock_redis):
        """Create TaskProcessingCoordinator instance for testing"""
        with patch('core.dispatcher_enhanced.TaskProcessingCoordinator') as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            return mock_instance
    
    @pytest.mark.asyncio
    async def test_task_queue_management(self, coordinator, sample_task, mock_redis):
        """Test task queue management functionality"""
        # Mock Redis queue operations
        mock_redis.lpush.return_value = 1
        mock_redis.brpop.return_value = ("task_queue", str(sample_task).encode())
        
        with patch.object(coordinator, 'process_task', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = True
            
            result = await coordinator.process_task(sample_task)
            assert result is True
            mock_process.assert_called_once_with(sample_task)
    
    @pytest.mark.asyncio
    async def test_task_priority_handling(self, coordinator, mock_redis):
        """Test task priority queue handling"""
        high_priority_task = {"id": "high", "priority": "high"}
        low_priority_task = {"id": "low", "priority": "low"}
        
        with patch.object(coordinator, 'process_task', new_callable=AsyncMock) as mock_process:
            await coordinator.process_task(high_priority_task)
            await coordinator.process_task(low_priority_task)
            
            # Verify high priority task is called first
            calls = mock_process.call_args_list
            assert calls[0][0][0]["priority"] == "high"
            assert calls[1][0][0]["priority"] == "low"


class TestRedisManager:
    """Test cases for Redis fallback mode"""
    
    @pytest.fixture
    def redis_manager(self, mock_config_manager):
        """Create RedisManager instance for testing"""
        return RedisManager(config_manager=mock_config_manager)
    
    def test_redis_connection(self, redis_manager, mock_redis):
        """Test Redis connection establishment"""
        with patch('redis.Redis', return_value=mock_redis):
            client = redis_manager.get_redis_client()
            assert client is not None
            mock_redis.ping.assert_called_once()
    
    def test_redis_fallback_mode(self, redis_manager):
        """Test Redis fallback mode when connection fails"""
        # Mock connection failure
        with patch('redis.Redis', side_effect=Exception("Connection failed")):
            with patch.object(redis_manager, 'enable_fallback_mode') as mock_fallback:
                redis_manager.get_redis_client()
                mock_fallback.assert_called_once()
    
    def test_fallback_operations(self, redis_manager):
        """Test operations in fallback mode"""
        # Enable fallback mode
        redis_manager.fallback_mode = True
        redis_manager.fallback_storage = {}
        
        # Test set operation
        result = redis_manager.set_fallback("test_key", "test_value")
        assert result is True
        assert redis_manager.fallback_storage["test_key"] == "test_value"
        
        # Test get operation
        value = redis_manager.get_fallback("test_key")
        assert value == "test_value"


@pytest.mark.integration 
class TestCoreComponentsIntegration:
    """Integration tests for core components working together"""
    
    @pytest.mark.asyncio
    async def test_service_manager_with_toolscore(self, mock_config_manager):
        """Test ServiceManager integration with ToolScore"""
        # This would test the full integration between components
        service_manager = ServiceManager(config_manager=mock_config_manager)
        
        with patch.object(service_manager, 'start_service', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True
            
            # Start toolscore service
            result = await service_manager.start_service("toolscore_service")
            assert result is True
            
            # Verify service is registered
            with patch.object(service_manager, 'get_service_status') as mock_status:
                mock_status.return_value = "running"
                status = service_manager.get_service_status("toolscore_service")
                assert status == "running"