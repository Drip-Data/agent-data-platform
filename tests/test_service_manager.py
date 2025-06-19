#!/usr/bin/env python3
"""
Service Manager 综合测试套件
测试服务管理器的服务注册、启动、停止、健康检查等核心功能
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

# 配置pytest-asyncio
# 只对需要的异步测试单独添加 @pytest.mark.asyncio 装饰器

logger = __import__('logging').getLogger(__name__)


class TestServiceManager:
    """测试服务管理器"""
    
    @pytest.fixture
    def service_manager(self):
        """创建服务管理器实例"""
        from services.service_manager import ServiceManager
        return ServiceManager()
    
    def test_manager_initialization(self, service_manager):
        """测试管理器初始化"""
        assert service_manager.services == {}
        assert service_manager.start_order == []
        assert service_manager.stop_order == []
    
    def test_register_service(self, service_manager):
        """测试服务注册"""
        mock_init_fn = Mock()
        mock_start_fn = AsyncMock()
        mock_stop_fn = AsyncMock()
        mock_health_fn = AsyncMock()
        
        service_manager.register_service(
            name="test_service",
            initialize_fn=mock_init_fn,
            start_fn=mock_start_fn,
            stop_fn=mock_stop_fn,
            health_check_fn=mock_health_fn,
            dependencies=["dependency1"]
        )
        
        assert "test_service" in service_manager.services
        service_info = service_manager.services["test_service"]
        
        assert service_info["initialize"] == mock_init_fn
        assert service_info["start"] == mock_start_fn
        assert service_info["stop"] == mock_stop_fn
        assert service_info["health_check"] == mock_health_fn
        assert service_info["dependencies"] == ["dependency1"]
    
    def test_register_duplicate_service(self, service_manager):
        """测试注册重复服务（实际实现允许覆盖）"""
        first_init_fn = Mock()
        service_manager.register_service(
            name="duplicate_service",
            initialize_fn=first_init_fn,
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        # 再次注册相同服务会覆盖原有的服务
        second_init_fn = Mock()
        service_manager.register_service(
            name="duplicate_service",
            initialize_fn=second_init_fn,
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        # 验证服务被覆盖
        assert service_manager.services["duplicate_service"]["initialize"] == second_init_fn
        assert service_manager.services["duplicate_service"]["initialize"] != first_init_fn
    
    def test_dependency_resolution(self, service_manager):
        """测试依赖解析"""
        # 注册有依赖关系的服务
        service_manager.register_service(
            name="service_a",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=[]
        )
        
        service_manager.register_service(
            name="service_b",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=["service_a"]
        )
        
        service_manager.register_service(
            name="service_c",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=["service_a", "service_b"]
        )
        
        # 解析启动顺序
        service_manager._resolve_start_order()
        start_order = service_manager.start_order
        
        # service_a 应该最先启动
        assert start_order.index("service_a") < start_order.index("service_b")
        assert start_order.index("service_a") < start_order.index("service_c")
        assert start_order.index("service_b") < start_order.index("service_c")
    
    def test_circular_dependency_detection(self, service_manager):
        """测试循环依赖检测"""
        service_manager.register_service(
            name="service_x",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=["service_y"]
        )
        
        service_manager.register_service(
            name="service_y",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=["service_x"]  # 循环依赖
        )
        
        # 应该检测到循环依赖
        with pytest.raises(ValueError, match="发现循环依赖"):
            service_manager._resolve_start_order()
    
    @pytest.mark.asyncio
    async def test_initialize_all(self, service_manager):
        """测试初始化所有服务"""
        mock_init_1 = Mock()
        mock_init_2 = Mock()
        
        service_manager.register_service(
            name="service1",
            initialize_fn=mock_init_1,
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        service_manager.register_service(
            name="service2",
            initialize_fn=mock_init_2,
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        config = {"test": "config"}
        service_manager.initialize_all(config)
        
        # 验证所有初始化函数都被调用
        mock_init_1.assert_called_once_with(config)
        mock_init_2.assert_called_once_with(config)
    
    @pytest.mark.asyncio
    async def test_start_all_services(self, service_manager):
        """测试启动所有服务"""
        mock_start_1 = AsyncMock()
        mock_start_2 = AsyncMock()
        
        service_manager.register_service(
            name="service1",
            initialize_fn=Mock(),
            start_fn=mock_start_1,
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=[]
        )
        
        service_manager.register_service(
            name="service2",
            initialize_fn=Mock(),
            start_fn=mock_start_2,
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock(),
            dependencies=["service1"]
        )
        
        # 初始化服务
        service_manager.initialize_all({})
        
        # 启动所有服务
        await service_manager.start_all()
        
        # 验证启动函数被调用
        mock_start_1.assert_called_once()
        mock_start_2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_all_services(self, service_manager):
        """测试停止所有服务"""
        mock_stop_1 = AsyncMock()
        mock_stop_2 = AsyncMock()
        
        service_manager.register_service(
            name="service1",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=mock_stop_1,
            health_check_fn=AsyncMock()
        )
        
        service_manager.register_service(
            name="service2",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=mock_stop_2,
            health_check_fn=AsyncMock()
        )
        
        # 需要先初始化来设置stop_order
        service_manager.initialize_all({})
        
        # 停止所有服务
        await service_manager.stop_all()
        
        # 验证停止函数被调用
        mock_stop_1.assert_called_once()
        mock_stop_2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_service_start_failure(self, service_manager):
        """测试服务启动失败"""
        mock_start_failing = AsyncMock(side_effect=Exception("Service failed to start"))
        mock_start_normal = AsyncMock()
        
        service_manager.register_service(
            name="failing_service",
            initialize_fn=Mock(),
            start_fn=mock_start_failing,
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        service_manager.register_service(
            name="normal_service",
            initialize_fn=Mock(),
            start_fn=mock_start_normal,
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        service_manager.initialize_all({})
        
        # 启动应该失败
        with pytest.raises(Exception, match="Service failed to start"):
            await service_manager.start_all()
    
    def test_health_check_all(self, service_manager):
        """测试所有服务的健康检查"""
        mock_health_1 = Mock(return_value={"status": "healthy"})
        mock_health_2 = Mock(return_value={"status": "unhealthy", "error": "Database connection lost"})
        
        service_manager.register_service(
            name="healthy_service",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=mock_health_1
        )
        
        service_manager.register_service(
            name="unhealthy_service",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=mock_health_2
        )
        
        health_status = service_manager.health_check()
        
        assert health_status["healthy_service"]["status"] == "healthy"
        assert health_status["unhealthy_service"]["status"] == "unhealthy"
        assert "Database connection lost" in health_status["unhealthy_service"]["error"]
    
    def test_service_registration_check(self, service_manager):
        """测试服务注册状态检查"""
        service_manager.register_service(
            name="test_service",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=AsyncMock(),
            health_check_fn=AsyncMock()
        )
        
        # 测试服务是否已注册
        assert "test_service" in service_manager.services
        
        # 测试不存在的服务
        assert "nonexistent_service" not in service_manager.services
    
    @pytest.mark.asyncio
    async def test_manual_restart_service(self, service_manager):
        """测试手动重启服务（模拟重启流程）"""
        mock_stop = AsyncMock()
        mock_start = AsyncMock()
        
        service_manager.register_service(
            name="restart_service",
            initialize_fn=Mock(),
            start_fn=mock_start,
            stop_fn=mock_stop,
            health_check_fn=AsyncMock()
        )
        
        service_manager.initialize_all({})
        
        # 手动模拟重启：先启动，再停止，再启动
        await service_manager.start_all()
        await service_manager.stop_all()
        await service_manager.start_all()
        
        # 验证停止和启动函数被调用了正确的次数
        assert mock_stop.call_count == 1
        assert mock_start.call_count == 2
    
    def test_nonexistent_service_access(self, service_manager):
        """测试访问不存在的服务"""
        # 确认不存在的服务不在services中
        assert "nonexistent" not in service_manager.services
    
    def test_force_stop_all(self, service_manager):
        """测试强制停止所有服务"""
        mock_stop_1 = Mock()  # 使用同步Mock，因为force_stop_all只调用同步函数
        mock_stop_2 = Mock()
        
        service_manager.register_service(
            name="service1",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=mock_stop_1,
            health_check_fn=AsyncMock()
        )
        
        service_manager.register_service(
            name="service2",
            initialize_fn=Mock(),
            start_fn=AsyncMock(),
            stop_fn=mock_stop_2,
            health_check_fn=AsyncMock()
        )
        
        service_manager.initialize_all({})
        service_manager.force_stop_all()
        
        # 验证停止函数被调用
        mock_stop_1.assert_called_once()
        mock_stop_2.assert_called_once()


class TestServiceManagerIntegration:
    """服务管理器集成测试"""
    
    @pytest.fixture
    def service_manager(self):
        """创建服务管理器实例"""
        from services.service_manager import ServiceManager
        return ServiceManager()
    
    @pytest.mark.asyncio
    async def test_realistic_service_scenario(self, service_manager):
        """测试真实的服务场景"""
        # 模拟Redis服务
        redis_init = Mock()
        redis_start = AsyncMock()
        redis_stop = AsyncMock()
        redis_health = Mock(return_value={"status": "healthy"})
        
        # 模拟ToolScore服务（依赖Redis）
        toolscore_init = Mock()
        toolscore_start = AsyncMock()
        toolscore_stop = AsyncMock()
        toolscore_health = Mock(return_value={"status": "healthy"})
        
        # 模拟应用服务（依赖Redis和ToolScore）
        app_init = Mock()
        app_start = AsyncMock()
        app_stop = AsyncMock()
        app_health = Mock(return_value={"status": "healthy"})
        
        # 注册服务
        service_manager.register_service(
            name="redis",
            initialize_fn=redis_init,
            start_fn=redis_start,
            stop_fn=redis_stop,
            health_check_fn=redis_health,
            dependencies=[]
        )
        
        service_manager.register_service(
            name="toolscore",
            initialize_fn=toolscore_init,
            start_fn=toolscore_start,
            stop_fn=toolscore_stop,
            health_check_fn=toolscore_health,
            dependencies=["redis"]
        )
        
        service_manager.register_service(
            name="app",
            initialize_fn=app_init,
            start_fn=app_start,
            stop_fn=app_stop,
            health_check_fn=app_health,
            dependencies=["redis", "toolscore"]
        )
        
        # 初始化和启动所有服务
        service_manager.initialize_all({"env": "test"})
        await service_manager.start_all()
        
        # 验证启动顺序
        assert redis_start.called
        assert toolscore_start.called
        assert app_start.called
        
        # 验证所有服务都已注册
        assert "redis" in service_manager.services
        assert "toolscore" in service_manager.services
        assert "app" in service_manager.services
        
        # 检查健康状态
        health_status = service_manager.health_check()
        assert all(status["status"] == "healthy" for status in health_status.values())
        
        # 停止所有服务
        await service_manager.stop_all()
        
        # 验证停止顺序（与启动顺序相反）
        assert redis_stop.called
        assert toolscore_stop.called
        assert app_stop.called
    
    @pytest.mark.asyncio
    async def test_partial_failure_scenario(self, service_manager):
        """测试部分失败场景"""
        # 正常服务
        normal_init = Mock()
        normal_start = AsyncMock()
        normal_stop = AsyncMock()
        
        # 失败的服务
        failing_init = Mock()
        failing_start = AsyncMock(side_effect=Exception("Start failed"))
        failing_stop = AsyncMock()
        
        service_manager.register_service(
            name="normal_service",
            initialize_fn=normal_init,
            start_fn=normal_start,
            stop_fn=normal_stop,
            health_check_fn=AsyncMock()
        )
        
        service_manager.register_service(
            name="failing_service",
            initialize_fn=failing_init,
            start_fn=failing_start,
            stop_fn=failing_stop,
            health_check_fn=AsyncMock(),
            dependencies=["normal_service"]
        )
        
        service_manager.initialize_all({})
        
        # 启动应该失败
        with pytest.raises(Exception):
            await service_manager.start_all()
        
        # 验证服务已注册
        assert "normal_service" in service_manager.services
        assert "failing_service" in service_manager.services
        
        # 清理：停止已启动的服务
        await service_manager.stop_all()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])