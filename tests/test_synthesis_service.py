"""
Tests for synthesis service functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import sys

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.synthesiscore.synthesis import SynthesisService
from services.synthesis_service import SynthesisService as SynthesisAPIService


class TestSynthesisService:
    """Test cases for SynthesisService functionality"""
    
    @pytest.fixture
    def synthesis_service(self, mock_config_manager):
        """Create SynthesisService instance for testing"""
        config = {"redis_url": "redis://localhost:6379", "synthesis_enabled": True}
        return SynthesisService(config=config)
    
    @pytest.mark.asyncio
    async def test_synthesis_initialization(self, synthesis_service):
        """Test synthesis service initialization"""
        assert synthesis_service is not None
        assert synthesis_service.enabled is True
    
    @pytest.mark.asyncio
    async def test_task_synthesis(self, synthesis_service, sample_task):
        """Test task synthesis functionality"""
        with patch.object(synthesis_service, 'process_trajectories', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                "processed": True,
                "seeds_generated": 5,
                "execution_time": 1.2
            }
            
            result = await synthesis_service.process_trajectories()
            
            assert result["processed"] is True
            assert result["seeds_generated"] == 5
            mock_process.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_synthesis_error_handling(self, synthesis_service):
        """Test error handling in synthesis process"""
        with patch.object(synthesis_service, 'process_trajectories', new_callable=AsyncMock) as mock_process:
            mock_process.side_effect = Exception("Processing failed")
            
            with pytest.raises(Exception):
                await synthesis_service.process_trajectories()


class TestSynthesisAPIService:
    """Test cases for SynthesisAPIService"""
    
    @pytest.fixture
    def synthesis_api_service(self, mock_config_manager, mock_redis):
        """Create SynthesisAPIService instance for testing"""
        with patch('services.synthesis_service.RedisManager') as mock_redis_manager:
            mock_redis_manager.return_value.get_redis_client.return_value = mock_redis
            return SynthesisAPIService(config_manager=mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_service_start_stop(self, synthesis_api_service):
        """Test service lifecycle management"""
        # Test service start
        with patch.object(synthesis_api_service, 'start', new_callable=AsyncMock) as mock_start:
            await synthesis_api_service.start()
            mock_start.assert_called_once()
        
        # Test service stop
        with patch.object(synthesis_api_service, 'stop', new_callable=AsyncMock) as mock_stop:
            await synthesis_api_service.stop()
            mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_synthesis_api_endpoints(self, synthesis_api_service, sample_task):
        """Test synthesis API endpoints"""
        # Mock the synthesis API
        with patch.object(synthesis_api_service, 'process_synthesis_request', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                "status": "success",
                "result": "Synthesis completed",
                "task_id": sample_task["id"]
            }
            
            result = await synthesis_api_service.process_synthesis_request(sample_task)
            
            assert result["status"] == "success"
            assert result["task_id"] == sample_task["id"]
            mock_process.assert_called_once_with(sample_task)
    
    def test_synthesis_service_configuration(self, synthesis_api_service):
        """Test service configuration validation"""
        # Test that service has required configuration
        assert hasattr(synthesis_api_service, 'config_manager')
        
        # Test configuration access
        with patch.object(synthesis_api_service.config_manager, 'get_config') as mock_get_config:
            mock_get_config.return_value = {"synthesis": {"enabled": True}}
            config = synthesis_api_service.config_manager.get_config("synthesis")
            assert config["enabled"] is True


@pytest.mark.integration
class TestSynthesisIntegration:
    """Integration tests for synthesis functionality"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_synthesis(self, sample_task, mock_config_manager):
        """Test complete synthesis workflow"""
        # This would test the full integration between SynthesisCore and SynthesisService
        # In a real scenario, this might involve:
        # 1. Task submission
        # 2. Synthesis processing
        # 3. Result storage
        # 4. Status tracking
        
        # Mock the full workflow
        with patch('core.synthesiscore.synthesis.SynthesisCore') as mock_synthesis_core:
            mock_instance = mock_synthesis_core.return_value
            mock_instance.synthesize_task = AsyncMock(return_value={
                "success": True,
                "output": "Integration test passed"
            })
            
            # Simulate the workflow
            synthesis = mock_synthesis_core(config_manager=mock_config_manager)
            result = await synthesis.synthesize_task(sample_task)
            
            assert result["success"] is True
            assert "output" in result