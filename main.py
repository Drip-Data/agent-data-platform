#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point (无Docker版本)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import signal
import argparse

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入核心组件
from core.config_manager import ConfigManager
from core.metrics import EnhancedMetrics
from core.redis_manager import RedisManager
from core.system_monitor import SystemMonitor
from core.toolscore.toolscore_client import ToolScoreClient as CoreToolScoreClient
from runtimes.reasoning.toolscore_client import ToolScoreClient as RuntimeToolScoreClient
from core.task_processing.task_loader import TaskLoader
from core.task_processing.task_enhancer import TaskEnhancer
from core.task_processing.task_distributor import TaskDistributor
from core.monitoring.queue_monitor import QueueMonitor
from core.llm_client import LLMClient # 导入LLMClient
from core.interfaces import TaskType # 导入TaskType
from core.dispatcher_enhanced import TaskProcessingCoordinator # 导入TaskProcessingCoordinator

from services.service_manager import ServiceManager
from services import (
    redis_service,
    toolscore_service,
    task_api_service,
    runtime_service,
    mcp_server_launcher,
    synthesis_service
)

from core.utils.path_utils import ensure_output_structure

# 创建必要的目录结构
ensure_output_structure()
os.makedirs(project_root / 'logs', exist_ok=True)
os.makedirs(project_root / 'config', exist_ok=True)
os.makedirs(project_root / 'data', exist_ok=True)

# 配置日志
class SafeFormatter(logging.Formatter):
    """安全的日志格式化器，处理Unicode字符"""
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            msg = record.getMessage()
            msg = msg.replace('✅', '[OK]').replace('❌', '[ERROR]').replace('⚠️', '[WARN]').replace('🚀', '[START]').replace('🔧', '[FIX]').replace('⏳', '[WAIT]').replace('🔄', '[PROC]')
            record.msg = msg
            record.args = ()
            return super().format(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/toolscore.log', mode='a', encoding='utf-8')
    ]
)

for handler in logging.root.handlers:
    handler.setFormatter(SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Agent Data Platform")
    parser.add_argument('--config-dir', type=str, default="config", help='配置文件目录路径')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def setup_signal_handlers(service_manager):
    """设置信号处理器以优雅关闭"""
    async def signal_handler(sig, frame): # 信号处理器也需要是异步的
        logger.info(f"收到信号 {sig}，正在优雅关闭...")
        await service_manager.stop_all()
        sys.exit(0)
    
    # 注册信号处理器，需要将异步函数包装为同步可调用对象
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(signal_handler(signal.SIGINT, None)))
    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(signal_handler(signal.SIGTERM, None)))

async def main_async():
    """异步主函数，应用入口点"""
    logger.info("=== Agent Data Platform 启动中 ===")
    
    args = parse_arguments()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("调试模式已启用。")

    # 1. 初始化 ConfigManager
    config_manager = ConfigManager(config_dir=args.config_dir)
    
    # 2. 加载所有必要配置
    redis_url = config_manager.get_redis_url()
    task_file = config_manager.get_task_file_path()
    routing_config = config_manager.load_routing_config()
    queue_mapping = {
        TaskType(task_type_str.lower()): queue_name
        for task_type_str, queue_name in routing_config.task_type_mapping.items()
    }
    
    # 3. 实例化核心组件
    metrics = EnhancedMetrics() # Metrics实例
    redis_manager = RedisManager(redis_url) # RedisManager实例
    
    # ToolScore服务启动后，获取其实际端口
    # 注意：ToolScore MCP服务器和HTTP监控API可能使用不同的端口
    # 根据日志，ToolScore MCP服务器动态分配的端口是8092
    # ToolScore HTTP监控API的端口是8091 (来自ports_config.yaml)
    # 确保这里使用正确的端口来初始化客户端
    
    # 假设ToolScore MCP服务器的实际端口由toolscore_service管理
    # 在toolscore_service启动后，可以从其内部获取实际端口
    # 从ports_config.yaml获取ToolScore MCP和HTTP API的端口
    ports_config = config_manager.get_ports_config()
    
    # ToolScore MCP服务器的端口
    # 优先使用配置的端口，如果配置了auto_detect，则ToolScore服务内部会动态分配
    # 这里我们直接从配置中读取，因为ToolScore服务会确保它监听的是这个端口或动态分配的端口
    toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
    
    # ToolScore HTTP监控API的端口
    toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
    
    toolscore_http_endpoint = f"http://localhost:{toolscore_http_port}"
    toolscore_websocket_endpoint = f"ws://localhost:{toolscore_mcp_port}/websocket"
    
    # 为运行时实例化专用的ToolScore客户端
    runtime_toolscore_client = RuntimeToolScoreClient(toolscore_http_endpoint)
    
    # 为其他核心组件实例化核心ToolScore客户端 (如果需要)
    core_toolscore_client = CoreToolScoreClient(config_manager)
    
    llm_client = LLMClient(config_manager.get_llm_config()) # LLMClient需要LLM配置
    
    # Task Processing Components
    task_loader = TaskLoader(task_file)
    task_enhancer = TaskEnhancer(core_toolscore_client)
    task_distributor = TaskDistributor(redis_url, metrics) # 注入metrics
    
    # Monitoring Components
    queue_monitor = QueueMonitor(redis_url)
    system_monitor = SystemMonitor(redis_url, config_manager) # 注入config_manager

    # 创建服务管理器
    service_manager = ServiceManager()
    
    # 注册所有服务
    # 注意：这里需要调整服务的initialize_fn和start_fn，以接收新实例化的组件
    # 这部分需要根据实际的服务实现进行调整，目前只是占位
    
    # 示例：注册 TaskProcessingCoordinator 作为服务
    service_manager.register_service(
        name="task_processing_coordinator",
        initialize_fn=lambda config: None, # 实际初始化在main_async中完成
        start_fn=lambda: asyncio.create_task(
            TaskProcessingCoordinator(
                redis_url=redis_url,
                config_manager=config_manager,
                toolscore_client=core_toolscore_client,
                queue_monitor=queue_monitor,
                task_loader=task_loader,
                task_enhancer=task_enhancer,
                task_distributor=task_distributor,
                queue_mapping=queue_mapping
            ).start()
        ),
        stop_fn=lambda: logger.info("TaskProcessingCoordinator 停止中..."), # 简单的停止逻辑
        health_check_fn=lambda: True, # 简单的健康检查
        dependencies=["redis", "toolscore"] # 依赖Redis和ToolScore
    )

    # 注册其他现有服务 (需要调整其initialize_fn和start_fn以接收依赖)
    service_manager.register_service(
        name="redis",
        initialize_fn=lambda config: redis_service.initialize(redis_manager), # 传递redis_manager实例
        start_fn=redis_service.start,
        stop_fn=redis_service.stop,
        health_check_fn=redis_service.health_check,
        dependencies=[]
    )
    
    service_manager.register_service(
        name="toolscore",
        initialize_fn=lambda config: toolscore_service.initialize(config_manager), # 传递config_manager实例
        start_fn=toolscore_service.start,
        stop_fn=toolscore_service.stop,
        health_check_fn=toolscore_service.health_check,
        dependencies=["redis"]
    )
    
    service_manager.register_service(
        name="mcp_servers",
        initialize_fn=lambda config: mcp_server_launcher.initialize(config_manager), # 传递config_manager实例
        start_fn=mcp_server_launcher.start,
        stop_fn=mcp_server_launcher.stop,
        health_check_fn=mcp_server_launcher.health_check,
        dependencies=["toolscore"]
    )
    
    service_manager.register_service(
        name="task_api",
        initialize_fn=lambda config: task_api_service.initialize(config_manager), # 传入config_manager实例
        start_fn=task_api_service.start,
        stop_fn=task_api_service.stop,
        health_check_fn=task_api_service.health_check,
        dependencies=["redis", "toolscore"]
    )
    
    service_manager.register_service(
        name="runtime",
        initialize_fn=lambda config: runtime_service.initialize(
            config or {},
            config_manager,
            llm_client,
            runtime_toolscore_client,
            toolscore_websocket_endpoint # 传入WebSocket端点
        ),
        start_fn=runtime_service.start,
        stop_fn=runtime_service.stop,
        health_check_fn=runtime_service.health_check,
        dependencies=["redis", "toolscore", "mcp_servers"]
    )
    
    service_manager.register_service(
        name="synthesis",
        initialize_fn=lambda config: synthesis_service.initialize(config or {}), # 传入配置字典
        start_fn=synthesis_service.start,
        stop_fn=synthesis_service.stop,
        health_check_fn=synthesis_service.health_check,
        dependencies=["redis"]
    )
    
    setup_signal_handlers(service_manager)
    
    try:
        service_manager.initialize_all({}) # config参数可能不再需要，因为组件已直接实例化
        service_manager.start_all()
        
        logger.info("所有服务已启动，按 Ctrl+C 停止")
        
        # 保持主事件循环运行
        while True:
            await asyncio.sleep(3600) # 保持运行，每小时检查一次
        
    except Exception as e:
        logger.error(f"启动过程中出错: {e}", exc_info=True)
        await service_manager.stop_all() # 确保这里也await
        sys.exit(1)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()