import logging
import asyncio # 导入asyncio
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

class ServiceManager:
    """统一管理所有服务的生命周期"""
    
    def __init__(self):
        self.services = {}
        self.start_order = []
        self.stop_order = []
        
    def register_service(self, name: str, 
                         initialize_fn: Callable, 
                         start_fn: Callable,
                         stop_fn: Optional[Callable] = None,
                         health_check_fn: Optional[Callable] = None,
                         dependencies: List[str] = []): # 将None改为[]
        """注册一个服务及其生命周期函数"""
        self.services[name] = {
            'initialize': initialize_fn,
            'start': start_fn,
            'stop': stop_fn,
            'health_check': health_check_fn,
            'dependencies': dependencies or []
        }
        
    def _resolve_start_order(self):
        """根据依赖关系解析服务启动顺序"""
        # 简单的拓扑排序实现
        visited = set()
        temp_visited = set()
        order = []
        
        def visit(name):
            if name in temp_visited:
                raise ValueError(f"发现循环依赖: {name}")
            if name in visited:
                return
            
            temp_visited.add(name)
            for dep in self.services[name]['dependencies']:
                if dep in self.services:
                    visit(dep)
            
            temp_visited.remove(name)
            visited.add(name)
            order.append(name)
        
        for service_name in self.services:
            if service_name not in visited:
                visit(service_name)
                
        self.start_order = order
        self.stop_order = list(reversed(order))
    
    def initialize_all(self, config=None):
        """初始化所有服务"""
        logger.info("正在初始化所有服务...")
        self._resolve_start_order()
        
        for name in self.start_order:
            logger.info(f"初始化服务: {name}")
            self.services[name]['initialize'](config)
    
    async def start_all(self):
        """按依赖顺序启动所有服务"""
        logger.info("正在启动所有服务...")
        
        for name in self.start_order:
            logger.info(f"启动服务: {name}")
            start_fn = self.services[name]['start']
            
            # 检查是否是异步函数
            if asyncio.iscoroutinefunction(start_fn):
                await start_fn()
            else:
                start_fn()
            
        logger.info("所有服务已启动")
    
    async def stop_all(self, timeout_per_service=8):
        """按依赖的反序停止所有服务"""
        logger.info("正在停止所有服务...")
        
        for name in self.stop_order:
            if self.services[name]['stop']:
                logger.info(f"停止服务: {name}")
                try:
                    # 为每个服务设置超时
                    if asyncio.iscoroutinefunction(self.services[name]['stop']):
                        await asyncio.wait_for(
                            self.services[name]['stop'](), 
                            timeout=timeout_per_service
                        )
                    else:
                        # 对于同步函数，在executor中运行以支持超时
                        await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, self.services[name]['stop']
                            ),
                            timeout=timeout_per_service
                        )
                    logger.info(f"服务 {name} 已成功停止")
                except asyncio.TimeoutError:
                    logger.warning(f"停止服务 {name} 超时 ({timeout_per_service}秒)，继续停止其他服务")
                except Exception as e:
                    logger.error(f"停止服务 {name} 时出错: {e}")
        
        logger.info("所有服务已停止")
    
    def force_stop_all(self):
        """强制停止所有服务（同步版本，用于紧急情况）"""
        logger.info("执行强制停止所有服务...")
        
        for name in self.stop_order:
            if self.services[name]['stop']:
                logger.info(f"强制停止服务: {name}")
                try:
                    # 只调用同步停止函数
                    if not asyncio.iscoroutinefunction(self.services[name]['stop']):
                        self.services[name]['stop']()
                    else:
                        logger.warning(f"跳过异步服务 {name}，在强制模式下无法调用")
                except Exception as e:
                    logger.error(f"强制停止服务 {name} 时出错: {e}")
        
        logger.info("强制停止完成")
    
    def get_service(self, name: str):
        """获取指定名称的服务实例"""
        if name not in self.services:
            logger.warning(f"Service '{name}' not found in registered services")
            return None
        
        # 对于特定的服务，返回实际的服务模块
        if name == 'toolscore':
            # 导入并返回toolscore服务模块
            try:
                from services import toolscore_service
                return toolscore_service
            except ImportError as e:
                logger.error(f"Failed to import toolscore_service: {e}")
                return None
        elif name == 'redis':
            try:
                from services import redis_service
                return redis_service
            except ImportError as e:
                logger.error(f"Failed to import redis_service: {e}")
                return None
        elif name == 'task_api':
            try:
                from services import task_api_service
                return task_api_service
            except ImportError as e:
                logger.error(f"Failed to import task_api_service: {e}")
                return None
        elif name == 'runtime':
            try:
                from services import runtime_service
                return runtime_service
            except ImportError as e:
                logger.error(f"Failed to import runtime_service: {e}")
                return None
        elif name == 'synthesis':
            try:
                from services import synthesis_service
                return synthesis_service
            except ImportError as e:
                logger.error(f"Failed to import synthesis_service: {e}")
                return None
        
        # 对于其他服务，返回服务信息字典
        service_info = self.services[name]
        return service_info
    
    def health_check(self):
        """检查所有服务的健康状态"""
        results = {}
        for name, service in self.services.items():
            if service['health_check']:
                try:
                    results[name] = service['health_check']()
                except Exception as e:
                    results[name] = {'status': 'error', 'message': str(e)}
            else:
                results[name] = {'status': 'unknown', 'message': 'No health check implemented'}
        
        return results
