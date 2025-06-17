"""
Tests for service management modules
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime

from services.service_manager import ServiceManager
from services.mcp_server_launcher import MCPServerLauncher
from services.task_api_service import TaskAPIService
from services.toolscore_service import ToolScoreService
from services.redis_service import RedisService


class TestServiceManager:
    """Test ServiceManager class"""
    
    @pytest.fixture
    def service_manager(self, mock_config_manager):
        """Create ServiceManager instance for testing"""
        return ServiceManager(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, service_manager):
        """Test ServiceManager initialization"""
        assert service_manager is not None
        assert hasattr(service_manager, 'config_manager')
        assert hasattr(service_manager, 'services')
        assert hasattr(service_manager, 'is_running')
    
    @pytest.mark.asyncio
    async def test_register_service(self, service_manager):
        """Test registering a service"""
        mock_service = AsyncMock()
        mock_service.name = "test_service"
        
        service_manager.register_service(mock_service)
        
        assert "test_service" in service_manager.services
        assert service_manager.services["test_service"] == mock_service
    
    @pytest.mark.asyncio
    async def test_start_all_services(self, service_manager):
        """Test starting all services"""
        mock_service1 = AsyncMock()
        mock_service1.name = "service1"
        mock_service1.start.return_value = True
        
        mock_service2 = AsyncMock()
        mock_service2.name = "service2"
        mock_service2.start.return_value = True
        
        service_manager.register_service(mock_service1)
        service_manager.register_service(mock_service2)
        
        result = await service_manager.start_all()
        
        assert result is True
        assert service_manager.is_running is True
        mock_service1.start.assert_called_once()
        mock_service2.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_service_failure(self, service_manager):
        """Test handling service start failure"""
        mock_service = AsyncMock()
        mock_service.name = "failing_service"
        mock_service.start.side_effect = Exception("Start failed")
        
        service_manager.register_service(mock_service)
        
        result = await service_manager.start_all()
        
        assert result is False
        assert service_manager.is_running is False
    
    @pytest.mark.asyncio
    async def test_stop_all_services(self, service_manager):
        """Test stopping all services"""
        mock_service1 = AsyncMock()
        mock_service1.name = "service1"
        mock_service1.stop.return_value = True
        
        mock_service2 = AsyncMock()
        mock_service2.name = "service2"
        mock_service2.stop.return_value = True
        
        service_manager.register_service(mock_service1)
        service_manager.register_service(mock_service2)
        service_manager.is_running = True
        
        result = await service_manager.stop_all()
        
        assert result is True
        assert service_manager.is_running is False
        mock_service1.stop.assert_called_once()
        mock_service2.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_restart_service(self, service_manager):
        """Test restarting a specific service"""
        mock_service = AsyncMock()
        mock_service.name = "test_service"
        mock_service.stop.return_value = True
        mock_service.start.return_value = True
        
        service_manager.register_service(mock_service)
        
        result = await service_manager.restart_service("test_service")
        
        assert result is True
        mock_service.stop.assert_called_once()
        mock_service.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_restart_nonexistent_service(self, service_manager):
        """Test restarting a non-existent service"""
        result = await service_manager.restart_service("nonexistent_service")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_service_status(self, service_manager):
        """Test getting service status"""
        mock_service = AsyncMock()
        mock_service.name = "test_service"
        mock_service.health_check.return_value = {"status": "healthy", "uptime": 3600}
        
        service_manager.register_service(mock_service)
        
        status = await service_manager.get_service_status("test_service")
        
        assert status["status"] == "healthy"
        assert status["uptime"] == 3600
        mock_service.health_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_all_services_status(self, service_manager):
        """Test getting status of all services"""
        mock_service1 = AsyncMock()
        mock_service1.name = "service1"
        mock_service1.health_check.return_value = {"status": "healthy"}
        
        mock_service2 = AsyncMock()
        mock_service2.name = "service2"
        mock_service2.health_check.return_value = {"status": "degraded"}
        
        service_manager.register_service(mock_service1)
        service_manager.register_service(mock_service2)
        
        statuses = await service_manager.get_all_services_status()
        
        assert len(statuses) == 2
        assert statuses["service1"]["status"] == "healthy"
        assert statuses["service2"]["status"] == "degraded"
    
    @pytest.mark.asyncio
    async def test_service_dependency_management(self, service_manager):
        """Test service dependency management"""
        # Create services with dependencies
        mock_service_a = AsyncMock()
        mock_service_a.name = "service_a"
        mock_service_a.dependencies = []
        mock_service_a.start.return_value = True
        
        mock_service_b = AsyncMock()
        mock_service_b.name = "service_b"
        mock_service_b.dependencies = ["service_a"]
        mock_service_b.start.return_value = True
        
        service_manager.register_service(mock_service_a)
        service_manager.register_service(mock_service_b)
        
        result = await service_manager.start_all()
        
        assert result is True
        # Service A should start before Service B
        mock_service_a.start.assert_called_once()
        mock_service_b.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_monitoring(self, service_manager):
        """Test health monitoring functionality"""
        mock_service = AsyncMock()
        mock_service.name = "monitored_service"
        mock_service.health_check.return_value = {"status": "healthy"}
        
        service_manager.register_service(mock_service)
        
        # Start health monitoring
        with patch.object(service_manager, '_health_check_interval', 0.1):
            health_task = asyncio.create_task(service_manager.start_health_monitoring())
            
            # Let it run for a short time
            await asyncio.sleep(0.2)
            health_task.cancel()
            
            # Health check should have been called multiple times
            assert mock_service.health_check.call_count >= 1


class TestMCPServerLauncher:
    """Test MCPServerLauncher class"""
    
    @pytest.fixture
    def mcp_launcher(self, mock_config_manager):
        """Create MCPServerLauncher instance for testing"""
        mock_config_manager.get_ports_config.return_value = {
            'mcp_servers': {
                'python_executor': {'port': 8083},
                'browser_navigator': {'port': 8084},
                'search_tool': {'port': 8085}
            }
        }
        return MCPServerLauncher(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, mcp_launcher):
        """Test MCPServerLauncher initialization"""
        assert mcp_launcher is not None
        assert hasattr(mcp_launcher, 'config_manager')
        assert hasattr(mcp_launcher, 'server_processes')
    
    @pytest.mark.asyncio
    async def test_start_server(self, mcp_launcher):
        """Test starting an MCP server"""
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_subprocess.return_value = mock_process
            
            result = await mcp_launcher.start_server("python_executor")
            
            assert result is True
            assert "python_executor" in mcp_launcher.server_processes
            mock_subprocess.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_server(self, mcp_launcher):
        """Test stopping an MCP server"""
        mock_process = AsyncMock()
        mock_process.terminate = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)
        
        mcp_launcher.server_processes["test_server"] = mock_process
        
        result = await mcp_launcher.stop_server("test_server")
        
        assert result is True
        assert "test_server" not in mcp_launcher.server_processes
        mock_process.terminate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_all_servers(self, mcp_launcher):
        """Test starting all MCP servers"""
        with patch.object(mcp_launcher, 'start_server', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True
            
            result = await mcp_launcher.start_all_servers()
            
            assert result is True
            # Should start all configured servers
            assert mock_start.call_count >= 3
    
    @pytest.mark.asyncio
    async def test_stop_all_servers(self, mcp_launcher):
        """Test stopping all MCP servers"""
        # Add some mock processes
        mock_process1 = AsyncMock()
        mock_process2 = AsyncMock()
        mcp_launcher.server_processes = {
            "server1": mock_process1,
            "server2": mock_process2
        }
        
        with patch.object(mcp_launcher, 'stop_server', new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = True
            
            result = await mcp_launcher.stop_all_servers()
            
            assert result is True
            assert mock_stop.call_count == 2
    
    @pytest.mark.asyncio
    async def test_get_server_status(self, mcp_launcher):
        """Test getting server status"""
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.returncode = None  # Still running
        
        mcp_launcher.server_processes["test_server"] = mock_process
        
        status = await mcp_launcher.get_server_status("test_server")
        
        assert status["running"] is True
        assert status["pid"] == 12345
    
    @pytest.mark.asyncio
    async def test_restart_server(self, mcp_launcher):
        """Test restarting an MCP server"""
        with patch.object(mcp_launcher, 'stop_server', new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = True
            
            with patch.object(mcp_launcher, 'start_server', new_callable=AsyncMock) as mock_start:
                mock_start.return_value = True
                
                result = await mcp_launcher.restart_server("test_server")
                
                assert result is True
                mock_stop.assert_called_once_with("test_server")
                mock_start.assert_called_once_with("test_server")


class TestTaskAPIService:
    """Test TaskAPIService class"""
    
    @pytest.fixture
    def task_api_service(self, mock_config_manager):
        """Create TaskAPIService instance for testing"""
        with patch('services.task_api_service.TaskManager'):
            with patch('services.task_api_service.RuntimeService'):
                return TaskAPIService(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, task_api_service):
        """Test TaskAPIService initialization"""
        assert task_api_service is not None
        assert hasattr(task_api_service, 'config_manager')
        assert hasattr(task_api_service, 'task_manager')
        assert hasattr(task_api_service, 'runtime_service')
    
    @pytest.mark.asyncio
    async def test_submit_task_endpoint(self, task_api_service, sample_task):
        """Test task submission endpoint"""
        with patch.object(task_api_service.task_manager, 'submit_task', new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = True
            
            result = await task_api_service.submit_task(sample_task)
            
            assert result["success"] is True
            assert result["task_id"] == sample_task.task_id
            mock_submit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_task_status_endpoint(self, task_api_service):
        """Test task status endpoint"""
        with patch.object(task_api_service.task_manager, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "status": "completed",
                "progress": 100,
                "updated_at": datetime.now().isoformat()
            }
            
            result = await task_api_service.get_task_status("test-task-001")
            
            assert result["status"] == "completed"
            assert result["progress"] == 100
            mock_status.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_task_result_endpoint(self, task_api_service):
        """Test task result endpoint"""
        mock_result = MagicMock()
        mock_result.task_id = "test-task-001"
        mock_result.success = True
        mock_result.execution_time = 2.5
        
        with patch.object(task_api_service.task_manager, 'get_task_result', new_callable=AsyncMock) as mock_get_result:
            mock_get_result.return_value = mock_result
            
            result = await task_api_service.get_task_result("test-task-001")
            
            assert result["task_id"] == "test-task-001"
            assert result["success"] is True
            assert result["execution_time"] == 2.5
            mock_get_result.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_task_endpoint(self, task_api_service):
        """Test task cancellation endpoint"""
        with patch.object(task_api_service.task_manager, 'cancel_task', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = True
            
            result = await task_api_service.cancel_task("test-task-001")
            
            assert result["success"] is True
            assert result["message"] == "Task cancelled successfully"
            mock_cancel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tasks_endpoint(self, task_api_service):
        """Test task listing endpoint"""
        mock_tasks = [
            {"task_id": "task-001", "status": "completed"},
            {"task_id": "task-002", "status": "running"}
        ]
        
        with patch.object(task_api_service.task_manager, 'list_tasks_by_status', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_tasks
            
            result = await task_api_service.list_tasks("running")
            
            assert len(result["tasks"]) == 2
            assert result["tasks"][0]["task_id"] == "task-001"
            mock_list.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_queue_info_endpoint(self, task_api_service):
        """Test queue information endpoint"""
        mock_queue_info = {
            "queue_name": "code_queue",
            "pending_tasks": 5,
            "active_tasks": 2
        }
        
        with patch.object(task_api_service.task_manager, 'get_queue_info', new_callable=AsyncMock) as mock_queue_info_call:
            mock_queue_info_call.return_value = mock_queue_info
            
            result = await task_api_service.get_queue_info("code_queue")
            
            assert result["queue_name"] == "code_queue"
            assert result["pending_tasks"] == 5
            mock_queue_info_call.assert_called_once()


class TestToolScoreService:
    """Test ToolScoreService class"""
    
    @pytest.fixture
    def toolscore_service(self, mock_config_manager):
        """Create ToolScoreService instance for testing"""
        return ToolScoreService(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, toolscore_service):
        """Test ToolScoreService initialization"""
        assert toolscore_service is not None
        assert hasattr(toolscore_service, 'config_manager')
        assert hasattr(toolscore_service, 'port')
    
    @pytest.mark.asyncio
    async def test_start_service(self, toolscore_service):
        """Test starting ToolScore service"""
        with patch('websockets.serve') as mock_serve:
            mock_server = AsyncMock()
            mock_serve.return_value = mock_server
            
            result = await toolscore_service.start()
            
            assert result is True
            mock_serve.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_service(self, toolscore_service):
        """Test stopping ToolScore service"""
        mock_server = AsyncMock()
        toolscore_service.server = mock_server
        
        result = await toolscore_service.stop()
        
        assert result is True
        mock_server.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_websocket_connection(self, toolscore_service):
        """Test handling WebSocket connections"""
        mock_websocket = AsyncMock()
        mock_websocket.recv.return_value = '{"type": "list_tools", "request_id": "test123"}'
        
        with patch.object(toolscore_service, '_handle_message', new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {"type": "response", "tools": []}
            
            await toolscore_service.handle_websocket(mock_websocket, "/")
            
            mock_websocket.recv.assert_called()
            mock_handle.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check(self, toolscore_service):
        """Test ToolScore service health check"""
        toolscore_service.server = AsyncMock()
        
        health = await toolscore_service.health_check()
        
        assert "status" in health
        assert "port" in health
        assert health["port"] == toolscore_service.port


class TestRedisService:
    """Test RedisService class"""
    
    @pytest.fixture
    def redis_service(self, mock_config_manager):
        """Create RedisService instance for testing"""
        mock_config_manager.get_redis_config.return_value = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'password': None
        }
        return RedisService(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, redis_service):
        """Test RedisService initialization"""
        assert redis_service is not None
        assert hasattr(redis_service, 'config_manager')
        assert hasattr(redis_service, 'redis_client')
    
    @pytest.mark.asyncio
    async def test_start_service(self, redis_service):
        """Test starting Redis service"""
        with patch.object(redis_service.redis_client, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = True
            
            result = await redis_service.start()
            
            assert result is True
            mock_ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_service(self, redis_service):
        """Test stopping Redis service"""
        with patch.object(redis_service.redis_client, 'close', new_callable=AsyncMock) as mock_close:
            result = await redis_service.stop()
            
            assert result is True
            mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check(self, redis_service):
        """Test Redis service health check"""
        with patch.object(redis_service.redis_client, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = True
            
            with patch.object(redis_service.redis_client, 'info', new_callable=AsyncMock) as mock_info:
                mock_info.return_value = {
                    'connected_clients': 5,
                    'used_memory': 1024000,
                    'uptime_in_seconds': 3600
                }
                
                health = await redis_service.health_check()
                
                assert health["status"] == "healthy"
                assert health["connected_clients"] == 5
                assert health["uptime_in_seconds"] == 3600
                mock_ping.assert_called_once()
                mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_connection_info(self, redis_service):
        """Test getting Redis connection information"""
        connection_info = redis_service.get_connection_info()
        
        assert "host" in connection_info
        assert "port" in connection_info
        assert "db" in connection_info
        assert connection_info["host"] == "localhost"
        assert connection_info["port"] == 6379
    
    @pytest.mark.asyncio
    async def test_flush_database(self, redis_service):
        """Test flushing Redis database"""
        with patch.object(redis_service.redis_client, 'flushdb', new_callable=AsyncMock) as mock_flush:
            mock_flush.return_value = True
            
            result = await redis_service.flush_database()
            
            assert result is True
            mock_flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_database_size(self, redis_service):
        """Test getting database size"""
        with patch.object(redis_service.redis_client, 'dbsize', new_callable=AsyncMock) as mock_dbsize:
            mock_dbsize.return_value = 1000
            
            size = await redis_service.get_database_size()
            
            assert size == 1000
            mock_dbsize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, redis_service):
        """Test Redis connection error handling"""
        with patch.object(redis_service.redis_client, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = Exception("Connection failed")
            
            result = await redis_service.start()
            
            assert result is False