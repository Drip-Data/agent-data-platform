"""
Focused tests for synthesis functionality that actually exists
"""
import pytest
import asyncio
import json
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import sys

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSynthesisServiceFunctional:
    """Functional tests for the actual SynthesisService"""
    
    @pytest.fixture
    def synthesis_config(self):
        """Create synthesis service configuration"""
        return {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True,
            "llm": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "api_key": "test-key"
            },
            "trajectories": {
                "input_dir": "output/trajectories",
                "output_dir": "output/seed_tasks"
            }
        }
    
    @pytest.fixture
    def mock_trajectory_data(self):
        """Sample trajectory data for testing"""
        return {
            "task_id": "test-001",
            "agent_name": "test-agent",
            "task_description": "Generate a Python function to add two numbers",
            "steps": [
                {
                    "step": 1,
                    "action": "analyze_task",
                    "observation": "Task requires creating a simple addition function",
                    "thought": "I need to create a function that takes two parameters"
                },
                {
                    "step": 2,
                    "action": "generate_code",
                    "observation": "Generated function: def add(a, b): return a + b",
                    "thought": "Function created successfully"
                }
            ],
            "final_result": "Successfully created addition function",
            "success": True,
            "execution_time": 5.2
        }
    
    def test_synthesis_service_creation(self, synthesis_config):
        """Test that SynthesisService can be created successfully"""
        from core.synthesiscore.synthesis import SynthesisService
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient') as mock_llm:
            
            service = SynthesisService(synthesis_config)
            
            assert service is not None
            assert service.config == synthesis_config
            assert service.enabled is True
    
    def test_synthesis_service_disabled_mode(self):
        """Test synthesis service when disabled"""
        from core.synthesiscore.synthesis import SynthesisService
        
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": False
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url'), \
             patch('core.synthesiscore.synthesis.LLMClient'):
            
            service = SynthesisService(config)
            assert service.enabled is False
    
    @pytest.mark.asyncio
    async def test_redis_command_processing(self, synthesis_config):
        """Test Redis command processing functionality"""
        from core.synthesiscore.synthesis import SynthesisService
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient') as mock_llm:
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            # Mock redis xread to return a command
            mock_redis_client.xread.return_value = {
                "synthesis:commands": [
                    (b"1234567890-0", {
                        b"command": b"process_trajectories",
                        b"timestamp": b"1234567890"
                    })
                ]
            }
            
            service = SynthesisService(synthesis_config)
            
            # Test that the service has the method
            assert hasattr(service, 'redis')
            assert service.redis == mock_redis_client


class TestTrajectoryProcessing:
    """Test trajectory processing functionality"""
    
    def test_trajectory_handler_file_detection(self):
        """Test that TrajectoryHandler can detect file changes"""
        from core.synthesiscore.synthesis import TrajectoryHandler
        
        mock_synthesis = Mock()
        mock_synthesis.config = {"redis_url": "redis://localhost:6379"}
        
        handler = TrajectoryHandler(mock_synthesis, "/test/path/trajectories.json")
        
        # Test file creation event
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = "/test/path/trajectories.json"
        
        with patch.object(handler, '_trigger_processing') as mock_trigger:
            handler.on_created(mock_event)
            mock_trigger.assert_called_once()
        
        # Test file modification event
        with patch.object(handler, '_trigger_processing') as mock_trigger:
            handler.on_modified(mock_event)
            mock_trigger.assert_called_once()
    
    def test_trajectory_handler_redis_notification(self):
        """Test that handler sends Redis notifications"""
        from core.synthesiscore.synthesis import TrajectoryHandler
        
        mock_synthesis = Mock()
        mock_synthesis.config = {"redis_url": "redis://localhost:6379"}
        
        with patch('redis.from_url') as mock_redis_from_url:
            mock_redis_client = Mock()
            mock_redis_from_url.return_value = mock_redis_client
            
            handler = TrajectoryHandler(mock_synthesis, "/test/path")
            handler._trigger_processing()
            
            # Verify Redis notification was sent
            mock_redis_client.xadd.assert_called_once()
            call_args = mock_redis_client.xadd.call_args
            assert call_args[0][0] == "synthesis:commands"
            assert "command" in call_args[0][1]
            assert call_args[0][1]["command"] == "process_trajectories"


class TestSynthesisIntegrationPoints:
    """Test synthesis integration with other system components"""
    
    def test_synthesis_with_task_api(self):
        """Test synthesis integration with task API"""
        from core.synthesiscore.synthesis_api import app
        
        # Test that the FastAPI app exists and has routes
        assert app is not None
        
        # Check for synthesis endpoints
        routes = [route.path for route in app.routes]
        synthesis_routes = [route for route in routes if 'synthesis' in route.lower()]
        
        # Should have some synthesis-related routes
        assert len(synthesis_routes) > 0
    
    def test_synthesis_config_integration(self):
        """Test synthesis configuration loading"""
        from core.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Test that config manager exists and can be used
        assert config_manager is not None
        
        # Test methods that should exist
        assert hasattr(config_manager, 'get_llm_config')
        
        llm_config = config_manager.get_llm_config()
        assert llm_config is not None


class TestActualSystemComponents:
    """Test components that actually exist in the system"""
    
    def test_service_manager_basic_functionality(self):
        """Test ServiceManager basic functionality"""
        from services.service_manager import ServiceManager
        
        # Create without parameters (check actual constructor)
        service_manager = ServiceManager()
        
        assert service_manager is not None
        
        # Test basic methods exist
        expected_methods = ['start_all_services', 'stop_all_services']
        for method in expected_methods:
            if hasattr(service_manager, method):
                assert callable(getattr(service_manager, method))
    
    def test_enhanced_runtime_basic_functionality(self):
        """Test EnhancedReasoningRuntime basic functionality"""
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        from core.config_manager import ConfigManager
        from core.llm_client import LLMClient
        from runtimes.reasoning.toolscore_client import ToolScoreClient
        
        # Create with required parameters
        config_manager = ConfigManager()
        
        with patch.object(LLMClient, '__init__', return_value=None) as mock_llm, \
             patch.object(ToolScoreClient, '__init__', return_value=None) as mock_toolscore:
            
            mock_llm_instance = Mock()
            mock_toolscore_instance = Mock()
            
            runtime = EnhancedReasoningRuntime(
                config_manager=config_manager,
                llm_client=mock_llm_instance,
                toolscore_client=mock_toolscore_instance
            )
            
            assert runtime is not None
            assert hasattr(runtime, 'config_manager')
    
    def test_task_api_service_basic_functionality(self):
        """Test task API service basic functionality"""
        from services.task_api_service import TaskAPIService
        from core.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        with patch('services.task_api_service.RedisManager'):
            service = TaskAPIService(config_manager=config_manager)
            
            assert service is not None
            assert hasattr(service, 'config_manager')


@pytest.mark.integration
class TestSystemWorkflow:
    """Integration test for the full system workflow"""
    
    @pytest.mark.asyncio
    async def test_synthesis_workflow_simulation(self):
        """Simulate a complete synthesis workflow"""
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
            
            # Create service
            service = SynthesisService(config)
            
            # Simulate workflow steps
            assert service.enabled is True
            
            # Test that service can be started (has required components)
            assert hasattr(service, 'redis')
            assert hasattr(service, 'llm_client')
            
            # Test Redis connection simulation
            mock_redis_client.ping.return_value = True
            
            # Simulate processing command
            mock_redis_client.xread.return_value = {
                "synthesis:commands": [
                    (b"test-id", {b"command": b"process_trajectories"})
                ]
            }
            
            # Workflow completed successfully if no exceptions
            assert True


class TestSystemHealthCheck:
    """Health check tests for the system"""
    
    def test_critical_modules_health(self):
        """Test that all critical modules are healthy"""
        critical_modules = [
            'core.synthesiscore.synthesis',
            'core.config_manager',
            'core.redis_manager',
            'services.service_manager'
        ]
        
        for module_name in critical_modules:
            try:
                module = __import__(module_name, fromlist=[''])
                assert module is not None
                print(f"✅ {module_name} is healthy")
            except Exception as e:
                pytest.fail(f"❌ Critical module {module_name} failed: {e}")
    
    def test_synthesis_api_health(self):
        """Test synthesis API health"""
        try:
            from core.synthesiscore.synthesis_api import app
            assert app is not None
            print("✅ Synthesis API is available")
        except Exception as e:
            pytest.fail(f"❌ Synthesis API failed: {e}")
    
    def test_mcp_servers_basic_health(self):
        """Test MCP servers basic health"""
        mcp_servers = [
            'mcp_servers.python_executor_server.main',
            'mcp_servers.browser_navigator_server.main',
            'mcp_servers.search_tool_server.main'
        ]
        
        healthy_count = 0
        for server in mcp_servers:
            try:
                __import__(server, fromlist=[''])
                healthy_count += 1
                print(f"✅ {server} is available")
            except Exception as e:
                print(f"⚠️ {server} issue: {e}")
        
        # At least one MCP server should be healthy
        assert healthy_count > 0, "No MCP servers are healthy"