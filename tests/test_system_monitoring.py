"""
Tests for system monitoring and utility modules
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import psutil
from datetime import datetime, timedelta

from core.system_monitor import SystemMonitor
from core.monitoring.health_checker import HealthChecker
from core.monitoring.metrics_collector import MetricsCollector
from core.monitoring.alert_manager import AlertManager


class TestSystemMonitor:
    """Test SystemMonitor class"""
    
    @pytest.fixture
    def system_monitor(self, mock_config_manager):
        """Create SystemMonitor instance for testing"""
        return SystemMonitor(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, system_monitor):
        """Test SystemMonitor initialization"""
        assert system_monitor is not None
        assert hasattr(system_monitor, 'config_manager')
        assert hasattr(system_monitor, 'is_monitoring')
    
    @pytest.mark.asyncio
    async def test_start_monitoring(self, system_monitor):
        """Test starting system monitoring"""
        with patch.object(system_monitor, '_monitoring_loop', new_callable=AsyncMock):
            result = await system_monitor.start_monitoring()
            
            assert result is True
            assert system_monitor.is_monitoring is True
    
    @pytest.mark.asyncio
    async def test_stop_monitoring(self, system_monitor):
        """Test stopping system monitoring"""
        system_monitor.is_monitoring = True
        
        result = await system_monitor.stop_monitoring()
        
        assert result is True
        assert system_monitor.is_monitoring is False
    
    @pytest.mark.asyncio
    async def test_get_system_metrics(self, system_monitor):
        """Test getting system metrics"""
        with patch('psutil.cpu_percent', return_value=45.2):
            with patch('psutil.virtual_memory') as mock_memory:
                mock_memory.return_value.percent = 67.8
                mock_memory.return_value.available = 4294967296  # 4GB
                
                with patch('psutil.disk_usage') as mock_disk:
                    mock_disk.return_value.percent = 23.5
                    mock_disk.return_value.free = 107374182400  # 100GB
                    
                    metrics = await system_monitor.get_system_metrics()
                    
                    assert metrics['cpu_percent'] == 45.2
                    assert metrics['memory_percent'] == 67.8
                    assert metrics['disk_percent'] == 23.5
                    assert 'timestamp' in metrics
    
    @pytest.mark.asyncio
    async def test_get_process_metrics(self, system_monitor):
        """Test getting process metrics"""
        with patch('psutil.Process') as mock_process:
            mock_proc = MagicMock()
            mock_proc.cpu_percent.return_value = 25.0
            mock_proc.memory_info.return_value.rss = 134217728  # 128MB
            mock_proc.num_threads.return_value = 8
            mock_proc.status.return_value = 'running'
            mock_process.return_value = mock_proc
            
            metrics = await system_monitor.get_process_metrics(12345)
            
            assert metrics['cpu_percent'] == 25.0
            assert metrics['memory_mb'] == 128.0
            assert metrics['num_threads'] == 8
            assert metrics['status'] == 'running'
    
    @pytest.mark.asyncio
    async def test_get_network_metrics(self, system_monitor):
        """Test getting network metrics"""
        with patch('psutil.net_io_counters') as mock_net:
            mock_net.return_value.bytes_sent = 1048576000  # 1GB
            mock_net.return_value.bytes_recv = 2097152000  # 2GB
            mock_net.return_value.packets_sent = 1000000
            mock_net.return_value.packets_recv = 1500000
            
            metrics = await system_monitor.get_network_metrics()
            
            assert metrics['bytes_sent'] == 1048576000
            assert metrics['bytes_recv'] == 2097152000
            assert metrics['packets_sent'] == 1000000
            assert metrics['packets_recv'] == 1500000
    
    @pytest.mark.asyncio
    async def test_check_system_health(self, system_monitor):
        """Test system health check"""
        with patch.object(system_monitor, 'get_system_metrics', new_callable=AsyncMock) as mock_metrics:
            mock_metrics.return_value = {
                'cpu_percent': 30.0,
                'memory_percent': 45.0,
                'disk_percent': 20.0
            }
            
            health = await system_monitor.check_system_health()
            
            assert health['status'] == 'healthy'
            assert health['cpu_status'] == 'normal'
            assert health['memory_status'] == 'normal'
            assert health['disk_status'] == 'normal'
    
    @pytest.mark.asyncio
    async def test_check_system_health_high_usage(self, system_monitor):
        """Test system health check with high resource usage"""
        with patch.object(system_monitor, 'get_system_metrics', new_callable=AsyncMock) as mock_metrics:
            mock_metrics.return_value = {
                'cpu_percent': 95.0,
                'memory_percent': 90.0,
                'disk_percent': 85.0
            }
            
            health = await system_monitor.check_system_health()
            
            assert health['status'] == 'critical'
            assert health['cpu_status'] == 'critical'
            assert health['memory_status'] == 'critical'
            assert health['disk_status'] == 'warning'
    
    @pytest.mark.asyncio
    async def test_get_running_processes(self, system_monitor):
        """Test getting running processes"""
        with patch('psutil.process_iter') as mock_iter:
            mock_proc1 = MagicMock()
            mock_proc1.info = {'pid': 123, 'name': 'python', 'cpu_percent': 10.0}
            
            mock_proc2 = MagicMock()
            mock_proc2.info = {'pid': 456, 'name': 'node', 'cpu_percent': 5.0}
            
            mock_iter.return_value = [mock_proc1, mock_proc2]
            
            processes = await system_monitor.get_running_processes()
            
            assert len(processes) == 2
            assert processes[0]['pid'] == 123
            assert processes[0]['name'] == 'python'
            assert processes[1]['pid'] == 456
            assert processes[1]['name'] == 'node'
    
    @pytest.mark.asyncio
    async def test_detect_anomalies(self, system_monitor):
        """Test anomaly detection"""
        metrics_history = [
            {'cpu_percent': 10.0, 'memory_percent': 20.0, 'timestamp': datetime.now() - timedelta(minutes=5)},
            {'cpu_percent': 15.0, 'memory_percent': 25.0, 'timestamp': datetime.now() - timedelta(minutes=4)},
            {'cpu_percent': 90.0, 'memory_percent': 85.0, 'timestamp': datetime.now() - timedelta(minutes=1)},
        ]
        
        anomalies = await system_monitor.detect_anomalies(metrics_history)
        
        assert len(anomalies) > 0
        assert any('cpu' in anomaly['metric'] for anomaly in anomalies)
        assert any('memory' in anomaly['metric'] for anomaly in anomalies)


class TestHealthChecker:
    """Test HealthChecker class"""
    
    @pytest.fixture
    def health_checker(self, mock_config_manager):
        """Create HealthChecker instance for testing"""
        return HealthChecker(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, health_checker):
        """Test HealthChecker initialization"""
        assert health_checker is not None
        assert hasattr(health_checker, 'config_manager')
        assert hasattr(health_checker, 'health_checks')
    
    @pytest.mark.asyncio
    async def test_register_health_check(self, health_checker):
        """Test registering a health check"""
        async def mock_check():
            return {"status": "healthy", "message": "Service is running"}
        
        health_checker.register_health_check("test_service", mock_check)
        
        assert "test_service" in health_checker.health_checks
    
    @pytest.mark.asyncio
    async def test_run_health_check(self, health_checker):
        """Test running a specific health check"""
        async def mock_check():
            return {"status": "healthy", "response_time": 0.1}
        
        health_checker.register_health_check("test_service", mock_check)
        
        result = await health_checker.run_health_check("test_service")
        
        assert result["status"] == "healthy"
        assert result["response_time"] == 0.1
    
    @pytest.mark.asyncio
    async def test_run_all_health_checks(self, health_checker):
        """Test running all health checks"""
        async def healthy_check():
            return {"status": "healthy"}
        
        async def unhealthy_check():
            return {"status": "unhealthy", "error": "Connection failed"}
        
        health_checker.register_health_check("service1", healthy_check)
        health_checker.register_health_check("service2", unhealthy_check)
        
        results = await health_checker.run_all_health_checks()
        
        assert len(results) == 2
        assert results["service1"]["status"] == "healthy"
        assert results["service2"]["status"] == "unhealthy"
    
    @pytest.mark.asyncio
    async def test_health_check_timeout(self, health_checker):
        """Test health check with timeout"""
        async def slow_check():
            await asyncio.sleep(2)  # Longer than typical timeout
            return {"status": "healthy"}
        
        health_checker.register_health_check("slow_service", slow_check)
        
        result = await health_checker.run_health_check("slow_service", timeout=1)
        
        assert result["status"] == "timeout"
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_health_check_exception(self, health_checker):
        """Test health check that raises an exception"""
        async def failing_check():
            raise Exception("Health check failed")
        
        health_checker.register_health_check("failing_service", failing_check)
        
        result = await health_checker.run_health_check("failing_service")
        
        assert result["status"] == "error"
        assert "Health check failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_overall_health(self, health_checker):
        """Test getting overall system health"""
        async def healthy_check():
            return {"status": "healthy"}
        
        async def degraded_check():
            return {"status": "degraded", "warning": "High response time"}
        
        health_checker.register_health_check("service1", healthy_check)
        health_checker.register_health_check("service2", degraded_check)
        
        overall_health = await health_checker.get_overall_health()
        
        assert overall_health["status"] == "degraded"  # Worst status wins
        assert overall_health["total_checks"] == 2
        assert overall_health["healthy_count"] == 1
        assert overall_health["degraded_count"] == 1


class TestMetricsCollector:
    """Test MetricsCollector class"""
    
    @pytest.fixture
    def metrics_collector(self, mock_config_manager):
        """Create MetricsCollector instance for testing"""
        return MetricsCollector(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, metrics_collector):
        """Test MetricsCollector initialization"""
        assert metrics_collector is not None
        assert hasattr(metrics_collector, 'config_manager')
        assert hasattr(metrics_collector, 'metrics_store')
    
    @pytest.mark.asyncio
    async def test_collect_metric(self, metrics_collector):
        """Test collecting a single metric"""
        metric_data = {
            "name": "response_time",
            "value": 0.150,
            "tags": {"service": "api", "endpoint": "/tasks"},
            "timestamp": datetime.now()
        }
        
        await metrics_collector.collect_metric(metric_data)
        
        assert len(metrics_collector.metrics_store) == 1
        assert metrics_collector.metrics_store[0]["name"] == "response_time"
        assert metrics_collector.metrics_store[0]["value"] == 0.150
    
    @pytest.mark.asyncio
    async def test_collect_system_metrics(self, metrics_collector):
        """Test collecting system metrics"""
        with patch('psutil.cpu_percent', return_value=35.0):
            with patch('psutil.virtual_memory') as mock_memory:
                mock_memory.return_value.percent = 55.0
                
                await metrics_collector.collect_system_metrics()
                
                cpu_metrics = [m for m in metrics_collector.metrics_store if m["name"] == "cpu_percent"]
                memory_metrics = [m for m in metrics_collector.metrics_store if m["name"] == "memory_percent"]
                
                assert len(cpu_metrics) == 1
                assert len(memory_metrics) == 1
                assert cpu_metrics[0]["value"] == 35.0
                assert memory_metrics[0]["value"] == 55.0
    
    @pytest.mark.asyncio
    async def test_collect_application_metrics(self, metrics_collector):
        """Test collecting application-specific metrics"""
        app_metrics = {
            "tasks_processed": 150,
            "active_connections": 25,
            "error_rate": 0.02,
            "average_response_time": 0.250
        }
        
        await metrics_collector.collect_application_metrics(app_metrics)
        
        task_metrics = [m for m in metrics_collector.metrics_store if m["name"] == "tasks_processed"]
        connection_metrics = [m for m in metrics_collector.metrics_store if m["name"] == "active_connections"]
        
        assert len(task_metrics) == 1
        assert len(connection_metrics) == 1
        assert task_metrics[0]["value"] == 150
        assert connection_metrics[0]["value"] == 25
    
    @pytest.mark.asyncio
    async def test_get_metrics_by_name(self, metrics_collector):
        """Test getting metrics by name"""
        await metrics_collector.collect_metric({
            "name": "cpu_percent",
            "value": 30.0,
            "timestamp": datetime.now()
        })
        
        await metrics_collector.collect_metric({
            "name": "cpu_percent",
            "value": 35.0,
            "timestamp": datetime.now()
        })
        
        cpu_metrics = await metrics_collector.get_metrics_by_name("cpu_percent")
        
        assert len(cpu_metrics) == 2
        assert cpu_metrics[0]["value"] == 30.0
        assert cpu_metrics[1]["value"] == 35.0
    
    @pytest.mark.asyncio
    async def test_get_metrics_by_time_range(self, metrics_collector):
        """Test getting metrics by time range"""
        now = datetime.now()
        old_time = now - timedelta(hours=2)
        recent_time = now - timedelta(minutes=30)
        
        await metrics_collector.collect_metric({
            "name": "test_metric",
            "value": 10.0,
            "timestamp": old_time
        })
        
        await metrics_collector.collect_metric({
            "name": "test_metric",
            "value": 20.0,
            "timestamp": recent_time
        })
        
        start_time = now - timedelta(hours=1)
        end_time = now
        
        metrics = await metrics_collector.get_metrics_by_time_range(start_time, end_time)
        
        assert len(metrics) == 1  # Only the recent metric
        assert metrics[0]["value"] == 20.0
    
    @pytest.mark.asyncio
    async def test_calculate_aggregates(self, metrics_collector):
        """Test calculating metric aggregates"""
        # Add multiple data points
        values = [10.0, 15.0, 20.0, 25.0, 30.0]
        for value in values:
            await metrics_collector.collect_metric({
                "name": "test_metric",
                "value": value,
                "timestamp": datetime.now()
            })
        
        aggregates = await metrics_collector.calculate_aggregates("test_metric")
        
        assert aggregates["count"] == 5
        assert aggregates["average"] == 20.0
        assert aggregates["min"] == 10.0
        assert aggregates["max"] == 30.0
        assert aggregates["sum"] == 100.0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_metrics(self, metrics_collector):
        """Test cleaning up old metrics"""
        old_time = datetime.now() - timedelta(days=2)
        recent_time = datetime.now() - timedelta(minutes=30)
        
        await metrics_collector.collect_metric({
            "name": "old_metric",
            "value": 10.0,
            "timestamp": old_time
        })
        
        await metrics_collector.collect_metric({
            "name": "recent_metric",
            "value": 20.0,
            "timestamp": recent_time
        })
        
        # Clean up metrics older than 1 day
        await metrics_collector.cleanup_old_metrics(max_age_hours=24)
        
        assert len(metrics_collector.metrics_store) == 1
        assert metrics_collector.metrics_store[0]["name"] == "recent_metric"


class TestAlertManager:
    """Test AlertManager class"""
    
    @pytest.fixture
    def alert_manager(self, mock_config_manager):
        """Create AlertManager instance for testing"""
        return AlertManager(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, alert_manager):
        """Test AlertManager initialization"""
        assert alert_manager is not None
        assert hasattr(alert_manager, 'config_manager')
        assert hasattr(alert_manager, 'alert_rules')
    
    @pytest.mark.asyncio
    async def test_add_alert_rule(self, alert_manager):
        """Test adding an alert rule"""
        rule = {
            "name": "high_cpu_usage",
            "metric": "cpu_percent",
            "threshold": 80.0,
            "operator": ">",
            "severity": "warning"
        }
        
        alert_manager.add_alert_rule(rule)
        
        assert len(alert_manager.alert_rules) == 1
        assert alert_manager.alert_rules[0]["name"] == "high_cpu_usage"
    
    @pytest.mark.asyncio
    async def test_evaluate_alerts(self, alert_manager):
        """Test evaluating alerts against metrics"""
        # Add alert rules
        alert_manager.add_alert_rule({
            "name": "high_cpu",
            "metric": "cpu_percent",
            "threshold": 70.0,
            "operator": ">",
            "severity": "warning"
        })
        
        alert_manager.add_alert_rule({
            "name": "low_memory",
            "metric": "memory_available_gb",
            "threshold": 1.0,
            "operator": "<",
            "severity": "critical"
        })
        
        # Test metrics
        metrics = [
            {"name": "cpu_percent", "value": 85.0},
            {"name": "memory_available_gb", "value": 0.5}
        ]
        
        alerts = await alert_manager.evaluate_alerts(metrics)
        
        assert len(alerts) == 2
        assert alerts[0]["rule_name"] == "high_cpu"
        assert alerts[0]["severity"] == "warning"
        assert alerts[1]["rule_name"] == "low_memory"
        assert alerts[1]["severity"] == "critical"
    
    @pytest.mark.asyncio
    async def test_send_alert(self, alert_manager):
        """Test sending an alert"""
        alert = {
            "rule_name": "test_alert",
            "severity": "critical",
            "message": "Test alert message",
            "timestamp": datetime.now()
        }
        
        with patch.object(alert_manager, '_send_notification', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            result = await alert_manager.send_alert(alert)
            
            assert result is True
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_alert_deduplication(self, alert_manager):
        """Test alert deduplication"""
        alert = {
            "rule_name": "duplicate_alert",
            "severity": "warning",
            "message": "Duplicate alert",
            "timestamp": datetime.now()
        }
        
        with patch.object(alert_manager, '_send_notification', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            # Send the same alert twice
            await alert_manager.send_alert(alert)
            await alert_manager.send_alert(alert)
            
            # Should only send once due to deduplication
            assert mock_send.call_count == 1
    
    @pytest.mark.asyncio
    async def test_get_active_alerts(self, alert_manager):
        """Test getting active alerts"""
        alert = {
            "rule_name": "active_alert",
            "severity": "critical",
            "message": "Active alert",
            "timestamp": datetime.now()
        }
        
        await alert_manager.send_alert(alert)
        
        active_alerts = await alert_manager.get_active_alerts()
        
        assert len(active_alerts) == 1
        assert active_alerts[0]["rule_name"] == "active_alert"
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, alert_manager):
        """Test resolving an alert"""
        alert = {
            "rule_name": "resolvable_alert",
            "severity": "warning",
            "message": "Resolvable alert",
            "timestamp": datetime.now()
        }
        
        await alert_manager.send_alert(alert)
        
        result = await alert_manager.resolve_alert("resolvable_alert")
        
        assert result is True
        
        active_alerts = await alert_manager.get_active_alerts()
        assert len(active_alerts) == 0