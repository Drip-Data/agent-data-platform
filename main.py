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
from dotenv import load_dotenv
import contextlib
import io
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / '.env')

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

class UnifiedLogCapture:
    """统一的日志捕获系统 - 捕获所有输出到单个文件"""
    
    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.log_file = None
        self.original_handlers = []
        
    def __enter__(self):
        # 创建日志目录
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
        
        # 打开统一日志文件
        self.log_file = open(self.log_file_path, 'a', encoding='utf-8')
        
        # 创建一个同时写入控制台和文件的包装器
        class UnifiedWriter:
            def __init__(self, console, file_handle):
                self.console = console
                self.file = file_handle
                
            def write(self, text):
                # 写入控制台
                self.console.write(text)
                self.console.flush()
                
                # 写入统一日志文件
                if text.strip():  # 只对非空内容添加时间戳
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # 检查是否已经有时间戳，避免重复
                    if not text.startswith(timestamp[:10]):  # 简单检查日期部分
                        self.file.write(f"[{timestamp}] {text}")
                    else:
                        self.file.write(text)
                else:
                    self.file.write(text)
                self.file.flush()
                
            def flush(self):
                self.console.flush()
                self.file.flush()
                
            def isatty(self):
                return self.console.isatty() if hasattr(self.console, 'isatty') else False
                
        # 替换stdout和stderr
        sys.stdout = UnifiedWriter(self.original_stdout, self.log_file)
        sys.stderr = UnifiedWriter(self.original_stderr, self.log_file)
        
        # 重新配置所有现有的logging handlers，让它们也输出到统一日志
        self._reconfigure_logging()
        
        return self
        
    def _reconfigure_logging(self):
        """重新配置logging系统，让所有日志都通过统一输出"""
        # 保存原始handlers
        root_logger = logging.getLogger()
        self.original_handlers = root_logger.handlers.copy()
        
        # 清除所有现有handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        # 创建一个新的StreamHandler，它会写入我们重定向的stdout
        # 这样所有logging输出都会通过我们的UnifiedWriter
        unified_handler = logging.StreamHandler(sys.stdout)
        unified_handler.setFormatter(SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        # 添加新的handler
        root_logger.addHandler(unified_handler)
        
        # 确保日志级别
        root_logger.setLevel(logging.DEBUG)
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复原始的logging handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        for handler in self.original_handlers:
            root_logger.addHandler(handler)
            
        # 恢复原始的stdout和stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        # 关闭日志文件
        if self.log_file:
            self.log_file.close()

# 保持向后兼容
TerminalOutputCapture = UnifiedLogCapture

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
import subprocess

def cleanup_ports():
    """增强的端口和进程清理功能"""
    # 扩展端口列表，包含所有可能的MCP服务器端口
    ports = [8088, 8089, 8090, 8091, 8092, 5555, 8081, 8082, 8080, 8084, 8085, 8086, 8087, 8000]
    
    print("🧹 开始增强端口清理...")
    
    # 首先清理所有相关的Python进程
    try:
        print("🔍 搜索并清理相关Python进程...")
        # 清理可能的main.py进程
        subprocess.run(['pkill', '-f', 'main.py'], timeout=5, check=False)
        # 清理MCP服务器进程
        subprocess.run(['pkill', '-f', 'mcp_servers'], timeout=5, check=False)
        subprocess.run(['pkill', '-f', 'microsandbox_server'], timeout=3, check=False)
        subprocess.run(['pkill', '-f', 'browser_use_server'], timeout=3, check=False)
        subprocess.run(['pkill', '-f', 'search_tool_server'], timeout=3, check=False)
        subprocess.run(['pkill', '-f', 'deepsearch_server'], timeout=3, check=False)
        print("✅ 进程清理完成")
    except Exception as e:
        print(f"⚠️ 进程清理时出错: {e}")
    
    # 等待进程清理完成
    import time
    time.sleep(2)
    
    # 然后清理端口
    for port in ports:
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=3, check=False)
                        print(f"🔥 强制清理端口 {port} 的进程 {pid}")
                    except Exception as e:
                        print(f"⚠️ 清理进程 {pid} 失败: {e}")
            else:
                print(f"✅ 端口 {port} 空闲")
                
        except Exception as e:
            print(f"⚠️ 检查端口 {port} 时出错: {e}")
    
    # 最后再次等待确保清理完成
    time.sleep(1)
    print("✅ 增强端口清理完成")

# 创建必要的目录结构
ensure_output_structure()
os.makedirs(project_root / 'logs', exist_ok=True)
os.makedirs(project_root / 'config', exist_ok=True)
os.makedirs(project_root / 'data', exist_ok=True)

# 配置日志

# 初始的基础logging配置 - 将被UnifiedLogCapture重新配置
logging.basicConfig(
    level=logging.DEBUG,  # 启用DEBUG级别日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        # 注释掉单独的文件handler，将由UnifiedLogCapture统一处理
        # logging.FileHandler('logs/toolscore.log', mode='a', encoding='utf-8')
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
    parser.add_argument('--start-services', action='store_true', help='启动所有服务（默认行为）')
    parser.add_argument('--xml-streaming', action='store_true', default=True, help='启用XML streaming输出格式（显示原始的<think>、<search>、<answer>标签）[默认启用]')
    parser.add_argument('--simple-runtime', action='store_true', default=True, help='使用简化运行时（减少冗余代码，专注核心功能）[默认启用]')
    parser.add_argument('--trajectory-storage', type=str, default='daily_grouped', 
                       choices=['individual', 'daily_grouped', 'weekly_grouped', 'monthly_grouped'],
                       help='轨迹存储模式：individual(单独文件), daily_grouped(按日分组), weekly_grouped(按周分组), monthly_grouped(按月分组)')
    return parser.parse_args()

def setup_signal_handlers(service_manager):
    """设置信号处理器以优雅关闭"""
    def signal_handler(sig, frame):
        logger.info(f"收到信号 {sig}，正在强制关闭所有服务...")
        
        # 设置一个短超时来尝试优雅关闭
        try:
            # 尝试使用服务管理器的强制停止
            service_manager.force_stop_all()
            logger.info("服务管理器强制停止完成")
        except Exception as e:
            logger.warning(f"服务管理器强制停止失败: {e}")
        
        # 无论如何都执行强制清理
        force_cleanup()
        
        # 强制退出
        logger.info("强制退出系统")
        os._exit(0)
    
    async def emergency_shutdown(service_manager):
        """紧急关闭流程"""
        try:
            # 设置较短的超时时间
            await asyncio.wait_for(service_manager.stop_all(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("服务停止超时，执行强制清理")
            force_cleanup()
        except Exception as e:
            logger.error(f"紧急关闭失败: {e}")
            force_cleanup()
    
    def force_cleanup():
        """强制清理所有资源"""
        logger.info("执行强制清理...")
        
        # 首先尝试使用系统命令强制清理MCP服务器进程
        try:
            import subprocess
            # 清理所有MCP服务器相关进程
            subprocess.run(['pkill', '-f', 'mcp_servers'], timeout=5, check=False)
            subprocess.run(['pkill', '-f', 'microsandbox_server'], timeout=3, check=False)
            subprocess.run(['pkill', '-f', 'browser_use_server'], timeout=3, check=False)
            subprocess.run(['pkill', '-f', 'search_tool_server'], timeout=3, check=False)
            logger.info("已尝试清理MCP服务器进程")
        except Exception as e:
            logger.warning(f"清理MCP服务器进程失败: {e}")
        
        # 强制杀死所有相关进程
        try:
            import psutil
            current_pid = os.getpid()
            current_process = psutil.Process(current_pid)
            
            # 杀死所有子进程
            for child in current_process.children(recursive=True):
                try:
                    child.terminate()
                    child.wait(timeout=2)
                except:
                    try:
                        child.kill()
                    except:
                        pass
        except ImportError:
            # 如果没有psutil，使用系统命令
            try:
                import subprocess
                subprocess.run(['pkill', '-f', 'python.*main.py'], timeout=5, check=False)
            except:
                pass
        
        # 释放端口
        release_ports([8088, 8089, 8100, 8081, 8082, 8080])
    
    def release_ports(ports):
        """强制释放端口"""
        for port in ports:
            try:
                import subprocess
                # 在macOS上查找并杀死占用端口的进程
                result = subprocess.run(['lsof', '-ti', f':{port}'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            subprocess.run(['kill', '-9', pid], timeout=3)
                            logger.info(f"强制释放端口 {port}，杀死进程 {pid}")
                        except:
                            pass
            except:
                pass
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main_async():
    """异步主函数，应用入口点"""
    # 启动前先清理端口
    cleanup_ports()
    
    logger.info("=== Agent Data Platform 启动中 ===")
    logger.debug("🔧 开始系统初始化流程...")
    
    args = parse_arguments()
    logger.debug(f"📝 命令行参数: {vars(args)}")
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("调试模式已启用。")

    # 1. 初始化 ConfigManager
    logger.debug("🔧 步骤1: 初始化ConfigManager...")
    config_manager = ConfigManager(config_dir=args.config_dir)
    logger.debug(f"✅ ConfigManager初始化完成，配置目录: {args.config_dir}")
    
    # 2. 加载所有必要配置
    logger.debug("🔧 步骤2: 加载系统配置...")
    redis_url = config_manager.get_redis_url()
    logger.debug(f"📡 Redis URL: {redis_url}")
    
    task_file = config_manager.get_task_file_path()
    logger.debug(f"📋 任务文件路径: {task_file}")
    
    routing_config = config_manager.load_routing_config()
    logger.debug(f"🚦 路由配置加载完成，任务类型映射: {routing_config.task_type_mapping}")
    
    queue_mapping = {
        TaskType(task_type_str.lower()): queue_name
        for task_type_str, queue_name in routing_config.task_type_mapping.items()
    }
    logger.debug(f"📋 队列映射: {queue_mapping}")
    
    # 3. 实例化核心组件
    logger.debug("🔧 步骤3: 初始化核心组件...")
    metrics = EnhancedMetrics() # Metrics实例
    logger.debug("✅ EnhancedMetrics初始化完成")
    
    redis_manager = RedisManager(redis_url) # RedisManager实例
    logger.debug("✅ RedisManager初始化完成")
    
    # ToolScore服务启动后，获取其实际端口
    ports_config = config_manager.get_ports_config()
    toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
    toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
    toolscore_http_endpoint = f"http://localhost:{toolscore_http_port}"
    toolscore_websocket_endpoint = f"ws://localhost:{toolscore_mcp_port}/websocket"
    
    # 为运行时实例化专用的ToolScore客户端
    runtime_toolscore_client = RuntimeToolScoreClient(toolscore_http_endpoint)
    
    # 为其他核心组件实例化核心ToolScore客户端
    core_toolscore_client = CoreToolScoreClient(config_manager)
    
    # 实例化统一工具管理器和LLM客户端
    from core.unified_tool_manager import UnifiedToolManager
    unified_tool_manager = UnifiedToolManager()
    llm_client = LLMClient(config_manager.get_llm_config(), tool_manager=unified_tool_manager)
    
    # Task Processing Components
    task_loader = TaskLoader(task_file)
    task_enhancer = TaskEnhancer(core_toolscore_client, simple_mode=args.simple_runtime)
    task_distributor = TaskDistributor(redis_url, metrics)
    
    # Monitoring Components
    queue_monitor = QueueMonitor(redis_url)
    system_monitor = SystemMonitor(redis_url, config_manager)

    # 实例化Orchestrator
    from core.orchestrator import Orchestrator
    orchestrator = Orchestrator(
        tool_manager=unified_tool_manager,
        llm_client=llm_client,
        redis_manager=redis_manager,
        metrics_manager=metrics
    )

    # 创建服务管理器
    service_manager = ServiceManager()
    
    # 注册TaskProcessingCoordinator
    service_manager.register_service(
        name="task_processing_coordinator",
        initialize_fn=lambda config: None,
        start_fn=lambda: asyncio.create_task(
            TaskProcessingCoordinator(
                redis_url=redis_url,
                config_manager=config_manager,
                toolscore_client=core_toolscore_client,
                queue_monitor=queue_monitor,
                task_loader=task_loader,
                task_enhancer=task_enhancer,
                task_distributor=task_distributor,
                orchestrator=orchestrator,
                queue_mapping=queue_mapping
            ).start()
        ),
        stop_fn=lambda: logger.info("TaskProcessingCoordinator 停止中..."),
        health_check_fn=lambda: True,
        dependencies=["redis", "toolscore"]
    )

    # 注册其他服务
    service_manager.register_service(
        name="redis",
        initialize_fn=lambda config: redis_service.initialize(redis_manager),
        start_fn=redis_service.start,
        stop_fn=redis_service.stop,
        health_check_fn=redis_service.health_check,
        dependencies=[]
    )
    
    service_manager.register_service(
        name="toolscore",
        initialize_fn=lambda config: toolscore_service.initialize(config_manager),
        start_fn=toolscore_service.start,
        stop_fn=toolscore_service.stop,
        health_check_fn=toolscore_service.health_check,
        dependencies=["redis"]
    )
    
    service_manager.register_service(
        name="mcp_servers",
        initialize_fn=lambda config: mcp_server_launcher.initialize(
            config_manager, unified_tool_manager
        ),
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
            unified_tool_manager,
            toolscore_websocket_endpoint,
            redis_manager,
            args.trajectory_storage
        ),
        start_fn=runtime_service.start,
        stop_fn=runtime_service.stop,
        health_check_fn=runtime_service.health_check,
        dependencies=["redis", "toolscore", "mcp_servers"]
    )
    
    # 获取LLM配置并合并到服务配置中
    llm_config = config_manager.get_llm_config()
    synthesis_config = {
        'redis_url': redis_url,
        'TRAJECTORIES_DIR': 'output/trajectories',
        **llm_config  # 合并LLM配置
    }
    
    service_manager.register_service(
        name="synthesis",
        initialize_fn=lambda config: synthesis_service.initialize(
            synthesis_config, 
            tool_manager=unified_tool_manager
        ),
        start_fn=synthesis_service.start,
        stop_fn=synthesis_service.stop,
        health_check_fn=synthesis_service.health_check,
        dependencies=["redis"]
    )
    
    setup_signal_handlers(service_manager)
    
    try:
        logger.debug("🔧 开始初始化所有服务...")
        service_manager.initialize_all({}) # config参数可能不再需要，因为组件已直接实例化
        logger.debug("✅ 所有服务初始化完成")
        
        logger.debug("🚀 开始启动所有服务...")
        await service_manager.start_all()
        logger.debug("✅ 所有服务启动完成")
        
        logger.info("🎉 所有服务已启动，系统运行中...")
        logger.info("📊 系统状态监控已启用，按 Ctrl+C 停止")
        
        # 保持主事件循环运行
        startup_time = asyncio.get_event_loop().time()
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次并输出状态
            current_time = asyncio.get_event_loop().time()
            uptime = int(current_time - startup_time)
            logger.debug(f"⏰ 系统运行时间: {uptime//3600}h {(uptime%3600)//60}m {uptime%60}s")
        
    except Exception as e:
        logger.error(f"启动过程中出错: {e}", exc_info=True)
        await service_manager.stop_all() # 确保这里也await
        sys.exit(1)

def main():
    # 设置统一日志捕获
    unified_log_path = os.path.join('logs', 'System.log')
    
    # 在开始时写入分隔符
    os.makedirs('logs', exist_ok=True)
    with open(unified_log_path, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"[系统启动] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*80}\n")
    
    # 使用统一日志捕获系统捕获所有输出
    with UnifiedLogCapture(unified_log_path):
        try:
            print(f"🚀 Agent Data Platform 启动中... (所有日志将统一记录到 {unified_log_path})")
            asyncio.run(main_async())
        except KeyboardInterrupt:
            print("\n⚡ 收到中断信号，正在优雅关闭...")
        except Exception as e:
            print(f"❌ 系统启动失败: {e}")
            raise
        finally:
            print("📝 终端输出捕获结束")

if __name__ == "__main__":
    main()